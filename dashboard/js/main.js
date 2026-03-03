/**
 * GEOPulse Dashboard — Unified JavaScript
 * 
 * Handles: Leaflet map, live data polling, sportscaster,
 * event ticker, anomaly panel, fleet rankings, detail drawer.
 * 
 * All data comes from the FastAPI backend at /api/*
 */

const API = '';  // Same origin — served by FastAPI

// === GLOBAL STATE ===
const state = {
  vehicles: [],
  events: [],
  anomalies: [],
  rankings: [],
  eventVersion: null,
  map: null,
  markers: {},
  heatLayer: null,
  heatmapVisible: true,
  trailsVisible: true,
  tripTrails: [],
  vehicleTrails: {},
  audioMuted: false,
  selectedId: null,
  lastDataTime: null,
  zoneMode: false,
  zoneBounds: null,
  zoneRect: null,
  zoneStartLatlng: null,
};

// === INITIALIZATION ===
document.addEventListener('DOMContentLoaded', async () => {
  startClock();
  initMap();
  initKeyboard();
  initStatusBar();
  initCollapsiblePanels();
  await loadAllData();
  startLiveUpdates();
  startFreshnessTracker();
  initResizers();
});

// === CLOCK ===
function startClock() {
  const el = document.getElementById('live-clock');
  if (!el) return;
  const tick = () => {
    const now = new Date();
    el.textContent = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
  };
  tick();
  setInterval(tick, 1000);
}

// === MAP (Leaflet — dark theme, no API key) ===
function initMap() {
  state.map = L.map('map', {
    center: [43.65, -79.38],  // Toronto area (Geotab HQ)
    zoom: 10,
    zoomControl: false,
    attributionControl: false,
    dragging: true, // we will toggle this during zone selection
  });
  
  L.control.zoom({ position: 'bottomright' }).addTo(state.map);

  // Dark CartoDB tile layer for premium dark-mode look
  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    maxZoom: 19,
    subdomains: 'abcd',
  }).addTo(state.map);

  // Re-center after data loads
  setTimeout(() => state.map.invalidateSize(), 200);
}

function updateMap(vehicles) {
  if (!state.map) return;
  const activeIds = new Set();

  vehicles.forEach(v => {
    if (!v.latitude || !v.longitude) return;
    activeIds.add(v.device_id);
    const latlng = [v.latitude, v.longitude];
    const score = v.deviation_score || 0;
    const color = score > 70 ? '#F85149' : score > 40 ? '#D29922' : '#3FB950';
    const isDriving = v.is_driving;
    const isAnomaly = score > 60;
    const bearing = v.bearing || 0;

    if (state.markers[v.device_id]) {
      // Smooth position update + trail
      const oldLatLng = state.markers[v.device_id].getLatLng();
      state.markers[v.device_id].setLatLng(latlng);

      // Add to vehicle trail
      if (state.trailsVisible && isDriving) {
        if (!state.vehicleTrails[v.device_id]) state.vehicleTrails[v.device_id] = [];
        state.vehicleTrails[v.device_id].push(latlng);
        if (state.vehicleTrails[v.device_id].length > 10) {
          state.vehicleTrails[v.device_id].shift();
        }
      }

      const iconEl = state.markers[v.device_id].getElement();
      if (iconEl) {
        const inner = iconEl.querySelector('.marker-inner');
        if (inner) {
          inner.style.background = 'transparent';
          inner.style.color = color;
          inner.className = `marker-inner arrow-only ${isDriving ? 'driving' : ''} ${isAnomaly ? 'anomaly' : ''}`;
        }
        // Rotate arrow based on bearing
        const arrow = iconEl.querySelector('.marker-arrow');
        if (arrow) {
          arrow.style.transform = `rotate(${bearing}deg)`;
          arrow.style.opacity = '0.9';
          arrow.style.filter = isAnomaly
            ? `drop-shadow(0 0 5px ${color}) drop-shadow(0 0 10px ${color})`
            : isDriving
              ? `drop-shadow(0 0 4px ${color})`
              : `drop-shadow(0 0 2px ${color})`;
          const polygon = arrow.querySelector('polygon');
          if (polygon) {
            polygon.setAttribute('fill', color);
            polygon.setAttribute('stroke', color);
          }
        }
      }
    } else {
      // Create directional arrow marker
      const icon = L.divIcon({
        className: 'vehicle-marker',
        html: `<div class="marker-inner arrow-only ${isDriving ? 'driving' : ''} ${isAnomaly ? 'anomaly' : ''}" style="background:transparent;color:${color};">
          <svg class="marker-arrow" width="26" height="26" viewBox="0 0 18 18" style="position:absolute;top:0;left:0;transform:rotate(${bearing}deg);opacity:0.9;filter:${isAnomaly ? `drop-shadow(0 0 5px ${color}) drop-shadow(0 0 10px ${color})` : isDriving ? `drop-shadow(0 0 4px ${color})` : `drop-shadow(0 0 2px ${color})`};">
            <polygon points="9,1 5,14 9,11 13,14" fill="${color}" stroke="rgba(255,255,255,0.3)" stroke-width="0.5"/>
          </svg>
        </div>`,
        iconSize: [26, 26],
        iconAnchor: [13, 13],
      });

      const marker = L.marker(latlng, { icon }).addTo(state.map);
      
      const speedText = v.speed > 0 ? `${Math.round(v.speed)} km/h` : 'Stopped';
      marker.bindTooltip(`
        <strong>${v.device_name}</strong><br>
        ${speedText} · Bearing: ${bearing}°<br>
        Deviation: <span style="color:${color};font-weight:700;">${score}/100</span>
      `, { className: 'marker-tooltip', direction: 'top', offset: [0, -12] });

      marker.on('click', () => openDrawer(v.device_id));
      state.markers[v.device_id] = marker;
    }
  });

  // Remove old markers
  Object.keys(state.markers).forEach(id => {
    if (!activeIds.has(id)) {
      state.map.removeLayer(state.markers[id]);
      delete state.markers[id];
    }
  });

  // Draw vehicle trails
  drawVehicleTrails();
}

function fitFleet() {
  if (!state.map || Object.keys(state.markers).length === 0) return;
  const group = L.featureGroup(Object.values(state.markers));
  state.map.fitBounds(group.getBounds().pad(0.1));
}

// === HEATMAP LAYER ===
function updateHeatmap(events) {
  if (!state.map || typeof L.heatLayer === 'undefined') return;

  // Remove old layer
  if (state.heatLayer) {
    state.map.removeLayer(state.heatLayer);
    state.heatLayer = null;
  }

  // Build heat points from events with coordinates
  const heatPoints = events
    .filter(e => e.latitude && e.longitude)
    .map(e => {
      const ruleName = (e.rule_name || '').toLowerCase();
      const intensity = ruleName.includes('harsh') || ruleName.includes('collision') ? 1.0 :
                       ruleName.includes('speed') ? 0.7 : 0.4;
      return [e.latitude, e.longitude, intensity];
    });

  if (heatPoints.length > 0) {
    state.heatLayer = L.heatLayer(heatPoints, {
      radius: 25,
      blur: 15,
      maxZoom: 15,
      gradient: { 0.2: '#388BFD', 0.5: '#D29922', 0.8: '#F85149', 1.0: '#FF0000' },
    });

    if (state.heatmapVisible) {
      state.heatLayer.addTo(state.map);
    }
  }
}

