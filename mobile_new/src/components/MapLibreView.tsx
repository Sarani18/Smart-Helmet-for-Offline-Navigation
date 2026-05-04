/**
 * MapLibreView
 *
 * Renders a MapLibre GL map inside a WebView — same library and OSM tile URL
 * as embedded/web_ui/index.html.  No Google Maps SDK required.
 *
 * Communication (RN → WebView) via postMessage:
 *   { type: 'setRoute',   coords: [[lon, lat], ...] }
 *   { type: 'setRider',   lon: number, lat: number, color: string }
 *   { type: 'flyTo',      lon: number, lat: number, zoom?: number }
 */

import React, {forwardRef, useImperativeHandle, useRef} from 'react';
import {StyleSheet, View} from 'react-native';
import WebView from 'react-native-webview';
import type {WebViewMessageEvent} from 'react-native-webview';

// ── types ─────────────────────────────────────────────────────────────────────

export interface MapLibreMessage {
  type: 'setRoute' | 'setRider' | 'flyTo' | 'setMarker';
  coords?: [number, number][];   // [lon, lat] pairs — for setRoute
  lon?: number;
  lat?: number;
  color?: string;
  zoom?: number;
  /** setMarker only — unique id so the marker can be updated in place */
  markerId?: string;
  /** setMarker only — size of the dot in px (default 14) */
  markerSize?: number;
}

export interface MapLibreViewRef {
  send: (msg: MapLibreMessage) => void;
}

interface Props {
  style?: object;
  initialLon: number;
  initialLat: number;
  initialZoom?: number;
  onReady?: () => void;
  onUserInteraction?: () => void;
}

// ── inline HTML ───────────────────────────────────────────────────────────────
// MapLibre 4.7.1 from CDN — same version as embedded/web_ui/index.html
// OSM raster tiles — same tile URL as embedded web UI

function buildHtml(lon: number, lat: number, zoom: number): string {
  return `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no"/>
  <link href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css" rel="stylesheet"/>
  <script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    html, body, #map { width: 100%; height: 100%; }
  </style>
</head>
<body>
  <div id="map"></div>
  <script>
    var map = new maplibregl.Map({
      container: 'map',
      style: {
        version: 8,
        sources: {
          osm: {
            type: 'raster',
            tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
            tileSize: 256,
            attribution: '© OpenStreetMap contributors'
          }
        },
        layers: [{ id: 'osm', type: 'raster', source: 'osm' }]
      },
      center: [${lon}, ${lat}],
      zoom: ${zoom},
      dragPan: true,
      touchZoomRotate: true,
      doubleClickZoom: true,
      scrollZoom: true,
      attributionControl: false
    });

    // Compact attribution
    map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right');

    map.on('load', function() {
      // Route source + layers
      map.addSource('route', {
        type: 'geojson',
        data: { type: 'Feature', geometry: { type: 'LineString', coordinates: [] } }
      });
      map.addLayer({
        id: 'route-casing',
        type: 'line',
        source: 'route',
        layout: { 'line-join': 'round', 'line-cap': 'round' },
        paint: { 'line-color': '#fff', 'line-width': 8 }
      });
      map.addLayer({
        id: 'route-line',
        type: 'line',
        source: 'route',
        layout: { 'line-join': 'round', 'line-cap': 'round' },
        paint: { 'line-color': '#1A73E8', 'line-width': 5 }
      });

      // Rider dot element
      var dotEl = document.createElement('div');
      dotEl.style.cssText = 'width:18px;height:18px;border-radius:50%;background:#1A73E8;border:3px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.4)';
      window._riderMarker = new maplibregl.Marker({ element: dotEl, anchor: 'center' })
        .setLngLat([${lon}, ${lat}])
        .addTo(map);

      // Named static markers registry (origin, dest, etc.)
      window._markers = {};

      var notifyInteraction = function() {
        if (window.ReactNativeWebView) {
          window.ReactNativeWebView.postMessage(JSON.stringify({ type: 'userInteraction' }));
        }
      };
      var canvas = map.getCanvas();
      canvas.addEventListener('touchstart', notifyInteraction, { passive: true });
      canvas.addEventListener('mousedown', notifyInteraction);
      canvas.addEventListener('wheel', notifyInteraction, { passive: true });

      // Signal ready to React Native
      if (window.ReactNativeWebView) {
        window.ReactNativeWebView.postMessage(JSON.stringify({ type: 'ready' }));
      }
    });

    // Handle messages from React Native
    window.addEventListener('message', handleMsg);
    document.addEventListener('message', handleMsg); // Android

    function handleMsg(e) {
      var msg;
      try { msg = JSON.parse(e.data); } catch(_) { return; }

      if (msg.type === 'setRoute' && msg.coords && msg.coords.length > 0) {
        map.getSource('route').setData({
          type: 'Feature',
          geometry: { type: 'LineString', coordinates: msg.coords }
        });
      } else if (msg.type === 'setRider') {
        if (window._riderMarker) {
          window._riderMarker.setLngLat([msg.lon, msg.lat]);
          window._riderMarker.getElement().style.background = msg.color || '#1A73E8';
        }
      } else if (msg.type === 'flyTo') {
        map.flyTo({ center: [msg.lon, msg.lat], zoom: msg.zoom || map.getZoom(), duration: 400 });
      } else if (msg.type === 'setMarker' && msg.markerId) {
        var sz = (msg.markerSize || 14) + 'px';
        if (window._markers[msg.markerId]) {
          window._markers[msg.markerId].setLngLat([msg.lon, msg.lat]);
          window._markers[msg.markerId].getElement().style.background = msg.color || '#1A73E8';
        } else {
          var el = document.createElement('div');
          el.style.cssText = 'width:' + sz + ';height:' + sz + ';border-radius:50%;background:' + (msg.color || '#1A73E8') + ';border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.4)';
          window._markers[msg.markerId] = new maplibregl.Marker({ element: el, anchor: 'center' })
            .setLngLat([msg.lon, msg.lat])
            .addTo(map);
        }
      }
    }
  </script>
</body>
</html>`;
}

// ── component ─────────────────────────────────────────────────────────────────

const MapLibreView = forwardRef<MapLibreViewRef, Props>(
  (
    {style, initialLon, initialLat, initialZoom = 13, onReady, onUserInteraction},
    ref,
  ) => {
    const webviewRef = useRef<WebView>(null);
    const html = buildHtml(initialLon, initialLat, initialZoom);

    useImperativeHandle(ref, () => ({
      send(msg: MapLibreMessage) {
        webviewRef.current?.injectJavaScript(
          `handleMsg({ data: ${JSON.stringify(JSON.stringify(msg))} }); true;`,
        );
      },
    }));

    const handleMessage = (e: WebViewMessageEvent) => {
      try {
        const msg = JSON.parse(e.nativeEvent.data);
        if (msg.type === 'ready') onReady?.();
        if (msg.type === 'userInteraction') onUserInteraction?.();
      } catch (_) {}
    };

    return (
      <View style={[styles.container, style]}>
        <WebView
          ref={webviewRef}
          originWhitelist={['*']}
          source={{html}}
          javaScriptEnabled
          domStorageEnabled
          // Allow fetching OSM tiles and MapLibre CDN assets
          mixedContentMode="always"
          nestedScrollEnabled
          onMessage={handleMessage}
          style={styles.webview}
        />
      </View>
    );
  },
);

const styles = StyleSheet.create({
  container: {overflow: 'hidden'},
  webview: {flex: 1, backgroundColor: '#e8e0d8'},
});

export default MapLibreView;
