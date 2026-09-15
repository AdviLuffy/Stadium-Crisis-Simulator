import sys
import os
import io
import logging
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google.genai import errors
from backend.models import StadiumZoneRecord
from backend.risk_engine import evaluate_zone_risk
from backend.simulation_engine import generate_standard_comparison
from backend.ai_service import (
    generate_ai_recommendation,
    sanitize_error_message,
    is_transient_error,
    is_non_transient_error,
    MODEL_FALLBACK_CHAIN,
)


def get_test_fixtures():
    record = StadiumZoneRecord(
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
    risk_eval = evaluate_zone_risk(record)
    comp = generate_standard_comparison(record)
    return risk_eval, comp


def test_successful_gemini_response():
    print("Testing 1: Successful Gemini Response on Primary Model...")
    risk_eval, comp = get_test_fixtures()

    valid_json = """{
      "risk": "Critical crowd accumulation at Gate C",
      "eta_minutes": 1.78,
      "recommended_action": "Scenario C: Open Gate D + Dispatch 4 Shuttles",
      "reason": "Combined actions reverse net flow to -500/min and clear the queue safely.",
      "alternatives_considered": ["Scenario A: Shuttles only", "Scenario B: Gate D only"],
      "confidence": 0.96
    }"""

    mock_resp = MagicMock()
    mock_resp.text = valid_json

    with patch.dict(os.environ, {"GEMINI_API_KEY": "dummy_key_123"}):
        with patch("google.genai.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.models.generate_content.return_value = mock_resp

            rec = generate_ai_recommendation(risk_eval, comp)

            assert rec.is_fallback is False, "Expected live Gemini reasoning"
            assert rec.model_used == "gemini-3.8-flash", f"Expected primary model, got {rec.model_used}"
            assert rec.confidence == 0.96
            assert rec.eta_minutes == 1.78
            assert "Scenario C" in rec.recommended_action
            print(f"  [PASS] Primary model {rec.model_used} succeeded with confidence {rec.confidence}")


def test_transient_503_fallback_chain_success():
    print("Testing 2: Transient 503 on Primary Model Followed by Fallback Success...")
    risk_eval, comp = get_test_fixtures()

    valid_json = """{
      "risk": "Severe congestion detected at Gate C",
      "eta_minutes": 1.78,
      "recommended_action": "Scenario C: Open Gate D + Dispatch 4 Shuttles",
      "reason": "Fallback model evaluated scenario outcomes and confirmed negative net flow.",
      "alternatives_considered": ["Scenario A", "Scenario B"],
      "confidence": 0.92
    }"""

    mock_success = MagicMock()
    mock_success.text = valid_json

    # 503 error on gemini-3.8-flash, success on gemini-3.7-flash
    def side_effect(model, contents, config):
        if model == "gemini-3.8-flash":
            raise errors.APIError(503, "This model is currently experiencing high demand. Spikes in demand are usually temporary.")
        elif model == "gemini-3.7-flash":
            return mock_success
        raise errors.APIError(503, "Unavailable")

    with patch.dict(os.environ, {"GEMINI_API_KEY": "dummy_key_123"}):
        with patch("google.genai.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.models.generate_content.side_effect = side_effect

            rec = generate_ai_recommendation(risk_eval, comp)

            assert rec.is_fallback is False, "Expected successful live fallback model"
            assert rec.model_used == "gemini-3.7-flash", f"Expected gemini-3.7-flash, got {rec.model_used}"
            assert rec.confidence == 0.92
            assert "Scenario C" in rec.recommended_action
            print(f"  [PASS] Successfully stepped down from 3.8 to {rec.model_used} on 503 error")


def test_all_models_unavailable_fallback():
    print("Testing 3: All Models Unavailable (503) -> Deterministic Fallback...")
    risk_eval, comp = get_test_fixtures()

    def side_effect(model, contents, config):
        raise errors.APIError(503, "Model overloaded - high demand spike.")

    with patch.dict(os.environ, {"GEMINI_API_KEY": "dummy_key_123"}):
        with patch("google.genai.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.models.generate_content.side_effect = side_effect

            rec = generate_ai_recommendation(risk_eval, comp)

            assert rec.is_fallback is True, "Expected fallback when all models fail"
            assert rec.model_used is None
            assert "503" in rec.fallback_notice or "high demand" in rec.fallback_notice.lower()
            print(f"  [PASS] Clean deterministic fallback when all models 503: '{rec.fallback_notice}'")


def test_malformed_json_fallback():
    print("Testing 4: Malformed Gemini Output -> Deterministic Fallback...")
    risk_eval, comp = get_test_fixtures()

    mock_resp = MagicMock()
    mock_resp.text = "I recommend opening Gate D immediately. (Missing JSON)"

    with patch.dict(os.environ, {"GEMINI_API_KEY": "dummy_key_123"}):
        with patch("google.genai.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.models.generate_content.return_value = mock_resp

            rec = generate_ai_recommendation(risk_eval, comp)

            assert rec.is_fallback is True, "Expected fallback when JSON is malformed"
            assert rec.model_used is None
            assert "JSONDecodeError" in rec.fallback_notice or "error" in rec.fallback_notice.lower()
            print(f"  [PASS] Safely rejected malformed output without crash: '{rec.fallback_notice}'")


def test_non_transient_error_no_retries():
    print("Testing 5: Non-Transient Error (401/403) Fast Fail...")
    risk_eval, comp = get_test_fixtures()

    call_count = 0

    def side_effect(model, contents, config):
        nonlocal call_count
        call_count += 1
        raise errors.APIError(401, "API_KEY_INVALID: The provided API key is expired or invalid.")

    with patch.dict(os.environ, {"GEMINI_API_KEY": "dummy_key_123"}):
        with patch("google.genai.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.models.generate_content.side_effect = side_effect

            rec = generate_ai_recommendation(risk_eval, comp)

            assert rec.is_fallback is True, "Expected fallback on 401"
            assert call_count == 1, f"Expected exactly 1 call (no retries wasted on 401), got {call_count}"
            print("  [PASS] Non-transient 401 error halted retries immediately on attempt 1")


def test_api_key_not_exposed_in_logs_or_fallback():
    print("Testing 6: API Key Scrubbing & Leak Prevention...")
    secret_key = "AIzaSyFakeSecretKeyForTesting123456"
    leak_message = f"Error communicating with Google API using key {secret_key}: 503 high demand."

    # Test sanitizer directly
    cleaned = sanitize_error_message(leak_message, secret_key)
    assert secret_key not in cleaned, "Secret key must be redacted"
    assert "[REDACTED_API_KEY]" in cleaned

    # Test within generate_ai_recommendation
    risk_eval, comp = get_test_fixtures()

    def leak_side_effect(model, contents, config):
        raise errors.APIError(503, leak_message)

    with patch.dict(os.environ, {"GEMINI_API_KEY": secret_key}):
        with patch("google.genai.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.models.generate_content.side_effect = leak_side_effect

            rec = generate_ai_recommendation(risk_eval, comp)

            assert secret_key not in (rec.fallback_notice or "")
            assert secret_key not in rec.reason
            assert secret_key not in rec.risk
            print("  [PASS] API key strictly redacted from all error messages and fallback notices")


def test_gemini_grounded_in_scenario_values():
    print("Testing 7: Gemini Response Strictly Grounded in Simulation Values...")
    risk_eval, comp = get_test_fixtures()

    grounded_json = """{
      "risk": "CRITICAL bottleneck at Gate C with 1.78 min time to capacity",
      "eta_minutes": 1.78,
      "recommended_action": "Scenario C: Open Gate D + Dispatch 4 Shuttles",
      "reason": "Authoritative simulation confirms Scenario C reverses net flow to -500/min, avoids capacity breach, and reduces projected queue to 5200.",
      "alternatives_considered": [
        "Scenario A: Dispatch 4 Shuttles (net flow +300/min, 5.33 min TTC)",
        "Scenario B: Open Gate D (net flow +100/min, 16.0 min TTC)"
      ],
      "confidence": 0.98
    }"""

    mock_resp = MagicMock()
    mock_resp.text = grounded_json

    with patch.dict(os.environ, {"GEMINI_API_KEY": "dummy_key_123"}):
        with patch("google.genai.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.models.generate_content.return_value = mock_resp

            rec = generate_ai_recommendation(risk_eval, comp)

            assert rec.is_fallback is False, "Expected live grounded reasoning to be accepted"
            assert rec.eta_minutes == 1.78, "Expected eta_minutes to match authoritative value"
            assert "-500/min" in rec.reason
            assert "5200" in rec.reason
            print("  [PASS] Grounded reasoning strictly matching authoritative simulation metrics accepted")


def test_gemini_hallucinated_numbers_triggers_fallback():
    print("Testing 8: Hallucinated Numerical Value Triggers Fallback Safeguard...")
    risk_eval, comp = get_test_fixtures()

    # Model hallucinates conflicting eta_minutes (e.g. 22.78 min instead of authoritative 1.78 min)
    hallucinated_json = """{
      "risk": "Mild congestion at Gate C",
      "eta_minutes": 22.78,
      "recommended_action": "Scenario B: Open Gate D",
      "reason": "Gate D clears 800 people and net flow is -750/min with 22.78% occupancy.",
      "alternatives_considered": ["Scenario A", "Scenario C"],
      "confidence": 0.85
    }"""

    mock_resp = MagicMock()
    mock_resp.text = hallucinated_json

    with patch.dict(os.environ, {"GEMINI_API_KEY": "dummy_key_123"}):
        with patch("google.genai.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.models.generate_content.return_value = mock_resp

            rec = generate_ai_recommendation(risk_eval, comp)

            assert rec.is_fallback is True, "Expected hallucinated numbers to trigger deterministic fallback"
            assert rec.model_used is None
            assert "Conflicting eta_minutes" in (rec.fallback_notice or "")
            print(f"  [PASS] Hallucinated numbers rejected by safeguard; cleanly triggered fallback: '{rec.fallback_notice}'")


def test_gemini_null_eta_minutes_regression():
    print("Testing 9: Regression - Gemini returns null eta_minutes (no TypeError: float() on NoneType)...")
    risk_eval, comp = get_test_fixtures()

    null_eta_json = """{
      "risk": "Moderate crowd at Gate C",
      "eta_minutes": null,
      "recommended_action": "Scenario B: Open Gate D",
      "reason": "Gate D provides extra egress.",
      "alternatives_considered": ["Scenario A"],
      "confidence": 0.85
    }"""

    mock_resp = MagicMock()
    mock_resp.text = null_eta_json

    with patch.dict(os.environ, {"GEMINI_API_KEY": "dummy_key_123"}):
        with patch("google.genai.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.models.generate_content.return_value = mock_resp

            # Must NOT raise TypeError: float() argument must be a string or a real number, not 'NoneType'
            rec = generate_ai_recommendation(risk_eval, comp)

            assert rec.is_fallback is True, "Expected null eta_minutes to be rejected and fall back safely"
            assert rec.model_used is None
            assert "eta_minutes" in (rec.fallback_notice or "")
            print(f"  [PASS] Null eta_minutes cleanly rejected without TypeError: '{rec.fallback_notice}'")


def test_authoritative_none_ttc_handled_safely():
    print("Testing 10: Authoritative TTC is None (negative net flow) handled safely without float(None)...")
    # Zone with inflow < outflow, so net flow <= 0 and time_to_capacity_minutes is None
    record = StadiumZoneRecord(
        timestamp="19:05:00",
        zone="Gate A",
        capacity=10000,
        current_crowd=5000,
        inflow_per_min=500,
        outflow_per_min=1000,
        queue_size=200,
        transport_capacity=1000,
        next_transport_minutes=10.0,
        available_shuttles=4,
        gate_d_available=True,
    )
    risk_eval = evaluate_zone_risk(record)
    assert risk_eval.time_to_capacity_minutes is None, "Fixture check: TTC must be None for negative net flow"
    comp = generate_standard_comparison(record)

    valid_json = """{
      "risk": "Low risk at Gate A",
      "eta_minutes": 999.0,
      "recommended_action": "Maintain normal operations",
      "reason": "Outflow exceeds inflow, queue is clearing.",
      "alternatives_considered": ["Scenario A"],
      "confidence": 0.95
    }"""

    mock_resp = MagicMock()
    mock_resp.text = valid_json

    with patch.dict(os.environ, {"GEMINI_API_KEY": "dummy_key_123"}):
        with patch("google.genai.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.models.generate_content.return_value = mock_resp

            # Must NOT raise TypeError when evaluating None authoritative TTC
            rec = generate_ai_recommendation(risk_eval, comp)

            assert rec.is_fallback is False, "Expected valid response accepted when authoritative TTC is None"
            assert rec.eta_minutes == 999.0
            print("  [PASS] Authoritative TTC=None evaluated safely without calling float(None)")


if __name__ == "__main__":
    test_successful_gemini_response()
    test_transient_503_fallback_chain_success()
    test_all_models_unavailable_fallback()
    test_malformed_json_fallback()
    test_non_transient_error_no_retries()
    test_api_key_not_exposed_in_logs_or_fallback()
    test_gemini_grounded_in_scenario_values()
    test_gemini_hallucinated_numbers_triggers_fallback()
    test_gemini_null_eta_minutes_regression()
    test_authoritative_none_ttc_handled_safely()
    print("\nALL 10 AI RESILIENCE & GROUNDING TESTS PASSED SUCCESSFULLY!")

