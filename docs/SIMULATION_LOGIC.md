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
- Estimated time to capacity
- Queue size
- Transport availability
- Available interventions

The risk engine should classify the situation as:

LOW
MEDIUM
HIGH
CRITICAL

The exact thresholds will be finalized and documented before implementation.

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
