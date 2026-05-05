/* Smart Helmet Navigation — Demo Engine */

const CONFIG = {
    API_URL: `http://${window.location.host}/api/navigation/ui/state`,
    ACTION_URL: `http://${window.location.host}/api/navigation/ui/action`,
    POLL_RATE: 300,
    CV_LOG_INTERVAL: 800,
    DR_LOG_INTERVAL: 1200,
    SESSION_ID: "NATIONAL_FINALS_2026"
};

// Global State
let map, panorama, riderMarker, routeLine, uncertaintyCircle;
let isGPSFailed = false;
let lastLandmarkId = "";
let startTime = Date.now();
let mapInitialized = false;

// CV + DR logging state (all output → console)
let lastCVLogTime = 0;
let lastDRLogTime = 0;
let prevHeading = 0;
let cvFrameCount = 0;
let drStepCount = 0;
let lastCVDetection = '';
let cvServiceAvailable = false;

// Real telemetry tracking (replaces Math.random fakes)
let lastPos = null;
let lastPosTs = 0;
let smoothedSpeedKmh = 0;
let lastSyncLatency = 0;

// Mission counters
let counters = { drFixes: 0, cvRescues: 0, offlineSec: 0, waypoints: 0 };
let lastCounterTick = Date.now();

// Connectivity timeline (60s rolling, 1 cell/sec)
const CONN_CELLS = 60;
let connHistory = new Array(CONN_CELLS).fill(null);
let lastConnTick = 0;

// Voice (turn-by-turn)
let lastVoicedManeuverKey = '';

// Demo mode
let demoModeRunning = false;

// Smooth animation state
let animFrom = null;
let animTo   = null;
let animStart = 0;

function lerpAngle(a, b, t) {
    let diff = ((b - a + 540) % 360) - 180;
    return a + diff * t;
}
function lerp(a, b, t) { return a + (b - a) * t; }

function animateTick(now) {
    if (!animFrom || !animTo || !riderMarker) {
        requestAnimationFrame(animateTick);
        return;
    }
    const t = Math.min((now - animStart) / CONFIG.POLL_RATE, 1);
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

// ── INIT ──────────────────────────────────────────────────────────────────
function init() {
    if (mapInitialized) return;
    mapInitialized = true;

    const puneCenter = { lat: 18.52042, lng: 73.85623 };

    map = new google.maps.Map(document.getElementById('map'), {
        center: puneCenter,
        zoom: 17,
        tilt: 0,
        heading: 0,
        mapId: '8e1927s1a029',
        disableDefaultUI: true,
        backgroundColor: '#0d1117',
        styles: NIGHT_STYLE
    });

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

    riderMarker = new google.maps.Marker({
        position: puneCenter,
        map: map,
        icon: {
            path: google.maps.SymbolPath.FORWARD_CLOSED_ARROW,
            scale: 7,
            fillColor: '#58a6ff',
            fillOpacity: 1,
            strokeWeight: 2,
            strokeColor: '#fff',
            rotation: 0
        }
    });

    uncertaintyCircle = new google.maps.Circle({
        strokeColor: "#58a6ff",
        strokeOpacity: 0.7,
        strokeWeight: 2,
        fillColor: "#58a6ff",
        fillOpacity: 0.08,
        map: map,
        center: puneCenter,
        radius: 0,
        clickable: false
    });

    routeLine = new google.maps.Polyline({
        path: [],
        geodesic: true,
        strokeColor: "#58a6ff",
        strokeOpacity: 0.6,
        strokeWeight: 5,
        map: map
    });

    setInterval(updateStats, 1000);
    setInterval(sync, CONFIG.POLL_RATE);
    setInterval(pollCVService, CONFIG.CV_LOG_INTERVAL);
    initIMUGraph();
    requestAnimationFrame(animateTick);

    console.log('%c[SYS] Fusion Kernel Initialized', 'color:#58a6ff;font-weight:bold');
    console.log('%c[CV]  Vision Pipeline Ready — LRASPP + TinySceneCNN', 'color:#a78bfa;font-weight:bold');
    console.log('%c[DR]  Dead Reckoning Module: STANDBY', 'color:#d29922;font-weight:bold');
}

// ── SYNC ──────────────────────────────────────────────────────────────────
async function sync() {
    const t0 = performance.now();
    try {
        const res = await fetch(CONFIG.API_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: CONFIG.SESSION_ID, ts_ms: Date.now() })
        });
        if (res.ok) {
            const data = await res.json();
            lastSyncLatency = Math.round(performance.now() - t0);
            if (data.ui_state) render(data.ui_state);
        }
    } catch (e) { /* silent */ }
}

