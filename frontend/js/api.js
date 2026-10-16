/**
 * GreenPulse – Centralized API Client
 * Manages communication with the FastAPI backend REST & WebSocket endpoints.
 */

const API_BASE = window.location.origin;

class GreenPulseAPI {
  constructor() {
    this.baseUrl = API_BASE;
    this.deviceId = 'esp32-greenpulse-01';
  }

  async request(endpoint, options = {}) {
    const url = `${this.baseUrl}${endpoint}`;
    const headers = {
      'Content-Type': 'application/json',
      ...options.headers,
    };

    try {
      const response = await fetch(url, { ...options, headers });
      if (!response.ok) {
        let errDetail = `HTTP ${response.status} ${response.statusText}`;
        try {
          const errJson = await response.json();
          if (errJson.detail) errDetail = errJson.detail;
        } catch (_) {}
        throw new Error(errDetail);
      }
      return await response.json();
    } catch (error) {
      console.error(`[API Error] ${endpoint}:`, error);
      throw error;
    }
  }

  // Health Check
  async getHealth() {
    return this.request('/api/health');
  }

  // Dashboard Aggregation
  async getDashboardSummary() {
    return this.request(`/api/dashboard?device_id=${this.deviceId}`);
  }

  // Device Status
  async getDeviceStatus() {
    return this.request(`/api/device/status?device_id=${this.deviceId}`);
  }

  // Sensors Telemetry
  async getLatestSensorReading() {
    return this.request(`/api/sensor/latest?device_id=${this.deviceId}`);
  }

  async getSensorHistory(limit = 40) {
    return this.request(`/api/sensor/history?device_id=${this.deviceId}&limit=${limit}`);
  }

  // Irrigation Settings
  async getSettings() {
    return this.request(`/api/irrigation/settings?device_id=${this.deviceId}`);
  }

  async updateSettings(settings) {
    return this.request(`/api/irrigation/settings?device_id=${this.deviceId}`, {
      method: 'PUT',
      body: JSON.stringify(settings),
    });
  }

  // Commands (START, STOP, EMERGENCY_STOP, SET_MODE_AUTO, SET_MODE_MANUAL)
  async sendCommand(command, duration = 10) {
    return this.request('/api/irrigation/commands', {
      method: 'POST',
      body: JSON.stringify({
        device_id: this.deviceId,
        command: command,
        duration_seconds: duration,
      }),
    });
  }

  // Watering History
  async getWateringHistory(limit = 20, offset = 0, mode = null) {
    let endpoint = `/api/irrigation/history?device_id=${this.deviceId}&limit=${limit}&offset=${offset}`;
    if (mode) endpoint += `&mode=${mode}`;
    return this.request(endpoint);
  }

  // CSV Export URL
  getHistoryExportUrl() {
    return `${this.baseUrl}/api/irrigation/history/export?device_id=${this.deviceId}`;
  }

  // Alerts
  async getAlerts(unresolvedOnly = false) {
    return this.request(`/api/alerts?device_id=${this.deviceId}&unresolved_only=${unresolvedOnly}`);
  }

  async resolveAlert(alertId) {
    return this.request(`/api/alerts/${alertId}/resolve`, {
      method: 'PUT',
    });
  }

  // Plants Management
  async getPlants() {
    return this.request('/api/plants');
  }

  async createPlant(plantData) {
    return this.request('/api/plants', {
      method: 'POST',
      body: JSON.stringify(plantData),
    });
  }

  async updatePlant(plantId, plantData) {
    return this.request(`/api/plants/${plantId}`, {
      method: 'PUT',
      body: JSON.stringify(plantData),
    });
  }

  async deletePlant(plantId) {
    return this.request(`/api/plants/${plantId}`, {
      method: 'DELETE',
    });
  }

  // Demo Simulation Endpoints
  async simulateReading(moisture, pumpStatus = 'OFF', mode = 'AUTO') {
    return this.request(`/api/demo/simulate-reading?moisture_percentage=${moisture}&pump_status=${pumpStatus}&irrigation_mode=${mode}`, {
      method: 'POST',
    });
  }

  async triggerScenario(scenarioNumber) {
    return this.request(`/api/demo/trigger-scenario?scenario_number=${scenarioNumber}`, {
      method: 'POST',
    });
  }
}

// Global API instance
window.api = new GreenPulseAPI();
