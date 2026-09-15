/**
 * Operations Dashboard Component
 */

export function renderDashboard(container, state, onSelectZone, onNavigate) {
  const overview = state.overview;
  const criticalEval = overview?.most_critical_zone;
  const selectedEval = state.selectedRiskEval || criticalEval;
  const selectedRecord = state.selectedRecord || criticalEval?.raw_record;
  const recommendation = state.activeRecommendation;

  if (!overview || !selectedEval || !selectedRecord) {
    container.innerHTML = `
      <div class="card" style="text-align: center; padding: 3rem;">
        <h3 style="color: var(--text-secondary); margin-bottom: 1rem;">No operational data loaded.</h3>
        <p style="color: var(--text-muted); margin-bottom: 1.5rem;">Upload a CSV file or load the standard demonstration scenario.</p>
        <button class="btn btn-primary" id="btn-load-demo-dash">⚡ Load Demo Scenario (Gate C Bottleneck)</button>
      </div>
    `;
    const btn = container.querySelector("#btn-load-demo-dash");
    if (btn) btn.addEventListener("click", () => onNavigate("upload"));
    return;
  }

  const isCritical = selectedEval.risk_level === "CRITICAL";
  const badgeClass = selectedEval.risk_level.toLowerCase();
  const etaDisplay = selectedEval.time_to_capacity_minutes !== null
    ? `${selectedEval.time_to_capacity_minutes}`
    : "∞";

  // Critical Alert Banner HTML (Hierarchy #1 & #2)
  const bannerHtml = `
    <div class="critical-alert-banner">
      <div class="alert-left">
        <div class="alert-pulse-badge">
          <span>●</span> ${selectedEval.risk_level}
        </div>
        <div class="alert-content">
          <h2>
            ${selectedEval.zone} — Rapid Crowd Surge Detected
          </h2>
          <p>
            Net influx is <strong>+${selectedEval.net_flow_per_min:,} people/min</strong> with ${selectedRecord.queue_size:,} in exterior queues.
            Action required before zone capacity breach.
          </p>
        </div>
      </div>

      <div class="alert-right">
        <div class="eta-display">
          <div class="eta-label">Time To Capacity</div>
          <div class="eta-value" style="color: ${isCritical ? 'var(--color-critical)' : 'var(--color-high)'}">
            ${etaDisplay} <span class="eta-unit">${selectedEval.time_to_capacity_minutes !== null ? 'min' : '(safe)'}</span>
          </div>
        </div>
        <button class="btn btn-primary" id="btn-banner-simulate" style="white-space: nowrap;">
          <span>⚡</span> Simulate Interventions
        </button>
      </div>
    </div>
  `;

  // Telemetry Card HTML (Hierarchy #3)
  const telemetryHtml = `
    <div class="card">
      <div class="card-header">
        <div class="card-title">
          <span>📊</span> Telemetry & Risk Analysis — ${selectedEval.zone}
        </div>
        <span class="badge ${badgeClass}">${selectedEval.risk_level} RISK (${selectedEval.risk_score}%)</span>
      </div>

      <div class="metrics-row">
        <div class="metric-box">
          <div class="metric-label">Current Crowd</div>
          <div class="metric-val">${selectedRecord.current_crowd:,}</div>
          <div class="metric-sub">of ${selectedRecord.capacity:,} max</div>
        </div>
        <div class="metric-box">
          <div class="metric-label">Net Influx</div>
          <div class="metric-val ${selectedEval.net_flow_per_min > 0 ? 'text-critical' : 'text-low'}">
            ${selectedEval.net_flow_per_min > 0 ? '+' : ''}${selectedEval.net_flow_per_min:,}
          </div>
          <div class="metric-sub">people / minute</div>
        </div>
        <div class="metric-box">
          <div class="metric-label">Remaining Cap</div>
          <div class="metric-val">${selectedEval.remaining_capacity:,}</div>
          <div class="metric-sub">available seats</div>
        </div>
        <div class="metric-box">
          <div class="metric-label">Exterior Queue</div>
          <div class="metric-val ${selectedRecord.queue_size > 2000 ? 'text-high' : ''}">
            ${selectedRecord.queue_size:,}
          </div>
          <div class="metric-sub">waiting at perimeter</div>
        </div>
      </div>

      <div class="progress-container">
        <div class="progress-header">
          <span>Occupancy Threshold</span>
          <span class="font-mono"><strong>${selectedEval.occupancy_percent}%</strong></span>
        </div>
        <div class="progress-bar-bg">
          <div class="progress-fill ${badgeClass}" style="width: ${Math.min(100, selectedEval.occupancy_percent)}%"></div>
        </div>
      </div>

      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; margin-top: 1rem;">
        <div class="stat-item">
          <div class="stat-label">Inflow vs Outflow Rate</div>
          <div style="font-size: 0.85rem; font-weight: 600; color: #fff; margin-top: 0.2rem;">
            ↓ ${selectedRecord.inflow_per_min:,}/m &nbsp;|&nbsp; ↑ ${selectedRecord.outflow_per_min:,}/m
          </div>
        </div>
        <div class="stat-item">
          <div class="stat-label">Next Transit Arrival</div>
          <div style="font-size: 0.85rem; font-weight: 600; color: #fff; margin-top: 0.2rem;">
            ⏱ ${selectedRecord.next_transport_minutes} min (Cap: ${selectedRecord.transport_capacity:,})
          </div>
        </div>
      </div>

      <div style="margin-top: 1.25rem;">
        <div class="control-label" style="font-size: 0.75rem; text-transform: uppercase; color: var(--text-muted); margin-bottom: 0.5rem;">
          Detected Risk Factors
        </div>
        <ul class="factors-list">
          ${selectedEval.risk_factors.map((f) => `
            <li class="factor-item ${isCritical ? 'critical' : 'warning'}">
              <span>⚠️</span>
              <span>${f}</span>
            </li>
          `).join('')}
        </ul>
      </div>
    </div>
  `;

  // AI Recommendation Card HTML (Hierarchy #4 & #5)
  let aiCardContent = "";
  if (state.isAiLoading) {
    aiCardContent = `
      <div style="text-align: center; padding: 4rem 1rem;">
        <div class="dot-indicator pulse" style="width: 14px; height: 14px; margin: 0 auto 1rem; background: #38bdf8;"></div>
        <h4 style="color: #fff; margin-bottom: 0.5rem;">Analyzing Operational State...</h4>
        <p style="font-size: 0.825rem; color: var(--text-muted);">
          Simulating tactical interventions and evaluating resource safety margins.
        </p>
      </div>
    `;
  } else if (recommendation) {
    const isFallback = recommendation.is_fallback;
    aiCardContent = `
      <div class="ai-meta-bar">
        <div class="ai-badge">
          <span>🧠</span> ${isFallback ? 'Deterministic Safety Engine' : 'Gemini 3.8 Flash Decision Engine'}
        </div>
        <div class="ai-confidence">
          Confidence: <strong>${Math.round(recommendation.confidence * 100)}%</strong>
        </div>
      </div>

      <div class="action-highlight-box">
        <div class="action-label">Recommended Tactical Action</div>
        <div class="action-title">${recommendation.recommended_action}</div>
      </div>

      <div class="ai-reason-box">
        <div style="font-size: 0.75rem; text-transform: uppercase; color: var(--text-muted); font-weight: 700; margin-bottom: 0.35rem;">
          Tactical Rationale (WHY)
        </div>
        <p>${recommendation.reason}</p>
      </div>

      <div class="alternatives-section">
        <div class="alternatives-heading">Alternatives Evaluated & Impact</div>
        <ul class="alternatives-list">
          ${recommendation.alternatives_considered.map((alt) => `
            <li class="alt-item">
              <span>•</span> <span>${alt}</span>
            </li>
          `).join('')}
        </ul>
      </div>

      ${isFallback ? `
        <div class="fallback-indicator">
          <span>ℹ️</span>
          <span>${recommendation.fallback_notice || 'Operating in deterministic offline mode (no external API key exposure).'}</span>
        </div>
      ` : ''}
    `;
  } else {
    aiCardContent = `
      <div style="text-align: center; padding: 3rem 1rem;">
        <p style="color: var(--text-muted);">No recommendation available.</p>
      </div>
    `;
  }

  const aiCardHtml = `
    <div class="card ai-card">
      <div class="card-header">
        <div class="card-title">
          <span>🛡️</span> AI Tactical Decision Support
        </div>
        <span class="badge" style="background: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.3);">
          ACTION REQUIRED
        </span>
      </div>
      ${aiCardContent}
    </div>
  `;

  // Multi-Zone Stadium Overview HTML (Hierarchy #6)
  const zoneCardsHtml = overview.zones.map((z) => {
    const isSelected = z.zone === selectedEval.zone;
    const zBadgeClass = z.risk_level.toLowerCase();
    const zEta = z.time_to_capacity_minutes !== null ? `${z.time_to_capacity_minutes}m` : 'Stable';
    return `
      <div class="zone-card ${isSelected ? 'selected' : ''}" data-zone="${z.zone}">
        <div class="zone-card-top">
          <span class="zone-name">${z.zone}</span>
          <span class="badge ${zBadgeClass}">${z.risk_level}</span>
        </div>

        <div class="zone-stats-grid">
          <div class="stat-item">
            <div class="stat-label">Occupancy</div>
            <div class="stat-value">${z.occupancy_percent}%</div>
          </div>
          <div class="stat-item">
            <div class="stat-label">Net Influx</div>
            <div class="stat-value ${z.net_flow_per_min > 0 ? 'text-critical' : 'text-low'}">
              ${z.net_flow_per_min > 0 ? '+' : ''}${z.net_flow_per_min}/m
            </div>
          </div>
          <div class="stat-item">
            <div class="stat-label">Crowd / Cap</div>
            <div style="font-size: 0.85rem; font-weight: 600; color: #fff; margin-top: 0.2rem;">
              ${z.raw_record.current_crowd:,} / ${z.raw_record.capacity:,}
            </div>
          </div>
          <div class="stat-item">
            <div class="stat-label">Time to Cap</div>
            <div style="font-size: 0.85rem; font-weight: 700; color: ${z.risk_level === 'CRITICAL' ? 'var(--color-critical)' : '#fff'}; margin-top: 0.2rem;">
              ⏱ ${zEta}
            </div>
          </div>
        </div>

        <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.725rem; color: var(--text-muted); margin-top: 0.5rem; border-top: 1px solid rgba(255,255,255,0.04); padding-top: 0.4rem;">
          <span>Queue: ${z.raw_record.queue_size:,}</span>
          <span style="color: #38bdf8; font-weight: 600;">Click to Inspect →</span>
        </div>
      </div>
    `;
  }).join('');

  container.innerHTML = `
    <!-- Top Alert Banner -->
    ${bannerHtml}

    <!-- Primary 2-Column Grid -->
    <div class="dashboard-grid">
      ${telemetryHtml}
      ${aiCardHtml}
    </div>

    <!-- Multi-Zone Overview Grid -->
    <div class="card" style="margin-top: 1.5rem;">
      <div class="card-header">
        <div class="card-title">
          <span>🏟️</span> Multi-Zone Stadium Operational Overview
        </div>
        <div style="font-size: 0.8rem; color: var(--text-secondary);">
          Total Stadium Crowd: <strong>${overview.total_crowd:,}</strong> / ${overview.total_capacity:,} (${overview.overall_occupancy_percent}%)
        </div>
      </div>
      <div class="zone-grid">
        ${zoneCardsHtml}
      </div>
    </div>
  `;

  // Attach event listeners
  const bannerSimulateBtn = container.querySelector("#btn-banner-simulate");
  if (bannerSimulateBtn) {
    bannerSimulateBtn.addEventListener("click", () => {
      onNavigate("simulator");
    });
  }

  container.querySelectorAll(".zone-card").forEach((card) => {
    card.addEventListener("click", () => {
      const zoneName = card.dataset.zone;
      if (zoneName) onSelectZone(zoneName);
    });
  });
}
