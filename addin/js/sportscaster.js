/**
 * GEOPulse — Live Sportscaster Engine
 *
 * Polls the backend for fleet events and generates
 * live audio commentary via the LLM + TTS pipeline.
 */

let sportscasterActive = false;
let commentaryQueue = [];

async function startBroadcast() {
    sportscasterActive = true;
    const statusEl = document.querySelector('.broadcast-status');
    if (statusEl) statusEl.classList.add('active');

    pollCommentary();
}

async function stopBroadcast() {
    sportscasterActive = false;
    const statusEl = document.querySelector('.broadcast-status');
    if (statusEl) statusEl.classList.remove('active');
}

async function pollCommentary() {
    if (!sportscasterActive) return;

    try {
        // Get recent events from state
        const recentEvents = (window.state || state).events.slice(0, 5);
        if (recentEvents.length > 0) {
            const commentary = await generateCommentary(recentEvents);
            if (commentary) {
                showCommentary(commentary);
            }
        }
    } catch (e) {
        console.warn('Commentary poll failed:', e);
    }

    // Poll every 60 seconds
    if (sportscasterActive) {
        setTimeout(pollCommentary, 60000);
    }
}

async function generateCommentary(events) {
    try {
        const res = await fetch(`${API_BASE}/api/generate-commentary`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ events }),
        });
        const data = await res.json();
        return data.text || null;
    } catch (e) {
        console.warn('Commentary generation failed:', e);
        return null;
    }
}

function showCommentary(text) {
    const textEl = document.getElementById('current-commentary');
    if (textEl) {
        textEl.textContent = text;
        textEl.style.animation = 'none';
        textEl.offsetHeight; // Trigger reflow
        textEl.style.animation = 'fade-in 0.5s ease';
    }

    // Animate waveform
    const waveform = document.querySelector('.sc-waveform');
    if (waveform) {
        waveform.classList.add('playing');
        setTimeout(() => waveform.classList.remove('playing'), 5000);
    }
}

// Auto-start broadcast on load
document.addEventListener('DOMContentLoaded', () => {
    setTimeout(startBroadcast, 3000); // Start 3s after page load
});
