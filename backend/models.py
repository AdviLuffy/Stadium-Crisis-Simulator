from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class StadiumZoneRecord(BaseModel):
    timestamp: str = Field(..., description="Time of observation (e.g. 19:05:00)")
    zone: str = Field(..., description="Zone identifier (e.g. Gate C)")
    capacity: int = Field(..., ge=1, description="Maximum safe zone capacity")
    current_crowd: int = Field(..., ge=0, description="Current number of people inside zone")
    inflow_per_min: int = Field(..., ge=0, description="Inflow rate in people/minute")
    outflow_per_min: int = Field(..., ge=0, description="Outflow rate in people/minute")
    queue_size: int = Field(..., ge=0, description="People waiting in external queues")
    transport_capacity: int = Field(..., ge=0, description="Capacity of upcoming transport service")
    next_transport_minutes: float = Field(..., ge=0.0, description="ETA of next scheduled transit in minutes")
    available_shuttles: int = Field(..., ge=0, description="Number of ready dispatchable shuttles")
    gate_d_available: bool = Field(..., description="Whether auxiliary Gate D is operable")


class ValidationErrorItem(BaseModel):
    row: Optional[int] = None
    field: Optional[str] = None
    message: str


class ValidationResult(BaseModel):
    is_valid: bool
    total_records: int = 0
    detected_zones: List[str] = []
    records: List[StadiumZoneRecord] = []
    errors: List[ValidationErrorItem] = []


class RiskEvaluation(BaseModel):
    zone: str
    timestamp: str
    occupancy_percent: float
    net_flow_per_min: int
    remaining_capacity: int
    time_to_capacity_minutes: Optional[float]  # None indicates Infinity (flow <= 0)
    risk_level: RiskLevel
    risk_score: float  # 0 - 100 scale for gauges
    risk_factors: List[str]
    raw_record: StadiumZoneRecord


class StadiumOverview(BaseModel):
    total_capacity: int
    total_crowd: int
    overall_occupancy_percent: float
    most_critical_zone: Optional[RiskEvaluation] = None
    zones: List[RiskEvaluation] = []


class InterventionParameters(BaseModel):
    shuttles_to_dispatch: int = 0
    open_gate_d: bool = False
    crowd_redirect_percent: float = 0.0  # 0 to 100%


class ScenarioOutcome(BaseModel):
    scenario_id: str
    scenario_name: str
    description: str
    parameters: InterventionParameters
    projected_inflow: int
    projected_outflow: int
    projected_net_flow: int
    projected_occupancy_percent: float
    projected_queue: int
    projected_time_to_capacity_minutes: Optional[float]
    projected_risk_level: RiskLevel
    projected_risk_score: float
    resources_consumed: Dict[str, Any]
    resources_remaining: Dict[str, Any]
    is_feasible: bool
    feasibility_error: Optional[str] = None


class ScenarioComparisonResponse(BaseModel):
    zone: str
    baseline: ScenarioOutcome
    scenarios: List[ScenarioOutcome]


class AiRecommendation(BaseModel):
    risk: str
    eta_minutes: float
    recommended_action: str
    reason: str
    alternatives_considered: List[str]
    confidence: float
    is_fallback: bool = False
    fallback_notice: Optional[str] = None
