#include <WiFi.h>
#include <WebServer.h>
#include <ESPmDNS.h>

// -------- Configuration --------
static const char *DEVICE_NAME = "SmartHelmet-ESP32";

// Optional LAN/phone-hotspot credentials. The ESP32 will try to join this
// network while also keeping its own hotspot active.
static const char *WIFI_SSID = "Vijit hotspot";
static const char *WIFI_PASSWORD = "buvijit1418bu";

// Stable ESP32 hotspot for the phone to connect to directly.
static const char *AP_SSID = "SmartHelmet-ESP32-AP";
static const char *AP_PASSWORD = "helmet1234";

static const unsigned long WIFI_CONNECT_TIMEOUT_MS = 20000;
static const unsigned long WIFI_RETRY_INTERVAL_MS = 15000;
static const unsigned long DEBUG_PRINT_INTERVAL_MS = 5000;

// -------- LED pin mapping --------
static const int LEFT_YELLOW_PINS[2] = {16, 17};
static const int LEFT_GREEN_PINS[2] = {18, 19};
static const int RIGHT_YELLOW_PINS[2] = {21, 22};
static const int RIGHT_GREEN_PINS[2] = {15, 23};

enum CueMode {
  MODE_CLEAR,
  MODE_STRAIGHT,
  MODE_LEFT_PREPARE,
  MODE_LEFT_NOW,
  MODE_LEFT_MISSED,
  MODE_RIGHT_PREPARE,
  MODE_RIGHT_NOW,
  MODE_RIGHT_MISSED,
  MODE_HAZARD,
  MODE_SOS_ON,
  MODE_SOS_OFF,
  MODE_ARRIVED
};

WebServer server(80);
CueMode g_mode = MODE_CLEAR;
String g_lastStatus = "INFO:BOOT";
String g_wifiMode = "NONE";
unsigned long g_lastTickMs = 0;
bool g_blinkState = false;
int g_chaseIndex = 0;
unsigned long g_lastWifiRetryMs = 0;
unsigned long g_lastDebugPrintMs = 0;

// -------- Helper Functions --------

void setGroup(const int *pins, int count, bool on) {
  for (int i = 0; i < count; i++) {
    digitalWrite(pins[i], on ? HIGH : LOW);
  }
}

void clearAllLeds() {
  setGroup(LEFT_YELLOW_PINS, 2, false);
  setGroup(LEFT_GREEN_PINS, 2, false);
  setGroup(RIGHT_YELLOW_PINS, 2, false);
  setGroup(RIGHT_GREEN_PINS, 2, false);
}

void setChase(const int *pins, int count, int activeIndex) {
  for (int i = 0; i < count; i++) {
    digitalWrite(pins[i], (i == activeIndex) ? HIGH : LOW);
  }
}

String trimUpper(String s) {
  s.trim();
  s.toUpperCase();
  return s;
}

const char *modeToString(CueMode mode) {
  switch (mode) {
    case MODE_CLEAR:         return "CLEAR";
    case MODE_STRAIGHT:      return "STRAIGHT";
    case MODE_LEFT_PREPARE:  return "LEFT_PREPARE";
    case MODE_LEFT_NOW:      return "LEFT_NOW";
    case MODE_LEFT_MISSED:   return "LEFT_MISSED";
    case MODE_RIGHT_PREPARE: return "RIGHT_PREPARE";
    case MODE_RIGHT_NOW:     return "RIGHT_NOW";
    case MODE_RIGHT_MISSED:  return "RIGHT_MISSED";
    case MODE_HAZARD:        return "HAZARD";
    case MODE_SOS_ON:        return "SOS_ON";
    case MODE_SOS_OFF:       return "SOS_OFF";
    case MODE_ARRIVED:       return "ARRIVED";
    default:                 return "UNKNOWN";
  }
}

void sendStatus(const String &text) {
  g_lastStatus = text;
  Serial.println(text);
}

const char *wifiStatusToString(wl_status_t status) {
  switch (status) {
    case WL_IDLE_STATUS: return "WL_IDLE_STATUS";
    case WL_NO_SSID_AVAIL: return "WL_NO_SSID_AVAIL";
    case WL_SCAN_COMPLETED: return "WL_SCAN_COMPLETED";
    case WL_CONNECTED: return "WL_CONNECTED";
    case WL_CONNECT_FAILED: return "WL_CONNECT_FAILED";
    case WL_CONNECTION_LOST: return "WL_CONNECTION_LOST";
    case WL_DISCONNECTED: return "WL_DISCONNECTED";
    default: return "WL_UNKNOWN";
  }
}

