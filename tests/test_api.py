import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_api_health():
    print("Testing /api/health...")
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    print("  [PASS] /api/health:", data)


def test_api_demo_data():
    print("Testing /api/data/demo...")
    res = client.get("/api/data/demo")
    assert res.status_code == 200
    data = res.json()
    assert data["is_valid"] is True
    assert data["total_records"] == 4
    assert "Gate C" in data["detected_zones"]
    print("  [PASS] /api/data/demo returned 4 valid records")


def test_api_upload_valid_and_invalid():
    print("Testing /api/upload...")
    # 1. Valid upload
    with open("data/demo_stadium_data.csv", "rb") as f:
        res = client.post("/api/upload", files={"file": ("demo.csv", f, "text/csv")})
    assert res.status_code == 200
    assert res.json()["is_valid"] is True
    print("  [PASS] /api/upload valid CSV accepted")

    # 2. Invalid file extension
    res_bad_ext = client.post("/api/upload", files={"file": ("demo.txt", b"hello", "text/plain")})
    assert res_bad_ext.status_code == 400
    print("  [PASS] /api/upload invalid extension rejected with 400")

    # 3. Invalid CSV contents (invalid_test_data.csv)
    with open("data/invalid_test_data.csv", "rb") as f:
        res_invalid = client.post("/api/upload", files={"file": ("invalid.csv", f, "text/csv")})
    assert res_invalid.status_code == 200
    assert res_invalid.json()["is_valid"] is False
    assert len(res_invalid.json()["errors"]) > 0
    print(f"  [PASS] /api/upload invalid CSV flagged with {len(res_invalid.json()['errors'])} errors")


def test_api_risk_evaluate():
    print("Testing /api/risk/evaluate...")
    res_demo = client.get("/api/data/demo").json()
    records = res_demo["records"]
    res = client.post("/api/risk/evaluate", json=records)
    assert res.status_code == 200
    overview = res.json()
    assert overview["total_capacity"] == 33000
    assert overview["most_critical_zone"]["zone"] == "Gate C"
    assert overview["most_critical_zone"]["risk_level"] == "CRITICAL"
    assert overview["most_critical_zone"]["occupancy_percent"] == 84.0
    assert overview["most_critical_zone"]["net_flow_per_min"] == 900
    assert overview["most_critical_zone"]["time_to_capacity_minutes"] == 1.78
    print("  [PASS] /api/risk/evaluate flagged Gate C as CRITICAL with 1.78 min ETA")


def test_api_simulate():
    print("Testing /api/simulate...")
    res_demo = client.get("/api/data/demo").json()
    gate_c = next(r for r in res_demo["records"] if r["zone"] == "Gate C")

    # Standard + custom simulation
    res = client.post(
        "/api/simulate",
        json={
            "record": gate_c,
            "custom_params": {
                "shuttles_to_dispatch": 3,
                "open_gate_d": True,
                "crowd_redirect_percent": 25.0,
            },
        },
    )
    assert res.status_code == 200
    comp = res.json()
    assert comp["zone"] == "Gate C"
    assert comp["baseline"]["projected_net_flow"] == 900
    assert len(comp["scenarios"]) == 4  # Scenario A, B, C + Custom
    custom_scen = next(s for s in comp["scenarios"] if s["scenario_id"] == "custom_scenario")
    assert custom_scen["is_feasible"] is True
    print("  [PASS] /api/simulate returned baseline + 4 scenarios successfully")


def test_api_recommend():
    print("Testing /api/recommend...")
    res_demo = client.get("/api/data/demo").json()
    gate_c = next(r for r in res_demo["records"] if r["zone"] == "Gate C")

    res = client.post("/api/recommend", json={"record": gate_c})
    assert res.status_code == 200
    data = res.json()
    rec = data["ai_recommendation"]
    assert rec["eta_minutes"] >= 0
    assert rec["recommended_action"]
    assert rec["confidence"] >= 0.5
    assert len(rec["reason"]) > 0
    print("  [PASS] /api/recommend returned valid recommendation:", rec["recommended_action"])


def test_static_files():
    print("Testing static asset serving...")
    res_index = client.get("/")
    assert res_index.status_code == 200
    assert "Stadium Crisis Simulator" in res_index.text

    res_css = client.get("/static/css/styles.css")
    assert res_css.status_code == 200
    assert "STADIUM CRISIS SIMULATOR" in res_css.text
    print("  [PASS] Static files served cleanly")


if __name__ == "__main__":
    test_api_health()
    test_api_demo_data()
    test_api_upload_valid_and_invalid()
    test_api_risk_evaluate()
    test_api_simulate()
    test_api_recommend()
    test_static_files()
    print("\nALL API INTEGRATION TESTS PASSED SUCCESSFULLY!")