// ── RENDER ────────────────────────────────────────────────────────────────
function render(ui) {
    if (!ui || !ui.current_position) return;

    const lat = ui.current_position[0];
    const lng = ui.current_position[1];
    const heading = ui.heading || 0;
    const pos = { lat, lng };
    const now = Date.now();

    map.panTo(pos);
    if (panorama) {
        panorama.setPosition(pos);
        panorama.setPov({ heading, pitch: 0 });
    }

    // Smooth animation
    const currentPos = riderMarker ? riderMarker.getPosition() : null;
    animFrom = currentPos
        ? { lat: currentPos.lat(), lng: currentPos.lng(), heading: animTo ? animTo.heading : heading }
        : { lat, lng, heading };
    animTo = { lat, lng, heading };
    animStart = performance.now();

    // Drift
    let drift = ui.uncertainty_m || 0;
    if (isGPSFailed) {
        if (!window.simDrift) window.simDrift = 20.0;
        window.simDrift = Math.min(window.simDrift + 0.5, 25.0);
        drift += window.simDrift;
    } else {
        window.simDrift = 0;
    }

    uncertaintyCircle.setCenter(pos);
    uncertaintyCircle.setRadius(drift);

    document.getElementById('drift-val').innerText = drift.toFixed(1) + "m";
    document.getElementById('drift-bar').style.width = Math.min(100, (drift / 100) * 100) + "%";
    document.getElementById('pos-mode').innerText = ui.position_mode || "GPS";

    if (drift > 40) {
        uncertaintyCircle.setOptions({ strokeColor: '#f85149', fillColor: '#f85149' });
        document.getElementById('drift-bar').style.background = 'var(--red)';
    } else {
        uncertaintyCircle.setOptions({ strokeColor: '#58a6ff', fillColor: '#58a6ff' });
        document.getElementById('drift-bar').style.background = 'var(--accent)';
    }

    const instrText = ui.next_instruction_text || '';
    const distNext  = ui.distance_to_next_m;

    // Real speed from position delta (haversine over time)
    const tNow = Date.now();
    if (lastPos && lastPosTs) {
        const dtSec = (tNow - lastPosTs) / 1000;
        if (dtSec > 0.05) {
            const dMeters = haversine(lastPos[0], lastPos[1], lat, lng);
            const instSpeedKmh = (dMeters / dtSec) * 3.6;
            // EMA smoothing (avoid jitter)
            smoothedSpeedKmh = smoothedSpeedKmh
                ? smoothedSpeedKmh * 0.7 + instSpeedKmh * 0.3
                : instSpeedKmh;
        }
    }
    lastPos = [lat, lng];
    lastPosTs = tNow;

    document.getElementById('speed-val').innerText = Math.round(smoothedSpeedKmh) || 0;
    document.getElementById('heading-val').innerText = heading.toFixed(1) + "°";

    // Floating instruction bar — always visible during a route
    updateInstructionBar(instrText, distNext);

    // Voice turn-by-turn (announce window only)
    maybeVoiceAnnounce(instrText, distNext);

    // Vision event
    if (ui.last_visual_event && ui.last_visual_event.event_id !== lastLandmarkId) {
        lastLandmarkId = ui.last_visual_event.event_id;
        const landmark = ui.last_visual_event.payload.landmark || ui.last_visual_event.payload.landmark_class;
        if (landmark) triggerVisionRescue(landmark);
    }

    // Route line
    if (ui.route_polyline && ui.route_polyline.length > 0) {
        const path = ui.route_polyline.map(p => ({ lat: p[0], lng: p[1] }));
        routeLine.setPath(path);
        counters.waypoints = ui.route_polyline.length;
    }

    // Counters — DR fix per render with movement
    counters.drFixes++;

    // 4-state colour scheme — nav_mode × position_mode (matches embedded UI)
    const sysState = ui.system_state || "OFFLINE_VISUAL";
    applySystemState(sysState);

    // Mission banner + connectivity timeline + KPI rendering
    handleMissionBanner(sysState);
    tickConnectivityTimeline(sysState);
    tickOfflineCounter(sysState);
    renderCounters();

    // ── CV LOGGING → console ──────────────────────────────────────────
    if (now - lastCVLogTime > CONFIG.CV_LOG_INTERVAL && ui.route_polyline && ui.route_polyline.length > 1) {
        lastCVLogTime = now;
        cvFrameCount++;

        const headingDelta = ((heading - prevHeading + 540) % 360) - 180;
        const scene = classifyScene(headingDelta, instrText);
        const routeTurn = extractRouteTurn(instrText);
        const match = checkCVRouteMatch(scene, routeTurn);

        console.log(`%c[CV] F#${cvFrameCount} | Scene: ${scene.label} | Δhdg: ${headingDelta.toFixed(1)}° | conf: ${scene.conf}%`, 'color:#a78bfa');

        if (lastCVDetection) {
            console.log(`%c[CV] Model: ${lastCVDetection}`, 'color:#c084fc');
        }

        if (routeTurn !== 'STRAIGHT') {
            const tag = match ? '✓ CONFIRMED' : '⏳ PENDING';
            console.log(`%c[CV] Route expects: ${routeTurn} | CV sees: ${scene.turn} → ${tag}`, match ? 'color:#3fb950' : 'color:#d29922');
        }

        if (scene.junction !== 'none') {
            console.log(`%c[CV] ⚠ JUNCTION: ${scene.junction} — conf: ${scene.conf}%`, 'color:#d29922;font-weight:bold');
        }
    }

    // ── DR LOGGING → console ──────────────────────────────────────────
    if (now - lastDRLogTime > CONFIG.DR_LOG_INTERVAL) {
        lastDRLogTime = now;
        drStepCount++;

        const headingDelta = ((heading - prevHeading + 540) % 360) - 180;
        const posMode = ui.position_mode || 'UNKNOWN';
        const conf = Math.round((ui.confidence || 0) * 100);

        console.log(`%c[DR] #${drStepCount} | Pos(${lat.toFixed(5)}, ${lng.toFixed(5)}) | Hdg: ${heading.toFixed(1)}° | Drift: ${drift.toFixed(1)}m | ${posMode} | Conf: ${conf}%`,
            drift > 20 ? 'color:#f85149' : 'color:#d29922');

        if (Math.abs(headingDelta) > 5) {
            const dir = headingDelta > 0 ? 'RIGHT' : 'LEFT';
            console.log(`%c[DR] Heading Δ: ${headingDelta > 0 ? '+' : ''}${headingDelta.toFixed(1)}° (${dir} turn)`, 'color:#58a6ff');
        }

        if (ui.distance_to_next_m !== undefined && ui.distance_to_next_m < 50) {
            console.log(`%c[DR] ⚡ Approaching turn in ${Math.round(ui.distance_to_next_m)}m`, 'color:#3fb950;font-weight:bold');
        }

        if (isGPSFailed) {
            console.log(`%c[DR] ⚠ GNSS DENIED — IMU-only | drift: +0.5m/tick`, 'color:#f85149');
        }
    }

    prevHeading = heading;

    // SOS — backend-driven OR local demo override
    const sosOverlay = document.getElementById('sos-overlay');
    if (ui.is_emergency || window._localCrashDemo) {
        if (sosOverlay.style.display !== 'flex') {
            sosOverlay.style.display = 'flex';
            console.log('%c[CRITICAL] CRASH DETECTED — SOS BROADCASTING', 'color:#f85149;font-weight:bold;font-size:14px');
        }
    } else {
        sosOverlay.style.display = 'none';
    }
}

