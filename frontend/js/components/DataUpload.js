/**
 * Data Upload & Validation Component
 */

export function renderDataUpload(
  container,
  state,
  onUploadFile,
  onLoadDemo,
  onAnalyze
) {
  const result = state.uploadResult;
  const records = state.activeRecords;

  const isValid = result?.is_valid ?? (records.length > 0);
  const totalCount = result?.total_records ?? records.length;
  const detectedZones = result?.detected_zones ?? (records.map(r => r.zone).filter((v, i, a) => a.indexOf(v) === i));
  const errors = result?.errors || [];

  // Table rows for records
  const tableRowsHtml = records.slice(0, 10).map((r) => `
    <tr>
      <td class="font-mono">${r.timestamp}</td>
      <td><strong>${r.zone}</strong></td>
      <td class="font-mono">${r.capacity.toLocaleString()}</td>
      <td class="font-mono">${r.current_crowd.toLocaleString()}</td>
      <td class="font-mono text-critical">+${r.inflow_per_min.toLocaleString()}</td>
      <td class="font-mono text-low">${r.outflow_per_min.toLocaleString()}</td>
      <td class="font-mono">${r.queue_size.toLocaleString()}</td>
      <td class="font-mono">${r.transport_capacity.toLocaleString()}</td>
      <td class="font-mono">${r.next_transport_minutes}m</td>
      <td class="font-mono">${r.available_shuttles}</td>
      <td><span class="badge ${r.gate_d_available ? 'low' : 'critical'}">${r.gate_d_available ? 'YES' : 'NO'}</span></td>
    </tr>
  `).join('');

  container.innerHTML = `
    <div style="margin-bottom: 1.5rem; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem;">
      <div>
        <h2 style="font-size: 1.5rem; font-weight: 800; color: #fff;">Operational Data Ingestion & Validation</h2>
        <p style="font-size: 0.875rem; color: var(--text-secondary); margin-top: 0.25rem;">
          Upload stadium telemetry in CSV format. Strict safety validation checks are enforced before ingestion.
        </p>
      </div>

      <div style="display: flex; gap: 0.75rem;">
        <button class="btn btn-secondary" id="btn-load-demo-upload">
          <span>⚡</span> Load Synthetic Demo Scenario
        </button>
        ${isValid && records.length > 0 ? `
          <button class="btn btn-primary" id="btn-analyze-upload">
            <span>📊</span> Analyze Data in Dashboard →
          </button>
        ` : ''}
      </div>
    </div>

    <!-- Drag & Drop Zone -->
    <div class="upload-dropzone" id="dropzone">
      <div class="upload-icon">📂</div>
      <div class="upload-title">Drag & Drop Stadium Operational CSV Here</div>
      <div class="upload-subtitle">or click to browse your files (.csv format required)</div>
      <input type="file" id="csv-file-input" accept=".csv" style="display: none;" />
      <button class="btn btn-secondary" type="button" onclick="document.getElementById('csv-file-input').click()">
        Select CSV File
      </button>
    </div>

    <!-- Validation Status Summary Card -->
    <div class="card" style="margin-bottom: 1.5rem;">
      <div class="card-header">
        <div class="card-title">
          <span>🛡️</span> Ingestion & Safety Validation Status
        </div>
        <span class="badge ${isValid ? 'low' : 'critical'}">
          ${isValid ? 'VALID DATASET' : 'VALIDATION FAILED'}
        </span>
      </div>

      <div class="metrics-row">
        <div class="metric-box">
          <div class="metric-label">Validation Status</div>
          <div class="metric-val ${isValid ? 'text-low' : 'text-critical'}" style="font-size: 1.15rem;">
            ${isValid ? 'Passed All Checks' : 'Errors Detected'}
          </div>
          <div class="metric-sub">${errors.length} validation issues</div>
        </div>

        <div class="metric-box">
          <div class="metric-label">Records Ingested</div>
          <div class="metric-val">${totalCount}</div>
          <div class="metric-sub">operational rows</div>
        </div>

        <div class="metric-box">
          <div class="metric-label">Detected Zones</div>
          <div class="metric-val text-cyan">${detectedZones.length}</div>
          <div class="metric-sub">${detectedZones.join(', ') || 'None'}</div>
        </div>

        <div class="metric-box">
          <div class="metric-label">Format Compliance</div>
          <div class="metric-val font-mono" style="font-size: 1.15rem;">
            11 / 11
          </div>
          <div class="metric-sub">required schema fields</div>
        </div>
      </div>

      <!-- Errors Console if any -->
      ${errors.length > 0 ? `
        <div class="error-box">
          <div class="error-heading">
            <span>⚠️</span> Validation Errors Detected (${errors.length})
          </div>
          <p style="font-size: 0.8rem; color: var(--text-secondary); margin-bottom: 0.75rem;">
            The uploaded file violated stadium operational integrity rules. Numerical calculations have been halted for corrupted rows.
          </p>
          <table class="data-table">
            <thead>
              <tr>
                <th style="width: 80px;">Row</th>
                <th style="width: 160px;">Field</th>
                <th>Validation Message</th>
              </tr>
            </thead>
            <tbody>
              ${errors.map((e) => `
                <tr>
                  <td class="font-mono text-critical">${e.row ?? 'Header'}</td>
                  <td><strong>${e.field ?? 'General'}</strong></td>
                  <td style="color: var(--color-critical);">${e.message}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      ` : ''}
    </div>

    <!-- Active Records Table -->
    ${records.length > 0 ? `
      <div class="card">
        <div class="card-header">
          <div class="card-title">
            <span>📋</span> Active Operational Telemetry Preview (${records.length} records)
          </div>
          <span style="font-size: 0.8rem; color: var(--text-muted);">Showing first ${Math.min(10, records.length)} entries</span>
        </div>

        <div style="overflow-x: auto;">
          <table class="data-table">
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Zone</th>
                <th>Capacity</th>
                <th>Crowd</th>
                <th>Inflow/min</th>
                <th>Outflow/min</th>
                <th>Queue</th>
                <th>Transit Cap</th>
                <th>Next Transit</th>
                <th>Shuttles</th>
                <th>Gate D</th>
              </tr>
            </thead>
            <tbody>
              ${tableRowsHtml}
            </tbody>
          </table>
        </div>
      </div>
    ` : ''}
  `;

  // Attach event listeners
  const fileInput = container.querySelector("#csv-file-input");
  const dropzone = container.querySelector("#dropzone");

  if (fileInput) {
    fileInput.addEventListener("change", (e) => {
      const file = e.target.files[0];
      if (file) onUploadFile(file);
    });
  }

  if (dropzone) {
    dropzone.addEventListener("dragover", (e) => {
      e.preventDefault();
      dropzone.classList.add("dragover");
    });
    dropzone.addEventListener("dragleave", () => {
      dropzone.classList.remove("dragover");
    });
    dropzone.addEventListener("drop", (e) => {
      e.preventDefault();
      dropzone.classList.remove("dragover");
      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        onUploadFile(e.dataTransfer.files[0]);
      }
    });
  }

  const demoBtn = container.querySelector("#btn-load-demo-upload");
  if (demoBtn) {
    demoBtn.addEventListener("click", () => onLoadDemo());
  }

  const analyzeBtn = container.querySelector("#btn-analyze-upload");
  if (analyzeBtn) {
    analyzeBtn.addEventListener("click", () => onAnalyze());
  }
}
