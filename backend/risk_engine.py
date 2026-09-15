from typing import List, Optional
from backend.models import StadiumZoneRecord, RiskEvaluation, RiskLevel, StadiumOverview


def evaluate_zone_risk(record: StadiumZoneRecord) -> RiskEvaluation:
    occupancy_percent = round((record.current_crowd / record.capacity) * 100.0, 2)
    net_flow_per_min = record.inflow_per_min - record.outflow_per_min
    remaining_capacity = record.capacity - record.current_crowd

    if net_flow_per_min > 0:
        time_to_capacity_minutes = round(remaining_capacity / net_flow_per_min, 2)
    else:
        time_to_capacity_minutes = None

    risk_factors: List[str] = []

    # Evaluate risk factors and level
    if time_to_capacity_minutes is not None and time_to_capacity_minutes <= 3.0:
        level = RiskLevel.CRITICAL
        risk_score = min(100.0, round(90.0 + (3.0 - time_to_capacity_minutes) * 3.3, 1))
        risk_factors.append(f"Immediate bottleneck alert: Zone will reach 100% capacity in {time_to_capacity_minutes} minutes.")
    elif occupancy_percent >= 90.0 and net_flow_per_min > 0:
        level = RiskLevel.CRITICAL
        risk_score = 92.0
        risk_factors.append(f"Critical occupancy ({occupancy_percent}%) with positive inflow expansion.")
    elif time_to_capacity_minutes is not None and time_to_capacity_minutes <= 5.0 and record.queue_size > 4000:
        level = RiskLevel.CRITICAL
        risk_score = 88.0
        risk_factors.append(f"Imminent capacity breach in {time_to_capacity_minutes} min compounded by large queue ({record.queue_size:,} people).")
    elif time_to_capacity_minutes is not None and time_to_capacity_minutes <= 8.0:
        level = RiskLevel.HIGH
        risk_score = round(70.0 + (8.0 - time_to_capacity_minutes) * 2.5, 1)
        risk_factors.append(f"Fast-accumulating crowd: Zone capacity limit projected in {time_to_capacity_minutes} minutes.")
    elif occupancy_percent >= 80.0:
        level = RiskLevel.HIGH
        risk_score = 75.0
        risk_factors.append(f"High occupancy at {occupancy_percent}% of safety threshold.")
    elif time_to_capacity_minutes is not None and time_to_capacity_minutes <= 15.0:
        level = RiskLevel.MEDIUM
        risk_score = 55.0
        risk_factors.append(f"Moderate crowd buildup: time to capacity is {time_to_capacity_minutes} minutes.")
    elif occupancy_percent >= 65.0 or record.queue_size > 2000:
        level = RiskLevel.MEDIUM
        risk_score = 48.0
        if occupancy_percent >= 65.0:
            risk_factors.append(f"Elevated occupancy at {occupancy_percent}%.")
        if record.queue_size > 2000:
            risk_factors.append(f"Substantial queue buildup of {record.queue_size:,} people.")
    else:
        level = RiskLevel.LOW
        risk_score = max(5.0, round(occupancy_percent * 0.35, 1))
        risk_factors.append("Operations normal: Zone flow is stable and within safe limits.")

    # Contextual factor additions
    if net_flow_per_min > 0:
        risk_factors.append(f"Positive net inflow (+{net_flow_per_min:,}/min): Inflow ({record.inflow_per_min:,}/min) exceeds outflow ({record.outflow_per_min:,}/min).")
    elif net_flow_per_min < 0:
        risk_factors.append(f"Negative net flow ({net_flow_per_min:,}/min): Outflow is clearing the zone safely.")

    if record.queue_size > 0:
        risk_factors.append(f"Exterior waiting queue: {record.queue_size:,} attendees.")

    if time_to_capacity_minutes is not None and record.next_transport_minutes > time_to_capacity_minutes:
        risk_factors.append(f"Transit lag warning: Next scheduled transit arrival is {record.next_transport_minutes} min, arriving AFTER capacity breach ({time_to_capacity_minutes} min).")

    return RiskEvaluation(
        zone=record.zone,
        timestamp=record.timestamp,
        occupancy_percent=occupancy_percent,
        net_flow_per_min=net_flow_per_min,
        remaining_capacity=remaining_capacity,
        time_to_capacity_minutes=time_to_capacity_minutes,
        risk_level=level,
        risk_score=risk_score,
        risk_factors=risk_factors,
        raw_record=record,
    )


def evaluate_stadium_overview(records: List[StadiumZoneRecord]) -> StadiumOverview:
    if not records:
        return StadiumOverview(
            total_capacity=0,
            total_crowd=0,
            overall_occupancy_percent=0.0,
            most_critical_zone=None,
            zones=[],
        )

    evaluations = [evaluate_zone_risk(r) for r in records]

    # Rank severity: CRITICAL > HIGH > MEDIUM > LOW, then by risk_score desc, then by time_to_capacity asc
    severity_order = {
        RiskLevel.CRITICAL: 4,
        RiskLevel.HIGH: 3,
        RiskLevel.MEDIUM: 2,
        RiskLevel.LOW: 1,
    }

    def sort_key(eval_item: RiskEvaluation):
        rank = severity_order[eval_item.risk_level]
        # Earlier time to capacity is more critical
        ttc = eval_item.time_to_capacity_minutes if eval_item.time_to_capacity_minutes is not None else 999999
        return (rank, eval_item.risk_score, -ttc)

    sorted_evals = sorted(evaluations, key=sort_key, reverse=True)
    most_critical = sorted_evals[0] if sorted_evals else None

    total_capacity = sum(r.capacity for r in records)
    total_crowd = sum(r.current_crowd for r in records)
    overall_occupancy = round((total_crowd / total_capacity) * 100.0, 2) if total_capacity > 0 else 0.0

    return StadiumOverview(
        total_capacity=total_capacity,
        total_crowd=total_crowd,
        overall_occupancy_percent=overall_occupancy,
        most_critical_zone=most_critical,
        zones=sorted_evals,
    )
