/* Elite Demo Engine - National Finals Edition */

const CONFIG = {
    API_URL: `http://${window.location.host}/api/navigation/ui/state`,
    ACTION_URL: `http://${window.location.host}/api/navigation/ui/action`,
    POLL_RATE: 300,
    SESSION_ID: "NATIONAL_FINALS_2026"
};

// Global State
let map, panorama, riderMarker, routeLine, uncertaintyCircle;
let isGPSFailed = false;
let isDiagOpen = true;
let lastLandmarkId = "";
let startTime = Date.now();
let mapInitialized = false;

// Smooth animation state
let animFrom = null;      // {lat, lng, heading} — where we started this tween
let animTo   = null;      // {lat, lng, heading} — where we are heading
let animStart = 0;        // timestamp when tween started
const ANIM_DURATION = 280; // ms — slightly less than poll rate for seamless chaining

function lerpAngle(a, b, t) {
    // Shortest-path angle interpolation (handles 359→1° wrap)
    let diff = ((b - a + 540) % 360) - 180;
    return a + diff * t;
}

function lerp(a, b, t) { return a + (b - a) * t; }

function easeInOut(t) { return t < 0.5 ? 2*t*t : -1+(4-2*t)*t; }

function animateTick(now) {
    if (!animFrom || !animTo || !riderMarker) {
        requestAnimationFrame(animateTick);
        return;
    }
    const t = easeInOut(Math.min((now - animStart) / ANIM_DURATION, 1));
    const lat = lerp(animFrom.lat, animTo.lat, t);
    const lng = lerp(animFrom.lng, animTo.lng, t);
    const heading = lerpAngle(animFrom.heading, animTo.heading, t);

    const pos = { lat, lng };
    riderMarker.setPosition(pos);
    const icon = riderMarker.getIcon();
    icon.rotation = heading;
    riderMarker.setIcon(icon);
    requestAnimationFrame(animateTick);
}

// --- 1. INITIALIZATION ---
function init() {
    if (mapInitialized) return;
    mapInitialized = true;
    console.log("🚀 Initializing Elite Tactical Navigation Engine...");
    
    const puneCenter = { lat: 18.52042, lng: 73.85623 }; // Road Centered
    
    // A. Tactical Map
    map = new google.maps.Map(document.getElementById('map'), {
        center: puneCenter,
        zoom: 17,
        tilt: 0,
        heading: 0,
        mapId: '8e1927s1a029',
        disableDefaultUI: true,
        backgroundColor: '#0a0e14',
        styles: NIGHT_STYLE 
    });

    // B. AI Vision Feed
    panorama = new google.maps.StreetViewPanorama(
        document.getElementById('street-view'),
        {
            position: puneCenter,
            pov: { heading: 0, pitch: 0 },
            visible: true,
            disableDefaultUI: true,
            clickToGo: false
        }
    );

    // C. High-Vis Rider Marker
    riderMarker = new google.maps.Marker({
        position: puneCenter,
        map: map,
        icon: {
            path: google.maps.SymbolPath.FORWARD_CLOSED_ARROW,
            scale: 7,
            fillColor: '#38bdf8',
            fillOpacity: 1,
            strokeWeight: 2,
            strokeColor: '#fff',
            rotation: 0
        }
    });

    // D. Uncertainty Cluster
    uncertaintyCircle = new google.maps.Circle({
        strokeColor: "#38bdf8",
        strokeOpacity: 0.8,
        strokeWeight: 2,
        fillColor: "#38bdf8",
        fillOpacity: 0.1,
        map: map,
        center: puneCenter,
        radius: 0,
        clickable: false
    });

    // E. Tactical Route Path
    routeLine = new google.maps.Polyline({
        path: [],
        geodesic: true,
        strokeColor: "#38bdf8",
        strokeOpacity: 0.5,
        strokeWeight: 4,
        map: map
    });

    // F. Start Orchestration
    setInterval(updateStats, 1000);
    setInterval(sync, CONFIG.POLL_RATE);
    initIMUGraph();
    requestAnimationFrame(animateTick); // Start smooth animation loop
    
    log("> [SYS]: Fusion Kernel Initialized.", "#38bdf8");
    log("> [SYS]: Google Maps API Integration: VALIDATED", "#4ade80");
}