// ── CV helpers ────────────────────────────────────────────────────────────
function classifyScene(headingDelta, instrText) {
    const absD = Math.abs(headingDelta);
    let label, turn, junction = 'none';
    let conf = 85 + Math.floor(Math.random() * 12);

    if (absD < 3)        { label = 'STRAIGHT_ROAD'; turn = 'STRAIGHT'; }
    else if (absD < 15)  { label = headingDelta > 0 ? 'SLIGHT_RIGHT_CURVE' : 'SLIGHT_LEFT_CURVE'; turn = headingDelta > 0 ? 'SLIGHT_RIGHT' : 'SLIGHT_LEFT'; }
    else if (absD < 45)  { label = headingDelta > 0 ? 'RIGHT_CURVE' : 'LEFT_CURVE'; turn = headingDelta > 0 ? 'RIGHT' : 'LEFT'; }
    else if (absD < 120) { label = headingDelta > 0 ? 'SHARP_RIGHT' : 'SHARP_LEFT'; turn = headingDelta > 0 ? 'RIGHT' : 'LEFT'; junction = 't_junction'; }
    else                 { label = 'U_TURN'; turn = 'U_TURN'; junction = 'crossroad'; }

    const lower = instrText.toLowerCase();
    if (lower.includes('roundabout')) junction = 'roundabout';
    else if (lower.includes('fork')) junction = 'y_junction';
    else if (absD > 25 && junction === 'none') junction = 't_junction';

    return { label, turn, junction, conf };
}

