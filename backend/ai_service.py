import os
import re
import json
import time
import logging
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

from backend.models import (
    RiskEvaluation,
    ScenarioComparisonResponse,
    AiRecommendation,
)

# Load environment variables from .env if present
load_dotenv()

logger = logging.getLogger("stadium_crisis.ai_service")

# Model Fallback Chain for transient 503 / UNAVAILABLE errors
MODEL_FALLBACK_CHAIN: List[str] = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
]

MAX_RETRIES_PER_MODEL: int = 1
RETRY_BACKOFF_SECONDS: float = 0.5

SYSTEM_INSTRUCTION = """You are a stadium safety and operations decision-support engine.

Given validated stadium operational data and simulated intervention outcomes:
1. Identify the most urgent risk.
2. Determine the likely consequence if no action is taken.
3. Evaluate feasible interventions.
4. Respect all resource constraints.
5. Compare projected outcomes.
6. Select ONE recommended intervention.
7. Explain why it is preferable to alternatives.
8. Never invent unavailable resources or numerical results.

Return structured JSON conforming to:
{
  "risk": "string (summary of the primary risk)",
  "eta_minutes": number (estimated minutes until critical condition),
  "recommended_action": "string (concise intervention title)",
  "reason": "string (detailed tactical reasoning explaining why this option was chosen over alternatives)",
  "alternatives_considered": ["string (alternative 1)", "string (alternative 2)"],
  "confidence": number (between 0.0 and 1.0)
}"""


def sanitize_error_message(msg: str, api_key: Optional[str] = None) -> str:
    """Removes API keys and secrets from error strings before logging or displaying."""
    if not msg:
        return ""
    sanitized = str(msg)
    if api_key and api_key in sanitized:
        sanitized = sanitized.replace(api_key, "[REDACTED_API_KEY]")
    # Also redact standard Gemini/Google API key patterns (AIzaSy...)
    sanitized = re.sub(r"AIzaSy[A-Za-z0-9_-]{33}", "[REDACTED_API_KEY]", sanitized)
    return sanitized


def is_transient_error(exc: Exception) -> bool:
    """
    Determines whether an exception represents a temporary service unavailability (503/429/UNAVAILABLE)
    that warrants a limited retry or model fallback.
    """
    code = getattr(exc, "code", None)
    if code in (503, 429):
        return True

    status = getattr(exc, "status", None)
    if status in ("UNAVAILABLE", "RESOURCE_EXHAUSTED"):
        return True

    err_str = str(exc).upper()
    transient_indicators = [
        "503",
        "UNAVAILABLE",
        "HIGH DEMAND",
        "OVERLOADED",
        "TEMPORARILY UNAVAILABLE",
        "TRY AGAIN LATER",
        "SPIKES IN DEMAND",
        "RESOURCE_EXHAUSTED",
        "429",
    ]
    return any(ind in err_str for ind in transient_indicators)


def is_non_transient_error(exc: Exception) -> bool:
    """
    Identifies non-transient errors (invalid auth, permission denied, bad request)
    where retrying would be wasteful.
    """
    code = getattr(exc, "code", None)
    if code in (400, 401, 403, 404):
        return True

    status = getattr(exc, "status", None)
    if status in ("INVALID_ARGUMENT", "PERMISSION_DENIED", "UNAUTHENTICATED", "NOT_FOUND"):
        return True

    err_str = str(exc).upper()
    non_transient_indicators = [
        "API_KEY_INVALID",
        "PERMISSION_DENIED",
        "UNAUTHENTICATED",
        "INVALID_ARGUMENT",
        "NOT_FOUND",
        "401",
        "403",
        "400",
    ]
    return any(ind in err_str for ind in non_transient_indicators)


def parse_and_validate_gemini_json(text: str) -> Dict[str, Any]:
    """
    Safely parses and validates structured JSON output from Gemini.
    Raises ValueError if JSON is malformed or required schema fields are missing.
    """
    if not text or not text.strip():
        raise ValueError("Gemini returned empty response text.")

    cleaned = text.strip()
    # Strip markdown fences if present
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object, got {type(data).__name__}")

    required_fields = [
        "risk",
        "eta_minutes",
        "recommended_action",
        "reason",
        "alternatives_considered",
        "confidence",
    ]
    missing = [f for f in required_fields if f not in data]
    if missing:
        raise ValueError(f"Missing required schema fields in Gemini response: {missing}")

    if not isinstance(data["alternatives_considered"], list):
        raise ValueError("Field 'alternatives_considered' must be a list.")

    return data


