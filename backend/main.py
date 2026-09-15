import os
from typing import List, Optional
from pathlib import Path
from fastapi import FastAPI, File, UploadFile, HTTPException, Body
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.models import (
    StadiumZoneRecord,
    ValidationResult,
    StadiumOverview,
    ScenarioComparisonResponse,
    InterventionParameters,
    ScenarioOutcome,
    AiRecommendation,
    RiskEvaluation,
)
from backend.validation import validate_csv_content
from backend.risk_engine import evaluate_zone_risk, evaluate_stadium_overview
from backend.simulation_engine import simulate_scenario, generate_standard_comparison
from backend.ai_service import generate_ai_recommendation

app = FastAPI(
    title="Stadium Crisis Simulator API",
    description="Operational decision-support engine for stadium crowd safety",
    version="1.0.0",
)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
FRONTEND_DIR = BASE_DIR / "frontend"
DEMO_CSV_PATH = DATA_DIR / "demo_stadium_data.csv"


class SimulationRequest(BaseModel):
    record: StadiumZoneRecord
    custom_params: Optional[InterventionParameters] = None


class RecommendRequest(BaseModel):
    record: StadiumZoneRecord


class FullRecommendationResponse(BaseModel):
    risk_evaluation: RiskEvaluation
    scenario_comparison: ScenarioComparisonResponse
    ai_recommendation: AiRecommendation


@app.get("/api/health")
def get_health():
    has_key = bool(os.environ.get("GEMINI_API_KEY", "").strip())
    return {
        "status": "healthy",
        "system": "Stadium Crisis Simulator Decision Support Engine",
        "gemini_api_configured": has_key,
        "mode": "Gemini 3.8 Flash Live AI" if has_key else "Deterministic Fallback Engine",
    }


@app.get("/api/data/demo", response_model=ValidationResult)
def get_demo_data():
    if not DEMO_CSV_PATH.exists():
        raise HTTPException(status_code=404, detail="Demo CSV file not found on server.")
    with open(DEMO_CSV_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    result = validate_csv_content(content)
    return result


@app.post("/api/upload", response_model=ValidationResult)
async def upload_csv(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type '{file.filename}'. Please upload a valid CSV file (.csv)."
        )
    contents = await file.read()
    try:
        csv_text = contents.decode("utf-8")
    except UnicodeDecodeError:
        try:
            csv_text = contents.decode("latin-1")
        except Exception:
            raise HTTPException(status_code=400, detail="Could not decode CSV text. Ensure UTF-8 or standard ASCII encoding.")

    return validate_csv_content(csv_text)


@app.post("/api/risk/evaluate", response_model=StadiumOverview)
def evaluate_stadium(records: List[StadiumZoneRecord]):
    return evaluate_stadium_overview(records)


@app.post("/api/simulate", response_model=ScenarioComparisonResponse)
def simulate_interventions(req: SimulationRequest):
    comparison = generate_standard_comparison(req.record)
    if req.custom_params:
        custom_outcome = simulate_scenario(
            record=req.record,
            params=req.custom_params,
            scenario_id="custom_scenario",
            scenario_name="Custom Intervention",
            description="Organizer-configured tactical intervention parameters.",
        )
        comparison.scenarios.append(custom_outcome)
    return comparison


@app.post("/api/recommend", response_model=FullRecommendationResponse)
def get_recommendation(req: RecommendRequest):
    risk_eval = evaluate_zone_risk(req.record)
    comparison = generate_standard_comparison(req.record)
    recommendation = generate_ai_recommendation(risk_eval, comparison)

    return FullRecommendationResponse(
        risk_evaluation=risk_eval,
        scenario_comparison=comparison,
        ai_recommendation=recommendation,
    )


# Serve frontend static assets if directory exists
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/")
    def serve_index():
        return FileResponse(FRONTEND_DIR / "index.html")