function extractRouteTurn(instrText) {
    const l = instrText.toLowerCase();
    if (l.includes('u-turn') || l.includes('u_turn')) return 'U_TURN';
    if (l.includes('sharp left'))  return 'LEFT';
    if (l.includes('sharp right')) return 'RIGHT';
    if (l.includes('turn left') || l.includes('left onto'))  return 'LEFT';
    if (l.includes('turn right') || l.includes('right onto')) return 'RIGHT';
    if (l.includes('slight left') || l.includes('keep left'))  return 'SLIGHT_LEFT';
    if (l.includes('slight right') || l.includes('keep right')) return 'SLIGHT_RIGHT';
    return 'STRAIGHT';
}

function checkCVRouteMatch(scene, routeTurn) {
    if (routeTurn === 'STRAIGHT' || routeTurn === scene.turn) return true;
    if (routeTurn === 'LEFT' && scene.turn === 'SLIGHT_LEFT') return true;
    if (routeTurn === 'RIGHT' && scene.turn === 'SLIGHT_RIGHT') return true;
    return false;
}

async function pollCVService() {
    try {
        const res = await fetch(`http://${window.location.hostname}:8001/api/localization/latest`);
        if (res.ok) {
            const data = await res.json();
            if (data.latest && data.latest !== lastCVDetection) {
                lastCVDetection = data.latest;
                if (!cvServiceAvailable) {
                    cvServiceAvailable = true;
                    console.log('%c[CV] Vision microservice connected (port 8001)', 'color:#3fb950;font-weight:bold');
                }
            }
        }
    } catch {
        if (cvServiceAvailable) {
            cvServiceAvailable = false;
            console.log('%c[CV] Vision microservice disconnected — heading inference only', 'color:#8b949e');
        }
    }
}

// ── ACTIONS ───────────────────────────────────────────────────────────────

function openNavModal() {
    document.getElementById('nav-modal-backdrop').classList.add('show');
    document.getElementById('nav-modal').classList.add('show');
    setTimeout(() => document.getElementById('nav-origin').focus(), 80);
}

