/**
 * What-If Crisis Simulator Component
 */

export function renderCrisisSimulator(
  container,
  state,
  onRunCustomSimulation,
  onSelectZone
) {
  const record = state.selectedRecord;
  const comparison = state.simulationComparison;
  const custom = state.customIntervention;

  if (!record || !comparison) {
    container.innerHTML = `
      <div class="card" style="text-align: center; padding: 3rem;">
        <h3 style="color: var(--text-secondary); margin-bottom: 1rem;">No simulation data loaded.</h3>
        <p style="color: var(--text-muted);">Please load data or select a zone from the dashboard.</p>
      </div>
    `;
    return;
  }

  // Pre-configured scenario comparison cards
  const allScenarios = [comparison.baseline, ...comparison.scenarios];

  const scenarioCardsHtml = allScenarios.map((scen) => {
    const isBaseline = scen.scenario_id === "baseline";
    const isRecommended = scen.scenario_id === "scenario_c";
    const isCustom = scen.scenario_id === "custom_scenario";
    const isInfeasible = !scen.is_feasible;

    const riskClass = scen.projected_risk_level.toLowerCase();
    const netFlowClass = scen.projected_net_flow < 0 ? "negative" : "positive";
    const ttcText = scen.projected_time_to_capacity_minutes !== null
      ? `${scen.projected_time_to_capacity_minutes} min`
      : "Averted (Safe)";

    return `
      <div class="scenario-box ${isBaseline ? 'baseline' : ''} ${isRecommended ? 'recommended' : ''} ${isInfeasible ? 'infeasible' : ''}">
        ${isRecommended ? '<div class="rec-banner">★ Recommended Action</div>' : ''}
        ${isCustom ? '<div class="rec-banner" style="background: #8b5cf6;">Custom Run</div>' : ''}

        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.5rem;">
          <div class="scenario-title">${scen.scenario_name}</div>
          <span class="badge ${riskClass}">${scen.projected_risk_level}</span>
        </div>

        <div class="scenario-desc">${scen.description}</div>

        ${isInfeasible ? `
          <div style="background: rgba(244, 63, 94, 0.15); border: 1px solid var(--color-critical-border); border-radius: 4px; padding: 0.6rem; color: var(--color-critical); font-size: 0.775rem; margin-bottom: 1rem;">
            <strong>Constraint Violation:</strong> ${scen.feasibility_error}
          </div>
        ` : ''}

        <div class="scenario-metrics-list">
          <div class="scen-metric-item">
            <span style="color: var(--text-secondary);">Projected Influx Rate</span>
            <span class="val ${netFlowClass}">${scen.projected_net_flow > 0 ? '+' : ''}${scen.projected_net_flow.toLocaleString()} /min</span>
          </div>
          <div class="scen-metric-item">
            <span style="color: var(--text-secondary);">Inflow vs Outflow</span>
            <span class="val" style="font-size: 0.75rem; color: var(--text-muted);">
              ↓ ${scen.projected_inflow.toLocaleString()}/m | ↑ ${scen.projected_outflow.toLocaleString()}/m
            </span>
          </div>
          <div class="scen-metric-item">
            <span style="color: var(--text-secondary);">Time to Zone Capacity</span>
            <span class="val" style="color: ${scen.projected_time_to_capacity_minutes !== null && scen.projected_time_to_capacity_minutes <= 3 ? 'var(--color-critical)' : 'inherit'}">
              ⏱ ${ttcText}
            </span>
          </div>
          <div class="scen-metric-item">
            <span style="color: var(--text-secondary);">Projected 5-Min Occupancy</span>
            <span class="val">${scen.projected_occupancy_percent}%</span>
          </div>
          <div class="scen-metric-item">
            <span style="color: var(--text-secondary);">Exterior Queue Drainage</span>
            <span class="val">${scen.projected_queue.toLocaleString()}</span>
          </div>
        </div>

        <div class="resource-usage-box">
          <div style="display: flex; justify-content: space-between; margin-bottom: 0.25rem;">
            <span>Resources Consumed:</span>
            <strong>
              ${scen.resources_consumed.shuttles_dispatched || 0} shuttles${scen.resources_consumed.gate_d_opened ? ' • Gate D' : ''}${scen.resources_consumed.crowd_redirect_percent ? ` • ${scen.resources_consumed.crowd_redirect_percent}% redirect` : ''}
            </strong>
          </div>
          <div style="display: flex; justify-content: space-between;">
            <span>Shuttles Remaining:</span>
            <strong>${scen.resources_remaining.available_shuttles ?? record.available_shuttles}</strong>
          </div>
        </div>
      </div>
    `;
  }).join('');

  // Zone selection options
  const zoneOptionsHtml = (state.overview?.zones || []).map((z) => `
    <option value="${z.zone}" ${z.zone === record.zone ? 'selected' : ''}>
      ${z.zone} (${z.risk_level} Risk - ${z.occupancy_percent}% Occ)
    </option>
  `).join('');

  container.innerHTML = `
    <div style="margin-bottom: 1.5rem; display: flex; justify-content: space-between; align-items: center; flex-wrap: gap;">
      <div>
        <h2 style="font-size: 1.5rem; font-weight: 800; color: #fff;">What-If Tactical Crisis Simulator</h2>
        <p style="font-size: 0.875rem; color: var(--text-secondary); margin-top: 0.25rem;">
          Test and compare operational interventions before committing resources. Verified by numerical calculations.
        </p>
      </div>

      <div style="display: flex; align-items: center; gap: 0.75rem;">
        <label style="font-size: 0.85rem; font-weight: 600; color: var(--text-secondary);">Target Zone:</label>
        <select id="sim-zone-selector" style="background: var(--bg-subtle); color: #fff; border: 1px solid var(--border-color); padding: 0.5rem 0.8rem; border-radius: var(--radius-sm); font-family: var(--font-sans); font-size: 0.85rem; outline: none; cursor: pointer;">
          ${zoneOptionsHtml}
        </select>
      </div>
    </div>

    <div class="simulator-layout">
      <!-- Interactive Custom Intervention Controls -->
      <div class="control-panel">
        <div class="card-header" style="margin-bottom: 1.25rem;">
          <div class="card-title">
            <span>⚙️</span> Interactive Intervention Controls
          </div>
        </div>

        <div class="control-group">
          <div class="control-label-row">
            <span class="control-label">Dispatch Rapid Shuttles</span>
            <span class="control-val-badge" id="val-shuttles">${custom.shuttles_to_dispatch} of ${record.available_shuttles}</span>
          </div>
          <input
            type="range"
            id="input-shuttles"
            min="0"
            max="${Math.max(1, record.available_shuttles)}"
            value="${custom.shuttles_to_dispatch}"
          />
          <div class="control-subtext">
            Each shuttle adds +150 people/min outflow capacity and drains waiting queues.
          </div>
        </div>

        <div class="control-group">
          <label class="switch-label">
            <div>
              <div class="control-label">Open Auxiliary Gate D</div>
              <div class="control-subtext">
                ${record.gate_d_available ? 'Available: unlocks +800 people/min exit corridor' : 'UNAVAILABLE: Gate D is currently inoperable'}
              </div>
            </div>
            <div class="switch">
              <input
                type="checkbox"
                id="input-gate-d"
                ${custom.open_gate_d ? 'checked' : ''}
                ${!record.gate_d_available ? 'disabled' : ''}
              />
              <span class="slider-toggle"></span>
            </div>
          </label>
        </div>

        <div class="control-group">
          <div class="control-label-row">
            <span class="control-label">Redirect Incoming Crowd</span>
            <span class="control-val-badge" id="val-redirect">${custom.crowd_redirect_percent}%</span>
          </div>
          <input
            type="range"
            id="input-redirect"
            min="0"
            max="100"
            step="5"
            value="${custom.crowd_redirect_percent}"
          />
          <div class="control-subtext">
            Broadcast perimeter dynamic signage to divert incoming crowds to adjacent gates.
          </div>
        </div>

        <div style="margin-top: 1.5rem; display: flex; flex-direction: column; gap: 0.75rem;">
          <button class="btn btn-primary" id="btn-run-simulation" style="width: 100%;">
            <span>⚡</span> Simulate Custom Intervention
          </button>
          <button class="btn btn-secondary" id="btn-reset-simulation" style="width: 100%;">
            <span>↺</span> Reset to Defaults
          </button>
        </div>

        <!-- Constraints summary -->
        <div style="margin-top: 1.5rem; border-top: 1px solid var(--border-color); padding-top: 1rem; font-size: 0.75rem; color: var(--text-muted);">
          <div style="font-weight: 700; text-transform: uppercase; margin-bottom: 0.35rem; color: var(--text-secondary);">
            Active Zone Constraints (${record.zone})
          </div>
          <div>• Available Shuttles: <strong>${record.available_shuttles}</strong></div>
          <div>• Gate D Auxiliary Status: <strong>${record.gate_d_available ? 'Available' : 'Unavailable'}</strong></div>
          <div>• Max Zone Capacity: <strong>${record.capacity.toLocaleString()}</strong></div>
        </div>
      </div>

      <!-- Scenarios Comparison Matrix -->
      <div>
        <div class="card-header" style="margin-bottom: 0;">
          <div class="card-title">
            <span>🔬</span> Scenario Comparison Matrix (${allScenarios.length} Scenarios Evaluated)
          </div>
          <span style="font-size: 0.8rem; color: var(--text-secondary);">
            Numerical projection based on physical stadium flow
          </span>
        </div>

        <div class="comparison-grid">
          ${scenarioCardsHtml}
        </div>
      </div>
    </div>
  `;

  // Event Listeners
  const zoneSelect = container.querySelector("#sim-zone-selector");
  if (zoneSelect) {
    zoneSelect.addEventListener("change", (e) => {
      onSelectZone(e.target.value);
    });
  }

  const shuttlesInput = container.querySelector("#input-shuttles");
  const shuttlesVal = container.querySelector("#val-shuttles");
  if (shuttlesInput && shuttlesVal) {
    shuttlesInput.addEventListener("input", (e) => {
      const val = parseInt(e.target.value, 10);
      shuttlesVal.textContent = `${val} of ${record.available_shuttles}`;
    });
  }

  const redirectInput = container.querySelector("#input-redirect");
  const redirectVal = container.querySelector("#val-redirect");
  if (redirectInput && redirectVal) {
    redirectInput.addEventListener("input", (e) => {
      redirectVal.textContent = `${e.target.value}%`;
    });
  }

  const runBtn = container.querySelector("#btn-run-simulation");
  if (runBtn) {
    runBtn.addEventListener("click", () => {
      const shuttles = parseInt(container.querySelector("#input-shuttles").value, 10);
      const gateD = container.querySelector("#input-gate-d").checked;
      const redirect = parseFloat(container.querySelector("#input-redirect").value);

      onRunCustomSimulation({
        shuttles_to_dispatch: shuttles,
        open_gate_d: gateD,
        crowd_redirect_percent: redirect,
      });
    });
  }

  const resetBtn = container.querySelector("#btn-reset-simulation");
  if (resetBtn) {
    resetBtn.addEventListener("click", () => {
      container.querySelector("#input-shuttles").value = "0";
      container.querySelector("#val-shuttles").textContent = `0 of ${record.available_shuttles}`;
      container.querySelector("#input-gate-d").checked = false;
      container.querySelector("#input-redirect").value = "0";
      container.querySelector("#val-redirect").textContent = "0%";
      onRunCustomSimulation({
        shuttles_to_dispatch: 0,
        open_gate_d: false,
        crowd_redirect_percent: 0,
      });
    });
  }
}
