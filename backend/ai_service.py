import os
import re
import json
import time
import math
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

CORE PRINCIPLES & NUMERICAL GROUNDING RULES:
1. Deterministic application calculations are authoritative.
2. Treat all supplied operational metrics and simulated scenario results as immutable facts.
3. NEVER recalculate, estimate, derive, reinterpret, or modify numerical values.
4. NEVER invent numerical values or hallucinate different flows, queues, occupancies, or times.
5. When mentioning a scenario's numerical result, copy the supplied value EXACTLY.
6. Do not infer a new queue size, occupancy, net flow, TTC, resource count, or capacity.
7. If a numerical value is not supplied, do not provide or assume one.
8. Gemini is the reasoning and explanation layer, NOT the calculator. Use the provided calculations directly.
9. Compare scenarios using the supplied simulation results only.
10. Do not include numerical values in the "reason" field or "alternatives_considered" unless explicitly required; explain comparisons qualitatively and let the application display authoritative simulation metrics separately.  

TASKS:
1. Identify the most urgent risk based strictly on current operational state.
2. Determine the likely consequence if no action is taken (baseline outcome).
3. Evaluate feasible interventions and respect all resource constraints.
4. Compare projected scenario outcomes using their authoritative simulation metrics.
5. Select ONE recommended intervention.
6. Explain why it is preferable to alternatives using exact simulation numbers without modification.
7. Never invent unavailable resources or modify numerical results.

