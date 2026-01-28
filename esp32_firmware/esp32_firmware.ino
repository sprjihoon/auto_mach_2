/**
 * ESP32 피킹 디바이스 펌웨어
 * 
 * 기능:
 * - WiFi로 PC WebSocket 서버에 연결
 * - LCD에 BIN ID, 수량 표시
 * - NeoPixel LED로 색상 표시
 * - 버튼 누르면 완료 신호 전송
 * 
 * 하드웨어:
 * - ESP32 DevKit
 * - I2C LCD 16x2 (주소 0x27)
 * - WS2812B NeoPixel (GPIO 15)
 * - 버튼 (GPIO 4, 풀업)
 * 
 * 라이브러리 필요:
 * - ArduinoJson
 * - WebSockets by Markus Sattler
 * - Adafruit NeoPixel
 * - LiquidCrystal_I2C
 */

#include <WiFi.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>
#include <Adafruit_NeoPixel.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>

// ===== WiFi 설정 (수정 필요!) =====
const char* WIFI_SSID = "YOUR_WIFI_SSID";      // WiFi 이름
const char* WIFI_PASSWORD = "YOUR_WIFI_PASS";  // WiFi 비밀번호
const char* WS_HOST = "192.168.1.13";          // PC IP 주소
const int WS_PORT = 8765;                       // WebSocket 포트

// ===== 핀 설정 =====
#define BUTTON_PIN      4      // 완료 버튼 (풀업)
#define NEOPIXEL_PIN    15     // NeoPixel 데이터 핀
#define NEOPIXEL_COUNT  8      // NeoPixel LED 개수
#define I2C_SDA         21     // I2C SDA
#define I2C_SCL         22     // I2C SCL

// ===== 객체 생성 =====
WebSocketsClient webSocket;
Adafruit_NeoPixel pixels(NEOPIXEL_COUNT, NEOPIXEL_PIN, NEO_GRB + NEO_KHZ800);
LiquidCrystal_I2C lcd(0x27, 16, 2);  // I2C 주소 0x27, 16x2 LCD

// ===== 상태 변수 =====
String deviceId = "";
String bindedBinId = "";
String currentMode = "";
int currentQty = 0;
bool isConnected = false;
bool buttonPressed = false;
unsigned long lastButtonTime = 0;
const unsigned long DEBOUNCE_TIME = 300;

// 깜빡임 관련
bool blinkEnabled = false;
unsigned long lastBlinkTime = 0;
bool blinkState = true;
const unsigned long BLINK_INTERVAL = 500;

// 현재 색상
uint32_t currentColor = 0;

// ===== 색상 정의 =====
uint32_t getColor(String colorName) {
    if (colorName == "purple" || colorName == "보라") {
        return pixels.Color(128, 0, 128);
    } else if (colorName == "green" || colorName == "초록") {
        return pixels.Color(0, 255, 0);
    } else if (colorName == "red" || colorName == "빨강") {
        return pixels.Color(255, 0, 0);
    } else if (colorName == "blue" || colorName == "파랑") {
        return pixels.Color(0, 0, 255);
    } else if (colorName == "yellow" || colorName == "노랑") {
        return pixels.Color(255, 255, 0);
    } else if (colorName == "orange" || colorName == "주황") {
        return pixels.Color(255, 165, 0);
    } else if (colorName == "white" || colorName == "흰색") {
        return pixels.Color(255, 255, 255);
    } else if (colorName == "cyan" || colorName == "청록") {
        return pixels.Color(0, 255, 255);
    }
    return pixels.Color(255, 255, 255);  // 기본 흰색
}

// ===== 디바이스 ID 생성 (MAC 기반) =====
String getDeviceId() {
    uint8_t mac[6];
    WiFi.macAddress(mac);
    char macStr[18];
    sprintf(macStr, "esp32_%02X%02X%02X", mac[3], mac[4], mac[5]);
    return String(macStr);
}

// ===== WiFi 연결 =====
void connectWiFi() {
    Serial.println("WiFi 연결 중...");
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("WiFi...");
    
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    
    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 30) {
        delay(500);
        Serial.print(".");
        attempts++;
    }
    
    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("\nWiFi 연결됨!");
        Serial.print("IP: ");
        Serial.println(WiFi.localIP());
        
        lcd.clear();
        lcd.setCursor(0, 0);
        lcd.print("WiFi OK");
        lcd.setCursor(0, 1);
        lcd.print(WiFi.localIP());
        delay(1000);
    } else {
        Serial.println("\nWiFi 연결 실패!");
        lcd.clear();
        lcd.setCursor(0, 0);
        lcd.print("WiFi FAIL");
        
        // 실패 표시 (빨간색)
        for (int i = 0; i < NEOPIXEL_COUNT; i++) {
            pixels.setPixelColor(i, pixels.Color(255, 0, 0));
        }
        pixels.show();
    }
}