void printWifiSummary() {
  Serial.println("\n========== SMART HELMET WIFI STATUS ==========");
  Serial.print("Device name: ");
  Serial.println(DEVICE_NAME);
  Serial.print("Firmware millis: ");
  Serial.println(millis());
  Serial.print("Current LED mode: ");
  Serial.println(modeToString(g_mode));
  Serial.print("Last status: ");
  Serial.println(g_lastStatus);

  Serial.print("AP SSID: ");
  Serial.println(AP_SSID);
  Serial.print("AP IP: ");
  Serial.println(WiFi.softAPIP());
  Serial.print("AP stations connected: ");
  Serial.println(WiFi.softAPgetStationNum());

  wl_status_t status = WiFi.status();
  Serial.print("STA target SSID: ");
  Serial.println(WIFI_SSID);
  Serial.print("STA status: ");
  Serial.print((int)status);
  Serial.print(" / ");
  Serial.println(wifiStatusToString(status));
  Serial.print("STA IP: ");
  Serial.println(WiFi.localIP());
  Serial.print("STA gateway: ");
  Serial.println(WiFi.gatewayIP());
  Serial.print("STA RSSI: ");
  Serial.println(status == WL_CONNECTED ? WiFi.RSSI() : 0);
  Serial.println("HTTP endpoints to try from phone:");
  Serial.print("  AP mode:  http://");
  Serial.print(WiFi.softAPIP());
  Serial.println("/status");
  if (status == WL_CONNECTED) {
    Serial.print("  Hotspot:  http://");
    Serial.print(WiFi.localIP());
    Serial.println("/status");
  }
  Serial.println("==============================================\n");
}

void scanForConfiguredWifi() {
  Serial.println("Scanning nearby WiFi networks...");
  int count = WiFi.scanNetworks(false, true);
  if (count < 0) {
    Serial.println("WiFi scan failed or still running.");
    return;
  }

  bool found = false;
  for (int i = 0; i < count; i++) {
    Serial.print("  [");
    Serial.print(i);
    Serial.print("] SSID='");
    Serial.print(WiFi.SSID(i));
    Serial.print("' RSSI=");
    Serial.print(WiFi.RSSI(i));
    Serial.print(" dBm CH=");
    Serial.print(WiFi.channel(i));
    Serial.print(" ENC=");
    Serial.println((int)WiFi.encryptionType(i));
    if (WiFi.SSID(i) == String(WIFI_SSID)) {
      found = true;
    }
  }

  Serial.print("Configured SSID found: ");
  Serial.println(found ? "YES" : "NO");
  WiFi.scanDelete();
}

void setMode(CueMode mode, const String &status) {
  g_mode = mode;
  g_lastTickMs = millis();
  g_blinkState = true;
  g_chaseIndex = 0;
  sendStatus(status);
}

void applyCommand(const String &rawCommand) {
  String command = trimUpper(rawCommand);

  if (command == "CLEAR" || command == "MODE_CLEAR") { setMode(MODE_CLEAR, "OK:CLEAR"); return; }
  if (command == "STRAIGHT" || command == "MODE_STRAIGHT") { setMode(MODE_STRAIGHT, "OK:STRAIGHT"); return; }
  if (command == "LEFT_PREPARE" || command == "MODE_LEFT_PREPARE") { setMode(MODE_LEFT_PREPARE, "OK:LEFT_PREPARE"); return; }
  if (command == "LEFT_NOW" || command == "LEFT" || command == "MODE_LEFT_NOW") { setMode(MODE_LEFT_NOW, "OK:LEFT_NOW"); return; }
  if (command == "LEFT_MISSED" || command == "MODE_LEFT_MISSED") { setMode(MODE_LEFT_MISSED, "OK:LEFT_MISSED"); return; }
  if (command == "RIGHT_PREPARE" || command == "MODE_RIGHT_PREPARE") { setMode(MODE_RIGHT_PREPARE, "OK:RIGHT_PREPARE"); return; }
  if (command == "RIGHT_NOW" || command == "RIGHT" || command == "MODE_RIGHT_NOW") { setMode(MODE_RIGHT_NOW, "OK:RIGHT_NOW"); return; }
  if (command == "RIGHT_MISSED" || command == "MODE_RIGHT_MISSED") { setMode(MODE_RIGHT_MISSED, "OK:RIGHT_MISSED"); return; }
  if (command == "HAZARD" || command == "MODE_HAZARD") { setMode(MODE_HAZARD, "OK:HAZARD"); return; }
  if (command == "SOS_ON" || command == "MODE_SOS_ON") { setMode(MODE_SOS_ON, "OK:SOS_ON"); return; }
  if (command == "SOS_OFF" || command == "MODE_SOS_OFF") { setMode(MODE_SOS_OFF, "OK:SOS_OFF"); return; }
  if (command == "ARRIVED" || command == "MODE_ARRIVED") { setMode(MODE_ARRIVED, "OK:ARRIVED"); return; }
  if (command == "PING") { sendStatus("OK:PONG"); return; }

  sendStatus("ERR:UNKNOWN_COMMAND");
}