Return structured JSON conforming to:
{
  "risk": "string (summary of the primary risk based on operational state)",
  "eta_minutes": number (estimated minutes until critical condition matching authoritative operational time_to_capacity_minutes),
  "recommended_action": "string (concise intervention title matching one of the feasible scenarios)",
  "reason": "string (detailed tactical reasoning explaining why this option was chosen over alternatives, copying exact numerical metrics from the simulation outcomes without alteration)",
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

    if data.get("eta_minutes") is None:
        raise ValueError("Field 'eta_minutes' must not be null/None in Gemini response.")

    if data.get("confidence") is None:
        raise ValueError("Field 'confidence' must not be null/None in Gemini response.")

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

        # Build prompt payload with validated facts only - explicitly marked authoritative
        payload = {
            "notice": "ALL NUMERICAL VALUES ARE PRE-CALCULATED AND AUTHORITATIVE. DO NOT MODIFY, RECALCULATE, OR INVENT NUMBERS.",
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
                "risk": risk_eval.risk_level.value,
            },
            "baseline_do_nothing_outcome": {
                "scenario_name": comparison.baseline.scenario_name,
                "intervention": "No Action (Status Quo)",
                "net_flow_per_min": comparison.baseline.projected_net_flow,
                "time_to_capacity_minutes": comparison.baseline.projected_time_to_capacity_minutes,
                "projected_occupancy_percent": comparison.baseline.projected_occupancy_percent,
                "projected_queue": comparison.baseline.projected_queue,
                "risk": comparison.baseline.projected_risk_level.value,
                "resource_usage": "None",
            },
            "authoritative_simulated_scenarios": [
                {
                    "scenario_id": s.scenario_id,
                    "scenario_name": s.scenario_name,
                    "intervention": s.description,
                    "is_feasible": s.is_feasible,
                    "feasibility_error": s.feasibility_error,
                    "inflow_per_min": s.projected_inflow,
                    "outflow_per_min": s.projected_outflow,
                    "net_flow_per_min": s.projected_net_flow,
                    "time_to_capacity_minutes": s.projected_time_to_capacity_minutes,
                    "projected_occupancy_percent": s.projected_occupancy_percent,
                    "projected_queue": s.projected_queue,
                    "risk": s.projected_risk_level.value,
                    "resource_usage": s.resources_consumed,
                    "resources_remaining": s.resources_remaining,
                }
                for s in comparison.scenarios
            ],
        }

        user_prompt = (
            f"AUTHORITATIVE OPERATIONAL DATA AND DETERMINISTIC SIMULATION OUTCOMES:\n"
            f"{json.dumps(payload, indent=2)}\n\n"
            f"CRITICAL GROUNDING INSTRUCTIONS:\n"
            f"- All numbers in the JSON above are pre-calculated by the deterministic simulation engine and are 100% authoritative.\n"
            f"- NEVER recalculate, modify, estimate, or invent numerical values.\n"
            f"- In your 'reason' field, refer to scenarios using their exact metrics (net_flow_per_min, time_to_capacity_minutes, projected_occupancy_percent, projected_queue) exactly as provided above.\n"
            f"- 'eta_minutes' must be set to the authoritative operational time_to_capacity_minutes ({risk_eval.time_to_capacity_minutes if risk_eval.time_to_capacity_minutes is not None else 999.0}).\n"
            f"- Return your structured recommendation in the required JSON format."
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

                    # Validation Safeguard: verify numerical fields safely without float(None) TypeError
                    raw_eta = raw_json.get("eta_minutes")
                    if raw_eta is None or isinstance(raw_eta, bool):
                        raise ValueError(
                            f"Missing or null eta_minutes in Gemini response: {raw_eta!r}"
                        )
                    try:
                        returned_eta = float(raw_eta)
                        if math.isnan(returned_eta):
                            raise ValueError("eta_minutes in Gemini response is NaN")
                    except (ValueError, TypeError):
                        raise ValueError(
                            f"Non-numeric eta_minutes in Gemini response: {raw_eta!r}"
                        )

                    raw_conf = raw_json.get("confidence")
                    if raw_conf is None or isinstance(raw_conf, bool):
                        raise ValueError(
                            f"Missing or null confidence in Gemini response: {raw_conf!r}"
                        )
                    try:
                        confidence = float(raw_conf)
                        if math.isnan(confidence) or confidence < 0.0 or confidence > 1.0:
                            raise ValueError(
                                f"Confidence {confidence} out of range [0.0, 1.0]"
                            )
                    except (ValueError, TypeError):
                        raise ValueError(
                            f"Non-numeric confidence in Gemini response: {raw_conf!r}"
                        )

                    if risk_eval.time_to_capacity_minutes is not None:
                        try:
                            expected_eta = round(float(risk_eval.time_to_capacity_minutes), 2)
                        except (ValueError, TypeError):
                            expected_eta = None

                        if expected_eta is not None:
                            # Preserve the existing 0.1 minute tolerance
                            if abs(returned_eta - expected_eta) > 0.1:
                                raise ValueError(
                                    f"Conflicting eta_minutes: model returned {returned_eta} but authoritative calculation is {expected_eta}"
                                )
                    else:
                        # Authoritative net flow <= 0, time to capacity is infinite / unavailable
                        if returned_eta < 60.0:
                            raise ValueError(
                                f"Conflicting eta_minutes: zone net flow <= 0 (infinite TTC), but model returned {returned_eta}"
                            )

                    # Successful structured reasoning
                    return AiRecommendation(
                        risk=str(raw_json.get("risk") or ""),
                        eta_minutes=returned_eta,
                        recommended_action=str(raw_json.get("recommended_action") or ""),
                        reason=str(raw_json.get("reason") or ""),
                        alternatives_considered=[str(a) for a in raw_json.get("alternatives_considered", [])],
                        confidence=confidence,
                        is_fallback=False,
                        fallback_notice=None,
                        model_used=model_name,
                    )

                except Exception as exc:
                    safe_err = sanitize_error_message(str(exc), api_key)

                    # 1. Non-transient errors (400, 401, 403, malformed output schema, numerical validation failure)
                    if is_non_transient_error(exc) or isinstance(exc, (json.JSONDecodeError, ValueError, TypeError)):
                        logger.warning(
                            f"Non-transient error or validation failure from Gemini on {model_name}: {type(exc).__name__} - {safe_err}. "
                            "Aborting model chain to avoid wasted retries."
                        )
                        return get_deterministic_fallback_recommendation(
                            risk_eval,
                            comparison,
                            fallback_reason=f"Gemini API error ({type(exc).__name__}: {safe_err}). Deterministic Safety Fallback Engine active.",
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
