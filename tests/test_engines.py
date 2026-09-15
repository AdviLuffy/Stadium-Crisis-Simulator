import sys
import os
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.models import StadiumZoneRecord, RiskLevel, InterventionParameters
from backend.validation import validate_csv_content
from backend.risk_engine import evaluate_zone_risk, evaluate_stadium_overview
from backend.simulation_engine import simulate_scenario, generate_standard_comparison
from backend.ai_service import generate_ai_recommendation


def test_validation():
    print("Testing Validation Engine...")

    # 1. Valid demo CSV
    demo_path = Path("data/demo_stadium_data.csv")
    with open(demo_path, "r", encoding="utf-8") as f:
        demo_content = f.read()
    res = validate_csv_content(demo_content)
    assert res.is_valid, f"Demo CSV should be valid: {res.errors}"
    assert len(res.records) == 4, f"Expected 4 records, got {len(res.records)}"
    assert "Gate C" in res.detected_zones, "Gate C should be in detected zones"
    print("  [PASS] Valid demo CSV passed")

    # 2. Empty CSV
    res_empty = validate_csv_content("")
    assert not res_empty.is_valid, "Empty CSV must be invalid"
    assert len(res_empty.errors) > 0, "Expected error on empty CSV"
    print("  [PASS] Empty CSV rejected")

    # 3. Missing columns
    bad_headers = "timestamp,zone,capacity\n19:05:00,Gate C,10000\n"
    res_bad_headers = validate_csv_content(bad_headers)
    assert not res_bad_headers.is_valid
    assert any("Missing required columns" in e.message for e in res_bad_headers.errors)
    print("  [PASS] Missing headers rejected")

    # 4. Crowd > Capacity
    overcrowded = (
        "timestamp,zone,capacity,current_crowd,inflow_per_min,outflow_per_min,queue_size,transport_capacity,next_transport_minutes,available_shuttles,gate_d_available\n"
        "19:05:00,Gate C,1000,1500,100,50,0,100,5,2,true\n"
    )
    res_overcrowd = validate_csv_content(overcrowded)
    assert not res_overcrowd.is_valid
    assert any("cannot exceed maximum safe capacity" in e.message for e in res_overcrowd.errors)
    print("  [PASS] Crowd > capacity rejected")

    # 5. Negative values
    neg_val = (
        "timestamp,zone,capacity,current_crowd,inflow_per_min,outflow_per_min,queue_size,transport_capacity,next_transport_minutes,available_shuttles,gate_d_available\n"
        "19:05:00,Gate C,1000,500,-100,50,0,100,5,2,true\n"
    )
    res_neg = validate_csv_content(neg_val)
    assert not res_neg.is_valid
    assert any("cannot be negative" in e.message for e in res_neg.errors)
    print("  [PASS] Negative inflow rejected")


def test_risk_engine():
    print("Testing Risk Engine...")
    gate_c_record = StadiumZoneRecord(
        timestamp="19:05:00",
        zone="Gate C",
        capacity=10000,
        current_crowd=8400,
        inflow_per_min=2000,
        outflow_per_min=1100,
        queue_size=6800,
        transport_capacity=1800,
        next_transport_minutes=5.0,
        available_shuttles=6,
        gate_d_available=True,
    )

    eval_c = evaluate_zone_risk(gate_c_record)
    assert eval_c.occupancy_percent == 84.0, f"Expected 84.0%, got {eval_c.occupancy_percent}%"
    assert eval_c.net_flow_per_min == 900, f"Expected 900 net flow, got {eval_c.net_flow_per_min}"
    assert eval_c.remaining_capacity == 1600, f"Expected 1600 remaining capacity, got {eval_c.remaining_capacity}"
    assert eval_c.time_to_capacity_minutes == 1.78, f"Expected 1.78 min, got {eval_c.time_to_capacity_minutes}"
    assert eval_c.risk_level == RiskLevel.CRITICAL, f"Expected CRITICAL, got {eval_c.risk_level}"
    print(f"  [PASS] Gate C risk evaluation matches spec: 84% occ, +900/min flow, 1.78 min ETA, {eval_c.risk_level.value}")


