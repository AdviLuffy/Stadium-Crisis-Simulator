/**
 * Stadium Crisis Simulator API Client
 */

export const api = {
  async getHealth() {
    const res = await fetch("/api/health");
    if (!res.ok) throw new Error(`Health check failed: ${res.statusText}`);
    return res.json();
  },

  async getDemoData() {
    const res = await fetch("/api/data/demo");
    if (!res.ok) throw new Error(`Failed to load demo data: ${res.statusText}`);
    return res.json();
  },

  async uploadCsv(file) {
    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch("/api/upload", {
      method: "POST",
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || "Upload failed");
    }
    return res.json();
  },

  async evaluateRisk(records) {
    const res = await fetch("/api/risk/evaluate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(records),
    });
    if (!res.ok) throw new Error(`Risk evaluation failed: ${res.statusText}`);
    return res.json();
  },

  async simulate(record, customParams = null) {
    const res = await fetch("/api/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ record, custom_params: customParams }),
    });
    if (!res.ok) throw new Error(`Simulation failed: ${res.statusText}`);
    return res.json();
  },

  async getRecommendation(record) {
    const res = await fetch("/api/recommend", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ record }),
    });
    if (!res.ok) throw new Error(`AI recommendation failed: ${res.statusText}`);
    return res.json();
  },
};
