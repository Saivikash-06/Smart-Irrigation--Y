/**
 * GreenPulse – Main Dashboard Application Controller
 * Handles UI interactions, live WebSockets, data binding, and state updates.
 */

document.addEventListener('DOMContentLoaded', () => {
  const app = new GreenPulseApp();
  app.init();
});

class GreenPulseApp {
  constructor() {
    this.currentTab = 'overview';
    this.chartManager = null;
    this.ws = null;
    this.wsReconnectTimer = null;
    this.pollingTimer = null;
    this.isDemoMode = false;
    this.activeSettings = {};
    this.historyPage = 0;
    this.historyLimit = 10;
  }

  async init() {
    this.setupNavigation();
    this.setupDemoMode();
    this.setupHardwareControls();
    this.setupSettingsForm();
    this.setupPlantManagement();
    this.setupHistoryFilters();

    // Initialize Chart
    this.chartManager = new MoistureChart('moistureTrendChart');

    // Initial Data Fetch
    await this.loadInitialData();

    // Start WebSocket & Polling Fallback
    this.initWebSocket();
    this.startPollingFallback();
  }

  /* ============================================================================
     NAVIGATION & TABS
     ============================================================================ */
  setupNavigation() {
    const navButtons = document.querySelectorAll('.nav-item button');
    navButtons.forEach(btn => {
      btn.addEventListener('click', (e) => {
        const targetTab = btn.getAttribute('data-tab');
        this.switchTab(targetTab);

        // Close mobile sidebar if open
        document.querySelector('.sidebar').classList.remove('mobile-open');
      });
    });

    const mobileMenuBtn = document.getElementById('mobileMenuToggle');
    if (mobileMenuBtn) {
      mobileMenuBtn.addEventListener('click', () => {
        document.querySelector('.sidebar').classList.toggle('mobile-open');
      });
    }
  }

  switchTab(tabId) {
    if (!tabId) return;
    this.currentTab = tabId;

    // Update Sidebar Navigation state
    document.querySelectorAll('.nav-item').forEach(item => {
      const btn = item.querySelector('button');
      if (btn && btn.getAttribute('data-tab') === tabId) {
        item.classList.add('active');
      } else {
        item.classList.remove('active');
      }
    });

    // Update View Panes
    document.querySelectorAll('.page-section').forEach(section => {
      if (section.id === `section-${tabId}`) {
        section.classList.add('active');
      } else {
        section.classList.remove('active');
      }
    });

    // Refresh context data based on tab
    if (tabId === 'history') {
      this.loadWateringHistory();
    } else if (tabId === 'plants') {
      this.loadPlants();
    } else if (tabId === 'alerts') {
      this.loadAlerts();
    } else if (tabId === 'settings') {
      this.loadSettings();
    }
  }

  /* ============================================================================
     DATA LOADING & STATE BINDING
     ============================================================================ */
  async loadInitialData() {
    try {
      const summary = await window.api.getDashboardSummary();
      this.renderDashboardSummary(summary);
      this.activeSettings = {
        threshold: summary.irrigation.threshold,
        automatic_mode: summary.irrigation.automatic_mode,
        duration: summary.irrigation.watering_duration_seconds,
      };

      // Initialize Chart
      if (this.chartManager) {
        this.chartManager.init(summary.chart_data || [], summary.irrigation.threshold);
      }
    } catch (err) {
      console.warn('Initial data load error:', err);
      this.showToast('Backend unavailable. Showing offline state.', 'error');
      this.setDeviceOfflineState(true, 'Backend connection failed');
    }
  }