// === TRIP TRAILS ===
function clearTripTrails() {
  state.tripTrails.forEach(trail => state.map.removeLayer(trail));
  state.tripTrails = [];
}

function addTripTrail(coordinates, color = '#388BFD') {
  if (!state.map || !coordinates || coordinates.length < 2) return;
  const polyline = L.polyline(coordinates, {
    color,
    weight: 3,
    opacity: 0.7,
    smoothFactor: 1,
    dashArray: '8, 6',
  }).addTo(state.map);
  state.tripTrails.push(polyline);
  return polyline;
}

// === DATA LOADING ===
async function loadAllData() {
  await Promise.all([
    fetchPositions(),
    fetchEvents(),
    fetchAnomalies(),
  ]);
  updateStats();
  fitFleet();

  // Auto-generate first commentary
  setTimeout(requestCommentary, 2000);
}

async function fetchPositions() {
  try {
    const res = await fetch(`${API}/api/live-positions`);
    const data = await res.json();
    state.vehicles = data.vehicles || [];
    
    // Filter by zone if active
    let displayVehicles = state.vehicles;
    if (state.zoneBounds) {
      displayVehicles = displayVehicles.filter(v => 
        v.latitude && v.longitude && state.zoneBounds.contains([v.latitude, v.longitude])
      );
    }
    
    updateMap(displayVehicles);
    renderRankings(displayVehicles);
  } catch (e) {
    console.warn('Position fetch failed:', e);
  }
}

async function fetchEvents() {
  try {
    const url = state.eventVersion
      ? `${API}/api/live-events?from_version=${state.eventVersion}`
      : `${API}/api/live-events`;
    const res = await fetch(url);
    const data = await res.json();

    if (data.events && data.events.length > 0) {
      // Merge, deduplicate by event ID, sort newest-first
      const seen = new Set(state.events.map(e => e.id));
      const newUnique = data.events.filter(e => e.id && !seen.has(e.id));
      state.events = [...newUnique, ...state.events]
        .sort((a, b) => new Date(b.active_from) - new Date(a.active_from))
        .slice(0, 100);
    }

    // Apply zone filter for heatmap (all events, not capped)
    const heatmapEvents = state.zoneBounds
      ? state.events.filter(e => !e.latitude || !e.longitude || state.zoneBounds.contains([e.latitude, e.longitude]))
      : state.events;
    updateHeatmap(heatmapEvents);

    // Build ticker with max 3 events per vehicle so one active vehicle doesn't dominate
    const perVehicleCount = {};
    const tickerEvents = [];
    for (const e of heatmapEvents) {
      const vid = e.device_id || e.device_name || 'unknown';
      perVehicleCount[vid] = (perVehicleCount[vid] || 0) + 1;
      if (perVehicleCount[vid] <= 3) tickerEvents.push(e);
      if (tickerEvents.length >= 20) break;
    }
    renderTicker(tickerEvents);

    if (data.next_version) state.eventVersion = data.next_version;
  } catch (e) {
    console.warn('Events fetch failed:', e);
  }
}

async function fetchAnomalies() {
  try {
    const res = await fetch(`${API}/api/anomalies?threshold=60`);
    const data = await res.json();
    state.anomalies = data.anomalies || [];
    
    // We can't strictly filter anomalies by GPS if they don't return it
    // But we could filter them by whether their device is in the zone bounds
    let displayAnomalies = state.anomalies;
    if (state.zoneBounds) {
      const activeDeviceIds = new Set(
        state.vehicles
          .filter(v => v.latitude && v.longitude && state.zoneBounds.contains([v.latitude, v.longitude]))
          .map(v => v.device_id)
      );
      displayAnomalies = displayAnomalies.filter(a => activeDeviceIds.has(a.entity_id));
    }
    
    renderAnomalies(displayAnomalies);
  } catch (e) {
    console.warn('Anomalies fetch failed:', e);
  }
}

function startLiveUpdates() {
  setInterval(async () => {
    await fetchPositions();
    await fetchEvents();
    updateStats();
  }, 5000);

  setInterval(fetchAnomalies, 60000);

  // Auto-refresh broadcast commentary every 90s with latest events
  const BROADCAST_INTERVAL = 90;
  setInterval(requestCommentary, BROADCAST_INTERVAL * 1000);
  startBroadcastCountdown(BROADCAST_INTERVAL);
}

// === BROADCAST COUNTDOWN ===
let _countdownSec = 0;
let _countdownInterval = null;

function startBroadcastCountdown(totalSec) {
  _countdownSec = totalSec;
  const timerEl = document.getElementById('countdown-timer');
  if (_countdownInterval) clearInterval(_countdownInterval);
  _countdownInterval = setInterval(() => {
    _countdownSec--;
    if (_countdownSec <= 0) _countdownSec = totalSec;
    if (timerEl) {
      const m = String(Math.floor(_countdownSec / 60)).padStart(2, '0');
      const s = String(_countdownSec % 60).padStart(2, '0');
      timerEl.textContent = `${m}:${s}`;
    }
  }, 1000);
}

function resetBroadcastCountdown() {
  _countdownSec = 90;
}

// === STATS ===
function updateStats() {
  let displayVehicles = state.vehicles;
  let displayAnomalies = state.anomalies;
  let displayEvents = state.events;

  if (state.zoneBounds) {
    const activeDeviceIds = new Set(
      state.vehicles
        .filter(v => v.latitude && v.longitude && state.zoneBounds.contains([v.latitude, v.longitude]))
        .map(v => v.device_id)
    );
    displayVehicles = state.vehicles.filter(v => activeDeviceIds.has(v.device_id));
    displayAnomalies = state.anomalies.filter(a => activeDeviceIds.has(a.entity_id));
    displayEvents = state.events.filter(e => !e.latitude || !e.longitude || state.zoneBounds.contains([e.latitude, e.longitude]));
  }

  setText('stat-total', displayVehicles.length);
  setText('stat-anomalies', displayAnomalies.length);
  setText('stat-events', displayEvents.length);
  state.lastDataTime = Date.now();
  updateStatusBar();
}

function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

// === TICKER ===
function renderTicker(events) {
  const list = document.getElementById('ticker-list');
  if (!list) return;

  document.getElementById('event-count').textContent = events.length;

  if (events.length === 0) {
    list.innerHTML = '<div class="ticker-empty">No events yet</div>';
    return;
  }

  list.innerHTML = events.slice(0, 20).map(e => {
    const time = formatTime(e.active_from);
    const color = getEventColor(e.rule_name || '');
    const icon = getEventIcon(e.rule_name || '');
    const vehicleName = e.device_name || 'Unknown Vehicle';
    const driverTag = (e.driver_name && e.driver_name !== e.device_name)
      ? ` <span class="ticker-driver">(${e.driver_name})</span>` : '';
    const rule = truncate(e.rule_name && e.rule_name !== 'Unknown Rule' ? e.rule_name : 'Event', 34);

    return `<div class="ticker-item">
      <span class="ticker-time">${time}</span>
      <span class="ticker-icon">${icon}</span>
      <span class="ticker-bar" style="background:${color};"></span>
      <span class="ticker-name">${vehicleName}${driverTag}</span>
      <span class="ticker-rule">${rule}</span>
    </div>`;
  }).join('');
}