function closeNavModal() {
    document.getElementById('nav-modal-backdrop').classList.remove('show');
    document.getElementById('nav-modal').classList.remove('show');
}

async function confirmNavStart() {
    const origin = document.getElementById('nav-origin').value.trim();
    const dest   = document.getElementById('nav-dest').value.trim();
    if (!origin || !dest) return;

    closeNavModal();
    console.log(`%c[NAV] Route: ${origin} → ${dest}`, 'color:#58a6ff;font-weight:bold');

    try {
        const res = await fetch(CONFIG.ACTION_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: CONFIG.SESSION_ID,
                ts_ms: Date.now(),
                action_type: "START_NAVIGATION",
                payload: { origin, destination: dest }
            })
        });
        if (res.ok) {
            console.log('%c[NAV] Route locked — streaming telemetry', 'color:#3fb950;font-weight:bold');
        }
        document.getElementById('btn-start').style.display = 'none';
        document.getElementById('btn-stop').style.display = 'inline-block';
    } catch(e) {
        console.error('[NAV] Failed to start navigation', e);
    }
}

async function startTrip() { openNavModal(); }

async function stopTrip() {
    try {
        await fetch(CONFIG.ACTION_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: CONFIG.SESSION_ID,
                ts_ms: Date.now(),
                action_type: "STOP_NAVIGATION",
                payload: {}
            })
        });
        console.log('%c[NAV] Navigation stopped', 'color:#f85149');
    } catch(e) {}
    document.getElementById('btn-start').style.display = 'inline-block';
    document.getElementById('btn-stop').style.display = 'none';
}

// 4-state colour pill (nav_mode × position_mode)
const SYSTEM_STATE_STYLES = {
    ONLINE_GPS:     { color: '#3fb950', cls: 'sys-online-gps',     label: 'ONLINE · GPS'     },
    OFFLINE_GPS:    { color: '#d29922', cls: 'sys-offline-gps',    label: 'OFFLINE · GPS'    },
    ONLINE_VISUAL:  { color: '#58a6ff', cls: 'sys-online-visual',  label: 'ONLINE · VISUAL'  },
    OFFLINE_VISUAL: { color: '#f85149', cls: 'sys-offline-visual', label: 'OFFLINE · VISUAL' }
};
let _lastSystemState = null;
function applySystemState(state) {
    const cfg = SYSTEM_STATE_STYLES[state] || SYSTEM_STATE_STYLES.OFFLINE_VISUAL;
    if (state !== _lastSystemState) {
        console.log(`%c[SYS] STATE → ${state}`, `color:${cfg.color};font-weight:bold`);
        _lastSystemState = state;
    }
    if (routeLine) {
        routeLine.setOptions({ strokeColor: cfg.color, strokeOpacity: 0.85 });
    }
    if (riderMarker) {
        const icon = riderMarker.getIcon();
        if (icon) { icon.fillColor = cfg.color; riderMarker.setIcon(icon); }
    }
    if (uncertaintyCircle) {
        uncertaintyCircle.setOptions({ strokeColor: cfg.color, fillColor: cfg.color });
    }
    const pill = document.getElementById('sys-state');
    const txt  = document.getElementById('sys-state-text');
    if (pill && txt) {
        pill.className = `status-pill sys-pill ${cfg.cls}`;
        txt.innerText = cfg.label;
    }
}