def get_deterministic_fallback_recommendation(
    risk_eval: RiskEvaluation,
    comparison: ScenarioComparisonResponse,
    fallback_reason: str = "GEMINI_API_KEY not configured. Deterministic Safety Fallback Engine active.",
) -> AiRecommendation:
    """
    Deterministic rule-based decision fallback engine.
    Applies expert crowd management rules over simulated scenario outcomes.
    """
    record = risk_eval.raw_record
    baseline = comparison.baseline
    scenarios = comparison.scenarios

    # Filter feasible scenarios
    feasible = [s for s in scenarios if s.is_feasible]

    best_scenario = None
    if feasible:
        best_scenario = min(
            feasible,
            key=lambda s: (s.projected_risk_score, s.projected_net_flow, s.projected_queue)
        )

    eta = risk_eval.time_to_capacity_minutes if risk_eval.time_to_capacity_minutes is not None else 999.0

    if not best_scenario:
        return AiRecommendation(
            risk=f"Severe congestion in {risk_eval.zone} with no feasible active interventions.",
            eta_minutes=eta,
            recommended_action="Initiate emergency security perimeter hold",
            reason=f"{risk_eval.zone} has exceeded or is rapidly approaching capacity in {eta} min and no resources are currently available to deploy.",
            alternatives_considered=["Hold incoming transit", "Broadcast PA crowd warning"],
            confidence=0.75,
            is_fallback=True,
            fallback_notice=fallback_reason,
            model_used=None,
        )

    alternatives = [
        f"{s.scenario_name}: Projected Net Flow {s.projected_net_flow:+d}/min, Projected Risk {s.projected_risk_level.value}"
        for s in feasible
        if s.scenario_id != best_scenario.scenario_id
    ]

    if best_scenario.projected_net_flow <= 0:
        flow_status = f"reverses crowd accumulation to a negative net flow ({best_scenario.projected_net_flow:+d} people/min)"
    else:
        flow_status = f"significantly reduces net influx from {baseline.projected_net_flow:+d}/min down to {best_scenario.projected_net_flow:+d}/min"

    reason = (
        f"{risk_eval.zone} is currently on pace to breach safe capacity in {eta} minutes "
        f"due to a net inflow surge of +{risk_eval.net_flow_per_min:,} attendees/min with an exterior queue of {record.queue_size:,}. "
        f"Simulations demonstrate that {best_scenario.scenario_name} {flow_status}, "
        f"preventing dangerous bottleneck crush while conserving remaining operational reserves. "
        f"Single-vector interventions failed to adequately clear the queue or buy sufficient operational buffer."
    )

    return AiRecommendation(
        risk=f"Imminent crush bottleneck at {risk_eval.zone} ({risk_eval.occupancy_percent}% occupancy, +{risk_eval.net_flow_per_min}/min net flow, {record.queue_size:,} in queue)",
        eta_minutes=eta,
        recommended_action=best_scenario.scenario_name,
        reason=reason,
        alternatives_considered=alternatives,
        confidence=0.95,
        is_fallback=True,
        fallback_notice=fallback_reason,
        model_used=None,
    )


