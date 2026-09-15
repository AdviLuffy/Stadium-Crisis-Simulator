from typing import List, Dict, Any, Tuple
from backend.models import (
    StadiumZoneRecord,
    InterventionParameters,
    ScenarioOutcome,
    ScenarioComparisonResponse,
    RiskLevel,
)

SHUTTLE_CAPACITY_RATE = 150  # Additional outflow per minute per shuttle
GATE_D_OUTFLOW_BOOST = 800   # Additional outflow per minute when Gate D is opened


def simulate_scenario(
    record: StadiumZoneRecord,
    params: InterventionParameters,
    scenario_id: str,
    scenario_name: str,
    description: str,
) -> ScenarioOutcome:
    # 1. Enforce Resource Constraints
    is_feasible = True
    feasibility_error = None

    if params.shuttles_to_dispatch < 0:
        is_feasible = False
        feasibility_error = "Shuttles to dispatch cannot be negative."
    elif params.shuttles_to_dispatch > record.available_shuttles:
        is_feasible = False
        feasibility_error = (
            f"Cannot dispatch {params.shuttles_to_dispatch} shuttles. "
            f"Only {record.available_shuttles} shuttles are available."
        )

    if params.open_gate_d and not record.gate_d_available:
        is_feasible = False
        feasibility_error = "Cannot open Gate D because Gate D is reported unavailable/inoperable."

    if params.crowd_redirect_percent < 0 or params.crowd_redirect_percent > 100:
        is_feasible = False
        feasibility_error = "Crowd redirection percentage must be between 0% and 100%."

    # Compute resource consumption
    resources_consumed: Dict[str, Any] = {
        "shuttles_dispatched": min(params.shuttles_to_dispatch, record.available_shuttles) if is_feasible else 0,
        "gate_d_opened": params.open_gate_d if is_feasible else False,
        "crowd_redirect_percent": params.crowd_redirect_percent if is_feasible else 0.0,
    }

    resources_remaining: Dict[str, Any] = {
        "available_shuttles": max(0, record.available_shuttles - resources_consumed["shuttles_dispatched"]),
        "gate_d_available": False if (params.open_gate_d and is_feasible) else record.gate_d_available,
    }

    if not is_feasible:
        # Return fallback baseline metrics with feasibility error
        remaining_cap = record.capacity - record.current_crowd
        net_flow = record.inflow_per_min - record.outflow_per_min
        ttc = round(remaining_cap / net_flow, 2) if net_flow > 0 else None

        return ScenarioOutcome(
            scenario_id=scenario_id,
            scenario_name=scenario_name,
            description=description,
            parameters=params,
            projected_inflow=record.inflow_per_min,
            projected_outflow=record.outflow_per_min,
            projected_net_flow=net_flow,
            projected_occupancy_percent=round((record.current_crowd / record.capacity) * 100.0, 2),
            projected_queue=record.queue_size,
            projected_time_to_capacity_minutes=ttc,
            projected_risk_level=RiskLevel.CRITICAL if ttc and ttc <= 3 else RiskLevel.HIGH,
            projected_risk_score=95.0,
            resources_consumed=resources_consumed,
            resources_remaining=resources_remaining,
            is_feasible=False,
            feasibility_error=feasibility_error,
        )

    # 2. Calculate Numerical Effects
    # Inflow reduction from redirection
    redirect_fraction = params.crowd_redirect_percent / 100.0
    projected_inflow = int(round(record.inflow_per_min * (1.0 - redirect_fraction)))

    # Outflow addition from shuttles and Gate D
    shuttle_boost = params.shuttles_to_dispatch * SHUTTLE_CAPACITY_RATE
    gate_d_boost = GATE_D_OUTFLOW_BOOST if params.open_gate_d else 0
    projected_outflow = record.outflow_per_min + shuttle_boost + gate_d_boost

    # Net flow
    projected_net_flow = projected_inflow - projected_outflow

    # Projected queue drainage (shuttles and Gate D accelerate queue clearance)
    total_drainage_boost = shuttle_boost + gate_d_boost
    projected_queue = max(0, int(record.queue_size - total_drainage_boost * 2.0))

    # Remaining capacity & time to capacity
    remaining_capacity = record.capacity - record.current_crowd
    if projected_net_flow > 0:
        projected_ttc = round(remaining_capacity / projected_net_flow, 2)
    else:
        projected_ttc = None  # Flow is stable or clearing

    # Projected occupancy (at 5 minutes horizon)
    horizon_minutes = 5
    projected_crowd_5min = max(0, min(record.capacity, record.current_crowd + (projected_net_flow * horizon_minutes)))
    projected_occupancy = round((projected_crowd_5min / record.capacity) * 100.0, 2)

    # Projected risk evaluation (aligned with risk engine)
    if projected_ttc is not None and projected_ttc <= 3.0:
        proj_level = RiskLevel.CRITICAL
        proj_score = min(100.0, round(90.0 + (3.0 - projected_ttc) * 3.3, 1))
    elif projected_ttc is not None and projected_ttc <= 8.0:
        proj_level = RiskLevel.HIGH
        proj_score = round(70.0 + (8.0 - projected_ttc) * 2.5, 1)
    elif projected_occupancy >= 90.0 and projected_net_flow > 0:
        proj_level = RiskLevel.HIGH
        proj_score = 75.0
    elif projected_ttc is not None and projected_ttc <= 20.0:
        proj_level = RiskLevel.MEDIUM
        proj_score = 50.0
    elif projected_net_flow > 0:
        proj_level = RiskLevel.MEDIUM
        proj_score = 45.0
    else:
        # Net flow <= 0 (clearing or stable)
        proj_level = RiskLevel.LOW
        proj_score = max(10.0, round(projected_occupancy * 0.25, 1))

    return ScenarioOutcome(
        scenario_id=scenario_id,
        scenario_name=scenario_name,
        description=description,
        parameters=params,
        projected_inflow=projected_inflow,
        projected_outflow=projected_outflow,
        projected_net_flow=projected_net_flow,
        projected_occupancy_percent=projected_occupancy,
        projected_queue=projected_queue,
        projected_time_to_capacity_minutes=projected_ttc,
        projected_risk_level=proj_level,
        projected_risk_score=proj_score,
        resources_consumed=resources_consumed,
        resources_remaining=resources_remaining,
        is_feasible=True,
        feasibility_error=None,
    )