String jsonValueForKey(const String &body, const char *key) {
  String quotedKey = "\"" + String(key) + "\"";
  int keyPos = body.indexOf(quotedKey);
  if (keyPos < 0) {
    return "";
  }

  int colonPos = body.indexOf(':', keyPos + quotedKey.length());
  if (colonPos < 0) {
    return "";
  }

  int q1 = body.indexOf('"', colonPos + 1);
  int q2 = body.indexOf('"', q1 + 1);
  if (q1 < 0 || q2 <= q1) {
    return "";
  }

  return body.substring(q1 + 1, q2);
}

String resolveCommandFromRequest() {
  if (server.hasArg("cmd")) {
    return server.arg("cmd");
  }
  if (server.hasArg("command")) {
    return server.arg("command");
  }
  if (server.hasArg("mode")) {
    return server.arg("mode");
  }

  if (server.hasArg("plain")) {
    String body = server.arg("plain");
    body.trim();
    if (body.length() == 0) {
      return "";
    }
    if (!body.startsWith("{")) {
      return body;
    }

    String command = jsonValueForKey(body, "command");
    if (command.length() == 0) {
      command = jsonValueForKey(body, "cmd");
    }
    if (command.length() == 0) {
      command = jsonValueForKey(body, "mode");
    }
    return command;
  }

  return "";
}

void handleHealth() {
  Serial.println("HTTP GET /health");
  server.send(200, "application/json", "{\"ok\":true}");
}

void handleStatus() {
  Serial.println("HTTP GET /status");
  String payload = "{";
  payload += "\"ok\":true,";
  payload += "\"device\":\"" + String(DEVICE_NAME) + "\",";
  payload += "\"status\":\"" + g_lastStatus + "\",";
  payload += "\"mode\":\"" + String(modeToString(g_mode)) + "\",";
  payload += "\"wifi_mode\":\"" + g_wifiMode + "\",";
  payload += "\"ap_ssid\":\"" + String(AP_SSID) + "\",";
  payload += "\"ap_ip\":\"" + WiFi.softAPIP().toString() + "\",";
  payload += "\"sta_ip\":\"" + WiFi.localIP().toString() + "\"";
  payload += "}";
  server.send(200, "application/json", payload);
}

void handleCommand() {
  String command = resolveCommandFromRequest();
  Serial.print("HTTP /command from ");
  Serial.print(server.client().remoteIP());
  Serial.print(" raw='");
  Serial.print(command);
  Serial.println("'");

  if (command.length() == 0) {
    server.send(400, "application/json", "{\"ok\":false,\"error\":\"missing_command\"}");
    return;
  }

  applyCommand(command);
  if (g_lastStatus.startsWith("ERR:")) {
    String payload = "{";
    payload += "\"ok\":false,";
    payload += "\"status\":\"" + g_lastStatus + "\"";
    payload += "}";
    server.send(400, "application/json", payload);
    return;
  }

  String payload = "{";
  payload += "\"ok\":true,";
  payload += "\"status\":\"" + g_lastStatus + "\",";
  payload += "\"mode\":\"" + String(modeToString(g_mode)) + "\"";
  payload += "}";
  server.send(200, "application/json", payload);
}

void handleRoot() {
  Serial.println("HTTP GET /");
  server.send(200, "text/plain", "SmartHelmet ESP32 LED controller");
}

