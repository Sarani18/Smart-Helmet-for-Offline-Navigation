#include <WiFi.h>
#include <WebServer.h>

// -------- Wi-Fi config --------
// Replace with your home/lab Wi-Fi details.
static const char *WIFI_SSID = "YOUR_WIFI_SSID";
static const char *WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

// Fallback AP (used if STA connection fails or SSID is placeholder).
static const char *FALLBACK_AP_SSID = "SmartHelmet-ESP32-AP";
static const char *FALLBACK_AP_PASSWORD = "helmet1234";

// -------- LED pin mapping (requested: 2-2 each) --------
static const int LEFT_YELLOW_PINS[2] = {16, 17};
static const int LEFT_GREEN_PINS[2] = {18, 19};
static const int RIGHT_YELLOW_PINS[2] = {21, 22};
static const int RIGHT_GREEN_PINS[2] = {15, 23};

enum CueMode {
  MODE_CLEAR,
  MODE_LEFT_PREPARE,
  MODE_LEFT_NOW,
  MODE_LEFT_MISSED,
  MODE_RIGHT_PREPARE,
  MODE_RIGHT_NOW,
  MODE_RIGHT_MISSED,
  MODE_HAZARD,
  MODE_ARRIVED
};

WebServer g_server(80);
CueMode g_mode = MODE_CLEAR;
String g_lastStatus = "INFO:BOOT";
String g_wifiMode = "NONE";
unsigned long g_lastTickMs = 0;
bool g_blinkState = false;
int g_chaseIndex = 0;

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
    case MODE_CLEAR:
      return "CLEAR";
    case MODE_LEFT_PREPARE:
      return "LEFT_PREPARE";
    case MODE_LEFT_NOW:
      return "LEFT_NOW";
    case MODE_LEFT_MISSED:
      return "LEFT_MISSED";
    case MODE_RIGHT_PREPARE:
      return "RIGHT_PREPARE";
    case MODE_RIGHT_NOW:
      return "RIGHT_NOW";
    case MODE_RIGHT_MISSED:
      return "RIGHT_MISSED";
    case MODE_HAZARD:
      return "HAZARD";
    case MODE_ARRIVED:
      return "ARRIVED";
    default:
      return "UNKNOWN";
  }
}

void sendStatus(const String &text) {
  g_lastStatus = text;
  Serial.println(text);
}

void applyCommand(const String &rawCommand) {
  String command = trimUpper(rawCommand);

  if (command == "CLEAR") {
    g_mode = MODE_CLEAR;
    sendStatus("OK:CLEAR");
    return;
  }
  if (command == "LEFT_PREPARE") {
    g_mode = MODE_LEFT_PREPARE;
    sendStatus("OK:LEFT_PREPARE");
    return;
  }
  if (command == "LEFT_NOW") {
    g_mode = MODE_LEFT_NOW;
    sendStatus("OK:LEFT_NOW");
    return;
  }
  if (command == "LEFT_MISSED") {
    g_mode = MODE_LEFT_MISSED;
    sendStatus("OK:LEFT_MISSED");
    return;
  }
  if (command == "RIGHT_PREPARE") {
    g_mode = MODE_RIGHT_PREPARE;
    sendStatus("OK:RIGHT_PREPARE");
    return;
  }
  if (command == "RIGHT_NOW") {
    g_mode = MODE_RIGHT_NOW;
    sendStatus("OK:RIGHT_NOW");
    return;
  }
  if (command == "RIGHT_MISSED") {
    g_mode = MODE_RIGHT_MISSED;
    sendStatus("OK:RIGHT_MISSED");
    return;
  }
  if (command == "HAZARD") {
    g_mode = MODE_HAZARD;
    sendStatus("OK:HAZARD");
    return;
  }
  if (command == "ARRIVED") {
    g_mode = MODE_ARRIVED;
    sendStatus("OK:ARRIVED");
    return;
  }
  if (command == "PING") {
    sendStatus("OK:PONG");
    return;
  }

  sendStatus("ERR:UNKNOWN_COMMAND");
}

