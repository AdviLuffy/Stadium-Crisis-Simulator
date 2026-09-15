/**
 * Central Reactive Application Store
 */

class AppStore {
  constructor() {
    this.state = {
      currentView: "dashboard", // "dashboard" | "simulator" | "upload"
      activeRecords: [],
      overview: null,
      selectedZoneName: null,
      selectedRecord: null,
      selectedRiskEval: null,
      activeRecommendation: null,
      simulationComparison: null,
      customIntervention: {
        shuttles_to_dispatch: 0,
        open_gate_d: false,
        crowd_redirect_percent: 0,
      },
      isAiLoading: false,
      isSimulating: false,
      uploadResult: null,
      systemHealth: null,
    };

    this.listeners = new Set();
  }

  subscribe(listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  notify() {
    for (const listener of this.listeners) {
      try {
        listener(this.state);
      } catch (err) {
        console.error("Listener error:", err);
      }
    }
  }

  setState(partialState) {
    this.state = { ...this.state, ...partialState };
    this.notify();
  }

  setView(viewName) {
    this.setState({ currentView: viewName });
  }

  selectZone(zoneName) {
    const record = this.state.activeRecords.find((r) => r.zone === zoneName) || null;
    const riskEval = this.state.overview?.zones.find((z) => z.zone === zoneName) || null;
    this.setState({
      selectedZoneName: zoneName,
      selectedRecord: record,
      selectedRiskEval: riskEval,
    });
  }

  setCustomIntervention(params) {
    this.setState({
      customIntervention: { ...this.state.customIntervention, ...params },
    });
  }
}

export const store = new AppStore();