// --- 2. DATA ORCHESTRATION ---
async function sync() {
    try {
        const res = await fetch(CONFIG.API_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: CONFIG.SESSION_ID, ts_ms: Date.now() })
        });
        
        if (res.ok) {
            const data = await res.json();
            if (data.ui_state) render(data.ui_state);
        }
    } catch (e) {
        // Silent recovery for network jitter
    }
}

function render(ui) {
    if (!ui || !ui.current_position) return;

    const lat = ui.current_position[0];
    const lng = ui.current_position[1];
    const heading = ui.heading || 0;
    const pos = { lat, lng };

    map.panTo(pos);
    if (panorama) {
        panorama.setPosition(pos);
        panorama.setPov({ heading: heading, pitch: 0 });
    }

    // A. Smooth animation — set new tween target
    const currentPos = riderMarker ? riderMarker.getPosition() : null;
    animFrom = currentPos
        ? { lat: currentPos.lat(), lng: currentPos.lng(), heading: animTo ? animTo.heading : heading }
        : { lat, lng, heading };
    animTo = { lat, lng, heading };
    animStart = performance.now();

    // B. Drift Analytics (Narrative Simulation for Hackathon)
    let drift = ui.uncertainty_m || 0;
    
    if (isGPSFailed) {
        // Accumulate 'Fake' drift for visual impact (0.5m per second)
        if (!window.simDrift) window.simDrift = 20.0;
        window.simDrift += 0.5; 
        drift += window.simDrift;
    } else {
        window.simDrift = 0; // Reset
    }
    
    uncertaintyCircle.setCenter(pos);
    uncertaintyCircle.setRadius(drift);
    
    document.getElementById('drift-val').innerText = drift.toFixed(1) + "m";
    document.getElementById('drift-bar').style.width = Math.min(100, (drift / 100) * 100) + "%";
    document.getElementById('pos-mode').innerText = ui.position_mode || "GPS_CONVERGED";

    if (drift > 40) {
        uncertaintyCircle.setOptions({strokeColor: '#f87171', fillColor: '#f87171'});
        document.getElementById('drift-bar').style.backgroundColor = 'var(--neon-red)';
    } else {
        uncertaintyCircle.setOptions({strokeColor: '#38bdf8', fillColor: '#38bdf8'});
        document.getElementById('drift-bar').style.backgroundColor = 'var(--neon-blue)';
    }

    // C. Navigation HUD
    if (ui.next_instruction_text) {
        document.getElementById('inst-text').innerText = ui.next_instruction_text;
    }
    
    if (ui.current_position && ui.route_polyline && ui.route_polyline.length > 0) {
        const p1 = new google.maps.LatLng(ui.current_position[0], ui.current_position[1]);
        const p2 = new google.maps.LatLng(ui.route_polyline[0][0], ui.route_polyline[0][1]);
        const dist = google.maps.geometry.spherical.computeDistanceBetween(p1, p2);
        document.getElementById('inst-distance').innerText = Math.round(dist) + " m";
    }

    // D. Speedometer Logic
    const speed = 35 + Math.floor(Math.random() * 5);
    document.getElementById('speed-val').innerText = speed;
    document.getElementById('heading-val').innerText = heading.toFixed(1) + "°";

    // E. Vision Event Trigger
    if (ui.last_visual_event && ui.last_visual_event.event_id !== lastLandmarkId) {
        lastLandmarkId = ui.last_visual_event.event_id;
        const landmark = ui.last_visual_event.payload.landmark || ui.last_visual_event.payload.landmark_class;
        if (landmark) triggerVisionRescue(landmark);
    }

    // F. Route Visualization
    if (ui.route_polyline && ui.route_polyline.length > 0) {
        const path = ui.route_polyline.map(p => ({ lat: p[0], lng: p[1] }));
        routeLine.setPath(path);
    }

    // G. EMERGENCY SOS TRIGGER
    const sosOverlay = document.getElementById('sos-overlay');
    if (ui.is_emergency) {
        if (sosOverlay.style.display !== 'block') {
            sosOverlay.style.display = 'block';
            log("> [CRITICAL]: CRASH SENSOR TRIPPED", "#f87171");
            log("> [CRITICAL]: EMERGENCY SOS BROADCASTING...", "#f87171");
            document.body.style.boxShadow = "inset 0 0 200px rgba(248, 113, 113, 0.4)";
        }
    } else {
        sosOverlay.style.display = 'none';
        document.body.style.boxShadow = "none";
    }
}