String resolveCommandFromRequest() {
  if (g_server.hasArg("cmd")) {
    return g_server.arg("cmd");
  }
  if (g_server.hasArg("command")) {
    return g_server.arg("command");
  }
  if (g_server.hasArg("plain")) {
    String body = g_server.arg("plain");
    body.trim();

    // If plain text command is sent, use directly.
    if (!body.startsWith("{")) {
      return body;
    }

    // Lightweight JSON extraction for {"command":"LEFT_NOW"}
    int keyPos = body.indexOf("\"command\"");
    if (keyPos >= 0) {
      int colonPos = body.indexOf(':', keyPos);
      int q1 = body.indexOf('"', colonPos + 1);
      int q2 = body.indexOf('"', q1 + 1);
      if (q1 >= 0 && q2 > q1) {
        return body.substring(q1 + 1, q2);
      }
    }
  }

  return "";
}

void handleHealth() {
  g_server.send(200, "application/json", "{\"ok\":true}");
}

void handleStatus() {
  String payload = "{";
  payload += "\"status\":\"" + g_lastStatus + "\",";
  payload += "\"mode\":\"" + String(modeToString(g_mode)) + "\",";
  payload += "\"wifi_mode\":\"" + g_wifiMode + "\",";
  payload += "\"ip\":\"" + WiFi.localIP().toString() + "\"";
  payload += "}";
  g_server.send(200, "application/json", payload);
}

void handleCommand() {
  String command = resolveCommandFromRequest();
  if (command.length() == 0) {
    g_server.send(400, "application/json", "{\"ok\":false,\"error\":\"missing_command\"}");
    return;
  }

  applyCommand(command);

  if (g_lastStatus.startsWith("ERR:")) {
    String payload = "{";
    payload += "\"ok\":false,";
    payload += "\"status\":\"" + g_lastStatus + "\"";
    payload += "}";
    g_server.send(400, "application/json", payload);
    return;
  }

  String payload = "{";
  payload += "\"ok\":true,";
  payload += "\"status\":\"" + g_lastStatus + "\",";
  payload += "\"mode\":\"" + String(modeToString(g_mode)) + "\"";
  payload += "}";
  g_server.send(200, "application/json", payload);
}

void setupHttpServer() {
  g_server.on("/health", HTTP_GET, handleHealth);
  g_server.on("/status", HTTP_GET, handleStatus);

  // Supports:
  // GET  /command?cmd=LEFT_PREPARE
  // POST /command with plain body LEFT_PREPARE
  // POST /command with JSON {"command":"LEFT_PREPARE"}
  g_server.on("/command", HTTP_GET, handleCommand);
  g_server.on("/command", HTTP_POST, handleCommand);

  g_server.begin();
  sendStatus("INFO:HTTP_SERVER_STARTED");
}

bool hasPlaceholderWifi() {
  String s = String(WIFI_SSID);
  s.trim();
  return (s.length() == 0 || s.startsWith("YOUR_"));
}

void setupWifi() {
  if (!hasPlaceholderWifi()) {
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    unsigned long startMs = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - startMs < 15000) {
      delay(400);
      Serial.print('.');
    }
    Serial.println();

    if (WiFi.status() == WL_CONNECTED) {
      g_wifiMode = "STA";
      sendStatus("INFO:WIFI_STA_CONNECTED");
      Serial.print("IP: ");
      Serial.println(WiFi.localIP());
      return;
    }
  }

  WiFi.mode(WIFI_AP);
  bool ok = WiFi.softAP(FALLBACK_AP_SSID, FALLBACK_AP_PASSWORD);
  if (ok) {
    g_wifiMode = "AP";
    sendStatus("INFO:WIFI_AP_STARTED");
    Serial.print("AP IP: ");
    Serial.println(WiFi.softAPIP());
    Serial.print("AP SSID: ");
    Serial.println(FALLBACK_AP_SSID);
  } else {
    g_wifiMode = "AP_FAILED";
    sendStatus("ERR:WIFI_AP_FAILED");
  }
}

