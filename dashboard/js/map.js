/**
 * GEOPulse — Google Maps Integration
 *
 * Dark-mode fleet map with color-coded vehicle markers,
 * trip trails, heatmap layer, and smooth live updates.
 */

const DARK_MAP_STYLE = [
    { elementType: 'geometry', stylers: [{ color: '#1a1a2e' }] },
    { elementType: 'labels.text.fill', stylers: [{ color: '#8ec3b9' }] },
    { elementType: 'labels.text.stroke', stylers: [{ color: '#1a1a2e' }] },
    { featureType: 'road', elementType: 'geometry', stylers: [{ color: '#304a7d' }] },
    { featureType: 'road', elementType: 'geometry.stroke', stylers: [{ color: '#1a1a2e' }] },
    { featureType: 'water', elementType: 'geometry', stylers: [{ color: '#0e1626' }] },
    { featureType: 'poi', stylers: [{ visibility: 'off' }] },
    { featureType: 'transit', stylers: [{ visibility: 'off' }] },
];

let map = null;
let markers = {};
let infoWindow = null;

function initMap() {
    const mapEl = document.getElementById('map');
    if (!mapEl || typeof google === 'undefined') {
        console.warn('Google Maps not loaded. Using fallback map display.');
        if (mapEl) {
            mapEl.innerHTML = `
                <div style="display:flex;align-items:center;justify-content:center;height:100%;
                            background:#1a1a2e;color:#7D8590;font-size:14px;flex-direction:column;gap:12px;">
                    <span style="font-size:48px;">🗺️</span>
                    <span>Map requires Google Maps API key</span>
                    <span style="font-size:12px;">Vehicles will appear here when configured</span>
                </div>`;
        }
        return;
    }

    map = new google.maps.Map(mapEl, {
        center: { lat: 43.5, lng: -79.7 },  // Geotab HQ area
        zoom: 10,
        styles: DARK_MAP_STYLE,
        disableDefaultUI: true,
        zoomControl: true,
        mapTypeControl: false,
    });

    infoWindow = new google.maps.InfoWindow();
}

function updateMapMarkers(vehicles) {
    if (!map) return;

    const activeIds = new Set();

    vehicles.forEach(v => {
        activeIds.add(v.device_id);
        const pos = { lat: v.latitude, lng: v.longitude };

        if (markers[v.device_id]) {
            // Smooth animate to new position
            smoothMove(markers[v.device_id], pos);
        } else {
            // Create new marker
            const color = getMarkerColor(v.deviation_score || 0);
            const marker = new google.maps.Marker({
                position: pos,
                map: map,
                title: v.device_name,
                icon: {
                    path: google.maps.SymbolPath.FORWARD_CLOSED_ARROW,
                    scale: 5,
                    fillColor: color,
                    fillOpacity: 1,
                    strokeWeight: 1,
                    strokeColor: '#0D1117',
                    rotation: v.bearing || 0,
                },
            });

            marker.addListener('click', () => {
                openDetailDrawer(v.device_id);
                highlightMarker(v.device_id);
            });

            markers[v.device_id] = marker;
        }

        // Update color based on deviation
        const marker = markers[v.device_id];
        if (marker && marker.getIcon) {
            const icon = marker.getIcon();
            if (icon) {
                icon.fillColor = getMarkerColor(v.deviation_score || 0);
                icon.rotation = v.bearing || 0;
                marker.setIcon(icon);
            }
        }
    });

    // Remove markers for vehicles no longer present
    Object.keys(markers).forEach(id => {
        if (!activeIds.has(id)) {
            markers[id].setMap(null);
            delete markers[id];
        }
    });
}

function smoothMove(marker, newPos) {
    const start = marker.getPosition();
    const startLat = start.lat();
    const startLng = start.lng();
    const endLat = newPos.lat;
    const endLng = newPos.lng;

    let step = 0;
    const numSteps = 30;
    const delay = 500 / numSteps;

    function animate() {
        step++;
        const t = step / numSteps;
        const lat = startLat + (endLat - startLat) * t;
        const lng = startLng + (endLng - startLng) * t;
        marker.setPosition({ lat, lng });
        if (step < numSteps) {
            setTimeout(animate, delay);
        }
    }
    animate();
}

function getMarkerColor(deviationScore) {
    if (deviationScore > 70) return '#F85149';  // Red
    if (deviationScore > 40) return '#D29922';  // Yellow
    return '#3FB950';                            // Green
}

function highlightMarker(vehicleId) {
    // Pulse animation via CSS class (handled in dashboard.css)
    const marker = markers[vehicleId];
    if (marker && map) {
        map.panTo(marker.getPosition());
        map.setZoom(14);
    }
}

function fitBoundsToFleet() {
    if (!map || Object.keys(markers).length === 0) return;
    const bounds = new google.maps.LatLngBounds();
    Object.values(markers).forEach(m => bounds.extend(m.getPosition()));
    map.fitBounds(bounds);
}