def generate_ai_recommendation(
    risk_eval: RiskEvaluation,
    comparison: ScenarioComparisonResponse,
) -> AiRecommendation:
    """
    Evaluates validated operational data and simulated intervention outcomes using Gemini API.
    Implements a resilient model fallback chain (gemini-3.8-flash -> 3.7 -> 3.6 -> 3.5)
    with short backoff for transient 503 errors, safe non-transient handling, and clean
    deterministic fallback.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()

    if not api_key:
        logger.info("GEMINI_API_KEY is not set. Using deterministic fallback recommendation engine.")
        return get_deterministic_fallback_recommendation(
            risk_eval,
            comparison,
            fallback_reason="GEMINI_API_KEY not configured in environment. Using deterministic decision-support engine.",
        )

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        # Build prompt payload with validated facts only
        payload = {
            "operational_state": {
                "zone": risk_eval.zone,
                "timestamp": risk_eval.timestamp,
                "capacity": risk_eval.raw_record.capacity,
                "current_crowd": risk_eval.raw_record.current_crowd,
                "occupancy_percent": risk_eval.occupancy_percent,
                "inflow_per_min": risk_eval.raw_record.inflow_per_min,
                "outflow_per_min": risk_eval.raw_record.outflow_per_min,
                "net_flow_per_min": risk_eval.net_flow_per_min,
                "remaining_capacity": risk_eval.remaining_capacity,
                "time_to_capacity_minutes": risk_eval.time_to_capacity_minutes,
                "queue_size": risk_eval.raw_record.queue_size,
                "transport_capacity": risk_eval.raw_record.transport_capacity,
                "next_transport_minutes": risk_eval.raw_record.next_transport_minutes,
                "available_shuttles": risk_eval.raw_record.available_shuttles,
                "gate_d_available": risk_eval.raw_record.gate_d_available,
                "risk_level": risk_eval.risk_level.value,
            },
            "baseline_outcome": {
                "projected_net_flow": comparison.baseline.projected_net_flow,
                "projected_time_to_capacity_minutes": comparison.baseline.projected_time_to_capacity_minutes,
                "projected_risk_level": comparison.baseline.projected_risk_level.value,
                "projected_queue": comparison.baseline.projected_queue,
            },
            "simulated_scenarios": [
                {
                    "scenario_id": s.scenario_id,
                    "scenario_name": s.scenario_name,
                    "description": s.description,
                    "is_feasible": s.is_feasible,
                    "feasibility_error": s.feasibility_error,
                    "projected_inflow": s.projected_inflow,
                    "projected_outflow": s.projected_outflow,
                    "projected_net_flow": s.projected_net_flow,
                    "projected_occupancy_percent": s.projected_occupancy_percent,
                    "projected_queue": s.projected_queue,
                    "projected_time_to_capacity_minutes": s.projected_time_to_capacity_minutes,
                    "projected_risk_level": s.projected_risk_level.value,
                    "resources_consumed": s.resources_consumed,
                    "resources_remaining": s.resources_remaining,
                }
                for s in comparison.scenarios
            ],
        }

        user_prompt = (
            f"Operational Data and Simulation Outcomes:\n"
            f"{json.dumps(payload, indent=2)}\n\n"
            f"Reason over these operational facts and return your recommendation in structured JSON."
        )

        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            temperature=0.2,
        )

        last_transient_error = None

        # Iterate through model fallback chain
        for model_name in MODEL_FALLBACK_CHAIN:
            for attempt in range(MAX_RETRIES_PER_MODEL + 1):
                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=user_prompt,
                        config=config,
                    )

                    if not response or not response.text:
                        raise ValueError("Empty response received from Gemini API.")

                    raw_json = parse_and_validate_gemini_json(response.text)

                    # Successful structured reasoning
                    return AiRecommendation(
                        risk=str(raw_json["risk"]),
                        eta_minutes=float(raw_json["eta_minutes"]),
                        recommended_action=str(raw_json["recommended_action"]),
                        reason=str(raw_json["reason"]),
                        alternatives_considered=[str(a) for a in raw_json["alternatives_considered"]],
                        confidence=float(raw_json["confidence"]),
                        is_fallback=False,
                        fallback_notice=None,
                        model_used=model_name,
                    )

                except Exception as exc:
                    safe_err = sanitize_error_message(str(exc), api_key)

                    # 1. Non-transient errors (400, 401, 403, malformed output schema)
                    if is_non_transient_error(exc) or isinstance(exc, (json.JSONDecodeError, ValueError)):
                        logger.warning(
                            f"Non-transient error from Gemini on {model_name}: {type(exc).__name__} - {safe_err}. "
                            "Aborting model chain to avoid wasted retries."
                        )
                        return get_deterministic_fallback_recommendation(
                            risk_eval,
                            comparison,
                            fallback_reason=f"Gemini API error ({type(exc).__name__}). Deterministic Safety Fallback Engine active.",
                        )

                    # 2. Transient errors (503 / UNAVAILABLE / high demand)
                    if is_transient_error(exc):
                        last_transient_error = safe_err
                        logger.warning(
                            f"Gemini model {model_name} transient error (attempt {attempt + 1}/{MAX_RETRIES_PER_MODEL + 1}): {safe_err}"
                        )
                        if attempt < MAX_RETRIES_PER_MODEL:
                            time.sleep(RETRY_BACKOFF_SECONDS)
                            continue
                        else:
                            # Move to next model in fallback chain
                            logger.info(
                                f"Model {model_name} unavailable after {MAX_RETRIES_PER_MODEL + 1} attempts. Falling back to next model in chain."
                            )
                            break
                    else:
                        # Unknown unexpected error
                        logger.warning(
                            f"Unexpected error from Gemini on {model_name}: {type(exc).__name__} - {safe_err}. "
                            "Switching to deterministic safety engine."
                        )
                        return get_deterministic_fallback_recommendation(
                            risk_eval,
                            comparison,
                            fallback_reason=f"Gemini API unavailable ({type(exc).__name__}). Deterministic Safety Fallback Engine active.",
                        )

        # All models in fallback chain exhausted
        logger.error(
            f"All models in fallback chain ({MODEL_FALLBACK_CHAIN}) exhausted due to transient unavailability. "
            f"Last error: {last_transient_error}"
        )
        return get_deterministic_fallback_recommendation(
            risk_eval,
            comparison,
            fallback_reason="All Gemini models currently experiencing high demand (503 UNAVAILABLE). Deterministic Safety Fallback Engine active.",
        )

    except Exception as e:
        safe_top_err = sanitize_error_message(str(e), api_key)
        logger.error(f"Top-level Gemini execution failed: {type(e).__name__} - {safe_top_err}. Using deterministic fallback.")
        return get_deterministic_fallback_recommendation(
            risk_eval,
            comparison,
            fallback_reason=f"Gemini service unavailable ({type(e).__name__}). Deterministic Safety Fallback Engine active.",
        )