void setupHttpServer() {
  server.on("/", HTTP_GET, handleRoot);
  server.on("/health", HTTP_GET, handleHealth);
  server.on("/status", HTTP_GET, handleStatus);
  server.on("/command", HTTP_GET, handleCommand);
  server.on("/command", HTTP_POST, handleCommand);
  server.begin();
  sendStatus("INFO:HTTP_SERVER_STARTED");
}

void setupWifi() {
  Serial.println("\n========== SMART HELMET BOOT ==========");
  Serial.print("Device name: ");
  Serial.println(DEVICE_NAME);
  Serial.print("Will create fallback AP: ");
  Serial.println(AP_SSID);
  Serial.print("Will try phone hotspot: ");
  Serial.println(WIFI_SSID);

  WiFi.mode(WIFI_AP_STA);
  WiFi.setHostname(DEVICE_NAME);

  bool apOk = WiFi.softAP(AP_SSID, AP_PASSWORD);
  if (apOk) {
    g_wifiMode = "AP";
    sendStatus("INFO:WIFI_AP_STARTED");
    Serial.print("Device name: ");
    Serial.println(DEVICE_NAME);
    Serial.print("AP SSID: ");
    Serial.println(AP_SSID);
    Serial.print("AP IP: ");
    Serial.println(WiFi.softAPIP());
  } else {
    g_wifiMode = "AP_FAILED";
    sendStatus("ERR:WIFI_AP_FAILED");
  }

  scanForConfiguredWifi();

  String ssid = String(WIFI_SSID);
  ssid.trim();
  if (ssid.length() == 0) {
    return;
  }

  Serial.print("\nJoining LAN/hotspot: ");
  Serial.println(WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  unsigned long startMs = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - startMs < WIFI_CONNECT_TIMEOUT_MS) {
    delay(400);
    Serial.print('.');
    if ((millis() - startMs) % 4000 < 450) {
      Serial.print(" ");
      Serial.print(wifiStatusToString(WiFi.status()));
      Serial.print(" ");
    }
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    g_wifiMode = apOk ? "AP_STA" : "STA";
    sendStatus("INFO:WIFI_STA_CONNECTED");
    Serial.print("STA IP: ");
    Serial.println(WiFi.localIP());
    if (MDNS.begin(DEVICE_NAME)) {
      MDNS.addService("http", "tcp", 80);
      Serial.print("mDNS: http://");
      Serial.print(DEVICE_NAME);
      Serial.println(".local/");
    }
  } else if (apOk) {
    sendStatus("INFO:WIFI_STA_FAILED_AP_ACTIVE");
    Serial.print("Final STA status: ");
    Serial.print((int)WiFi.status());
    Serial.print(" / ");
    Serial.println(wifiStatusToString(WiFi.status()));
  } else {
    sendStatus("ERR:WIFI_FAILED");
  }

  printWifiSummary();
}

void maintainWifi() {
  if (WiFi.status() == WL_CONNECTED) {
    return;
  }

  unsigned long nowMs = millis();
  if (nowMs - g_lastWifiRetryMs < WIFI_RETRY_INTERVAL_MS) {
    return;
  }

  g_lastWifiRetryMs = nowMs;
  Serial.print("WiFi STA disconnected, retrying hotspot. Status=");
  Serial.print((int)WiFi.status());
  Serial.print(" / ");
  Serial.println(wifiStatusToString(WiFi.status()));
  WiFi.disconnect(false);
  delay(100);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}

void printPeriodicDebug() {
  unsigned long nowMs = millis();
  if (nowMs - g_lastDebugPrintMs < DEBUG_PRINT_INTERVAL_MS) {
    return;
  }

  g_lastDebugPrintMs = nowMs;
  Serial.print("[debug] mode=");
  Serial.print(modeToString(g_mode));
  Serial.print(" wifi=");
  Serial.print(wifiStatusToString(WiFi.status()));
  Serial.print(" sta_ip=");
  Serial.print(WiFi.localIP());
  Serial.print(" ap_ip=");
  Serial.print(WiFi.softAPIP());
  Serial.print(" ap_clients=");
  Serial.println(WiFi.softAPgetStationNum());
}

