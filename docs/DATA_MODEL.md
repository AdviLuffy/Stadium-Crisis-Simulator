# Stadium Crisis Simulator — Data Model

## Purpose

The dataset represents synthetic operational conditions inside a
large stadium during a major event.

The data is used to detect developing crowd bottlenecks and provide
context for the AI decision engine.

## Fields

### timestamp

Time at which the observation was recorded.

Example:
19:05:00

### zone

Stadium zone or gate being monitored.

Example:
Gate C

### capacity

Maximum safe operating capacity of the zone.

Example:
10000

### current_crowd

Number of people currently present in the zone.

Example:
8400

### inflow_per_min

Number of people entering the zone per minute.

Example:
2000

### outflow_per_min

Number of people leaving the zone per minute.

Example:
1100

### queue_size

Number of people currently waiting for transportation or access.

Example:
6800

### transport_capacity

Capacity available on the next relevant transport service.

Example:
1800

### next_transport_minutes

Minutes until the next transport service arrives.

Example:
5

### available_shuttles

Number of shuttle buses currently available.

Example:
6

### gate_d_available

Whether an alternative gate is currently available.

Example:
true