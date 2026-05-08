#include <WiFi.h>

// -------- Configuration --------
static const char *WIFI_SSID = "Priyal's S25";
static const char *WIFI_PASSWORD = "priyal@1401";

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

WiFiServer server(80);
CueMode g_mode = MODE_CLEAR;
unsigned long g_lastTickMs = 0;
bool g_blinkState = false;
int g_chaseIndex = 0;

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
  Serial.println(text);
}

void applyCommand(const String &rawCommand) {
  String command = trimUpper(rawCommand);

  if (command == "CLEAR") { g_mode = MODE_CLEAR; sendStatus("OK:CLEAR"); return; }
  if (command == "STRAIGHT") { g_mode = MODE_STRAIGHT; sendStatus("OK:STRAIGHT"); return; }
  if (command == "LEFT_PREPARE") { g_mode = MODE_LEFT_PREPARE; sendStatus("OK:LEFT_PREPARE"); return; }
  if (command == "LEFT_NOW") { g_mode = MODE_LEFT_NOW; sendStatus("OK:LEFT_NOW"); return; }
  if (command == "LEFT_MISSED") { g_mode = MODE_LEFT_MISSED; sendStatus("OK:LEFT_MISSED"); return; }
  if (command == "RIGHT_PREPARE") { g_mode = MODE_RIGHT_PREPARE; sendStatus("OK:RIGHT_PREPARE"); return; }
  if (command == "RIGHT_NOW") { g_mode = MODE_RIGHT_NOW; sendStatus("OK:RIGHT_NOW"); return; }
  if (command == "RIGHT_MISSED") { g_mode = MODE_RIGHT_MISSED; sendStatus("OK:RIGHT_MISSED"); return; }
  if (command == "HAZARD") { g_mode = MODE_HAZARD; sendStatus("OK:HAZARD"); return; }
  if (command == "SOS_ON") { g_mode = MODE_SOS_ON; sendStatus("OK:SOS_ON"); return; }
  if (command == "SOS_OFF") { g_mode = MODE_SOS_OFF; sendStatus("OK:SOS_OFF"); return; }
  if (command == "ARRIVED") { g_mode = MODE_ARRIVED; sendStatus("OK:ARRIVED"); return; }
  if (command == "PING") { sendStatus("OK:PONG"); return; }

  sendStatus("ERR:UNKNOWN_COMMAND");
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

  // WiFi connection
  Serial.print("\nConnecting to WiFi: ");
  Serial.println(WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  unsigned long startMs = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - startMs < 15000) {
    delay(500);
    Serial.print('.');
  }

  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("WiFi Connected!");
    Serial.print("IP Address: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("WiFi Failed!");
  }

  server.begin();
  Serial.println("TCP server started on port 80");
  Serial.println("\nSend commands via Serial or TCP:");
  Serial.println("  LEFT_NOW, LEFT_PREPARE, RIGHT_NOW, RIGHT_PREPARE");
  Serial.println("  HAZARD, ARRIVED, CLEAR, PING\n");

  g_mode = MODE_CLEAR;
  g_lastTickMs = millis();
  g_blinkState = false;
  g_chaseIndex = 0;
}

void loop() {
  updatePattern();

  // ====== READ FROM SERIAL MONITOR ======
  if (Serial.available()) {
    String command = Serial.readStringUntil('\n');
    command.trim();
    if (command.length() > 0) {
      Serial.print(">> ");
      applyCommand(command);
    }
  }

  // ====== READ FROM TCP CLIENT ======
  WiFiClient client = server.available();
  if (!client) {
    return;
  }

  String command = "";
  unsigned long timeoutMs = millis() + 2000;

  while (client.connected() && millis() < timeoutMs) {
    if (client.available()) {
      char c = client.read();
      if (c == '\n') {
        break;
      }
      if (c != '\r') {
        command += c;
      }
    }
  }

  command.trim();
  if (command.length() > 0) {
    applyCommand(command);
  }

  client.println("OK");
  client.stop();
}