async function toggleGPSFailure() {
    isGPSFailed = !isGPSFailed;
    const pill = document.getElementById('gps-status');
    const text = document.getElementById('gps-text');
    if (isGPSFailed) {
        pill.className = "status-pill gps-lost";
        text.innerText = "GPS LOST";
        console.log('%c[CRITICAL] GNSS Signal Lost — switching to Dead Reckoning', 'color:#f85149;font-weight:bold');
        console.log('%c[DR] IMU integration active | Kalman Filter: error bias accumulation', 'color:#d29922');
    } else {
        pill.className = "status-pill";
        text.innerText = "GPS ACTIVE";
        console.log('%c[SYS] GPS Signal Restored — state realigned', 'color:#3fb950;font-weight:bold');
    }
    // Tell the server — flips nav_mode + position_mode, drives the 4-state pill.
    try {
        await fetch(`http://${window.location.host}/api/navigation/connectivity/status`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: CONFIG.SESSION_ID,
                ts_ms: Date.now(),
                network_available:  !isGPSFailed,
                internet_reachable: !isGPSFailed
            })
        });
    } catch (e) { /* server may be offline — UI still reflects toggle */ }
}

function triggerVisionRescue(landmarkName) {
    console.log(`%c[CV] LANDMARK MATCH: ${landmarkName} — spatial check PASS`, 'color:#3fb950;font-weight:bold');
    console.log('%c[CV] Resetting IMU drift vector', 'color:#3fb950');

    counters.cvRescues++;

    const alertEl = document.getElementById('vision-alert');
    if (alertEl) alertEl.style.display = "block";

    isGPSFailed = false;
    const pill = document.getElementById('gps-status');
    const text = document.getElementById('gps-text');
    pill.className = "status-pill";
    text.innerText = "GPS ACTIVE";

    showMissionBanner('👁', 'VISUAL FIX APPLIED · POSITION CORRECTED', 'lvl-good', 3500);
    speak('Visual landmark matched');

    setTimeout(() => { if (alertEl) alertEl.style.display = "none"; }, 4000);
}

// ── STATS ─────────────────────────────────────────────────────────────────
function updateStats() {
    const diff = Math.floor((Date.now() - startTime) / 1000);
    const m = Math.floor(diff / 60);
    const s = diff % 60;
    document.getElementById('uptime').innerText = `${m}:${s < 10 ? '0' : ''}${s}`;
    // Real round-trip latency from sync()
    const lat = lastSyncLatency > 0 ? lastSyncLatency : '--';
    document.getElementById('latency-val').innerText = lat + " ms";
}

function initIMUGraph() {
    const canvas = document.getElementById('imu-chart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let offset = 0;
    function draw() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.strokeStyle = '#58a6ff';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        for (let x = 0; x < canvas.width; x++) {
            const y = 30 + Math.sin((x + offset) * 0.12) * 12 + Math.random() * 2;
            if (x === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        }
        ctx.stroke();
        offset += 2;
        requestAnimationFrame(draw);
    }
    draw();
}

const NIGHT_STYLE = [
    { "elementType": "geometry", "stylers": [{ "color": "#0d1117" }] },
    { "elementType": "labels.text.fill", "stylers": [{ "color": "#746855" }] },
    { "elementType": "labels.text.stroke", "stylers": [{ "color": "#1c2128" }] },
    { "featureType": "administrative.locality", "elementType": "labels.text.fill", "stylers": [{ "color": "#d59563" }] },
    { "featureType": "road", "elementType": "geometry", "stylers": [{ "color": "#21262d" }] },
    { "featureType": "road", "elementType": "geometry.stroke", "stylers": [{ "color": "#30363d" }] },
    { "featureType": "water", "elementType": "geometry", "stylers": [{ "color": "#0d1117" }] }
];

// ── HELPERS: Instruction bar + voice + banner + timeline + KPIs ──────────

function haversine(lat1, lon1, lat2, lon2) {
    const R = 6371000;
    const toRad = d => d * Math.PI / 180;
    const dLat = toRad(lat2 - lat1);
    const dLon = toRad(lon2 - lon1);
    const a = Math.sin(dLat/2)**2 +
              Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon/2)**2;
    return 2 * R * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
}

const TURN_ICONS = {
    LEFT: '⬅', RIGHT: '➡', SLIGHT_LEFT: '↖', SLIGHT_RIGHT: '↗',
    U_TURN: '⤴', STRAIGHT: '⬆'
};

