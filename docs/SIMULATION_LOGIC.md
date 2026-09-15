# Stadium Crisis Simulator — Simulation Logic

## 1. Occupancy

occupancy_percent =
(current_crowd / capacity) × 100

## 2. Net Crowd Flow

net_flow_per_min =
inflow_per_min - outflow_per_min

## 3. Remaining Capacity

remaining_capacity =
capacity - current_crowd

## 4. Time to Capacity

If net_flow_per_min > 0:

time_to_capacity =
remaining_capacity / net_flow_per_min

If net_flow_per_min <= 0:

time_to_capacity = Infinity

## 5. Risk

The system evaluates:

- Current occupancy
- Net crowd flow
- Estimated time to capacity (TTC)
- Queue size
- Transport availability
- Available interventions

The system classifies risk into four transparent levels: `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`.

### 5.1 Current Telemetry Risk Thresholds (`backend/risk_engine.py`)

Used for real-time observation and zone status evaluation:

- **CRITICAL**:
  - `time_to_capacity <= 3.0` minutes, OR
  - `occupancy_percent >= 90%` AND positive net flow (`net_flow > 0`), OR
  - `time_to_capacity <= 5.0` minutes AND `queue_size > 4,000`
- **HIGH**:
  - `time_to_capacity <= 8.0` minutes, OR
  - `occupancy_percent >= 80%`
- **MEDIUM**:
  - `time_to_capacity <= 15.0` minutes, OR
  - `occupancy_percent >= 65%` OR `queue_size > 2,000`
- **LOW**:
  - All other stable conditions (e.g., negative/zero net flow and safe occupancy).

### 5.2 Projected Scenario Risk Thresholds (`backend/simulation_engine.py`)

Used by the What-If Crisis Simulator to evaluate projected outcomes under simulated interventions:

- **CRITICAL**:
  - Projected `TTC <= 3.0` minutes
- **HIGH**:
  - Projected `TTC <= 8.0` minutes, OR
  - Projected 5-minute occupancy `>= 90%` AND positive projected net flow (`net_flow > 0`)
- **MEDIUM**:
  - Projected `TTC <= 20.0` minutes, OR
  - Positive projected net flow (`net_flow > 0`) otherwise
- **LOW**:
  - Projected net flow `<= 0` (crowd accumulating trend is halted or clearing safely)

#### Purpose of Projected Scenario Thresholds

Projected scenarios use these calibrated thresholds to distinguish intervention effectiveness across distinct tactical options:
- **Baseline (No Action)**: 1.78 min TTC $\rightarrow$ `CRITICAL`.
- **Scenario A (4 Shuttles)**: 5.33 min TTC $\rightarrow$ `HIGH` (buys time but net influx remains elevated at +300/min).
- **Scenario B (Open Gate D)**: 16.0 min TTC, 89% projected 5-min occupancy, +100/min net flow $\rightarrow$ intentionally classified as `MEDIUM`. This reflects that opening Gate D substantially mitigates the acute breach risk compared to shuttles alone by establishing a 16-minute operational buffer.
- **Scenario C (Gate D + 4 Shuttles)**: Negative net flow (-500/min), crowd clearing $\rightarrow$ `LOW`.

## 6. Scenario Simulation

The organizer can test possible interventions.

Examples:

- Dispatch additional shuttles
- Open an alternative gate
- Redirect incoming crowd
- Combine multiple feasible interventions

Each scenario produces a projected operational state.

## 7. GenAI Reasoning

GenAI receives validated calculated data and simulated outcomes.

GenAI must:

1. Identify the most urgent risk.
2. Evaluate feasible interventions.
3. Compare scenario outcomes.
4. Select ONE recommended action.
5. Explain the recommendation in plain English.
6. Never invent unavailable resources or numerical results.
7. Return structured JSON.

## 8. Separation of Responsibilities

Traditional software performs:

- Data validation
- Mathematical calculations
- Risk metrics
- Scenario simulation
- Resource constraints

GenAI performs:

- Contextual reasoning
- Intervention comparison
- Recommendation
- Explanation
