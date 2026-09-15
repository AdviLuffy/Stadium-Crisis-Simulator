/**
 * Main Application Orchestrator
 */

import { api } from "./api.js";
import { store } from "./store.js";
import { renderNavbar } from "./components/Navbar.js";
import { renderDashboard } from "./components/Dashboard.js";
import { renderCrisisSimulator } from "./components/CrisisSimulator.js";
import { renderDataUpload } from "./components/DataUpload.js";

class App {
  constructor() {
    this.navContainer = document.getElementById("navbar-mount");
    this.dashboardContainer = document.getElementById("view-dashboard");
    this.simulatorContainer = document.getElementById("view-simulator");
    this.uploadContainer = document.getElementById("view-upload");

    // Subscribe to store updates
    store.subscribe((state) => this.render(state));
  }

  async init() {
    try {
      // 1. Check system health and Gemini API key status
      const health = await api.getHealth();
      store.setState({ systemHealth: health });

      // 2. Automatically load demo dataset on startup
      await this.loadDemoDataset();
    } catch (err) {
      console.error("Initialization error:", err);
    }
  }

  async loadDemoDataset() {
    try {
      const demoResult = await api.getDemoData();
      if (!demoResult.is_valid || demoResult.records.length === 0) {
        console.error("Demo data validation failed:", demoResult.errors);
        return;
      }

      await this.processRecords(demoResult.records, demoResult);
    } catch (err) {
      console.error("Failed to load demo data:", err);
    }
  }

  async processRecords(records, uploadResult = null) {
    try {
      store.setState({ isAiLoading: true, uploadResult, activeRecords: records });

      // 1. Evaluate stadium risk across all zones
      const overview = await api.evaluateRisk(records);

      // 2. Default target to most critical zone (e.g. Gate C)
      const targetZoneEval = overview.most_critical_zone || overview.zones[0];
      const targetRecord = targetZoneEval ? targetZoneEval.raw_record : records[0];

      // 3. Run baseline and standard what-if simulation comparison
      const comparison = await api.simulate(targetRecord);

      // 4. Update store state
      store.setState({
        overview,
        selectedZoneName: targetRecord.zone,
        selectedRecord: targetRecord,
        selectedRiskEval: targetZoneEval,
        simulationComparison: comparison,
      });

      // 5. Query AI decision support layer
      const recResult = await api.getRecommendation(targetRecord);
      store.setState({
        activeRecommendation: recResult.ai_recommendation,
        isAiLoading: false,
      });
    } catch (err) {
      console.error("Error processing records:", err);
      store.setState({ isAiLoading: false });
    }
  }

  async handleSelectZone(zoneName) {
    const record = store.state.activeRecords.find((r) => r.zone === zoneName);
    const riskEval = store.state.overview?.zones.find((z) => z.zone === zoneName);
    if (!record) return;

    store.setState({
      selectedZoneName: zoneName,
      selectedRecord: record,
      selectedRiskEval: riskEval,
      isAiLoading: true,
    });

    try {
      const comparison = await api.simulate(record, store.state.customIntervention);
      const recResult = await api.getRecommendation(record);

      store.setState({
        simulationComparison: comparison,
        activeRecommendation: recResult.ai_recommendation,
        isAiLoading: false,
      });
    } catch (err) {
      console.error("Failed to switch zone:", err);
      store.setState({ isAiLoading: false });
    }
  }

  async handleRunCustomSimulation(params) {
    const record = store.state.selectedRecord;
    if (!record) return;

    store.setCustomIntervention(params);
    try {
      const comparison = await api.simulate(record, params);
      store.setState({ simulationComparison: comparison });
    } catch (err) {
      console.error("Custom simulation failed:", err);
    }
  }

  async handleUploadFile(file) {
    try {
      const result = await api.uploadCsv(file);
      store.setState({ uploadResult: result });

      if (result.is_valid && result.records.length > 0) {
        await this.processRecords(result.records, result);
      }
    } catch (err) {
      alert(`Upload failed: ${err.message}`);
    }
  }

  handleNavigate(viewName) {
    store.setView(viewName);
  }

  render(state) {
    // Render top navigation
    renderNavbar(this.navContainer, state, (view) => this.handleNavigate(view));

    // Show/hide view containers
    const views = [
      { id: "dashboard", elem: this.dashboardContainer },
      { id: "simulator", elem: this.simulatorContainer },
      { id: "upload", elem: this.uploadContainer },
    ];

    views.forEach(({ id, elem }) => {
      if (elem) {
        if (state.currentView === id) {
          elem.classList.add("active");
        } else {
          elem.classList.remove("active");
        }
      }
    });

    // Render active view
    if (state.currentView === "dashboard" && this.dashboardContainer) {
      renderDashboard(
        this.dashboardContainer,
        state,
        (zone) => this.handleSelectZone(zone),
        (view) => this.handleNavigate(view)
      );
    } else if (state.currentView === "simulator" && this.simulatorContainer) {
      renderCrisisSimulator(
        this.simulatorContainer,
        state,
        (params) => this.handleRunCustomSimulation(params),
        (zone) => this.handleSelectZone(zone)
      );
    } else if (state.currentView === "upload" && this.uploadContainer) {
      renderDataUpload(
        this.uploadContainer,
        state,
        (file) => this.handleUploadFile(file),
        () => this.loadDemoDataset(),
        () => this.handleNavigate("dashboard")
      );
    }
  }
}

// Bootstrap on DOM ready
document.addEventListener("DOMContentLoaded", () => {
  const app = new App();
  app.init();
});
