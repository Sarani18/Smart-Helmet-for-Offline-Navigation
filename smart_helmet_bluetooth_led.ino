#include <BluetoothSerial.h>

// -------- LED pin mapping (8 LEDs: 4 green, 4 yellow) --------
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

BluetoothSerial SerialBT;
CueMode g_mode = MODE_CLEAR;
String g_lastStatus = "INFO:BOOT";
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
    case MODE_STRAIGHT:
      return "STRAIGHT";
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
    case MODE_SOS_ON:
      return "SOS_ON";
    case MODE_SOS_OFF:
      return "SOS_OFF";
    case MODE_ARRIVED:
      return "ARRIVED";
    default:
      return "UNKNOWN";
  }
}

void sendStatus(const String &text) {
  g_lastStatus = text;
  Serial.println(text);
  SerialBT.println(text);
}

void applyCommand(const String &rawCommand) {
  String command = trimUpper(rawCommand);

  if (command == "CLEAR") {
    g_mode = MODE_CLEAR;
    sendStatus("OK:CLEAR");
    return;
  }
  if (command == "STRAIGHT") {
    g_mode = MODE_STRAIGHT;
    sendStatus("OK:STRAIGHT");
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
  if (command == "SOS_ON") {
    g_mode = MODE_SOS_ON;
    sendStatus("OK:SOS_ON");
    return;
  }
  if (command == "SOS_OFF") {
    g_mode = MODE_SOS_OFF;
    sendStatus("OK:SOS_OFF");
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

void updatePattern() {
  unsigned long nowMs = millis();

  switch (g_mode) {
    case MODE_CLEAR:
    case MODE_STRAIGHT:
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
    case MODE_SOS_ON:
      if (nowMs - g_lastTickMs >= 180) {
        g_lastTickMs = nowMs;
        g_blinkState = !g_blinkState;
      }
      clearAllLeds();
      setGroup(LEFT_YELLOW_PINS, 2, g_blinkState);
      setGroup(RIGHT_YELLOW_PINS, 2, g_blinkState);
      break;

    case MODE_SOS_OFF:
      clearAllLeds();
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

  SerialBT.begin("SmartHelmet-LED");
  sendStatus("INFO:BLUETOOTH_STARTED");

  g_mode = MODE_CLEAR;
  g_lastTickMs = millis();
  g_blinkState = false;
  g_chaseIndex = 0;
}

void loop() {
  updatePattern();

  if (SerialBT.available()) {
    String command = SerialBT.readStringUntil('\n');
    command.trim();
    if (command.length() > 0) {
      applyCommand(command);
    }
  }

  delay(10);
}</content>
<parameter name="filePath">c:\Users\Admin\Desktop\Smart-Helmet-for-Offline-Navigation\smart_helmet_bluetooth_led.ino