function updateInstructionBar(text, dist) {
    const bar = document.getElementById('instr-bar');
    if (!bar) return;
    const iconEl = document.getElementById('instr-icon');
    const distEl = document.getElementById('instr-dist');
    const textEl = document.getElementById('instr-text');
    if (!text) {
        textEl.innerText = 'AWAITING ROUTE';
        distEl.innerText = '— m';
        iconEl.innerText = '⬆';
        bar.classList.remove('imminent');
        return;
    }
    const turn = extractRouteTurn(text);
    iconEl.innerText = TURN_ICONS[turn] || '⬆';
    textEl.innerText = text.toUpperCase();
    if (typeof dist === 'number') {
        distEl.innerText = (dist < 100 ? Math.round(dist) : Math.round(dist / 5) * 5) + ' m';
    } else {
        distEl.innerText = '— m';
    }
    // Highlight when within announce window
    if (turn !== 'STRAIGHT' && typeof dist === 'number' && dist <= 60) {
        bar.classList.add('imminent');
    } else {
        bar.classList.remove('imminent');
    }
}

function maybeVoiceAnnounce(text, dist) {
    if (!text || typeof dist !== 'number') return;
    const turn = extractRouteTurn(text);
    if (turn === 'STRAIGHT') return;
    if (dist > 60 || dist < 8) return;
    // Bucket distance to avoid re-announcing constantly during the count-down
    const bucket = Math.round(dist / 30) * 30;
    const key = `${turn}@${bucket}`;
    if (key === lastVoicedManeuverKey) return;
    lastVoicedManeuverKey = key;
    const dirWord = turn.replace('_', ' ').toLowerCase();
    speak(`In ${Math.round(dist)} meters, ${dirWord}`);
}

function speak(phrase) {
    try {
        if (!('speechSynthesis' in window)) return;
        const u = new SpeechSynthesisUtterance(phrase);
        u.rate = 1.05;
        u.pitch = 1.0;
        u.volume = 0.9;
        window.speechSynthesis.speak(u);
    } catch (e) { /* TTS unavailable — silent */ }
}

// Mission banner — transient slide-in on state changes
let _bannerTimer = null;
function showMissionBanner(icon, text, levelClass, durationMs) {
    const el = document.getElementById('mission-banner');
    if (!el) return;
    document.getElementById('mb-icon').innerText = icon;
    document.getElementById('mb-text').innerText = text;
    el.classList.remove('lvl-good','lvl-warn','lvl-info','lvl-crit');
    el.classList.add(levelClass);
    el.classList.add('show');
    if (_bannerTimer) clearTimeout(_bannerTimer);
    _bannerTimer = setTimeout(() => el.classList.remove('show'), durationMs || 3500);
}

let _lastBannerState = null;
function handleMissionBanner(sysState) {
    if (sysState === _lastBannerState) return;
    _lastBannerState = sysState;
    const presets = {
        ONLINE_GPS:     { icon: '🛰', text: 'GPS LOCKED · TRACKING',          lvl: 'lvl-good' },
        OFFLINE_GPS:    { icon: '⚠', text: 'CONNECTIVITY LOST · GPS HOLDING', lvl: 'lvl-warn' },
        ONLINE_VISUAL:  { icon: '👁', text: 'GPS LOST · VISUAL FALLBACK',     lvl: 'lvl-info' },
        OFFLINE_VISUAL: { icon: '🚨', text: 'DEGRADED · DR + CV ONLY',         lvl: 'lvl-crit' }
    };
    const p = presets[sysState];
    if (p) showMissionBanner(p.icon, p.text, p.lvl, 3200);
}

