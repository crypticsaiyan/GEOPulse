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
        if (!data.text) return null;
        return { text: data.text, audio_b64: data.audio_b64 || null };
    } catch (e) {
        console.warn('Commentary generation failed:', e);
        return null;
    }
}

function playAudioB64(b64) {
    try {
        const binary = atob(b64);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
        const blob = new Blob([bytes], { type: 'audio/mpeg' });
        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);
        audio.onended = () => URL.revokeObjectURL(url);
        audio.play().catch(err => {
            console.warn('Audio playback failed, falling back to speech synthesis:', err);
            return null;
        });
        return audio;
    } catch (e) {
        console.warn('Audio decode failed:', e);
        return null;
    }
}

function speakFallback(text) {
    if (!window.speechSynthesis) return;
    const utt = new SpeechSynthesisUtterance(text);
    utt.rate = 1.05;
    utt.pitch = 1.0;
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utt);
}

function showCommentary(commentary) {
    const text = typeof commentary === 'string' ? commentary : commentary.text;
    const audio_b64 = commentary && commentary.audio_b64 ? commentary.audio_b64 : null;

    const textEl = document.getElementById('current-commentary');
    if (textEl) {
        textEl.textContent = text;
        textEl.style.animation = 'none';
        textEl.offsetHeight; // Trigger reflow
        textEl.style.animation = 'fade-in 0.5s ease';
    }

    // Play audio
    if (audio_b64) {
        const played = playAudioB64(audio_b64);
        if (!played) speakFallback(text);
    } else {
        speakFallback(text);
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