  renderDashboardSummary(data) {
    if (!data) return;

    // Device status
    const isOnline = data.device.is_online;
    this.updateDeviceConnectivity(isOnline, data.device.last_seen);

    // Sensor Readings
    const moisture = data.sensor.current_moisture;
    const rawAdc = data.sensor.raw_adc;
    const pumpStatus = data.sensor.pump_status;
    const mode = data.sensor.irrigation_mode;
    const lastUpdate = data.sensor.last_update;

    // Update Metric Cards
    this.updateElementText('metricMoistureVal', `${moisture.toFixed(1)}%`);
    this.updateElementText('metricRawAdcVal', `ADC: ${rawAdc}`);
    this.updateElementText('metricPumpVal', pumpStatus);
    this.updateElementText('metricModeVal', mode);
    this.updateElementText('metricEventsVal', data.irrigation.total_watering_events);
    this.updateElementText('metricWaterVal', `${data.irrigation.total_water_liters.toFixed(1)} L`);

    // Pump status badge & visuals
    this.renderPumpStatus(pumpStatus);

    // Moisture condition pill
    this.renderConditionPill(moisture);

    // Soil meter bar
    this.updateMeterBar(moisture, data.irrigation.threshold);

    // Timestamps
    if (lastUpdate) {
      const timeStr = new Date(lastUpdate).toLocaleTimeString();
      this.updateElementText('lastSensorUpdateText', `Updated at ${timeStr}`);
    }

    // Emergency stop visual status
    const isEmergency = data.irrigation.is_emergency_stop;
    const emergencyBanner = document.getElementById('emergencyActiveNotice');
    if (emergencyBanner) {
      emergencyBanner.style.display = isEmergency ? 'block' : 'none';
    }

    // Recent activity list
    this.renderRecentActivity(data.recent_activity || []);

    // Active alerts count & list
    this.renderActiveAlerts(data.active_alerts || []);
  }

  updateDeviceConnectivity(isOnline, lastSeenIso) {
    const statusChip = document.getElementById('deviceStatusChip');
    const pulseDot = document.getElementById('sidebarPulseDot');
    const offlineBanner = document.getElementById('offlineNoticeBanner');

    const formattedTime = lastSeenIso ? new Date(lastSeenIso).toLocaleTimeString() : 'Never';

    if (isOnline) {
      if (statusChip) {
        statusChip.className = 'status-chip online';
        statusChip.innerHTML = `<span class="pulse-dot online"></span> ESP32 Online`;
      }
      if (pulseDot) pulseDot.className = 'pulse-dot online';
      if (offlineBanner) offlineBanner.classList.remove('active');
    } else {
      if (statusChip) {
        statusChip.className = 'status-chip offline';
        statusChip.innerHTML = `<span class="pulse-dot"></span> Device Offline`;
      }
      if (pulseDot) pulseDot.className = 'pulse-dot';
      if (offlineBanner) {
        offlineBanner.classList.add('active');
        document.getElementById('offlineBannerText').innerText =
          `Device offline – displaying the last available reading (Last seen: ${formattedTime})`;
      }
    }
  }

  renderPumpStatus(status) {
    const badge = document.getElementById('pumpStateBadge');
    if (!badge) return;

    if (status === 'ON') {
      badge.className = 'pump-status-badge on';
      badge.innerHTML = '💧 PUMP RUNNING';
    } else {
      badge.className = 'pump-status-badge off';
      badge.innerHTML = '⏸️ PUMP IDLE (OFF)';
    }

    // Control buttons state
    const btnStart = document.getElementById('btnStartWatering');
    const btnStop = document.getElementById('btnStopWatering');
    if (btnStart) btnStart.disabled = (status === 'ON');
    if (btnStop) btnStop.disabled = (status === 'OFF');
  }

  renderConditionPill(moisture) {
    const pill = document.getElementById('conditionPill');
    const desc = document.getElementById('conditionDesc');
    if (!pill) return;

    if (moisture < 30.0) {
      pill.className = 'condition-pill dry';
      pill.innerText = 'DRY';
      if (desc) desc.innerText = 'Dry – irrigation may be required.';
    } else if (moisture < 45.0) {
      pill.className = 'condition-pill acceptable';
      pill.innerText = 'ACCEPTABLE';
      if (desc) desc.innerText = 'Moisture is acceptable but should be monitored.';
    } else if (moisture <= 75.0) {
      pill.className = 'condition-pill optimal';
      pill.innerText = 'COMFORTABLE';
      if (desc) desc.innerText = 'Comfortable moisture range for the demonstration plant.';
    } else {
      pill.className = 'condition-pill high';
      pill.innerText = 'HIGH';
      if (desc) desc.innerText = "High moisture – check the plant's watering requirements.";
    }
  }

  updateMeterBar(moisture, threshold = 30) {
    const fill = document.getElementById('soilMeterFill');
    const marker = document.getElementById('soilMeterThresholdMarker');
    if (fill) fill.style.width = `${Math.min(100, Math.max(0, moisture))}%`;
    if (marker) marker.style.left = `${Math.min(100, Math.max(0, threshold))}%`;
  }