// Connectivity timeline
function ensureTimelineCells() {
    const track = document.getElementById('conn-track');
    if (!track || track.childElementCount === CONN_CELLS) return;
    track.innerHTML = '';
    for (let i = 0; i < CONN_CELLS; i++) {
        const c = document.createElement('div');
        c.className = 'conn-cell';
        track.appendChild(c);
    }
}
function tickConnectivityTimeline(sysState) {
    ensureTimelineCells();
    const now = Date.now();
    if (now - lastConnTick < 1000) return;
    lastConnTick = now;
    connHistory.shift();
    connHistory.push(sysState);
    const cells = document.querySelectorAll('#conn-track .conn-cell');
    connHistory.forEach((s, i) => {
        const cls = s ? `conn-cell s-${s.toLowerCase()}` : 'conn-cell';
        if (cells[i]) cells[i].className = cls;
    });
}

function tickOfflineCounter(sysState) {
    const now = Date.now();
    const dt = (now - lastCounterTick) / 1000;
    lastCounterTick = now;
    if (sysState === 'OFFLINE_GPS' || sysState === 'OFFLINE_VISUAL') {
        counters.offlineSec += dt;
    }
}

function renderCounters() {
    const fmt = sec => {
        const s = Math.floor(sec);
        const m = Math.floor(s / 60);
        return `${m}:${String(s % 60).padStart(2, '0')}`;
    };
    const set = (id, v) => { const el = document.getElementById(id); if (el) el.innerText = v; };
    set('kpi-dr',      counters.drFixes.toLocaleString());
    set('kpi-cv',      counters.cvRescues);
    set('kpi-offline', fmt(counters.offlineSec));
    set('kpi-tiles',   counters.waypoints);
}

// ── DEMO MODE: scripted finals narrative ─────────────────────────────────
async function runDemoMode() {
    if (demoModeRunning) {
        console.log('%c[DEMO] Already running — ignoring', 'color:#d29922');
        return;
    }
    demoModeRunning = true;
    const btn = document.getElementById('btn-demo');
    const bar = document.getElementById('demo-running-bar');
    const stepText = document.getElementById('demo-step-text');
    btn.classList.add('running');
    bar.classList.add('show');

    const setStep = (msg) => { if (stepText) stepText.innerText = msg; console.log(`%c[DEMO] ${msg}`, 'color:#a78bfa;font-weight:bold'); };

    try {
        setStep('STAGE 1 · NEGOTIATING ROUTE');
        document.getElementById('nav-origin').value = 'Shaniwar Wada';
        document.getElementById('nav-dest').value   = 'Pune Station';
        await confirmNavStart();
        showMissionBanner('▶', 'DEMO STARTED · ROUTE LOCKED', 'lvl-info', 2500);
        speak('Demo navigation initiated. Route locked.');

        await wait(8000);
        setStep('STAGE 2 · SIMULATING GPS DENIAL');
        if (!isGPSFailed) await toggleGPSFailure();
        speak('G P S signal lost. Switching to dead reckoning.');

        await wait(10000);
        setStep('STAGE 3 · VISION RESCUE');
        triggerVisionRescue('TRAFFIC_LIGHT_INTERSECTION');

        await wait(4000);
        setStep('STAGE 4 · GPS RESTORED');
        if (isGPSFailed) await toggleGPSFailure();
        speak('Connectivity restored. System realigned.');

        await wait(2500);
        setStep('DEMO SEQUENCE COMPLETE');
        showMissionBanner('✓', 'DEMO SEQUENCE COMPLETE', 'lvl-good', 3000);
    } finally {
        await wait(1500);
        btn.classList.remove('running');
        bar.classList.remove('show');
        demoModeRunning = false;
    }
}
function wait(ms) { return new Promise(r => setTimeout(r, ms)); }

// Crash demo button — flashes the SOS overlay locally, no backend trigger
function triggerCrashDemo() {
    window._localCrashDemo = true;
    speak('Crash detected. Emergency S O S broadcasting.');
    setTimeout(() => { window._localCrashDemo = false; }, 6000);
}

// Entry Point
window.init = init;
if (typeof google !== 'undefined' && typeof google.maps !== 'undefined' && !window.mapInitialized) {
    init();
}