def generate_standard_comparison(record: StadiumZoneRecord) -> ScenarioComparisonResponse:
    """
    Generates the core comparison matrix:
    Baseline: No intervention
    Scenario A: Dispatch 4 shuttles
    Scenario B: Open Gate D
    Scenario C: Open Gate D + dispatch 4 shuttles
    """
    # 1. Baseline
    baseline = simulate_scenario(
        record=record,
        params=InterventionParameters(shuttles_to_dispatch=0, open_gate_d=False, crowd_redirect_percent=0.0),
        scenario_id="baseline",
        scenario_name="Baseline (No Action)",
        description="Status quo operational trajectory without active tactical intervention.",
    )

    # 2. Scenario A: Dispatch 4 shuttles (or clamped to available)
    shuttles_a = min(4, record.available_shuttles)
    scenario_a = simulate_scenario(
        record=record,
        params=InterventionParameters(shuttles_to_dispatch=shuttles_a, open_gate_d=False, crowd_redirect_percent=0.0),
        scenario_id="scenario_a",
        scenario_name=f"Scenario A: Dispatch {shuttles_a} Shuttles",
        description=f"Deploy {shuttles_a} rapid shuttle units to augment transit outflow (+{shuttles_a * SHUTTLE_CAPACITY_RATE}/min).",
    )

    # 3. Scenario B: Open Gate D
    scenario_b = simulate_scenario(
        record=record,
        params=InterventionParameters(shuttles_to_dispatch=0, open_gate_d=record.gate_d_available, crowd_redirect_percent=0.0),
        scenario_id="scenario_b",
        scenario_name="Scenario B: Open Auxiliary Gate D",
        description="Unlock Gate D auxiliary corridor to absorb pedestrian flow (+800/min outflow).",
    )

    # 4. Scenario C: Open Gate D + Dispatch 4 shuttles
    scenario_c = simulate_scenario(
        record=record,
        params=InterventionParameters(shuttles_to_dispatch=shuttles_a, open_gate_d=record.gate_d_available, crowd_redirect_percent=0.0),
        scenario_id="scenario_c",
        scenario_name=f"Scenario C: Open Gate D + Dispatch {shuttles_a} Shuttles",
        description=f"Combined multi-vector intervention: open Gate D (+800/min) and dispatch {shuttles_a} shuttles (+{shuttles_a * SHUTTLE_CAPACITY_RATE}/min) to reverse crowd accumulation.",
    )

    return ScenarioComparisonResponse(
        zone=record.zone,
        baseline=baseline,
        scenarios=[scenario_a, scenario_b, scenario_c],
    )