// === ANOMALIES ===
function renderAnomalies(anomalies) {
  const panel = document.getElementById('anomaly-panel');
  const list = document.getElementById('anomaly-list');
  const count = document.getElementById('anomaly-count');
  if (!list) return;

  count.textContent = anomalies.length;

  if (anomalies.length > 0) {
    panel.classList.add('has-anomalies');
  } else {
    panel.classList.remove('has-anomalies');
    list.innerHTML = '<div class="ticker-empty">✅ No anomalies detected</div>';
    return;
  }

  list.innerHTML = anomalies.slice(0, 8).map(a => {
    const score = a.deviation_score || 0;
    const color = score > 70 ? 'var(--red)' : score > 40 ? 'var(--yellow)' : 'var(--green)';
    const icon = score > 70 ? '🔴' : score > 40 ? '🟡' : '🟢';
    
    return `<div class="anomaly-item" onclick="openDrawer('${a.entity_id}')">
      <div class="anomaly-item-header">
        <span class="anomaly-name">${icon} ${a.name || 'Unknown'}</span>
        <span class="anomaly-score" style="color:${color};">${score}</span>
      </div>
      <div class="anomaly-meta">${a.anomaly_type || 'unknown'} · confidence ${a.confidence || 0}%</div>
      <div class="anomaly-actions">
        <button class="btn btn-red" onclick="event.stopPropagation();welfareCheck('${a.entity_id}','${a.name}')">⚠️ Welfare</button>
        <button class="btn btn-outline" onclick="event.stopPropagation();openDrawer('${a.entity_id}')">Details →</button>
      </div>
    </div>`;
  }).join('');
}

// === RANKINGS ===
function renderRankings(vehicles) {
  const list = document.getElementById('rankings-list');
  if (!list) return;

  // Sort by deviation (most normal first = best performers)
  const sorted = [...vehicles]
    .filter(v => v.device_name)
    .sort((a, b) => (a.deviation_score || 0) - (b.deviation_score || 0));

  if (sorted.length === 0) {
    list.innerHTML = '<div class="ticker-empty">No rankings yet</div>';
    return;
  }

  list.innerHTML = sorted.slice(0, 10).map((v, i) => {
    const score = v.deviation_score || 0;
    const color = score > 70 ? 'var(--red)' : score > 40 ? 'var(--yellow)' : 'var(--green)';
    const medal = i === 0 ? '🥇' : i === 1 ? '🥈' : i === 2 ? '🥉' : '';

    return `<div class="rank-item" onclick="openDrawer('${v.device_id}')">
      <span class="rank-pos">${medal || '#' + (i + 1)}</span>
      <span class="rank-name">${v.device_name}</span>
      <div class="rank-bar-container">
        <div class="rank-bar" style="width:${Math.min(score, 100)}%;background:${color};"></div>
      </div>
      <span class="rank-score" style="color:${color};">${score}</span>
    </div>`;
  }).join('');
}

// === SPORTSCASTER ===
async function requestCommentary() {
  const btn = document.getElementById('btn-refresh-commentary');
  if (btn) btn.style.animation = 'spin 1s linear infinite';

  try {
    // Filter by zone if active
    let commentaryEvents = state.events;
    let commentaryAnomalies = state.anomalies;
    let commentaryVehicles = state.vehicles;

    if (state.zoneBounds) {
      const zoneDeviceIds = new Set(
        state.vehicles
          .filter(v => v.latitude && v.longitude && state.zoneBounds.contains([v.latitude, v.longitude]))
          .map(v => v.device_id)
      );
      commentaryEvents = state.events.filter(e =>
        !e.device_id || zoneDeviceIds.has(e.device_id)
      );
      commentaryAnomalies = state.anomalies.filter(a => zoneDeviceIds.has(a.entity_id));
      commentaryVehicles = state.vehicles.filter(v => zoneDeviceIds.has(v.device_id));
    }

    const recentEvents = commentaryEvents.slice(0, 10);

    // Build rich anomaly context
    let anomalyContext = '';
    if (commentaryAnomalies.length > 0) {
      const topAnomalies = commentaryAnomalies.slice(0, 3);
      const anomalyDetails = topAnomalies.map(a =>
        `${a.name || a.entity_id} (deviation: ${a.deviation_score}/100${a.anomaly_type ? ', type: ' + a.anomaly_type : ''})`
      ).join('; ');
      anomalyContext = `${commentaryAnomalies.length} anomalies detected. Top: ${anomalyDetails}.`;
    } else {
      anomalyContext = 'No anomalies — fleet operating within normal behavioral baselines.';
    }

    const zoneContext = state.zoneBounds ? ' [ZONE ACTIVE — reporting on selected area only]' : '';

    // Send richer event payload for better commentary
    const leanEvents = recentEvents.map(e => {
      const obj = {
        device_name: e.device_name || 'Unknown',
        rule_name: e.rule_name || 'event',
        driver_name: e.driver_name || '',
      };
      // Attach deviation score from anomalies if available
      const matchedAnomaly = commentaryAnomalies.find(a => a.entity_id === e.device_id);
      if (matchedAnomaly) obj.deviation_score = matchedAnomaly.deviation_score;
      return obj;
    });

    const movingCount = commentaryVehicles.filter(v => (v.speed || 0) > 0).length;
    const stoppedCount = commentaryVehicles.length - movingCount;

    const res = await fetch(`${API}/api/generate-commentary`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        events: leanEvents,
        context: `${commentaryVehicles.length} vehicles tracked (${movingCount} moving, ${stoppedCount} stopped). ${anomalyContext} ${recentEvents.length} events in the last window.${zoneContext}`,
      }),
    });
    const data = await res.json();

    if (data.text) {
      showCommentary(data.text, data.provider, data.audio_b64 || null);
    }
  } catch (e) {
    showCommentary('Broadcast signal lost. Reconnecting...', 'error');
  }

  if (btn) btn.style.animation = '';
}