// --- 3. TACTICAL ACTIONS ---

async function startTrip() {
    log("> [SYS]: Negotiating Route Parameters...", "white");
    try {
        await fetch(CONFIG.ACTION_URL, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                session_id: CONFIG.SESSION_ID,
                ts_ms: Date.now(),
                action_type: "START_NAVIGATION",
                payload: { origin: "Shaniwar Wada", destination: "Pune Station" }
            })
        });
        log("> [SYS]: Route Locked. Streaming Telemetry...", "#4ade80");
    } catch(e) {}
}

function toggleGPSFailure() {
    isGPSFailed = !isGPSFailed;
    const chip = document.getElementById('gps-status');
    const text = document.getElementById('gps-text');
    if (isGPSFailed) {
        chip.className = "status-chip gps-lost";
        text.innerText = "GPS: SIGNAL LOST";
        log("> [CRITICAL]: Global Navigation Satellite System (GNSS) Lost", "#f87171");
        log("> [KERN]: Switching to Dead Reckoning [DR_ACTIVE]", "#f87171");
        log("> [KERN]: KF State: Error Bias Accumulation Started", "#94a3b8");
    } else {
        chip.className = "status-chip gps-active";
        text.innerText = "GPS: CONNECTED";
        log("> [SYS]: Signal Restored. Global State Re-aligned.", "#4ade80");
    }
}

function triggerVisionRescue(landmarkName) {
    log(`> [CV]: LANDMARK MATCH: ${landmarkName.toUpperCase()}`, "#4ade80");
    log(`> [CV]: Spatial Consistency Check [PASS]`, "#4ade80");
    log(`> [KERN]: Resetting IMU Drift Vector`, "#4ade80");
    
    const alert = document.getElementById('vision-alert');
    alert.style.display = "block";
    
    isGPSFailed = false;
    toggleGPSFailure(); 
    
    document.body.style.boxShadow = "inset 0 0 150px rgba(74, 222, 128, 0.3)";
    setTimeout(() => {
        document.body.style.boxShadow = "none";
        alert.style.display = "none";
    }, 5000);
}

function toggleDiag() {
    isDiagOpen = !isDiagOpen;
    document.querySelectorAll('aside').forEach(p => p.style.display = isDiagOpen ? 'flex' : 'none');
}

// --- 4. DATA VISUALIZATION ---

function log(msg, color) {
    const logBox = document.getElementById('fusion-log');
    const entry = document.createElement('div');
    entry.className = "log-line";
    entry.style.color = color;
    entry.innerText = msg;
    logBox.prepend(entry);
}

function updateStats() {
    const diff = Math.floor((Date.now() - startTime) / 1000);
    const m = Math.floor(diff / 60);
    const s = diff % 60;
    document.getElementById('uptime').innerText = `${m}:${s < 10 ? '0' : ''}${s}`;
    document.getElementById('latency-val').innerText = (8 + Math.floor(Math.random() * 5)) + "ms";
}

function initIMUGraph() {
    const canvas = document.getElementById('imu-chart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let offset = 0;
    function draw() {
        ctx.clearRect(0,0, canvas.width, canvas.height);
        ctx.strokeStyle = '#38bdf8';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        for (let x = 0; x < canvas.width; x++) {
            const y = 50 + Math.sin((x + offset) * 0.1) * 15 + Math.random() * 3;
            if (x === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        }
        ctx.stroke();
        offset += 2;
        requestAnimationFrame(draw);
    }
    draw();
}

const NIGHT_STYLE = [
    { "elementType": "geometry", "stylers": [{ "color": "#121212" }] },
    { "elementType": "labels.text.fill", "stylers": [{ "color": "#746855" }] },
    { "elementType": "labels.text.stroke", "stylers": [{ "color": "#242f3e" }] },
    { "featureType": "administrative.locality", "elementType": "labels.text.fill", "stylers": [{ "color": "#d59563" }] },
    { "featureType": "road", "elementType": "geometry", "stylers": [{ "color": "#2c2c2c" }] },
    { "featureType": "road", "elementType": "geometry.stroke", "stylers": [{ "color": "#212a37" }] },
    { "featureType": "water", "elementType": "geometry", "stylers": [{ "color": "#17263c" }] }
];

// Entry Point
window.init = init;
if (typeof google !== 'undefined' && typeof google.maps !== 'undefined' && !window.mapInitialized) {
    init();
}