def test_simulation_engine():
    print("Testing Simulation Engine...")
    gate_c_record = StadiumZoneRecord(
        timestamp="19:05:00",
        zone="Gate C",
        capacity=10000,
        current_crowd=8400,
        inflow_per_min=2000,
        outflow_per_min=1100,
        queue_size=6800,
        transport_capacity=1800,
        next_transport_minutes=5.0,
        available_shuttles=6,
        gate_d_available=True,
    )

    comp = generate_standard_comparison(gate_c_record)
    assert comp.baseline.projected_net_flow == 900
    assert comp.baseline.projected_time_to_capacity_minutes == 1.78
    assert comp.baseline.projected_risk_level == RiskLevel.CRITICAL

    # Scenario A: 4 shuttles (+600 outflow -> net flow 300)
    scen_a = comp.scenarios[0]
    assert scen_a.projected_net_flow == 300
    assert scen_a.projected_time_to_capacity_minutes == 5.33
    assert scen_a.projected_risk_level == RiskLevel.HIGH

    # Scenario B: Gate D (+800 outflow -> net flow 100)
    scen_b = comp.scenarios[1]
    assert scen_b.projected_net_flow == 100
    assert scen_b.projected_time_to_capacity_minutes == 16.0
    assert scen_b.projected_risk_level == RiskLevel.MEDIUM

    # Scenario C: Gate D + 4 shuttles (+1400 outflow -> net flow -500, cleared!)
    scen_c = comp.scenarios[2]
    assert scen_c.projected_net_flow == -500
    assert scen_c.projected_time_to_capacity_minutes is None
    assert scen_c.projected_risk_level == RiskLevel.LOW
    print(f"  [PASS] Simulation outcomes match: Baseline (+900, 1.78m) -> A (+300, 5.33m) -> B (+100, 16m) -> C (-500, Averted!)")

    # Resource constraints
    # Cannot dispatch 10 shuttles when only 6 available
    invalid_shuttles = simulate_scenario(
        record=gate_c_record,
        params=InterventionParameters(shuttles_to_dispatch=10, open_gate_d=False),
        scenario_id="invalid_shuttles",
        scenario_name="Excess Shuttles",
        description="Testing resource limit",
    )
    assert not invalid_shuttles.is_feasible
    assert "Only 6 shuttles are available" in invalid_shuttles.feasibility_error
    print("  [PASS] Resource constraint (shuttle limit) enforced")

    # Cannot open Gate D when unavailable
    gate_c_no_d = gate_c_record.model_copy(update={"gate_d_available": False})
    invalid_gate_d = simulate_scenario(
        record=gate_c_no_d,
        params=InterventionParameters(shuttles_to_dispatch=2, open_gate_d=True),
        scenario_id="invalid_gate_d",
        scenario_name="Unavailable Gate D",
        description="Testing gate availability",
    )
    assert not invalid_gate_d.is_feasible
    assert "Gate D is reported unavailable" in invalid_gate_d.feasibility_error
    print("  [PASS] Resource constraint (Gate D unavailable) enforced")


def test_ai_fallback():
    print("Testing AI Service Fallback...")
    gate_c_record = StadiumZoneRecord(
        timestamp="19:05:00",
        zone="Gate C",
        capacity=10000,
        current_crowd=8400,
        inflow_per_min=2000,
        outflow_per_min=1100,
        queue_size=6800,
        transport_capacity=1800,
        next_transport_minutes=5.0,
        available_shuttles=6,
        gate_d_available=True,
    )
    risk_eval = evaluate_zone_risk(gate_c_record)
    comp = generate_standard_comparison(gate_c_record)
    rec = generate_ai_recommendation(risk_eval, comp)

    assert rec.is_fallback, "Should be fallback without GEMINI_API_KEY"
    assert rec.eta_minutes == 1.78
    assert "Scenario C" in rec.recommended_action or "Open Gate D" in rec.recommended_action
    assert len(rec.alternatives_considered) > 0
    assert rec.confidence > 0.8
    print(f"  [PASS] Fallback recommendation generated: {rec.recommended_action}")


if __name__ == "__main__":
    test_validation()
    test_risk_engine()
    test_simulation_engine()
    test_ai_fallback()
    print("\nALL AUTOMATED TESTS PASSED SUCCESSFULLY!")
