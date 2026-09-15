import os
import json
import logging
from typing import Optional
from dotenv import load_dotenv

from backend.models import (
    RiskEvaluation,
    ScenarioComparisonResponse,
    AiRecommendation,
)

# Load environment variables from .env if present
load_dotenv()

logger = logging.getLogger("stadium_crisis.ai_service")

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

    # Find the scenario that minimizes projected risk score and projected net flow
    # Prefer negative net flow (clearing the zone)
    best_scenario = None
    if feasible:
        # Sort by: 1. Risk level (LOW > MEDIUM > HIGH > CRITICAL), 2. projected net flow asc, 3. projected queue asc
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
        )

    alternatives = [
        f"{s.scenario_name}: Projected Net Flow {s.projected_net_flow:+d}/min, Projected Risk {s.projected_risk_level.value}"
        for s in feasible
        if s.scenario_id != best_scenario.scenario_id
    ]

    # Generate grounded reasoning
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
    )


def generate_ai_recommendation(
    risk_eval: RiskEvaluation,
    comparison: ScenarioComparisonResponse,
) -> AiRecommendation:
    """
    Evaluates validated operational data and simulated intervention outcomes using Gemini 3.8 Flash,
    falling back transparently to the deterministic engine if API key is missing or unavailable.
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

        user_prompt = f"Operational Data and Simulation Outcomes:\n{json.dumps(payload, indent=2)}\n\nReason over these facts and return your recommendation in JSON."

        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            temperature=0.2,
        )

        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=user_prompt,
            config=config,
        )

        if not response or not response.text:
            raise ValueError("Empty response received from Gemini API.")

        raw_json = json.loads(response.text.strip())

        return AiRecommendation(
            risk=str(raw_json.get("risk", f"High congestion alert at {risk_eval.zone}")),
            eta_minutes=float(raw_json.get("eta_minutes", risk_eval.time_to_capacity_minutes or 0.0)),
            recommended_action=str(raw_json.get("recommended_action", "Deploy combined interventions")),
            reason=str(raw_json.get("reason", "Evaluated from simulated scenarios.")),
            alternatives_considered=list(raw_json.get("alternatives_considered", [])),
            confidence=float(raw_json.get("confidence", 0.9)),
            is_fallback=False,
            fallback_notice=None,
        )

    except Exception as e:
        logger.warning(f"Gemini API call failed: {e}. Falling back to deterministic engine.")
        return get_deterministic_fallback_recommendation(
            risk_eval,
            comparison,
            fallback_reason=f"Gemini API unavailable ({type(e).__name__}). Deterministic Safety Fallback Engine active.",
        )