void updatePattern() {
  unsigned long nowMs = millis();

  switch (g_mode) {
    case MODE_CLEAR:
      clearAllLeds();
      break;

    case MODE_LEFT_PREPARE:
      if (nowMs - g_lastTickMs >= 550) {
        g_lastTickMs = nowMs;
        g_blinkState = !g_blinkState;
      }
      clearAllLeds();
      setGroup(LEFT_YELLOW_PINS, 2, g_blinkState);
      break;

    case MODE_RIGHT_PREPARE:
      if (nowMs - g_lastTickMs >= 550) {
        g_lastTickMs = nowMs;
        g_blinkState = !g_blinkState;
      }
      clearAllLeds();
      setGroup(RIGHT_YELLOW_PINS, 2, g_blinkState);
      break;

    case MODE_LEFT_MISSED:
      if (nowMs - g_lastTickMs >= 180) {
        g_lastTickMs = nowMs;
        g_blinkState = !g_blinkState;
      }
      clearAllLeds();
      setGroup(LEFT_YELLOW_PINS, 2, g_blinkState);
      break;

    case MODE_RIGHT_MISSED:
      if (nowMs - g_lastTickMs >= 180) {
        g_lastTickMs = nowMs;
        g_blinkState = !g_blinkState;
      }
      clearAllLeds();
      setGroup(RIGHT_YELLOW_PINS, 2, g_blinkState);
      break;

    case MODE_LEFT_NOW:
      if (nowMs - g_lastTickMs >= 120) {
        g_lastTickMs = nowMs;
        g_chaseIndex = (g_chaseIndex + 1) % 2;
      }
      clearAllLeds();
      setGroup(LEFT_YELLOW_PINS, 2, true);
      setChase(LEFT_GREEN_PINS, 2, g_chaseIndex);
      break;

    case MODE_RIGHT_NOW:
      if (nowMs - g_lastTickMs >= 120) {
        g_lastTickMs = nowMs;
        g_chaseIndex = (g_chaseIndex + 1) % 2;
      }
      clearAllLeds();
      setGroup(RIGHT_YELLOW_PINS, 2, true);
      setChase(RIGHT_GREEN_PINS, 2, g_chaseIndex);
      break;

    case MODE_HAZARD:
      if (nowMs - g_lastTickMs >= 180) {
        g_lastTickMs = nowMs;
        g_blinkState = !g_blinkState;
      }
      clearAllLeds();
      setGroup(LEFT_YELLOW_PINS, 2, g_blinkState);
      setGroup(RIGHT_YELLOW_PINS, 2, g_blinkState);
      break;

    case MODE_ARRIVED:
      if (nowMs - g_lastTickMs >= 350) {
        g_lastTickMs = nowMs;
        g_blinkState = !g_blinkState;
      }
      clearAllLeds();
      setGroup(LEFT_GREEN_PINS, 2, g_blinkState);
      setGroup(RIGHT_GREEN_PINS, 2, g_blinkState);
      break;
  }
}

void setupPins() {
  for (int i = 0; i < 2; i++) {
    pinMode(LEFT_YELLOW_PINS[i], OUTPUT);
    pinMode(LEFT_GREEN_PINS[i], OUTPUT);
    pinMode(RIGHT_YELLOW_PINS[i], OUTPUT);
    pinMode(RIGHT_GREEN_PINS[i], OUTPUT);
  }
  clearAllLeds();
}

void setup() {
  Serial.begin(115200);
  delay(200);

  setupPins();
  setupWifi();
  setupHttpServer();

  g_mode = MODE_CLEAR;
  g_lastTickMs = millis();
  g_blinkState = false;
  g_chaseIndex = 0;
}

void loop() {
  updatePattern();
  g_server.handleClient();
  delay(10);
}
