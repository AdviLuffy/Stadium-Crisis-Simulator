# Stadium Crisis Simulator

An AI-powered decision-support system for stadium organizers that evaluates crowd risk, simulates possible interventions, and recommends a feasible action before a developing bottleneck becomes critical.

## Problem

Stadium organizers often need to make decisions while crowd conditions are changing rapidly.

The important question is not only:

> "Is there a crowd bottleneck?"

It is:

> **"What should the organizer do before the bottleneck becomes dangerous?"**

Stadium Crisis Simulator answers this by combining deterministic operational calculations with GenAI-based decision reasoning.

## What It Does

The system:

1. Accepts live or synthetic operational data.
2. Validates the uploaded dataset.
3. Calculates crowd occupancy, net flow, remaining capacity, and time-to-capacity.
4. Classifies operational risk.
5. Simulates feasible interventions.
6. Compares projected outcomes.
7. Uses Gemini to reason over the validated results.
8. Recommends one feasible intervention and explains why.

### Example

For a simulated Gate C scenario:

- Capacity: 10,000
- Current crowd: 8,400
- Inflow: 2,000/min
- Outflow: 1,100/min
- Net flow: +900/min
- Time to capacity: 1.78 minutes

The system can compare interventions such as:

- Dispatching rapid shuttles
- Opening an auxiliary gate
- Redirecting incoming crowd
- Combining interventions

The organizer can then compare the projected outcomes before selecting an action.

## Key Differentiator

This is not only a bottleneck detection system.

It is a **what-if decision simulator**.

Instead of simply predicting that a bottleneck will occur, the system evaluates possible interventions and provides a structured recommendation based on the resulting operational state.

## System Architecture

```text
Operational Data
       |
       v
Data Validation
       |
       v
Deterministic Risk Engine
       |
       +----> Occupancy
       +----> Net Flow
       +----> Time-to-Capacity
       +----> Risk Level
       |
       v
Intervention Simulator
       |
       +----> Shuttle Scenarios
       +----> Auxiliary Gate
       +----> Crowd Redirection
       +----> Combined Actions
       |
       v
Scenario Comparison
       |
       v
Gemini Reasoning Engine
       |
       v
Recommended Action
       |
       v
Organizer Decision
