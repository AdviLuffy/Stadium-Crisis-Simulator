/**
 * Navbar Component
 */

export function renderNavbar(container, state, onNavigate) {
  const isFallback = !state.systemHealth?.gemini_api_configured;
  const aiStatusLabel = isFallback ? "Rule Engine Fallback" : "Gemini 3.8 Flash Active";
  const aiDotClass = isFallback ? "medium" : "low";

  container.innerHTML = `
    <header class="navbar">
      <div class="navbar-container">
        <div class="brand">
          <div class="brand-icon">⚡</div>
          <div>
            <div style="display: flex; align-items: center; gap: 0.5rem;">
              <span class="brand-title">Stadium Crisis Simulator</span>
              <span class="brand-badge">Decision Support</span>
            </div>
            <div style="font-size: 0.725rem; color: var(--text-muted);">Real-Time Crowd Dynamics & Tactical What-If Engine</div>
          </div>
        </div>

        <nav class="nav-links">
          <button class="nav-btn ${state.currentView === 'dashboard' ? 'active' : ''}" data-view="dashboard">
            <span>📊</span> Operations Dashboard
          </button>
          <button class="nav-btn ${state.currentView === 'simulator' ? 'active' : ''}" data-view="simulator">
            <span>⚡</span> Crisis Simulator
          </button>
          <button class="nav-btn ${state.currentView === 'upload' ? 'active' : ''}" data-view="upload">
            <span>📁</span> Data Upload
          </button>
        </nav>

        <div class="nav-status">
          <div class="status-pill" title="${state.systemHealth?.mode || 'Decision Engine'}">
            <span class="dot-indicator" style="background-color: ${isFallback ? 'var(--color-medium)' : 'var(--color-low)'}; box-shadow: 0 0 6px ${isFallback ? 'var(--color-medium)' : 'var(--color-low)'}"></span>
            <span>${aiStatusLabel}</span>
          </div>
          <div class="status-pill" style="color: var(--text-muted);">
            <span>LIVE OBS: <strong>19:05:00</strong></span>
          </div>
        </div>
      </div>
    </header>
  `;

  // Attach navigation listeners
  container.querySelectorAll(".nav-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const view = btn.dataset.view;
      if (view) onNavigate(view);
    });
  });
}
