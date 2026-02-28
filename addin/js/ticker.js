/**
 * GEOPulse — Event Ticker
 *
 * Displays live fleet events with slide-in animations.
 * Events auto-scroll and old items are removed.
 */

const MAX_TICKER_ITEMS = 20;

function initTicker() {
    const ticker = document.getElementById('event-ticker');
    if (!ticker) return;

    // Render initial events from state
    const events = (window.state || state).events || [];
    events.slice(0, MAX_TICKER_ITEMS).forEach(e => {
        const item = createTickerItem(e);
        ticker.appendChild(item);
    });
}

function addTickerItems(newEvents) {
    const ticker = document.getElementById('event-ticker');
    if (!ticker) return;

    newEvents.forEach(event => {
        const item = createTickerItem(event);
        ticker.insertBefore(item, ticker.firstChild);
    });

    // Remove excess items
    while (ticker.children.length > MAX_TICKER_ITEMS) {
        ticker.removeChild(ticker.lastChild);
    }
}

function createTickerItem(event) {
    const item = document.createElement('div');
    item.className = 'ticker-item';

    const time = formatTime(event.active_from);
    const color = getEventColor(event.rule_name || '');
    const name = event.device_name || event.driver_name || 'Unknown';
    const rule = event.rule_name || 'Event';

    item.innerHTML = `
        <span class="ticker-time">${time}</span>
        <span class="ticker-dot" style="background:${color};"></span>
        <span class="ticker-name">${name}</span>
        <span class="ticker-rule" style="color:var(--text-muted);">${truncate(rule, 30)}</span>
    `;

    return item;
}

function getEventColor(ruleName) {
    const lower = ruleName.toLowerCase();
    if (lower.includes('harsh') || lower.includes('brake') || lower.includes('collision')) return '#F85149';
    if (lower.includes('speed') || lower.includes('exceed')) return '#D29922';
    if (lower.includes('idle') || lower.includes('stop')) return '#388BFD';
    return '#3FB950';
}

function formatTime(dateStr) {
    if (!dateStr) return '--:--';
    try {
        const d = new Date(dateStr);
        return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
    } catch {
        return '--:--';
    }
}

function truncate(str, len) {
    return str.length > len ? str.substring(0, len) + '…' : str;
}