void updatePattern() {
  unsigned long nowMs = millis();

  switch (g_mode) {
    case MODE_CLEAR:
    case MODE_STRAIGHT:
      clearAllLeds();
      break;
    case MODE_LEFT_PREPARE:
      if (nowMs - g_lastTickMs >= 550) { g_lastTickMs = nowMs; g_blinkState = !g_blinkState; }
      clearAllLeds(); setGroup(LEFT_YELLOW_PINS, 2, g_blinkState);
      break;
    case MODE_RIGHT_PREPARE:
      if (nowMs - g_lastTickMs >= 550) { g_lastTickMs = nowMs; g_blinkState = !g_blinkState; }
      clearAllLeds(); setGroup(RIGHT_YELLOW_PINS, 2, g_blinkState);
      break;
    case MODE_LEFT_MISSED:
      if (nowMs - g_lastTickMs >= 180) { g_lastTickMs = nowMs; g_blinkState = !g_blinkState; }
      clearAllLeds(); setGroup(LEFT_YELLOW_PINS, 2, g_blinkState);
      break;
    case MODE_RIGHT_MISSED:
      if (nowMs - g_lastTickMs >= 180) { g_lastTickMs = nowMs; g_blinkState = !g_blinkState; }
      clearAllLeds(); setGroup(RIGHT_YELLOW_PINS, 2, g_blinkState);
      break;
    case MODE_LEFT_NOW:
      if (nowMs - g_lastTickMs >= 120) { g_lastTickMs = nowMs; g_chaseIndex = (g_chaseIndex + 1) % 2; }
      clearAllLeds(); setGroup(LEFT_YELLOW_PINS, 2, true); setChase(LEFT_GREEN_PINS, 2, g_chaseIndex);
      break;
    case MODE_RIGHT_NOW:
      if (nowMs - g_lastTickMs >= 120) { g_lastTickMs = nowMs; g_chaseIndex = (g_chaseIndex + 1) % 2; }
      clearAllLeds(); setGroup(RIGHT_YELLOW_PINS, 2, true); setChase(RIGHT_GREEN_PINS, 2, g_chaseIndex);
      break;
    case MODE_HAZARD:
    case MODE_SOS_ON:
      if (nowMs - g_lastTickMs >= 180) { g_lastTickMs = nowMs; g_blinkState = !g_blinkState; }
      clearAllLeds(); setGroup(LEFT_YELLOW_PINS, 2, g_blinkState); setGroup(RIGHT_YELLOW_PINS, 2, g_blinkState);
      break;
    case MODE_SOS_OFF:
      clearAllLeds();
      break;
    case MODE_ARRIVED:
      if (nowMs - g_lastTickMs >= 350) { g_lastTickMs = nowMs; g_blinkState = !g_blinkState; }
      clearAllLeds(); setGroup(LEFT_GREEN_PINS, 2, g_blinkState); setGroup(RIGHT_GREEN_PINS, 2, g_blinkState);
      break;
  }
}

// -------- Main Setup and Loop --------

void setup() {
  Serial.begin(115200);
  delay(200);

  // Pin initialization
  for (int i = 0; i < 2; i++) {
    pinMode(LEFT_YELLOW_PINS[i], OUTPUT);
    pinMode(LEFT_GREEN_PINS[i], OUTPUT);
    pinMode(RIGHT_YELLOW_PINS[i], OUTPUT);
    pinMode(RIGHT_GREEN_PINS[i], OUTPUT);
  }
  clearAllLeds();

  setupWifi();
  setupHttpServer();
  Serial.println("\nSend commands via Serial or HTTP:");
  Serial.println("  GET  http://192.168.4.1/command?cmd=LEFT_PREPARE");
  Serial.println("  POST http://192.168.4.1/command body: LEFT_NOW");
  Serial.println("  Use CLEAR or MODE_CLEAR after a completed turn\n");

  g_mode = MODE_CLEAR;
  g_lastTickMs = millis();
  g_blinkState = false;
  g_chaseIndex = 0;
}

void loop() {
  updatePattern();
  maintainWifi();
  printPeriodicDebug();
  server.handleClient();

  // ====== READ FROM SERIAL MONITOR ======
  if (Serial.available()) {
    String command = Serial.readStringUntil('\n');
    command.trim();
    if (command.length() > 0) {
      Serial.print(">> ");
      if (trimUpper(command) == "STATUS" || trimUpper(command) == "WIFI") {
        printWifiSummary();
        return;
      }
      applyCommand(command);
    }
  }
  delay(5);
}
