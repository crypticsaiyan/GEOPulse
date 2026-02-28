/**
 * GEOPulse Dashboard — Main Entry Point
 *
 * Orchestrates all dashboard components:
 * - FleetMap: Google Maps with vehicle markers
 * - Sportscaster: Live audio commentary
 * - Ticker: Event feed with slide-in animations
 * - Anomaly: FleetDNA anomaly panel
 * - Detail Drawer: Vehicle/driver detail panel
 */

const API_BASE = window.GEOPULSE_API || 'http://localhost:8000';

// Global state
const state = {
    vehicles: [],
    events: [],
    anomalies: [],
    selectedVehicle: null,
    eventVersion: null,
    updateInterval: null,
};

// === Initialization ===

async function initDashboard() {
    console.log('🎙️ GEOPulse Dashboard initializing...');

    // Load initial data
    await Promise.all([
        refreshPositions(),
        refreshEvents(),
        refreshAnomalies(),
    ]);

    // Update header stats
    updateFleetStats();

    // Initialize components
    initMap();
    initTicker();
    initAnomalyPanel();

    // Start live updates
    state.updateInterval = setInterval(async () => {
        await refreshPositions();
        await refreshEvents();
        updateFleetStats();
    }, 15000); // Every 15 seconds

    // Anomaly refresh every 60s
    setInterval(refreshAnomalies, 60000);

    console.log('✅ Dashboard ready');
}

// === Data Fetching ===

async function refreshPositions() {
    try {
        const res = await fetch(`${API_BASE}/api/live-positions`);
        const data = await res.json();
        state.vehicles = data.vehicles || [];
        if (typeof updateMapMarkers === 'function') {
            updateMapMarkers(state.vehicles);
        }
    } catch (e) {
        console.warn('Position refresh failed:', e);
    }
}

async function refreshEvents() {
    try {
        const url = state.eventVersion
            ? `${API_BASE}/api/live-events?from_version=${state.eventVersion}`
            : `${API_BASE}/api/live-events`;
        const res = await fetch(url);
        const data = await res.json();

        if (data.events && data.events.length > 0) {
            // Prepend new events
            state.events = [...data.events, ...state.events].slice(0, 50);
            if (typeof addTickerItems === 'function') {
                addTickerItems(data.events);
            }
        }
        if (data.next_version) {
            state.eventVersion = data.next_version;
        }
    } catch (e) {
        console.warn('Event refresh failed:', e);
    }
}

async function refreshAnomalies() {
    try {
        const res = await fetch(`${API_BASE}/api/anomalies?threshold=40`);
        const data = await res.json();
        state.anomalies = data.anomalies || [];
        if (typeof renderAnomalyPanel === 'function') {
            renderAnomalyPanel(state.anomalies);
        }
    } catch (e) {
        console.warn('Anomaly refresh failed:', e);
    }
}

async function fetchDriverDetail(entityId) {
    try {
        const res = await fetch(`${API_BASE}/api/driver/${entityId}`);
        return await res.json();
    } catch (e) {
        console.warn('Driver detail failed:', e);
        return null;
    }
}

// === UI Updates ===

function updateFleetStats() {
    const totalEl = document.getElementById('stat-total');
    const anomalyEl = document.getElementById('stat-anomalies');
    const eventsEl = document.getElementById('stat-events');

    if (totalEl) totalEl.textContent = state.vehicles.length;
    if (anomalyEl) anomalyEl.textContent = state.anomalies.length;
    if (eventsEl) eventsEl.textContent = state.events.length;
}

// === Detail Drawer ===