  renderRecentActivity(events) {
    const tbody = document.getElementById('recentActivityTableBody');
    if (!tbody) return;

    if (!events.length) {
      tbody.innerHTML = `<tr><td colspan="5" class="text-center" style="text-align:center; padding: 24px; color: var(--text-muted);">No recent watering events recorded.</td></tr>`;
      return;
    }

    tbody.innerHTML = events.map(ev => `
      <tr>
        <td><strong>#${ev.id}</strong></td>
        <td>${new Date(ev.start_time).toLocaleTimeString()}</td>
        <td><span class="badge ${ev.irrigation_mode.toLowerCase()}">${ev.irrigation_mode}</span></td>
        <td>${ev.moisture_before.toFixed(1)}% → ${ev.moisture_after ? ev.moisture_after.toFixed(1) + '%' : '–'}</td>
        <td><strong>${ev.estimated_water_liters.toFixed(2)} L</strong></td>
      </tr>
    `).join('');
  }

  renderActiveAlerts(alerts) {
    const container = document.getElementById('activeAlertsList');
    if (!container) return;

    if (!alerts.length) {
      container.innerHTML = `
        <div style="text-align:center; padding: 20px; color: var(--text-muted); font-size: 13px;">
          ✅ No active alerts. All garden parameters are within safe ranges.
        </div>`;
      return;
    }

    container.innerHTML = alerts.map(al => `
      <div style="display:flex; justify-content:space-between; align-items:center; padding:12px; border-radius:var(--radius-md); background:${al.severity === 'danger' ? '#fee2e2' : '#fef3c7'}; margin-bottom:8px;">
        <div>
          <strong style="color:${al.severity === 'danger' ? '#991b1b' : '#92400e'}; font-size:13px;">${al.alert_type}</strong>
          <p style="margin:2px 0 0; font-size:12px; color:#475569;">${al.message}</p>
        </div>
        <button class="btn btn-secondary" style="padding:4px 10px; font-size:11px;" onclick="window.api.resolveAlert(${al.id}).then(() => window.location.reload())">Resolve</button>
      </div>
    `).join('');
  }