// ===== WebSocket 이벤트 핸들러 =====
void webSocketEvent(WStype_t type, uint8_t* payload, size_t length) {
    switch (type) {
        case WStype_DISCONNECTED:
            Serial.println("[WS] 연결 해제됨");
            isConnected = false;
            lcd.clear();
            lcd.setCursor(0, 0);
            lcd.print("Disconnected");
            
            // 연결 해제 표시 (주황색)
            for (int i = 0; i < NEOPIXEL_COUNT; i++) {
                pixels.setPixelColor(i, pixels.Color(255, 165, 0));
            }
            pixels.show();
            break;
            
        case WStype_CONNECTED:
            Serial.println("[WS] 연결됨!");
            isConnected = true;
            
            // hello 메시지 전송
            sendHello();
            
            lcd.clear();
            lcd.setCursor(0, 0);
            lcd.print("Connected!");
            lcd.setCursor(0, 1);
            lcd.print(deviceId);
            
            // 연결 성공 표시 (초록색)
            for (int i = 0; i < NEOPIXEL_COUNT; i++) {
                pixels.setPixelColor(i, pixels.Color(0, 255, 0));
            }
            pixels.show();
            delay(500);
            
            // 대기 상태
            showStandby();
            break;
            
        case WStype_TEXT:
            Serial.printf("[WS] 수신: %s\n", payload);
            handleMessage((char*)payload);
            break;
            
        case WStype_ERROR:
            Serial.println("[WS] 에러!");
            break;
    }
}

// ===== Hello 메시지 전송 =====
void sendHello() {
    StaticJsonDocument<128> doc;
    doc["type"] = "hello";
    doc["device_id"] = deviceId;
    
    String json;
    serializeJson(doc, json);
    webSocket.sendTXT(json);
    Serial.println("[WS] Hello 전송: " + json);
}

// ===== Done 메시지 전송 =====
void sendDone() {
    if (bindedBinId.length() == 0) {
        Serial.println("[WS] BIN 바인딩 안됨, done 전송 안함");
        return;
    }
    
    StaticJsonDocument<128> doc;
    doc["type"] = "done";
    doc["bin_id"] = bindedBinId;
    doc["device_id"] = deviceId;
    
    String json;
    serializeJson(doc, json);
    webSocket.sendTXT(json);
    Serial.println("[WS] Done 전송: " + json);
    
    // 완료 표시 (잠깐 초록색 깜빡임)
    for (int i = 0; i < 3; i++) {
        for (int j = 0; j < NEOPIXEL_COUNT; j++) {
            pixels.setPixelColor(j, pixels.Color(0, 255, 0));
        }
        pixels.show();
        delay(100);
        for (int j = 0; j < NEOPIXEL_COUNT; j++) {
            pixels.setPixelColor(j, 0);
        }
        pixels.show();
        delay(100);
    }
    
    // 대기 상태로 복귀
    showStandby();
}

// ===== 메시지 처리 =====
void handleMessage(const char* payload) {
    StaticJsonDocument<256> doc;
    DeserializationError error = deserializeJson(doc, payload);
    
    if (error) {
        Serial.println("JSON 파싱 오류!");
        return;
    }
    
    String msgType = doc["type"].as<String>();
    
    if (msgType == "bind") {
        // 바인딩 명령
        bindedBinId = doc["bin_id"].as<String>();
        Serial.println("바인딩됨: " + bindedBinId);
        
        lcd.clear();
        lcd.setCursor(0, 0);
        lcd.print("Bound to:");
        lcd.setCursor(0, 1);
        lcd.print(bindedBinId);
        
    } else if (msgType == "display") {
        // 디스플레이 명령
        currentMode = doc["mode"].as<String>();
        String binId = doc["bin"].as<String>();
        String color = doc["color"].as<String>();
        currentQty = doc["qty"].as<int>();
        blinkEnabled = doc["blink"] | false;
        
        Serial.printf("Display: bin=%s, color=%s, qty=%d, blink=%d\n",
                      binId.c_str(), color.c_str(), currentQty, blinkEnabled);
        
        // LCD 표시
        lcd.clear();
        lcd.setCursor(0, 0);
        lcd.print(binId);
        lcd.setCursor(0, 1);
        lcd.print("Qty: ");
        lcd.print(currentQty);
        
        // LED 색상 설정
        currentColor = getColor(color);
        for (int i = 0; i < NEOPIXEL_COUNT; i++) {
            pixels.setPixelColor(i, currentColor);
        }
        pixels.show();
        
        blinkState = true;
        lastBlinkTime = millis();
        
    } else if (msgType == "off") {
        // LED/LCD 끄기
        Serial.println("Display OFF");
        
        blinkEnabled = false;
        currentColor = 0;
        
        for (int i = 0; i < NEOPIXEL_COUNT; i++) {
            pixels.setPixelColor(i, 0);
        }
        pixels.show();
        
        showStandby();
    }
}

