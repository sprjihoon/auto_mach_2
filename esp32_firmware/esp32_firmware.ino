/**
 * ESP32 피킹 디바이스 펌웨어
 * 
 * 기능:
 * - WiFi로 PC WebSocket 서버에 연결
 * - LCD에 BIN ID, 수량 표시
 * - NeoPixel LED로 색상 표시
 * - 버튼 누르면 완료 신호 전송
 * - 버튼 5초 길게 누르면 WiFi 설정 모드 진입
 * 
 * WiFi 설정 모드:
 * - ESP32가 "AutoMach_Setup" 핫스팟 생성
 * - 스마트폰/PC로 접속 후 192.168.4.1 열기
 * - WiFi SSID, 비밀번호, PC IP 주소 설정
 * - 설정 저장 후 자동 재부팅
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
#include <WebServer.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>
#include <Adafruit_NeoPixel.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <Preferences.h>

// ===== 핀 설정 =====
#define BUTTON_PIN      4      // 완료 버튼 (풀업)
#define NEOPIXEL_PIN    15     // NeoPixel 데이터 핀
#define NEOPIXEL_COUNT  8      // NeoPixel LED 개수
#define I2C_SDA         21     // I2C SDA
#define I2C_SCL         22     // I2C SCL

// ===== 설정 모드 =====
#define SETUP_BUTTON_HOLD_TIME  5000   // 5초 길게 누르면 설정 모드
#define AP_SSID                 "AutoMach_Setup"
#define AP_PASSWORD             ""      // 빈 문자열 = 오픈 네트워크

// ===== 객체 생성 =====
WebSocketsClient webSocket;
WebServer server(80);
Adafruit_NeoPixel pixels(NEOPIXEL_COUNT, NEOPIXEL_PIN, NEO_GRB + NEO_KHZ800);
LiquidCrystal_I2C lcd(0x27, 16, 2);
Preferences preferences;

// ===== WiFi 설정 (NVS에서 로드) =====
String wifiSSID = "";
String wifiPassword = "";
String wsHost = "";
int wsPort = 8765;

// ===== 상태 변수 =====
String deviceId = "";
String bindedBinId = "";
String currentMode = "";
int currentQty = 0;
bool isConnected = false;
bool buttonPressed = false;
unsigned long lastButtonTime = 0;
unsigned long buttonPressStart = 0;
bool buttonHeldForSetup = false;
const unsigned long DEBOUNCE_TIME = 300;

// 설정 모드 여부
bool setupMode = false;

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
    return pixels.Color(255, 255, 255);
}

// ===== 디바이스 ID 생성 (MAC 기반) =====
String getDeviceId() {
    uint8_t mac[6];
    WiFi.macAddress(mac);
    char macStr[18];
    sprintf(macStr, "esp32_%02X%02X%02X", mac[3], mac[4], mac[5]);
    return String(macStr);
}

// ===== NVS에서 설정 로드 =====
void loadSettings() {
    preferences.begin("automach", true);  // 읽기 전용
    wifiSSID = preferences.getString("wifi_ssid", "");
    wifiPassword = preferences.getString("wifi_pass", "");
    wsHost = preferences.getString("ws_host", "");
    wsPort = preferences.getInt("ws_port", 8765);
    preferences.end();
    
    Serial.println("=== 저장된 설정 ===");
    Serial.println("WiFi SSID: " + wifiSSID);
    Serial.println("WS Host: " + wsHost);
    Serial.println("WS Port: " + String(wsPort));
}

// ===== NVS에 설정 저장 =====
void saveSettings() {
    preferences.begin("automach", false);  // 쓰기 모드
    preferences.putString("wifi_ssid", wifiSSID);
    preferences.putString("wifi_pass", wifiPassword);
    preferences.putString("ws_host", wsHost);
    preferences.putInt("ws_port", wsPort);
    preferences.end();
    
    Serial.println("설정 저장됨!");
}

// ===== 설정 웹페이지 HTML =====
String getSetupPage() {
    String html = R"(
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AutoMach ESP32 설정</title>
    <style>
        * { box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, sans-serif; }
        body { margin: 0; padding: 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; }
        .container { max-width: 400px; margin: 0 auto; }
        .card { background: white; border-radius: 16px; padding: 30px; box-shadow: 0 10px 40px rgba(0,0,0,0.2); }
        h1 { margin: 0 0 10px 0; color: #333; font-size: 24px; text-align: center; }
        .subtitle { color: #666; text-align: center; margin-bottom: 25px; font-size: 14px; }
        .device-id { background: #f0f0f0; padding: 8px 12px; border-radius: 8px; text-align: center; margin-bottom: 20px; font-family: monospace; }
        .form-group { margin-bottom: 20px; }
        label { display: block; margin-bottom: 8px; font-weight: 600; color: #333; font-size: 14px; }
        input { width: 100%; padding: 14px; border: 2px solid #e0e0e0; border-radius: 10px; font-size: 16px; transition: border-color 0.2s; }
        input:focus { outline: none; border-color: #667eea; }
        .hint { font-size: 12px; color: #888; margin-top: 5px; }
        button { width: 100%; padding: 16px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; border-radius: 10px; font-size: 16px; font-weight: 600; cursor: pointer; transition: transform 0.2s, box-shadow 0.2s; }
        button:hover { transform: translateY(-2px); box-shadow: 0 5px 20px rgba(102,126,234,0.4); }
        button:active { transform: translateY(0); }
        .status { margin-top: 20px; padding: 15px; border-radius: 10px; text-align: center; display: none; }
        .status.success { display: block; background: #d4edda; color: #155724; }
        .status.error { display: block; background: #f8d7da; color: #721c24; }
        .divider { border-top: 1px solid #eee; margin: 25px 0; }
        .section-title { font-size: 12px; color: #888; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 15px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <h1>🔧 AutoMach 설정</h1>
            <p class="subtitle">ESP32 피킹 디바이스 WiFi 설정</p>
            <div class="device-id">)";
    html += deviceId;
    html += R"(</div>
            
            <form action="/save" method="POST">
                <div class="section-title">WiFi 연결</div>
                
                <div class="form-group">
                    <label>WiFi 이름 (SSID)</label>
                    <input type="text" name="ssid" value=")";
    html += wifiSSID;
    html += R"(" required placeholder="WiFi 네트워크 이름">
                </div>
                
                <div class="form-group">
                    <label>WiFi 비밀번호</label>
                    <input type="password" name="password" value=")";
    html += wifiPassword;
    html += R"(" placeholder="비밀번호 입력">
                    <div class="hint">오픈 네트워크는 비워두세요</div>
                </div>
                
                <div class="divider"></div>
                <div class="section-title">서버 연결</div>
                
                <div class="form-group">
                    <label>PC IP 주소</label>
                    <input type="text" name="host" value=")";
    html += wsHost;
    html += R"(" required placeholder="예: 192.168.0.100">
                    <div class="hint">PC에서 ipconfig 명령으로 확인</div>
                </div>
                
                <div class="form-group">
                    <label>포트 번호</label>
                    <input type="number" name="port" value=")";
    html += String(wsPort);
    html += R"(" required placeholder="8765">
                    <div class="hint">기본값: 8765</div>
                </div>
                
                <button type="submit">💾 설정 저장 및 재부팅</button>
            </form>
        </div>
    </div>
</body>
</html>
)";
    return html;
}

// ===== 저장 완료 페이지 =====
String getSavedPage() {
    return R"(
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>설정 완료</title>
    <style>
        * { font-family: -apple-system, BlinkMacSystemFont, sans-serif; }
        body { margin: 0; padding: 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; display: flex; align-items: center; justify-content: center; }
        .card { background: white; border-radius: 16px; padding: 40px; text-align: center; box-shadow: 0 10px 40px rgba(0,0,0,0.2); max-width: 350px; }
        .icon { font-size: 60px; margin-bottom: 20px; }
        h1 { margin: 0 0 15px 0; color: #155724; font-size: 22px; }
        p { color: #666; margin: 0; line-height: 1.6; }
        .countdown { font-size: 48px; color: #667eea; font-weight: bold; margin: 20px 0; }
    </style>
</head>
<body>
    <div class="card">
        <div class="icon">✅</div>
        <h1>설정이 저장되었습니다!</h1>
        <p>ESP32가 재부팅됩니다.<br>새로운 WiFi에 연결을 시도합니다.</p>
        <div class="countdown" id="countdown">3</div>
        <p style="font-size: 12px; color: #888;">이 핫스팟이 곧 사라집니다</p>
    </div>
    <script>
        let count = 3;
        setInterval(() => {
            count--;
            if (count >= 0) document.getElementById('countdown').textContent = count;
        }, 1000);
    </script>
</body>
</html>
)";
}

// ===== 웹서버 핸들러: 메인 페이지 =====
void handleRoot() {
    server.send(200, "text/html", getSetupPage());
}

// ===== 웹서버 핸들러: 설정 저장 =====
void handleSave() {
    if (server.hasArg("ssid")) wifiSSID = server.arg("ssid");
    if (server.hasArg("password")) wifiPassword = server.arg("password");
    if (server.hasArg("host")) wsHost = server.arg("host");
    if (server.hasArg("port")) wsPort = server.arg("port").toInt();
    
    saveSettings();
    
    server.send(200, "text/html", getSavedPage());
    
    // LCD에 표시
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("Settings Saved!");
    lcd.setCursor(0, 1);
    lcd.print("Rebooting...");
    
    // 성공 표시 (초록색)
    for (int i = 0; i < NEOPIXEL_COUNT; i++) {
        pixels.setPixelColor(i, pixels.Color(0, 255, 0));
    }
    pixels.show();
    
    // 3초 후 재부팅
    delay(3000);
    ESP.restart();
}

// ===== 설정 모드 시작 =====
void startSetupMode() {
    setupMode = true;
    
    Serial.println("\n========================================");
    Serial.println("  WiFi 설정 모드 진입!");
    Serial.println("========================================");
    
    // AP 모드로 전환
    WiFi.mode(WIFI_AP);
    WiFi.softAP(AP_SSID, AP_PASSWORD);
    
    IPAddress IP = WiFi.softAPIP();
    Serial.print("AP IP 주소: ");
    Serial.println(IP);
    
    // 웹서버 설정
    server.on("/", handleRoot);
    server.on("/save", HTTP_POST, handleSave);
    server.begin();
    
    Serial.println("웹서버 시작됨!");
    Serial.println("1. '" + String(AP_SSID) + "' WiFi에 연결하세요");
    Serial.println("2. 브라우저에서 http://192.168.4.1 접속");
    Serial.println("========================================\n");
    
    // LCD 표시
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("Setup Mode");
    lcd.setCursor(0, 1);
    lcd.print("192.168.4.1");
    
    // LED 표시 (파란색 순환)
    for (int i = 0; i < NEOPIXEL_COUNT; i++) {
        pixels.setPixelColor(i, pixels.Color(0, 100, 255));
    }
    pixels.show();
}

// ===== WiFi 연결 =====
void connectWiFi() {
    if (wifiSSID.length() == 0) {
        Serial.println("WiFi 설정 없음! 설정 모드로 진입합니다.");
        startSetupMode();
        return;
    }
    
    Serial.println("WiFi 연결 중: " + wifiSSID);
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("WiFi...");
    lcd.setCursor(0, 1);
    lcd.print(wifiSSID.substring(0, 16));
    
    WiFi.mode(WIFI_STA);
    WiFi.begin(wifiSSID.c_str(), wifiPassword.c_str());
    
    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 30) {
        delay(500);
        Serial.print(".");
        
        // 연결 중 LED 애니메이션
        pixels.setPixelColor(attempts % NEOPIXEL_COUNT, pixels.Color(0, 0, 255));
        pixels.show();
        
        attempts++;
    }
    
    // LED 클리어
    pixels.clear();
    pixels.show();
    
    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("\nWiFi 연결됨!");
        Serial.print("IP: ");
        Serial.println(WiFi.localIP());
        
        lcd.clear();
        lcd.setCursor(0, 0);
        lcd.print("WiFi OK");
        lcd.setCursor(0, 1);
        lcd.print(WiFi.localIP());
        
        // 성공 표시 (초록색)
        for (int i = 0; i < NEOPIXEL_COUNT; i++) {
            pixels.setPixelColor(i, pixels.Color(0, 255, 0));
        }
        pixels.show();
        delay(1000);
    } else {
        Serial.println("\nWiFi 연결 실패!");
        Serial.println("설정 모드로 진입합니다...");
        
        lcd.clear();
        lcd.setCursor(0, 0);
        lcd.print("WiFi FAIL");
        lcd.setCursor(0, 1);
        lcd.print("Setup mode...");
        
        // 실패 표시 (빨간색)
        for (int i = 0; i < NEOPIXEL_COUNT; i++) {
            pixels.setPixelColor(i, pixels.Color(255, 0, 0));
        }
        pixels.show();
        delay(2000);
        
        // 설정 모드로 전환
        startSetupMode();
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
            
            for (int i = 0; i < NEOPIXEL_COUNT; i++) {
                pixels.setPixelColor(i, pixels.Color(255, 165, 0));
            }
            pixels.show();
            break;
            
        case WStype_CONNECTED:
            Serial.println("[WS] 연결됨!");
            isConnected = true;
            
            sendHello();
            
            lcd.clear();
            lcd.setCursor(0, 0);
            lcd.print("Connected!");
            lcd.setCursor(0, 1);
            lcd.print(deviceId);
            
            for (int i = 0; i < NEOPIXEL_COUNT; i++) {
                pixels.setPixelColor(i, pixels.Color(0, 255, 0));
            }
            pixels.show();
            delay(500);
            
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
        bindedBinId = doc["bin_id"].as<String>();
        Serial.println("바인딩됨: " + bindedBinId);
        
        lcd.clear();
        lcd.setCursor(0, 0);
        lcd.print("Bound to:");
        lcd.setCursor(0, 1);
        lcd.print(bindedBinId);
        
    } else if (msgType == "display") {
        currentMode = doc["mode"].as<String>();
        String binId = doc["bin"].as<String>();
        String color = doc["color"].as<String>();
        currentQty = doc["qty"].as<int>();
        blinkEnabled = doc["blink"] | false;
        
        Serial.printf("Display: bin=%s, color=%s, qty=%d, blink=%d\n",
                      binId.c_str(), color.c_str(), currentQty, blinkEnabled);
        
        lcd.clear();
        lcd.setCursor(0, 0);
        lcd.print(binId);
        lcd.setCursor(0, 1);
        lcd.print("Qty: ");
        lcd.print(currentQty);
        
        currentColor = getColor(color);
        for (int i = 0; i < NEOPIXEL_COUNT; i++) {
            pixels.setPixelColor(i, currentColor);
        }
        pixels.show();
        
        blinkState = true;
        lastBlinkTime = millis();
        
    } else if (msgType == "off") {
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
    
    for (int i = 0; i < NEOPIXEL_COUNT; i++) {
        pixels.setPixelColor(i, pixels.Color(10, 10, 10));
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

// ===== 버튼 처리 (설정 모드 진입 포함) =====
void handleButton() {
    bool currentState = digitalRead(BUTTON_PIN) == LOW;
    unsigned long now = millis();
    
    if (currentState) {
        // 버튼이 눌려있는 상태
        if (buttonPressStart == 0) {
            buttonPressStart = now;
        }
        
        // 5초 이상 눌렀는지 확인
        if (!buttonHeldForSetup && (now - buttonPressStart >= SETUP_BUTTON_HOLD_TIME)) {
            buttonHeldForSetup = true;
            
            Serial.println("\n버튼 5초 유지 - 설정 모드 진입!");
            
            // LED로 피드백 (보라색 깜빡임)
            for (int i = 0; i < 3; i++) {
                for (int j = 0; j < NEOPIXEL_COUNT; j++) {
                    pixels.setPixelColor(j, pixels.Color(128, 0, 128));
                }
                pixels.show();
                delay(200);
                pixels.clear();
                pixels.show();
                delay(200);
            }
            
            // 설정 모드 시작
            startSetupMode();
        }
        
    } else {
        // 버튼이 떼어진 상태
        if (buttonPressStart > 0 && !buttonHeldForSetup) {
            // 짧게 눌렀다 뗀 경우 (일반 버튼 동작)
            if (now - buttonPressStart > 50 && now - buttonPressStart < SETUP_BUTTON_HOLD_TIME) {
                if (now - lastButtonTime > DEBOUNCE_TIME) {
                    lastButtonTime = now;
                    
                    Serial.println("버튼 눌림!");
                    
                    if (isConnected && !setupMode) {
                        sendDone();
                    }
                }
            }
        }
        
        buttonPressStart = 0;
        buttonHeldForSetup = false;
    }
}

// ===== 설정 모드 LED 애니메이션 =====
void handleSetupModeAnimation() {
    static unsigned long lastAnimTime = 0;
    static int animIndex = 0;
    
    unsigned long now = millis();
    if (now - lastAnimTime >= 200) {
        lastAnimTime = now;
        
        // 순환하는 파란색 LED
        pixels.clear();
        pixels.setPixelColor(animIndex, pixels.Color(0, 100, 255));
        pixels.setPixelColor((animIndex + 1) % NEOPIXEL_COUNT, pixels.Color(0, 50, 128));
        pixels.show();
        
        animIndex = (animIndex + 1) % NEOPIXEL_COUNT;
    }
}

// ===== 설정 =====
void setup() {
    Serial.begin(115200);
    Serial.println("\n\n========================================");
    Serial.println("  ESP32 피킹 디바이스 시작");
    Serial.println("  버튼 5초 누르기 = WiFi 설정 모드");
    Serial.println("========================================");
    
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
    pixels.setBrightness(50);
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
    
    // 저장된 설정 로드
    loadSettings();
    
    // 부팅 시 버튼이 눌려있으면 설정 모드
    if (digitalRead(BUTTON_PIN) == LOW) {
        Serial.println("버튼 누른 채 부팅 - 설정 모드!");
        lcd.clear();
        lcd.setCursor(0, 0);
        lcd.print("Release button");
        lcd.setCursor(0, 1);
        lcd.print("for setup mode");
        
        // 버튼 떼기 대기
        while (digitalRead(BUTTON_PIN) == LOW) {
            delay(100);
        }
        delay(500);
        
        startSetupMode();
        return;
    }
    
    // WiFi 연결
    connectWiFi();
    
    // 설정 모드가 아니면 WebSocket 연결
    if (!setupMode && WiFi.status() == WL_CONNECTED) {
        Serial.println("WebSocket 연결 중: " + wsHost + ":" + String(wsPort));
        
        webSocket.begin(wsHost.c_str(), wsPort, "/");
        webSocket.onEvent(webSocketEvent);
        webSocket.setReconnectInterval(5000);
        
        lcd.clear();
        lcd.setCursor(0, 0);
        lcd.print("Connecting WS...");
        lcd.setCursor(0, 1);
        lcd.print(wsHost);
    }
}

// ===== 메인 루프 =====
void loop() {
    // 버튼 처리 (설정 모드 진입 감지)
    handleButton();
    
    if (setupMode) {
        // 설정 모드: 웹서버 처리
        server.handleClient();
        handleSetupModeAnimation();
        return;
    }
    
    // 일반 모드
    
    // WiFi 재연결
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("WiFi 재연결 시도...");
        connectWiFi();
        
        if (setupMode) return;  // 설정 모드로 전환된 경우
        
        delay(1000);
        return;
    }
    
    // WebSocket 처리
    webSocket.loop();
    
    // 깜빡임 처리
    handleBlink();
}