  /* ============================================================================
     WEBSOCKET & REAL-TIME INGESTION
     ============================================================================ */
  initWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/dashboard`;

    try {
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        console.log('[WebSocket] Connected to GreenPulse live telemetry stream');
        clearInterval(this.wsReconnectTimer);
      };

      this.ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          this.handleWebSocketMessage(msg);
        } catch (e) {
          console.error('[WebSocket] Parsing error:', e);
        }
      };

      this.ws.onclose = () => {
        console.warn('[WebSocket] Connection closed. Retrying in 4s...');
        this.reconnectWebSocket();
      };

      this.ws.onerror = (err) => {
        console.warn('[WebSocket] Socket error observed');
      };
    } catch (e) {
      this.reconnectWebSocket();
    }
  }

  reconnectWebSocket() {
    if (this.wsReconnectTimer) return;
    this.wsReconnectTimer = setTimeout(() => {
      this.wsReconnectTimer = null;
      this.initWebSocket();
    }, 4000);
  }

  startPollingFallback() {
    // Polls every 4s to ensure synchronization even if WebSocket drops
    setInterval(async () => {
      try {
        const summary = await window.api.getDashboardSummary();
        this.renderDashboardSummary(summary);
      } catch (_) {}
    }, 4000);
  }

  handleWebSocketMessage(msg) {
    if (!msg || !msg.type) return;

    if (msg.type === 'SENSOR_READING') {
      const d = msg.data;
      this.updateElementText('metricMoistureVal', `${d.moisture_percentage.toFixed(1)}%`);
      this.updateElementText('metricRawAdcVal', `ADC: ${d.raw_adc_value}`);
      this.updateElementText('metricPumpVal', d.pump_status);
      this.updateElementText('metricModeVal', d.irrigation_mode);
      this.renderPumpStatus(d.pump_status);
      this.renderConditionPill(d.moisture_percentage);
      this.updateMeterBar(d.moisture_percentage, this.activeSettings.threshold);
      this.updateDeviceConnectivity(true, d.recorded_at);

      if (this.chartManager) {
        this.chartManager.addReading(d.recorded_at, d.moisture_percentage);
      }
    } else if (msg.type === 'IRRIGATION_EVENT') {
      this.showToast(`Watering event completed (${msg.data.estimated_water_liters}L used)`, 'info');
      this.loadInitialData();
    } else if (msg.type === 'SETTINGS_UPDATED') {
      if (this.chartManager && msg.data.moisture_threshold) {
        this.chartManager.updateThreshold(msg.data.moisture_threshold);
      }
    }
  }

  /* ============================================================================
     HARDWARE CONTROLS
     ============================================================================ */
  setupHardwareControls() {
    // Start Watering
    const btnStart = document.getElementById('btnStartWatering');
    if (btnStart) {
      btnStart.addEventListener('click', async () => {
        try {
          btnStart.disabled = true;
          const res = await window.api.sendCommand('START', 10);
          this.showToast('Command dispatched: Start Watering', 'info');
        } catch (err) {
          this.showToast(`Error: ${err.message}`, 'error');
        }
      });
    }

    // Stop Watering
    const btnStop = document.getElementById('btnStopWatering');
    if (btnStop) {
      btnStop.addEventListener('click', async () => {
        try {
          btnStop.disabled = true;
          await window.api.sendCommand('STOP');
          this.showToast('Command dispatched: Stop Watering', 'info');
        } catch (err) {
          this.showToast(`Error: ${err.message}`, 'error');
        }
      });
    }

    // Auto Mode Toggle
    const btnAuto = document.getElementById('btnSetAutoMode');
    if (btnAuto) {
      btnAuto.addEventListener('click', async () => {
        try {
          await window.api.sendCommand('SET_MODE_AUTO');
          this.showToast('Switched to Automatic Irrigation Mode', 'info');
          this.loadInitialData();
        } catch (err) {
          this.showToast(`Error: ${err.message}`, 'error');
        }
      });
    }

    // Manual Mode Toggle
    const btnManual = document.getElementById('btnSetManualMode');
    if (btnManual) {
      btnManual.addEventListener('click', async () => {
        try {
          await window.api.sendCommand('SET_MODE_MANUAL');
          this.showToast('Switched to Manual Irrigation Mode', 'info');
          this.loadInitialData();
        } catch (err) {
          this.showToast(`Error: ${err.message}`, 'error');
        }
      });
    }

    // Emergency Stop
    const btnEmergency = document.getElementById('btnEmergencyStop');
    if (btnEmergency) {
      btnEmergency.addEventListener('click', async () => {
        if (confirm('ENGAGE EMERGENCY STOP? All watering will cease immediately.')) {
          try {
            await window.api.sendCommand('EMERGENCY_STOP');
            this.showToast('🚨 EMERGENCY STOP ACTIVATED!', 'error');
            this.loadInitialData();
          } catch (err) {
            this.showToast(`Error: ${err.message}`, 'error');
          }
        }
      });
    }
  }

  /* ============================================================================
     DEMO MODE & PRESET SCENARIOS
     ============================================================================ */
  setupDemoMode() {
    const demoToggle = document.getElementById('demoModeToggle');
    const demoBanner = document.getElementById('demoBanner');

    if (demoToggle) {
      demoToggle.addEventListener('change', (e) => {
        this.isDemoMode = e.target.checked;
        if (demoBanner) {
          demoBanner.style.display = this.isDemoMode ? 'flex' : 'none';
        }
        if (this.isDemoMode) {
          this.showToast('Demo Mode Enabled: Simulated Telemetry Active', 'warning');
        } else {
          this.showToast('Demo Mode Disabled: Listening to Live Hardware', 'info');
        }
      });
    }

    // Scenario Trigger Buttons
    document.querySelectorAll('.btn-scenario').forEach(btn => {
      btn.addEventListener('click', async () => {
        const scenarioNum = parseInt(btn.getAttribute('data-scenario'));
        try {
          const res = await window.api.triggerScenario(scenarioNum);
          this.showToast(`Test Scenario #${scenarioNum} applied!`, 'info');
          await this.loadInitialData();
        } catch (err) {
          this.showToast(`Failed scenario: ${err.message}`, 'error');
        }
      });
    });
  }

  /* ============================================================================
     WATERING HISTORY & CSV EXPORT
     ============================================================================ */
  setupHistoryFilters() {
    const modeSelect = document.getElementById('historyModeFilter');
    if (modeSelect) {
      modeSelect.addEventListener('change', () => {
        this.historyPage = 0;
        this.loadWateringHistory();
      });
    }

    const btnExport = document.getElementById('btnExportCsv');
    if (btnExport) {
      btnExport.addEventListener('click', () => {
        window.location.href = window.api.getHistoryExportUrl();
      });
    }
  }

  async loadWateringHistory() {
    const tbody = document.getElementById('historyFullTableBody');
    if (!tbody) return;

    const mode = document.getElementById('historyModeFilter')?.value || null;
    const offset = this.historyPage * this.historyLimit;

    try {
      const data = await window.api.getWateringHistory(this.historyLimit, offset, mode);
      this.updateElementText('historyTotalCountText', `Total Events: ${data.total_count}`);
      this.updateElementText('historyTotalWaterText', `Total Water Used: ${data.total_estimated_water_liters.toFixed(2)} Liters`);

      if (!data.events.length) {
        tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:24px; color:var(--text-muted);">No watering history records found.</td></tr>`;
        return;
      }

      tbody.innerHTML = data.events.map(ev => `
        <tr>
          <td><strong>#${ev.id}</strong></td>
          <td>${new Date(ev.start_time).toLocaleString()}</td>
          <td>${ev.end_time ? new Date(ev.end_time).toLocaleTimeString() : 'In Progress'}</td>
          <td><span class="badge ${ev.irrigation_mode.toLowerCase()}">${ev.irrigation_mode}</span></td>
          <td>${ev.moisture_before.toFixed(1)}% → ${ev.moisture_after ? ev.moisture_after.toFixed(1) + '%' : '–'}</td>
          <td><span class="badge ${ev.status === 'COMPLETED' ? 'completed' : 'danger'}">${ev.status}</span></td>
          <td><strong>${ev.estimated_water_liters.toFixed(2)} L</strong></td>
        </tr>
      `).join('');
    } catch (err) {
      this.showToast('Failed to load watering history', 'error');
    }
  }

  /* ============================================================================
     PLANT MANAGEMENT
     ============================================================================ */
  setupPlantManagement() {
    const btnOpenModal = document.getElementById('btnOpenAddPlantModal');
    const modal = document.getElementById('plantModalOverlay');
    const btnCloseModal = document.getElementById('btnClosePlantModal');
    const form = document.getElementById('addPlantForm');

    if (btnOpenModal && modal) {
      btnOpenModal.addEventListener('click', () => modal.classList.add('active'));
    }
    if (btnCloseModal && modal) {
      btnCloseModal.addEventListener('click', () => modal.classList.remove('active'));
    }

    if (form) {
      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const plantData = {
          name: document.getElementById('plantNameInput').value,
          plant_type: document.getElementById('plantTypeInput').value,
          location: document.getElementById('plantLocationInput').value,
          preferred_moisture_min: parseFloat(document.getElementById('plantMinMoistureInput').value),
          preferred_moisture_max: parseFloat(document.getElementById('plantMaxMoistureInput').value),
          irrigation_threshold: parseFloat(document.getElementById('plantThresholdInput').value),
          notes: document.getElementById('plantNotesInput').value,
        };

        try {
          await window.api.createPlant(plantData);
          this.showToast(`Plant '${plantData.name}' created!`, 'info');
          modal.classList.remove('active');
          form.reset();
          this.loadPlants();
        } catch (err) {
          this.showToast(`Error: ${err.message}`, 'error');
        }
      });
    }
  }

  async loadPlants() {
    const grid = document.getElementById('plantsGridContainer');
    if (!grid) return;

    try {
      const plants = await window.api.getPlants();
      if (!plants.length) {
        grid.innerHTML = `<div style="grid-column: 1/-1; text-align:center; padding:32px; color:var(--text-muted);">No plants in the garden collection yet. Click "Add New Plant" above.</div>`;
        return;
      }

      grid.innerHTML = plants.map(p => `
        <div class="plant-card">
          <div>
            <div class="plant-header">
              <div>
                <h3 class="plant-title">${p.name}</h3>
                <span class="plant-species">${p.plant_type}</span>
              </div>
              <span class="badge auto">📍 ${p.location}</span>
            </div>
            <div class="plant-details">
              <div class="plant-detail-row">
                <span style="color:var(--text-muted);">Preferred Moisture:</span>
                <strong>${p.preferred_moisture_min}% – ${p.preferred_moisture_max}%</strong>
              </div>
              <div class="plant-detail-row">
                <span style="color:var(--text-muted);">Irrigation Threshold:</span>
                <strong style="color:#ef4444;">${p.irrigation_threshold}%</strong>
              </div>
            </div>
            ${p.notes ? `<p style="font-size:12px; color:var(--text-muted); margin-top:8px;">${p.notes}</p>` : ''}
          </div>
          <div style="margin-top:16px; display:flex; justify-content:flex-end;">
            <button class="btn btn-secondary" style="padding:6px 12px; font-size:12px; color:#ef4444;" onclick="window.deletePlantItem(${p.id})">Delete</button>
          </div>
        </div>
      `).join('');
    } catch (err) {
      this.showToast('Could not load plant collection', 'error');
    }
  }

  /* ============================================================================
     SETTINGS
     ============================================================================ */
  setupSettingsForm() {
    const form = document.getElementById('settingsForm');
    if (!form) return;

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const payload = {
        device_name: document.getElementById('settingDeviceName').value,
        moisture_threshold: parseFloat(document.getElementById('settingThreshold').value),
        watering_duration_seconds: parseInt(document.getElementById('settingDuration').value),
        minimum_interval_seconds: parseInt(document.getElementById('settingInterval').value),
        max_watering_duration_seconds: parseInt(document.getElementById('settingMaxDuration').value),
        automatic_mode: document.getElementById('settingAutoMode').checked,
        dry_adc: parseInt(document.getElementById('settingDryAdc').value),
        wet_adc: parseInt(document.getElementById('settingWetAdc').value),
      };

      try {
        await window.api.updateSettings(payload);
        this.showToast('Irrigation and calibration settings saved successfully!', 'info');
        this.loadSettings();
      } catch (err) {
        this.showToast(`Failed to update settings: ${err.message}`, 'error');
      }
    });
  }

  async loadSettings() {
    try {
      const s = await window.api.getSettings();
      document.getElementById('settingDeviceName').value = s.device_name;
      document.getElementById('settingThreshold').value = s.moisture_threshold;
      document.getElementById('settingDuration').value = s.watering_duration_seconds;
      document.getElementById('settingInterval').value = s.minimum_interval_seconds;
      document.getElementById('settingMaxDuration').value = s.max_watering_duration_seconds;
      document.getElementById('settingAutoMode').checked = s.automatic_mode;
      document.getElementById('settingDryAdc').value = s.dry_adc;
      document.getElementById('settingWetAdc').value = s.wet_adc;
    } catch (_) {}
  }

  /* ============================================================================
     ALERTS
     ============================================================================ */
  async loadAlerts() {
    const container = document.getElementById('allAlertsList');
    if (!container) return;

    try {
      const alerts = await window.api.getAlerts(false);
      if (!alerts.length) {
        container.innerHTML = `<div style="text-align:center; padding:32px; color:var(--text-muted);">No alerts logged. System is operating normally.</div>`;
        return;
      }

      container.innerHTML = alerts.map(al => `
        <div style="background:white; border-radius:var(--radius-md); padding:16px; margin-bottom:12px; border:1px solid var(--border-subtle); display:flex; justify-content:space-between; align-items:center;">
          <div>
            <div style="display:flex; align-items:center; gap:8px; margin-bottom:4px;">
              <span class="badge ${al.severity === 'danger' ? 'danger' : 'auto'}">${al.alert_type}</span>
              <span style="font-size:12px; color:var(--text-muted);">${new Date(al.created_at).toLocaleString()}</span>
              ${al.resolved_at ? `<span class="badge completed">Resolved</span>` : `<span class="badge danger">Active</span>`}
            </div>
            <p style="font-size:13.5px; color:var(--text-main); margin:0;">${al.message}</p>
          </div>
          ${!al.resolved_at ? `
            <button class="btn btn-secondary" style="padding:6px 14px; font-size:12px;" onclick="window.api.resolveAlert(${al.id}).then(() => window.location.reload())">Resolve</button>
          ` : ''}
        </div>
      `).join('');
    } catch (_) {}
  }

  /* ============================================================================
     UTILITIES & HELPERS
     ============================================================================ */
  updateElementText(id, text) {
    const el = document.getElementById(id);
    if (el) el.innerText = text;
  }

  showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    const icon = type === 'error' ? '❌' : type === 'warning' ? '⚠️' : '✅';
    toast.innerHTML = `<span>${icon}</span> <span>${message}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateX(100%)';
      toast.style.transition = 'all 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }
}

// Global hook for plant delete
window.deletePlantItem = async function(plantId) {
  if (confirm('Delete this plant record?')) {
    try {
      await window.api.deletePlant(plantId);
      window.location.reload();
    } catch (e) {
      alert(e.message);
    }
  }
};