// ===== 대기 상태 표시 =====
void showStandby() {
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("Ready");
    lcd.setCursor(0, 1);
    if (bindedBinId.length() > 0) {
        lcd.print(bindedBinId);
    } else {
        lcd.print("(unbound)");
    }
    
    // LED 끄기 또는 희미하게
    for (int i = 0; i < NEOPIXEL_COUNT; i++) {
        pixels.setPixelColor(i, pixels.Color(10, 10, 10));  // 희미한 흰색
    }
    pixels.show();
}

// ===== 깜빡임 처리 =====
void handleBlink() {
    if (!blinkEnabled || currentColor == 0) return;
    
    unsigned long now = millis();
    if (now - lastBlinkTime >= BLINK_INTERVAL) {
        lastBlinkTime = now;
        blinkState = !blinkState;
        
        for (int i = 0; i < NEOPIXEL_COUNT; i++) {
            if (blinkState) {
                pixels.setPixelColor(i, currentColor);
            } else {
                pixels.setPixelColor(i, 0);
            }
        }
        pixels.show();
    }
}

// ===== 버튼 처리 =====
void handleButton() {
    bool currentState = digitalRead(BUTTON_PIN) == LOW;  // 풀업이므로 LOW가 눌림
    unsigned long now = millis();
    
    if (currentState && !buttonPressed && (now - lastButtonTime > DEBOUNCE_TIME)) {
        buttonPressed = true;
        lastButtonTime = now;
        
        Serial.println("버튼 눌림!");
        
        if (isConnected) {
            sendDone();
        }
    } else if (!currentState) {
        buttonPressed = false;
    }
}

// ===== 설정 =====
void setup() {
    Serial.begin(115200);
    Serial.println("\n\n=== ESP32 피킹 디바이스 시작 ===");
    
    // 버튼 핀 설정
    pinMode(BUTTON_PIN, INPUT_PULLUP);
    
    // I2C 초기화
    Wire.begin(I2C_SDA, I2C_SCL);
    
    // LCD 초기화
    lcd.init();
    lcd.backlight();
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("Initializing...");
    
    // NeoPixel 초기화
    pixels.begin();
    pixels.setBrightness(50);  // 밝기 50/255
    pixels.clear();
    pixels.show();
    
    // 시작 애니메이션
    for (int i = 0; i < NEOPIXEL_COUNT; i++) {
        pixels.setPixelColor(i, pixels.Color(0, 0, 255));
        pixels.show();
        delay(50);
    }
    
    // 디바이스 ID 생성
    deviceId = getDeviceId();
    Serial.println("Device ID: " + deviceId);
    
    // WiFi 연결
    connectWiFi();
    
    // WebSocket 설정
    if (WiFi.status() == WL_CONNECTED) {
        webSocket.begin(WS_HOST, WS_PORT, "/");
        webSocket.onEvent(webSocketEvent);
        webSocket.setReconnectInterval(5000);  // 5초마다 재연결 시도
        
        lcd.clear();
        lcd.setCursor(0, 0);
        lcd.print("Connecting WS...");
    }
}

// ===== 메인 루프 =====
void loop() {
    // WiFi 재연결
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("WiFi 재연결 시도...");
        connectWiFi();
        delay(1000);
        return;
    }
    
    // WebSocket 처리
    webSocket.loop();
    
    // 버튼 처리
    handleButton();
    
    // 깜빡임 처리
    handleBlink();
}