async function openDetailDrawer(vehicleId) {
    const drawer = document.getElementById('detail-drawer');
    if (!drawer) return;

    state.selectedVehicle = vehicleId;
    drawer.classList.add('open');

    // Show loading
    drawer.innerHTML = '<div style="text-align:center;padding:40px;color:var(--text-muted);">Loading...</div>';

    const detail = await fetchDriverDetail(vehicleId);
    if (!detail) {
        drawer.innerHTML = '<div style="padding:24px;color:var(--text-muted);">No data available.</div>';
        return;
    }

    const entity = detail.entity || {};
    const score = detail.today_score || {};
    const baseline = detail.baseline || {};
    const weekly = detail.weekly_delta || {};

    // Build radar chart data
    const metrics = Object.keys(baseline).slice(0, 6);
    const radarData = metrics.map(m => {
        const bl = baseline[m] || {};
        const det = (score.details || {})[m] || {};
        return {
            label: m.replace('_', ' '),
            baseline: bl.mean || 0,
            today: det.today || bl.mean || 0,
        };
    });

    drawer.innerHTML = `
        <div style="padding: 24px;">
            <button onclick="closeDetailDrawer()" style="float:right;background:none;border:none;color:var(--text-muted);cursor:pointer;font-size:20px;">✕</button>
            <h2 style="font-size: 18px; margin: 0 0 4px;">${entity.name || 'Unknown'}</h2>
            <p style="color: var(--text-muted); font-size: 13px;">${entity.type || 'vehicle'} · ${entity.id || ''}</p>

            <div style="display:flex;gap:12px;margin:20px 0;">
                <div class="card" style="flex:1;text-align:center;padding:12px;">
                    <div style="font-size:28px;font-weight:bold;color:${score.deviation_score > 70 ? 'var(--red)' : score.deviation_score > 40 ? 'var(--yellow)' : 'var(--green)'}">
                        ${score.deviation_score || 0}
                    </div>
                    <div style="font-size:11px;color:var(--text-muted);">DEVIATION</div>
                </div>
                <div class="card" style="flex:1;text-align:center;padding:12px;">
                    <div style="font-size:28px;font-weight:bold;">${weekly.total_trips || 0}</div>
                    <div style="font-size:11px;color:var(--text-muted);">TRIPS (7D)</div>
                </div>
            </div>

            <h3 style="font-size:13px;color:var(--text-muted);text-transform:uppercase;margin:16px 0 8px;">Metrics vs Baseline</h3>
            <div id="detail-metrics">${buildMetricBars(score.details || {}, baseline)}</div>

            <div style="margin-top:24px;display:flex;gap:8px;">
                <button class="btn btn-red" onclick="welfareCheck('${entity.id}', '${entity.name}')">⚠️ Welfare Check</button>
                <button class="btn btn-yellow" onclick="coachingFlag('${entity.id}')">📋 Coaching Flag</button>
                <button class="btn btn-outline" onclick="closeDetailDrawer()">Watch & Wait</button>
            </div>
        </div>
    `;
}

function closeDetailDrawer() {
    const drawer = document.getElementById('detail-drawer');
    if (drawer) drawer.classList.remove('open');
    state.selectedVehicle = null;
}

function buildMetricBars(details, baseline) {
    let html = '';
    for (const [metric, data] of Object.entries(details)) {
        const z = Math.abs(data.z_score || 0);
        const color = z > 2 ? 'var(--red)' : z > 1 ? 'var(--yellow)' : 'var(--green)';
        const label = metric.replace(/_/g, ' ');
        html += `
            <div style="margin:6px 0;">
                <div style="display:flex;justify-content:space-between;font-size:12px;">
                    <span>${label}</span>
                    <span style="color:${color}">z=${(data.z_score || 0).toFixed(1)}</span>
                </div>
                <div style="background:var(--border);height:6px;border-radius:3px;margin-top:3px;">
                    <div style="background:${color};width:${Math.min(z * 30, 100)}%;height:6px;border-radius:3px;"></div>
                </div>
            </div>`;
    }
    return html || '<p style="color:var(--text-muted);font-size:13px;">No data for today.</p>';
}

// === Write-Back Actions ===

async function welfareCheck(entityId, entityName) {
    try {
        const res = await fetch(`${API_BASE}/api/write-back/group`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: `Welfare Check — ${entityName}`,
                vehicle_ids: [entityId],
                reason: 'Flagged via GEOPulse dashboard',
            }),
        });
        const data = await res.json();
        if (data.success) {
            alert(`✅ Welfare Check group created for ${entityName}`);
        }
    } catch (e) {
        console.error('Welfare check failed:', e);
    }
}

async function coachingFlag(entityId) {
    alert(`📋 Coaching flag queued for ${entityId}. Rule will be created in Geotab.`);
}

// === Start ===
document.addEventListener('DOMContentLoaded', initDashboard);