function showCommentary(text, provider, audio_b64 = null) {
  const textEl = document.getElementById('commentary-text');
  const metaEl = document.getElementById('commentary-meta');
  const waveform = document.getElementById('waveform');

  // Reset broadcast countdown when new commentary arrives
  resetBroadcastCountdown();

  // Strip markdown and LLM-added wrapper quotes
  let cleanText = text
    .replace(/[*_~`#>]+/g, '')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/^"+|"+$/g, '');  // strip leading/trailing quotes from LLM

  state.lastCommentaryText = cleanText;
  state.lastAudioB64 = audio_b64;

  if (textEl) {
    textEl.style.opacity = '0';
    setTimeout(() => {
      textEl.textContent = `"${cleanText}"`;
      textEl.style.opacity = '1';
    }, 200);
  }

  if (metaEl) {
    const now = new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
    metaEl.innerHTML = `<span class="live-indicator">● LIVE</span> ${now} · via ${provider || 'AI'}`;
  }

  // Kick off audio immediately — use inline base64 if server sent it (no second request)
  if (!state.audioMuted) {
    playCommentaryAudio(cleanText, waveform, audio_b64);
  }
}

// === EMAIL SENDER MULTI ===
async function promptForEmail() {
  const email = prompt("Enter email address to send the current audio summary:");
  if (!email || !email.includes('@')) {
    if (email !== null) alert("Please enter a valid email address.");
    return;
  }
  
  const btn = document.getElementById('btn-mail-commentary');
  const oldText = btn.textContent;
  btn.textContent = '⏳';
  
  try {
    const res = await fetch(`${API}/api/send-mail`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: email,
        summary_text: state.lastCommentaryText || "No summary text generated yet.",
        audio_b64: state.lastAudioB64 || null,
        include_overview: true
      })
    });
    
    const data = await res.json();
    if (res.ok && data.success) {
      alert("Email sent successfully!");
    } else {
      alert("Failed to send email: " + (data.detail || "Unknown error"));
    }
  } catch (err) {
    console.error(err);
    alert("Error sending email.");
  } finally {
    btn.textContent = oldText;
  }
}

// === AUDIO PLAYBACK ===

const globalAudio = new Audio();
let _pendingAudio = null;  // queued when no user gesture yet

// Browsers block audio until the user has clicked something.
// Track this and drain the queue on first interaction.
let _hasGesture = false;
document.addEventListener('click', () => {
  if (!_hasGesture) {
    _hasGesture = true;
    
    // Unlock the global audio element
    globalAudio.play().catch(() => {});
    globalAudio.pause();

    // Prewarm speech synthesis — speak a single space so the browser unlocks it
    // Do NOT call cancel() immediately after — that blocks subsequent speech
    if ('speechSynthesis' in window) {
      const warm = new SpeechSynthesisUtterance(' ');
      warm.volume = 0;
      speechSynthesis.speak(warm);
    }
    // Play anything queued before the first click
    if (_pendingAudio) {
      const { text, waveform, audio_b64 } = _pendingAudio;
      _pendingAudio = null;
      playCommentaryAudio(text, waveform, audio_b64 || null);
    }
  }
}, { once: false });

// In-memory TTS cache: text → blob URL
const ttsCache = new Map();

async function playCommentaryAudio(text, waveform, audio_b64 = null) {
  stopCurrentAudio();

  const cleanText = text
    .replace(/[*_~`#>]+/g, '')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/^"+|"+$/g, '');  // strip LLM-added quotes

  // If no user gesture yet, queue and wait — browser will block any audio
  if (!_hasGesture) {
    _pendingAudio = { text: cleanText, waveform, audio_b64 };
    _prefetchTTS(cleanText);  // pre-warm TTS in background while waiting
    console.log('[GEOPulse audio] Queued audio — waiting for user gesture');
    return;
  }

  if (waveform) waveform.classList.add('active');

  // --- Fast path 1: inline base64 from server ---
  if (audio_b64) {
    try {
      console.log('[GEOPulse audio] Playing inline base64 audio');
      const url = _b64toObjectURL(audio_b64);
      await _playURL(url, waveform, () => URL.revokeObjectURL(url));
      return;
    } catch (e) {
      console.warn('[GEOPulse audio] Inline b64 playback failed, trying fallbacks:', e);
    }
  }

  // --- Fast path 2: previously cached Google TTS ---
  if (ttsCache.has(cleanText)) {
    try {
      console.log('[GEOPulse audio] Playing cached TTS');
      await _playURL(ttsCache.get(cleanText), waveform);
      return;
    } catch (e) {
      console.warn('[GEOPulse audio] Cached TTS playback failed:', e);
      ttsCache.delete(cleanText);
    }
  }

  // --- Fallback: browser speech synthesis (zero network wait) ---
  console.log('[GEOPulse audio] Using browser speech synthesis');
  speakWithBrowser(cleanText, waveform);
  _prefetchTTS(cleanText);
}

function _b64toObjectURL(b64) {
  const byteChars = atob(b64);
  const bytes = new Uint8Array(byteChars.length);
  for (let i = 0; i < byteChars.length; i++) bytes[i] = byteChars.charCodeAt(i);
  return URL.createObjectURL(new Blob([bytes], { type: 'audio/mpeg' }));
}

function _playURL(url, waveform, onEnd) {
  return new Promise((resolve, reject) => {
    globalAudio.src = url;
    globalAudio.onended = () => {
      if (waveform) waveform.classList.remove('active');
      if (onEnd) onEnd();
      resolve();
    };
    globalAudio.onerror = () => { reject(); };
    globalAudio.play().catch(reject);
  });
}

async function _prefetchTTS(text) {
  if (ttsCache.has(text)) return;  // already cached
  try {
    const res = await fetch(`${API}/api/tts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, voice: 'en-US-Journey-D' }),
    });
    if (!res.ok) return;
    const blob = await res.blob();
    // Store as object URL — revoke old entry first to avoid leaks
    const old = ttsCache.get(text);
    if (old) URL.revokeObjectURL(old);
    ttsCache.set(text, URL.createObjectURL(blob));
    // Keep cache small
    if (ttsCache.size > 10) {
      const oldest = ttsCache.keys().next().value;
      URL.revokeObjectURL(ttsCache.get(oldest));
      ttsCache.delete(oldest);
    }
  } catch (e) { /* silent — browser fallback already played */ }
}


function speakWithBrowser(text, waveform) {
  if (!('speechSynthesis' in window)) {
    if (waveform) setTimeout(() => waveform.classList.remove('active'), 5000);
    return;
  }

  speechSynthesis.cancel();

  function _speak() {
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1.08;
    utterance.pitch = 1.0;
    utterance.volume = 1.0;

    const voices = speechSynthesis.getVoices();
    const preferred =
      voices.find(v => v.name === 'Google UK English Male') ||
      voices.find(v => v.name === 'Google US English') ||
      voices.find(v => v.name.includes('Google') && v.lang.startsWith('en')) ||
      voices.find(v => v.name.includes('Daniel')) ||
      voices.find(v => v.lang === 'en-US' && !v.localService) ||
      voices.find(v => v.lang.startsWith('en-US')) ||
      voices.find(v => v.lang.startsWith('en'));
    if (preferred) utterance.voice = preferred;

  utterance.onstart = () => { console.log('[GEOPulse audio] Speech started'); if (waveform) waveform.classList.add('active'); };
    utterance.onend   = () => { console.log('[GEOPulse audio] Speech ended'); if (waveform) waveform.classList.remove('active'); };
    utterance.onerror = (e) => { console.warn('[GEOPulse audio] Speech error:', e.error); if (waveform) waveform.classList.remove('active'); };
    speechSynthesis.speak(utterance);
  }

  // Voices may not be loaded yet on first call — wait for them
  const voices = speechSynthesis.getVoices();
  if (voices.length > 0) {
    _speak();
  } else {
    speechSynthesis.onvoiceschanged = () => {
      speechSynthesis.onvoiceschanged = null;
      _speak();
    };
  }
}

function stopCurrentAudio() {
  globalAudio.pause();
  globalAudio.onended = null;
  globalAudio.onerror = null;

  if ('speechSynthesis' in window) {
    speechSynthesis.cancel();
  }
}

// === DETAIL DRAWER ===
async function openDrawer(entityId) {
  const drawer = document.getElementById('detail-drawer');
  const overlay = document.getElementById('drawer-overlay');
  const content = document.getElementById('drawer-content');
  if (!drawer || !content) return;

  state.selectedId = entityId;
  drawer.classList.add('open');
  overlay.classList.add('active');

  content.innerHTML = `<div style="text-align:center;padding:60px 0;color:var(--text-muted);">
    <div style="font-size:32px;margin-bottom:12px;animation:spin 1s linear infinite;">⟳</div>
    Loading vehicle DNA...
  </div>`;

  try {
    const res = await fetch(`${API}/api/driver/${entityId}`);
    const data = await res.json();
    renderDrawerContent(content, data);
  } catch (e) {
    content.innerHTML = `<div style="padding:24px;color:var(--text-muted);">Failed to load data.</div>`;
  }
}

function closeDrawer() {
  document.getElementById('detail-drawer')?.classList.remove('open');
  document.getElementById('drawer-overlay')?.classList.remove('active');
  state.selectedId = null;
}

function renderDrawerContent(container, data) {
  const entity = data.entity || {};
  const score = data.today_score || {};
  const baseline = data.baseline || {};
  const weekly = data.weekly_delta || {};
  const deviation = score.deviation_score || 0;
  const devColor = deviation > 70 ? 'var(--red)' : deviation > 40 ? 'var(--yellow)' : 'var(--green)';

  // Build metric rows
  const details = score.details || {};
  let metricsHTML = '';
  for (const [metric, d] of Object.entries(details)) {
    const z = Math.abs(d.z_score || 0);
    const mColor = z > 2 ? 'var(--red)' : z > 1 ? 'var(--yellow)' : 'var(--green)';
    const label = metric.replace(/_/g, ' ');
    metricsHTML += `
      <div class="metric-row">
        <span class="metric-label">${label}</span>
        <div class="metric-bar-track">
          <div class="metric-bar-fill" style="width:${Math.min(z * 30, 100)}%;background:${mColor};"></div>
        </div>
        <span class="metric-zscore" style="color:${mColor};">z=${(d.z_score || 0).toFixed(1)}</span>
      </div>`;
  }

  if (!metricsHTML) {
    metricsHTML = '<div style="color:var(--text-muted);font-size:13px;padding:8px 0;">No activity data for today.</div>';
  }

  // Weekly comparison
  const weekComp = weekly.week_vs_baseline || {};
  let weekHTML = '';
  for (const [metric, comp] of Object.entries(weekComp)) {
    const delta = comp.delta_pct || 0;
    const color = Math.abs(delta) < 10 ? 'var(--green)' : delta > 0 ? 'var(--red)' : 'var(--yellow)';
    weekHTML += `
      <div class="metric-row">
        <span class="metric-label">${metric.replace(/_/g, ' ')}</span>
        <span class="metric-zscore" style="color:${color};">${delta > 0 ? '+' : ''}${delta.toFixed(1)}%</span>
      </div>`;
  }

  container.innerHTML = `
    <div class="drawer-header">
      <div>
        <div class="drawer-entity-name">${entity.name || 'Unknown'}</div>
        <div class="drawer-entity-meta">${entity.type || 'vehicle'} · ${entity.id || ''}</div>
      </div>
      <button class="drawer-close" onclick="closeDrawer()">✕</button>
    </div>

    <div class="drawer-score-cards">
      <div class="score-card">
        <div class="score-card-value" style="color:${devColor};">${deviation}</div>
        <div class="score-card-label">Deviation Score</div>
      </div>
      <div class="score-card">
        <div class="score-card-value">${weekly.total_trips || 0}</div>
        <div class="score-card-label">Trips (7 days)</div>
      </div>
      <div class="score-card">
        <div class="score-card-value">${weekly.days_active || 0}</div>
        <div class="score-card-label">Days Active</div>
      </div>
      <div class="score-card">
        <div class="score-card-value">${score.confidence || 0}%</div>
        <div class="score-card-label">Confidence</div>
      </div>
    </div>

    ${Object.keys(baseline).length > 0 ? `
    <div class="drawer-section-title">Baseline Profile (90 days)</div>
    <div class="radar-container">
      <canvas id="radar-chart" width="280" height="280"></canvas>
    </div>` : ''}

    <div class="drawer-section-title">Today vs Baseline</div>
    ${metricsHTML}

    ${weekHTML ? `
    <div class="drawer-section-title">This Week vs Normal</div>
    ${weekHTML}` : ''}

    ${weekly.positive_highlights?.length ? `
    <div class="drawer-section-title">✅ Highlights</div>
    <div style="font-size:13px;color:var(--green);">${weekly.positive_highlights.join('<br>')}</div>` : ''}

    ${weekly.improvement_areas?.length ? `
    <div class="drawer-section-title">⚠️ Areas to Watch</div>
    <div style="font-size:13px;color:var(--yellow);">${weekly.improvement_areas.join('<br>')}</div>` : ''}

    <div class="drawer-actions">
      <button class="btn btn-red" onclick="generateReport('${entity.id}', 'incident')">📄 Incident Report</button>
      <button class="btn btn-yellow" onclick="generateReport('${entity.id}', 'coaching')">📋 Coaching Report</button>
      <button class="btn btn-green" onclick="replayTrip('${entity.id}')">▶️ Trip Replay</button>
      <button class="btn btn-outline" onclick="closeDrawer()">Close</button>
    </div>
    <div id="drawer-report-container"></div>
    <div id="drawer-replay-container"></div>
  `;

  // Render radar chart if we have baseline
  if (Object.keys(baseline).length > 0) {
    setTimeout(() => renderRadar(baseline, details), 100);
  }
}

function renderRadar(baseline, todayDetails) {
  const canvas = document.getElementById('radar-chart');
  if (!canvas) return;

  const labels = Object.keys(baseline).slice(0, 6).map(m => m.replace(/_/g, ' '));
  const baselineData = Object.values(baseline).slice(0, 6).map(b => b.mean || 0);
  
  // Normalize to 0-100 scale for visual comparison
  const maxVals = baselineData.map((v, i) => {
    const key = Object.keys(baseline)[i];
    return Math.max(v, (todayDetails[key]?.today || v), baseline[key]?.p95 || v);
  });
  
  const normalizedBaseline = baselineData.map((v, i) => (v / (maxVals[i] || 1)) * 100);
  const normalizedToday = Object.keys(baseline).slice(0, 6).map((key, i) => {
    const todayVal = todayDetails[key]?.today || baselineData[i];
    return (todayVal / (maxVals[i] || 1)) * 100;
  });

  new Chart(canvas, {
    type: 'radar',
    data: {
      labels,
      datasets: [
        {
          label: 'Baseline',
          data: normalizedBaseline,
          borderColor: 'rgba(56, 139, 253, 0.8)',
          backgroundColor: 'rgba(56, 139, 253, 0.1)',
          pointBackgroundColor: '#388BFD',
          borderWidth: 2,
          pointRadius: 3,
        },
        {
          label: 'Today',
          data: normalizedToday,
          borderColor: 'rgba(248, 81, 73, 0.8)',
          backgroundColor: 'rgba(248, 81, 73, 0.1)',
          pointBackgroundColor: '#F85149',
          borderWidth: 2,
          pointRadius: 3,
        },
      ],
    },
    options: {
      responsive: true,
      plugins: {
        legend: {
          display: true,
          position: 'bottom',
          labels: { color: '#7D8590', font: { size: 11, family: 'Inter' } },
        },
      },
      scales: {
        r: {
          angleLines: { color: 'rgba(48, 54, 61, 0.4)' },
          grid: { color: 'rgba(48, 54, 61, 0.3)' },
          pointLabels: { color: '#C9D1D9', font: { size: 10, family: 'Inter' } },
          ticks: { display: false },
          suggestedMin: 0,
          suggestedMax: 100,
        },
      },
    },
  });
}

// === WRITE-BACK ===
async function welfareCheck(entityId, entityName) {
  try {
    const res = await fetch(`${API}/api/write-back/group`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: `Welfare Check — ${entityName}`,
        vehicle_ids: [entityId],
        reason: 'Flagged via GEOPulse Dashboard',
      }),
    });
    const data = await res.json();
    if (data.success) {
      showToast(`✅ Welfare Check group created for ${entityName}`, 'success');
    } else {
      showToast(`❌ Failed to create group`, 'error');
    }
  } catch (e) {
    showToast(`❌ Write-back failed: ${e.message}`, 'error');
  }
}

// === TOAST ===
function showToast(message, type = 'success') {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `<span>${message}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.animation = 'toast-out 0.3s ease forwards';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// === HELPERS ===
function formatTime(dateStr) {
  if (!dateStr) return '--:--';
  try {
    const d = new Date(dateStr);
    return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
  } catch { return '--:--'; }
}

function getEventIcon(ruleName) {
  const l = (ruleName || '').toLowerCase();
  if (l.includes('collision')) return '💥';
  if (l.includes('harsh') || l.includes('brake')) return '⚡';
  if (l.includes('speed') || l.includes('exceed')) return '🚀';
  if (l.includes('idle') || l.includes('stop')) return '💤';
  if (l.includes('seat belt') || l.includes('seatbelt')) return '🔒';
  if (l.includes('after hours')) return '🌙';
  return '•';
}

function getEventColor(ruleName) {
  const l = (ruleName || '').toLowerCase();
  if (l.includes('harsh') || l.includes('brake') || l.includes('collision')) return '#F85149';
  if (l.includes('speed') || l.includes('exceed')) return '#D29922';
  if (l.includes('idle') || l.includes('stop')) return '#388BFD';
  return '#3FB950';
}

function truncate(str, len) {
  return str && str.length > len ? str.substring(0, len) + '…' : str || '';
}

// === MUTE TOGGLE ===
function toggleMute() {
  state.audioMuted = !state.audioMuted;
  const btn = document.getElementById('btn-mute');
  if (btn) btn.textContent = state.audioMuted ? '🔇' : '🔊';
  if (state.audioMuted) stopCurrentAudio();
  showToast(state.audioMuted ? '🔇 Audio muted' : '🔊 Audio enabled', 'success');
}

// === HEATMAP / TRAILS / ZONE TOGGLES ===
function toggleZoneSelection() {
  const btn = document.getElementById('btn-zone');
  if (state.zoneBounds) {
    // Clear the active zone
    if (state.zoneRect) state.map.removeLayer(state.zoneRect);
    state.zoneBounds = null;
    state.zoneRect = null;
    btn.textContent = '[ ] Select Zone';
    btn.classList.remove('active');
    
    // Re-render everything with full data
    fetchPositions();
    fetchEvents();
    fetchAnomalies();
    requestCommentary();
    
    showToast('🌍 Zone cleared. Showing full fleet.', 'success');
    return;
  }

  // Toggle selection mode
  state.zoneMode = !state.zoneMode;
  if (state.zoneMode) {
    btn.classList.add('active');
    btn.textContent = '[Cancel Selection]';
    state.map.dragging.disable();
    state.map.getContainer().style.cursor = 'crosshair';
    
    state.map.on('mousedown', onZoneMouseDown);
    showToast('💠 Click and drag on map to draw a tactical zone.', 'info');
  } else {
    btn.classList.remove('active');
    btn.textContent = '[ ] Select Zone';
    state.map.dragging.enable();
    state.map.getContainer().style.cursor = '';
    state.map.off('mousedown', onZoneMouseDown);
  }
}

function onZoneMouseDown(e) {
  state.zoneStartLatlng = e.latlng;
  state.zoneBounds = L.latLngBounds(state.zoneStartLatlng, state.zoneStartLatlng);
  state.zoneRect = L.rectangle(state.zoneBounds, { color: '#B5E853', weight: 1, fillOpacity: 0.1, dashArray: '4,4' }).addTo(state.map);
  
  state.map.on('mousemove', onZoneMouseMove);
  state.map.on('mouseup', onZoneMouseUp);
}

function onZoneMouseMove(e) {
  state.zoneBounds = L.latLngBounds(state.zoneStartLatlng, e.latlng);
  state.zoneRect.setBounds(state.zoneBounds);
}

function onZoneMouseUp(e) {
  state.map.off('mousemove', onZoneMouseMove);
  state.map.off('mouseup', onZoneMouseUp);
  state.map.off('mousedown', onZoneMouseDown);
  
  state.map.dragging.enable();
  state.map.getContainer().style.cursor = '';
  state.zoneMode = false;
  
  const btn = document.getElementById('btn-zone');
  btn.classList.add('active');
  btn.textContent = '[X] Clear Zone';
  
  showToast('🎯 Tactical zone established. Dashboard filtered.', 'success');
  
  // Re-render currently cached data but filtered by the new bounds
  fetchPositions();
  fetchEvents();
  fetchAnomalies();
  requestCommentary();
}

function toggleHeatmap() {
  state.heatmapVisible = !state.heatmapVisible;
  const btn = document.getElementById('btn-heatmap');
  if (btn) btn.style.opacity = state.heatmapVisible ? '1' : '0.4';
  if (state.heatLayer) {
    if (state.heatmapVisible) {
      state.heatLayer.addTo(state.map);
    } else {
      state.map.removeLayer(state.heatLayer);
    }
  }
  showToast(state.heatmapVisible ? '🔥 Heatmap on' : '🔥 Heatmap off', 'success');
}

function toggleTrails() {
  state.trailsVisible = !state.trailsVisible;
  const btn = document.getElementById('btn-trails');
  if (btn) btn.style.opacity = state.trailsVisible ? '1' : '0.4';
  if (!state.trailsVisible) {
    clearTripTrails();
    state.vehicleTrails = {};
  }
  showToast(state.trailsVisible ? '〰️ Trails on' : '〰️ Trails off', 'success');
}

function drawVehicleTrails() {
  // Clear old trail polylines
  clearTripTrails();
  if (!state.trailsVisible) return;

  Object.entries(state.vehicleTrails).forEach(([id, points]) => {
    if (points.length < 2) return;
    const v = state.vehicles.find(v => v.device_id === id);
    const score = v?.deviation_score || 0;
    const color = score > 70 ? '#F85149' : score > 40 ? '#D29922' : '#3FB950';
    addTripTrail(points, color);
  });
}

// === KEYBOARD SHORTCUTS ===
function initKeyboard() {
  document.addEventListener('keydown', (e) => {
    // Don't trigger when typing in inputs
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    
    switch (e.key.toLowerCase()) {
      case 'f': fitFleet(); break;
      case 'm': toggleMute(); break;
      case 'escape': closeDrawer(); break;
      case 'h': toggleHeatmap(); break;
      case 't': toggleTrails(); break;
    }
  });
}

// === STATUS BAR ===
function initStatusBar() {
  // Fetch LLM provider info
  fetch(`${API}/health`).then(r => r.json()).then(data => {
    setText('status-llm', `LLM: ${data.llm_provider || 'Gemini'}`); 
  }).catch(() => {
    setText('status-llm', 'LLM: —');
  });
}

function updateStatusBar() {
  // Vehicle count
  setText('status-vehicles', `${state.vehicles.length} vehicles tracked`);
  
  // Connection status
  const connDot = document.getElementById('status-conn-dot');
  const connText = document.getElementById('status-conn');
  if (connDot && connText) {
    connDot.className = 'status-dot'; // green = connected
    connText.textContent = 'Geotab Connected';
  }

  // Timestamp
  const now = new Date();
  setText('status-time', now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }));
}

function startFreshnessTracker() {
  setInterval(() => {
    if (!state.lastDataTime) return;
    const age = Math.round((Date.now() - state.lastDataTime) / 1000);
    const freshnessEl = document.getElementById('status-freshness');
    const connDot = document.getElementById('status-conn-dot');
    
    if (freshnessEl) {
      freshnessEl.textContent = `Data: ${age}s ago`;
    }
    if (connDot) {
      if (age < 10) {
        connDot.className = 'status-dot';
      } else if (age < 30) {
        connDot.className = 'status-dot stale';
      } else {
        connDot.className = 'status-dot offline';
      }
    }
  }, 1000);
}

// Spin animation for refresh button
const style = document.createElement('style');
style.textContent = '@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }';
document.head.appendChild(style);


// === ACE CHAT PANEL ===
async function sendAceQuery() {
  const inputEl = document.getElementById('ace-input');
  const logEl = document.getElementById('ace-chat-log');
  const sourceEl = document.getElementById('ace-source');
  
  if (!inputEl || !logEl || !inputEl.value.trim()) return;

  const question = inputEl.value.trim();
  inputEl.value = '';

  // Add question to log
  logEl.innerHTML += `<div class="ace-msg"><div class="ace-msg-question">${question}</div></div>`;
  logEl.scrollTop = logEl.scrollHeight;

  // Add loading indicator
  const loadingId = 'ace-load-' + Date.now();
  logEl.innerHTML += `<div class="ace-msg" id="${loadingId}"><div class="ace-msg-loading">// querying Geotab Ace...</div></div>`;
  logEl.scrollTop = logEl.scrollHeight;

  try {
    const res = await fetch(`${API}/api/ace-query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question })
    });
    
    if (!res.ok) {
      let detail = 'API Error';
      try { detail = (await res.json()).detail || detail; } catch (_) {}
      throw new Error(detail);
    }
    const data = await res.json();
    
    // Remove loading
    document.getElementById(loadingId)?.remove();

    // Show source
    if (sourceEl) {
      sourceEl.textContent = data.source === 'ace' ? 'Geotab Ace AI' : 'Local Fallback';
      sourceEl.style.borderColor = data.source === 'ace' ? 'var(--accent)' : 'var(--yellow)';
    }

    // Add answer — render Markdown if marked.js is available
    const rawAnswer = data.answer || 'No response';
    const renderedAnswer = (typeof marked !== 'undefined')
      ? marked.parse(rawAnswer, { breaks: true, gfm: true })
      : rawAnswer.replace(/\n/g, '<br>');
    logEl.innerHTML += `<div class="ace-msg"><div class="ace-msg-answer ace-md">${renderedAnswer}</div></div>`;
    logEl.scrollTop = logEl.scrollHeight;

  } catch (err) {
    document.getElementById(loadingId)?.remove();
    const msg = err.message && err.message !== 'API Error' ? err.message : 'error communicating with ace';
    logEl.innerHTML += `<div class="ace-msg"><div class="ace-msg-answer" style="color:var(--red)">// ${msg}</div></div>`;
    logEl.scrollTop = logEl.scrollHeight;
  }
}

// === REPORT GENERATION ===
async function generateReport(entityId, type) {
  const container = document.getElementById('drawer-report-container');
  if (!container) return;

  const typeLabel = type === 'coaching' ? 'COACHING' : 'INCIDENT';
  const typeIcon = type === 'coaching' ? '📋' : '📄';
  container.innerHTML = `<div class="report-section"><div class="report-header"><span class="report-icon">${typeIcon}</span><span class="report-title">GENERATING ${typeLabel} REPORT...</span></div><div class="report-body" style="color:var(--text-muted);animation:blink 1s infinite;">// querying AI engine...</div></div>`;
  
  try {
    const res = await fetch(`${API}/api/generate-report`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ entity_id: entityId, report_type: type })
    });
    
    if (!res.ok) throw new Error('API Error');
    const data = await res.json();

    // Render Markdown if marked.js is available
    const rendered = (typeof marked !== 'undefined')
      ? marked.parse(data.report, { breaks: true, gfm: true })
      : data.report.replace(/\n/g, '<br>');

    container.innerHTML = `
      <div class="report-section">
        <div class="report-header">
          <span class="report-icon">${typeIcon}</span>
          <span class="report-title">${typeLabel} REPORT</span>
          <span class="report-provider">via ${data.provider || 'AI'}</span>
        </div>
        <div class="report-body ace-md">${rendered}</div>
      </div>`;
  } catch (err) {
    container.innerHTML = `<div class="report-section"><div class="report-header"><span class="report-icon">❌</span><span class="report-title">REPORT FAILED</span></div><div class="report-body" style="color:var(--red)">// failed to generate ${type} report</div></div>`;
  }
}

// === TRIP REPLAY ====================
let replayTimer = null;
let replayState = {
  points: [],
  currentIndex: 0,
  marker: null,
  trail: null,
  layerGroup: null,
  isPlaying: false
};

async function replayTrip(deviceId) {
  const container = document.getElementById('drawer-replay-container');
  if (!container) return;

  // Stop any existing replay
  stopReplay();

  container.innerHTML = `<div class="replay-controls" style="color:var(--text-muted);">// loading trip data...</div>`;

  try {
    const res = await fetch(`${API}/api/trip-replay/${deviceId}`);
    if (!res.ok) throw new Error('API Error');
    const data = await res.json();
    
    if (!data.points || data.points.length === 0) {
      container.innerHTML = `<div class="replay-controls" style="color:var(--yellow);">// no trip data found for today</div>`;
      return;
    }

    // Initialize replay state
    replayState.points = data.points;
    replayState.currentIndex = 0;
    
    // Create map layer group specifically for this replay
    if (replayState.layerGroup) state.map.removeLayer(replayState.layerGroup);
    replayState.layerGroup = L.layerGroup().addTo(state.map);

    // Initial Marker
    const startPt = data.points[0];
    const icon = L.divIcon({
      className: 'custom-div-icon',
      html: `<div style="background-color: var(--accent); width: 14px; height: 14px; border-radius: 50%; border: 2px solid #000; box-shadow: 0 0 10px var(--green-glow);"></div>`,
      iconSize: [14, 14],
      iconAnchor: [7, 7]
    });
    replayState.marker = L.marker([startPt.lat, startPt.lng], { icon }).addTo(replayState.layerGroup);
    
    // Trail polyline
    replayState.trail = L.polyline([[startPt.lat, startPt.lng]], {
      color: 'var(--accent)',
      weight: 3,
      opacity: 0.8,
      dashArray: '5, 5'
    }).addTo(replayState.layerGroup);

    // Zoom map to start
    state.map.setView([startPt.lat, startPt.lng], 15);

    // Render controls
    container.innerHTML = `
      <div class="replay-controls">
        <button class="replay-btn" id="btn-replay-play" onclick="toggleReplayPlay()">▶</button>
        <button class="replay-btn" id="btn-replay-stop" onclick="stopReplay()">■</button>
        <div class="replay-progress">
          <div class="replay-progress-bar" id="replay-progress-bar" style="width: 0%"></div>
        </div>
        <div class="replay-time" id="replay-time">${new Date(startPt.time).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}</div>
      </div>
    `;

    // Automatically start playing
    toggleReplayPlay();

  } catch (err) {
    container.innerHTML = `<div class="replay-controls" style="color:var(--red)">// failed to load trip</div>`;
  }
}

function toggleReplayPlay() {
  replayState.isPlaying = !replayState.isPlaying;
  const btn = document.getElementById('btn-replay-play');
  if (btn) btn.textContent = replayState.isPlaying ? '⏸' : '▶';

  if (replayState.isPlaying) {
    if (replayState.currentIndex >= replayState.points.length - 1) {
      // restarts if at end
      replayState.currentIndex = 0;
      replayState.trail.setLatLngs([[replayState.points[0].lat, replayState.points[0].lng]]);
    }
    replayTimer = setInterval(playNextReplayPoint, 100); // 100ms per point
  } else {
    clearInterval(replayTimer);
  }
}

function stopReplay() {
  clearInterval(replayTimer);
  replayState.isPlaying = false;
  if (replayState.layerGroup) {
    state.map.removeLayer(replayState.layerGroup);
    replayState.layerGroup = null;
  }
  const container = document.getElementById('drawer-replay-container');
  if (container) container.innerHTML = '';
}

function playNextReplayPoint() {
  if (replayState.currentIndex >= replayState.points.length - 1) {
    clearInterval(replayTimer);
    replayState.isPlaying = false;
    const btn = document.getElementById('btn-replay-play');
    if (btn) btn.textContent = '▶';
    return;
  }

  replayState.currentIndex++;
  const pt = replayState.points[replayState.currentIndex];
  
  // Move marker
  replayState.marker.setLatLng([pt.lat, pt.lng]);
  
  // Extend trail
  replayState.trail.addLatLng([pt.lat, pt.lng]);
  
  // Update progress bar & time
  const pct = (replayState.currentIndex / (replayState.points.length - 1)) * 100;
  document.getElementById('replay-progress-bar').style.width = pct + '%';
  document.getElementById('replay-time').textContent = new Date(pt.time).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit',second:'2-digit'});

  // Auto-pan map if point leaves view
  const bounds = state.map.getBounds();
  if (!bounds.contains([pt.lat, pt.lng])) {
    state.map.panTo([pt.lat, pt.lng], {animate: true, duration: 0.5});
  }
}


// === SIDEBAR & RESIZERS ===
function toggleSidebar(side) {
  const sidebar = document.getElementById(`sidebar-${side}`);
  const resizer = document.getElementById(`resizer-${side}`);
  if (sidebar && resizer) {
    sidebar.classList.toggle('collapsed');
    resizer.classList.toggle('collapsed');
    
    // Invalidate map size after a short delay so Leaflet recalculates bounds
    setTimeout(() => {
      if (state.map) state.map.invalidateSize();
    }, 50); // Need to wait for rendering to update
  }
}

function initCollapsiblePanels() {
  document.querySelectorAll('.sidebar-left .panel-header').forEach(header => {
    // Add chevron indicator
    const chevron = document.createElement('span');
    chevron.className = 'panel-chevron';
    chevron.textContent = '\u25BE';
    header.appendChild(chevron);

    header.addEventListener('click', (e) => {
      // Don't toggle if clicking buttons inside the header
      if (e.target.closest('button, .ctrl-btn, .broadcast-controls')) return;
      const panel = header.closest('.panel');
      if (panel) panel.classList.toggle('panel-collapsed');
    });
  });
}

function initResizers() {
  const leftResizer = document.getElementById('resizer-left');
  const rightResizer = document.getElementById('resizer-right');
  const mainGrid = document.querySelector('.main-grid');

  if (leftResizer && mainGrid) {
    let startX, startWidth;
    leftResizer.addEventListener('mousedown', (e) => {
      startX = e.clientX;
      startWidth = parseInt(getComputedStyle(mainGrid).getPropertyValue('--sidebar-left-width')) || 320;
      document.body.style.cursor = 'col-resize';
      leftResizer.classList.add('dragging');
      
      const onMouseMove = (e) => {
        let newWidth = startWidth + (e.clientX - startX);
        if (newWidth < 250) newWidth = 250;
        if (newWidth > 600) newWidth = 600;
        mainGrid.style.setProperty('--sidebar-left-width', `${newWidth}px`);
        if (state.map) state.map.invalidateSize();
      };
      
      const onMouseUp = () => {
        document.body.style.cursor = '';
        leftResizer.classList.remove('dragging');
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseup', onMouseUp);
      };
      
      document.addEventListener('mousemove', onMouseMove);
      document.addEventListener('mouseup', onMouseUp);
    });
  }

  if (rightResizer && mainGrid) {
    let startX, startWidth;
    rightResizer.addEventListener('mousedown', (e) => {
      startX = e.clientX;
      startWidth = parseInt(getComputedStyle(mainGrid).getPropertyValue('--sidebar-right-width')) || 380;
      document.body.style.cursor = 'col-resize';
      rightResizer.classList.add('dragging');
      
      const onMouseMove = (e) => {
        let newWidth = startWidth - (e.clientX - startX);
        if (newWidth < 250) newWidth = 250;
        if (newWidth > 600) newWidth = 600;
        mainGrid.style.setProperty('--sidebar-right-width', `${newWidth}px`);
        if (state.map) state.map.invalidateSize();
      };
      
      const onMouseUp = () => {
        document.body.style.cursor = '';
        rightResizer.classList.remove('dragging');
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseup', onMouseUp);
      };
      
      document.addEventListener('mousemove', onMouseMove);
      document.addEventListener('mouseup', onMouseUp);
    });
  }
}
