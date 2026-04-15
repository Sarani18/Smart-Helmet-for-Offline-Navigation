#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

// BLE identity
static const char *DEVICE_NAME = "SmartHelmet-ESP32";

// UUIDs shared with laptop tools
static const char *SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e";
static const char *COMMAND_CHAR_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e";
static const char *STATUS_CHAR_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e";

// Pin mapping for ESP32 DevKit V1 (safe output pins)
static const int LEFT_YELLOW_PINS[3] = {16, 17, 18};
static const int LEFT_GREEN_PINS[3] = {19, 21, 22};
static const int RIGHT_YELLOW_PINS[3] = {23, 25, 26};
static const int RIGHT_GREEN_PINS[3] = {27, 32, 33};

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

BLEServer *g_server = nullptr;
BLECharacteristic *g_commandChar = nullptr;
BLECharacteristic *g_statusChar = nullptr;

bool g_deviceConnected = false;
bool g_oldDeviceConnected = false;
CueMode g_mode = MODE_CLEAR;
unsigned long g_lastTickMs = 0;
bool g_blinkState = false;
int g_chaseIndex = 0;

void setGroup(const int *pins, int count, bool on) {
  for (int i = 0; i < count; i++) {
    digitalWrite(pins[i], on ? HIGH : LOW);
  }
}

void clearAllLeds() {
  setGroup(LEFT_YELLOW_PINS, 3, false);
  setGroup(LEFT_GREEN_PINS, 3, false);
  setGroup(RIGHT_YELLOW_PINS, 3, false);
  setGroup(RIGHT_GREEN_PINS, 3, false);
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

void sendStatus(const String &text) {
  if (g_statusChar == nullptr) {
    return;
  }
  g_statusChar->setValue(text.c_str());
  if (g_deviceConnected) {
    g_statusChar->notify();
  }
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

class ServerCallbacks : public BLEServerCallbacks {
  void onConnect(BLEServer *server) override {
    (void)server;
    g_deviceConnected = true;
    sendStatus("INFO:BLE_CONNECTED");
  }

  void onDisconnect(BLEServer *server) override {
    (void)server;
    g_deviceConnected = false;
    sendStatus("INFO:BLE_DISCONNECTED");
  }
};

class CommandCallbacks : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *characteristic) override {
    std::string value = characteristic->getValue();
    if (value.empty()) {
      return;
    }
    String command;
    for (size_t i = 0; i < value.length(); i++) {
      command += static_cast<char>(value[i]);
    }
    applyCommand(command);
  }
};

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
      setGroup(LEFT_YELLOW_PINS, 3, g_blinkState);
      break;

    case MODE_RIGHT_PREPARE:
      if (nowMs - g_lastTickMs >= 550) {
        g_lastTickMs = nowMs;
        g_blinkState = !g_blinkState;
      }
      clearAllLeds();
      setGroup(RIGHT_YELLOW_PINS, 3, g_blinkState);
      break;

    case MODE_LEFT_MISSED:
      if (nowMs - g_lastTickMs >= 180) {
        g_lastTickMs = nowMs;
        g_blinkState = !g_blinkState;
      }
      clearAllLeds();
      setGroup(LEFT_YELLOW_PINS, 3, g_blinkState);
      break;

    case MODE_RIGHT_MISSED:
      if (nowMs - g_lastTickMs >= 180) {
        g_lastTickMs = nowMs;
        g_blinkState = !g_blinkState;
      }
      clearAllLeds();
      setGroup(RIGHT_YELLOW_PINS, 3, g_blinkState);
      break;

    case MODE_LEFT_NOW:
      if (nowMs - g_lastTickMs >= 120) {
        g_lastTickMs = nowMs;
        g_chaseIndex = (g_chaseIndex + 1) % 3;
      }
      clearAllLeds();
      setGroup(LEFT_YELLOW_PINS, 3, true);
      setChase(LEFT_GREEN_PINS, 3, g_chaseIndex);
      break;

    case MODE_RIGHT_NOW:
      if (nowMs - g_lastTickMs >= 120) {
        g_lastTickMs = nowMs;
        g_chaseIndex = (g_chaseIndex + 1) % 3;
      }
      clearAllLeds();
      setGroup(RIGHT_YELLOW_PINS, 3, true);
      setChase(RIGHT_GREEN_PINS, 3, g_chaseIndex);
      break;

    case MODE_HAZARD:
      if (nowMs - g_lastTickMs >= 180) {
        g_lastTickMs = nowMs;
        g_blinkState = !g_blinkState;
      }
      clearAllLeds();
      setGroup(LEFT_YELLOW_PINS, 3, g_blinkState);
      setGroup(RIGHT_YELLOW_PINS, 3, g_blinkState);
      break;

    case MODE_ARRIVED:
      if (nowMs - g_lastTickMs >= 350) {
        g_lastTickMs = nowMs;
        g_blinkState = !g_blinkState;
      }
      clearAllLeds();
      setGroup(LEFT_GREEN_PINS, 3, g_blinkState);
      setGroup(RIGHT_GREEN_PINS, 3, g_blinkState);
      break;
  }
}

void setupPins() {
  for (int i = 0; i < 3; i++) {
    pinMode(LEFT_YELLOW_PINS[i], OUTPUT);
    pinMode(LEFT_GREEN_PINS[i], OUTPUT);
    pinMode(RIGHT_YELLOW_PINS[i], OUTPUT);
    pinMode(RIGHT_GREEN_PINS[i], OUTPUT);
  }
  clearAllLeds();
}

void setupBle() {
  BLEDevice::init(DEVICE_NAME);

  g_server = BLEDevice::createServer();
  g_server->setCallbacks(new ServerCallbacks());

  BLEService *service = g_server->createService(SERVICE_UUID);

  g_commandChar = service->createCharacteristic(
      COMMAND_CHAR_UUID,
      BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR);
  g_commandChar->setCallbacks(new CommandCallbacks());

  g_statusChar = service->createCharacteristic(
      STATUS_CHAR_UUID,
      BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY);
  g_statusChar->addDescriptor(new BLE2902());
  g_statusChar->setValue("INFO:BOOT");

  service->start();

  BLEAdvertising *advertising = BLEDevice::getAdvertising();
  advertising->addServiceUUID(SERVICE_UUID);
  advertising->setScanResponse(true);
  advertising->setMinPreferred(0x06);
  advertising->setMinPreferred(0x12);
  BLEDevice::startAdvertising();

  sendStatus("INFO:BLE_ADVERTISING");
}

void setup() {
  Serial.begin(115200);
  delay(200);

  setupPins();
  setupBle();

  g_mode = MODE_CLEAR;
  g_lastTickMs = millis();
  g_blinkState = false;
  g_chaseIndex = 0;
}

void loop() {
  updatePattern();

  if (!g_deviceConnected && g_oldDeviceConnected) {
    delay(200);
    g_server->startAdvertising();
    g_oldDeviceConnected = g_deviceConnected;
  }

  if (g_deviceConnected && !g_oldDeviceConnected) {
    g_oldDeviceConnected = g_deviceConnected;
  }

  delay(10);
}
