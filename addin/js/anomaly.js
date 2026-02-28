/**
 * GEOPulse — Anomaly Panel
 *
 * Displays FleetDNA anomaly cards with pulsing red borders
 * and quick-action buttons (Welfare Check, Coaching, Watch).
 */

function initAnomalyPanel() {
    renderAnomalyPanel((window.state || state).anomalies || []);
}

function renderAnomalyPanel(anomalies) {
    const panel = document.getElementById('anomaly-panel');
    if (!panel) return;

    const content = panel.querySelector('.anomaly-content') || panel;

    if (anomalies.length === 0) {
        content.innerHTML = `
            <div style="text-align:center;padding:20px;color:var(--text-muted);font-size:13px;">
                <span style="font-size:24px;">✅</span><br>
                No anomalies detected
            </div>`;
        panel.classList.remove('anomaly-active');
        return;
    }

    // Activate pulse animation
    panel.classList.add('anomaly-active');

    let html = '';
    anomalies.forEach(a => {
        const score = a.deviation_score || 0;
        const color = score > 70 ? 'var(--red)' : 'var(--yellow)';
        const icon = score > 70 ? '🔴' : '🟡';

        html += `
            <div class="anomaly-item" style="padding:12px;border-bottom:1px solid var(--border);cursor:pointer;"
                 onclick="openDetailDrawer('${a.entity_id}')">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <div>
                        <span>${icon}</span>
                        <strong style="color:${color};">${a.name || 'Unknown'}</strong>
                    </div>
                    <span style="font-size:20px;font-weight:bold;color:${color};">${score}</span>
                </div>
                <div style="font-size:12px;color:var(--text-muted);margin-top:4px;">
                    ${a.anomaly_type || 'unknown'} anomaly · confidence: ${a.confidence || 0}%
                </div>
                <div style="display:flex;gap:6px;margin-top:8px;">
                    <button class="btn btn-red" style="font-size:11px;padding:4px 10px;"
                            onclick="event.stopPropagation();welfareCheck('${a.entity_id}','${a.name}')">
                        Welfare Check
                    </button>
                    <button class="btn btn-outline" style="font-size:11px;padding:4px 10px;"
                            onclick="event.stopPropagation();openDetailDrawer('${a.entity_id}')">
                        Details
                    </button>
                </div>
            </div>`;
    });

    content.innerHTML = html;
}
