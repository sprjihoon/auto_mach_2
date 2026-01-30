/**
 * ESP32 피킹 디바이스 펌웨어
 * 
 * 하드웨어: ESP32-2432S028 (Cheap Yellow Display)
 * - 2.8" TFT 320x240 ILI9341
 * - 터치스크린 (XPT2046) - 미사용
 * - RGB LED
 * 
 * 기능:
 * - WiFi로 PC WebSocket 서버에 연결
 * - TFT에 BIN ID, 수량 표시
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
 * 라이브러리 필요:
 * - TFT_eSPI (설정 필요)
 * - ArduinoJson
 * - WebSockets by Markus Sattler
 * - Adafruit NeoPixel
 */

#include <WiFi.h>
#include <WebServer.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>
#include <Adafruit_NeoPixel.h>
#include <Preferences.h>
#include <TFT_eSPI.h>
#include <SPI.h>

// ===== CYD 핀 설정 =====
// TFT는 TFT_eSPI User_Setup.h에서 설정됨
#define BUTTON_PIN      0       // BOOT 버튼 (GPIO 0)
#define NEOPIXEL_PIN    27      // 외부 NeoPixel (또는 RGB LED)
#define NEOPIXEL_COUNT  8       // NeoPixel LED 개수

// CYD 내장 RGB LED (active low)
#define CYD_LED_RED     4
#define CYD_LED_GREEN   16
#define CYD_LED_BLUE    17

// TFT 백라이트
#define TFT_BL          21

// ===== 설정 모드 =====
#define SETUP_BUTTON_HOLD_TIME  5000   // 5초 길게 누르면 설정 모드
#define AP_SSID                 "AutoMach_Setup"
#define AP_PASSWORD             ""      // 빈 문자열 = 오픈 네트워크

// ===== 색상 정의 (16비트 RGB565) =====
#define COLOR_BG        TFT_BLACK
#define COLOR_TEXT      TFT_WHITE
#define COLOR_TITLE     TFT_CYAN
#define COLOR_SUCCESS   TFT_GREEN
#define COLOR_ERROR     TFT_RED
#define COLOR_WARNING   TFT_ORANGE
#define COLOR_INFO      TFT_YELLOW
#define COLOR_SETUP     0x5D1F  // 보라색

// ===== 객체 생성 =====
TFT_eSPI tft = TFT_eSPI();
WebSocketsClient webSocket;
WebServer server(80);
Adafruit_NeoPixel pixels(NEOPIXEL_COUNT, NEOPIXEL_PIN, NEO_GRB + NEO_KHZ800);
Preferences preferences;

// ===== WiFi 설정 (NVS에서 로드) =====
String wifiSSID = "spring303";
String wifiPassword = "wkdwlgns";
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

// ===== TFT 화면 유틸리티 =====
void tftClear() {
    // 전체 화면을 명시적으로 클리어 (노이즈 방지)
    tft.fillRect(0, 0, tft.width(), tft.height(), COLOR_BG);
}

void tftDrawCentered(const char* text, int y, uint16_t color, int textSize) {
    tft.setTextColor(color, COLOR_BG);
    tft.setTextSize(textSize);
    int textWidth = strlen(text) * 6 * textSize;
    int x = (tft.width() - textWidth) / 2;
    if (x < 0) x = 0;
    tft.setCursor(x, y);
    tft.print(text);
}

void tftDrawText(const char* text, int x, int y, uint16_t color, int textSize) {
    tft.setTextColor(color, COLOR_BG);
    tft.setTextSize(textSize);
    tft.setCursor(x, y);
    tft.print(text);
}

void tftDrawBigNumber(int num, int y, uint16_t color) {
    char buf[16];
    sprintf(buf, "%d", num);
    tft.setTextColor(color, COLOR_BG);
    tft.setTextSize(8);
    int textWidth = strlen(buf) * 6 * 8;
    int x = (tft.width() - textWidth) / 2;
    if (x < 0) x = 0;
    tft.setCursor(x, y);
    tft.print(buf);
}

void tftDrawStatusBar(const char* status, uint16_t bgColor) {
    tft.fillRect(0, tft.height() - 30, tft.width(), 30, bgColor);
    tft.setTextColor(TFT_WHITE, bgColor);
    tft.setTextSize(2);
    int textWidth = strlen(status) * 6 * 2;
    int x = (tft.width() - textWidth) / 2;
    tft.setCursor(x, tft.height() - 22);
    tft.print(status);
}

// ===== CYD 내장 LED 제어 =====
void setCydLed(bool r, bool g, bool b) {
    digitalWrite(CYD_LED_RED, !r);    // Active low
    digitalWrite(CYD_LED_GREEN, !g);
    digitalWrite(CYD_LED_BLUE, !b);
}

// ===== 색상 정의 (NeoPixel용) =====
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

// 색상 이름을 TFT 색상으로 변환
uint16_t getTftColor(String colorName) {
    if (colorName == "purple" || colorName == "보라") return TFT_PURPLE;
    if (colorName == "green" || colorName == "초록") return TFT_GREEN;
    if (colorName == "red" || colorName == "빨강") return TFT_RED;
    if (colorName == "blue" || colorName == "파랑") return TFT_BLUE;
    if (colorName == "yellow" || colorName == "노랑") return TFT_YELLOW;
    if (colorName == "orange" || colorName == "주황") return TFT_ORANGE;
    if (colorName == "white" || colorName == "흰색") return TFT_WHITE;
    if (colorName == "cyan" || colorName == "청록") return TFT_CYAN;
    return TFT_WHITE;
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
    wifiSSID = preferences.getString("wifi_ssid", wifiSSID);
    wifiPassword = preferences.getString("wifi_pass", wifiPassword);
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
            <h1>AutoMach Setup</h1>
            <p class="subtitle">ESP32 Picking Device WiFi Setup</p>
            <div class="device-id">)";
    html += deviceId;
    html += R"(</div>
            
            <form action="/save" method="POST">
                <div class="section-title">WiFi Connection</div>
                
                <div class="form-group">
                    <label>WiFi Name (SSID)</label>
                    <input type="text" name="ssid" value=")";
    html += wifiSSID;
    html += R"(" required placeholder="WiFi network name">
                </div>
                
                <div class="form-group">
                    <label>WiFi Password</label>
                    <input type="password" name="password" value=")";
    html += wifiPassword;
    html += R"(" placeholder="Enter password">
                    <div class="hint">Leave empty for open network</div>
                </div>
                
                <div class="divider"></div>
                <div class="section-title">Server Connection</div>
                
                <div class="form-group">
                    <label>PC IP Address</label>
                    <input type="text" name="host" value=")";
    html += wsHost;
    html += R"(" required placeholder="e.g. 192.168.0.100">
                    <div class="hint">Run ipconfig on PC to find</div>
                </div>
                
                <div class="form-group">
                    <label>Port Number</label>
                    <input type="number" name="port" value=")";
    html += String(wsPort);
    html += R"(" required placeholder="8765">
                    <div class="hint">Default: 8765</div>
                </div>
                
                <button type="submit">Save & Reboot</button>
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
    <title>Settings Saved</title>
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
        <div class="icon">OK</div>
        <h1>Settings Saved!</h1>
        <p>ESP32 will reboot now.<br>Connecting to new WiFi...</p>
        <div class="countdown" id="countdown">3</div>
        <p style="font-size: 12px; color: #888;">This hotspot will disappear</p>
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
    
    // TFT에 표시
    tftClear();
    tftDrawCentered("SETTINGS", 60, COLOR_SUCCESS, 3);
    tftDrawCentered("SAVED!", 100, COLOR_SUCCESS, 3);
    tftDrawCentered("Rebooting...", 160, COLOR_TEXT, 2);
    
    // 성공 표시 (초록색)
    for (int i = 0; i < NEOPIXEL_COUNT; i++) {
        pixels.setPixelColor(i, pixels.Color(0, 255, 0));
    }
    pixels.show();
    setCydLed(false, true, false);
    
    // 3초 후 재부팅
    delay(3000);
    ESP.restart();
}

// ===== 설정 모드 시작 =====
void startSetupMode() {
    setupMode = true;
    
    Serial.println("\n========================================");
    Serial.println("  WiFi Setup Mode!");
    Serial.println("========================================");
    
    // AP 모드로 전환
    WiFi.mode(WIFI_AP);
    WiFi.softAP(AP_SSID, AP_PASSWORD);
    
    IPAddress IP = WiFi.softAPIP();
    Serial.print("AP IP: ");
    Serial.println(IP);
    
    // 웹서버 설정
    server.on("/", handleRoot);
    server.on("/save", HTTP_POST, handleSave);
    server.begin();
    
    Serial.println("Web server started!");
    Serial.println("1. Connect to '" + String(AP_SSID) + "' WiFi");
    Serial.println("2. Open http://192.168.4.1 in browser");
    Serial.println("========================================\n");
    
    // TFT 표시
    tftClear();
    tft.fillRect(0, 0, tft.width(), 50, COLOR_SETUP);
    tftDrawCentered("SETUP MODE", 15, TFT_WHITE, 3);
    
    tftDrawCentered("Connect to WiFi:", 70, COLOR_TEXT, 2);
    tftDrawCentered(AP_SSID, 100, COLOR_INFO, 2);
    
    tftDrawCentered("Then open:", 140, COLOR_TEXT, 2);
    tftDrawCentered("192.168.4.1", 170, COLOR_SUCCESS, 3);
    
    tftDrawCentered(deviceId.c_str(), 220, TFT_DARKGREY, 1);
    
    // LED 표시 (파란색)
    for (int i = 0; i < NEOPIXEL_COUNT; i++) {
        pixels.setPixelColor(i, pixels.Color(0, 100, 255));
    }
    pixels.show();
    setCydLed(false, false, true);
}

// ===== WiFi 연결 =====
void connectWiFi() {
    if (wifiSSID.length() == 0) {
        Serial.println("No WiFi settings! Entering setup mode.");
        startSetupMode();
        return;
    }
    
    Serial.println("Connecting to WiFi: " + wifiSSID);
    
    // TFT 표시
    tftClear();
    tftDrawCentered("CONNECTING", 40, COLOR_TITLE, 3);
    tftDrawCentered("WiFi", 80, COLOR_TEXT, 2);
    tftDrawCentered(wifiSSID.substring(0, 20).c_str(), 110, COLOR_INFO, 2);
    
    WiFi.mode(WIFI_STA);
    WiFi.begin(wifiSSID.c_str(), wifiPassword.c_str());
    
    int attempts = 0;
    int dotX = 40;
    while (WiFi.status() != WL_CONNECTED && attempts < 30) {
        delay(500);
        Serial.print(".");
        
        // 진행 표시
        tft.fillCircle(dotX + (attempts % 10) * 20, 160, 5, COLOR_INFO);
        if ((attempts % 10) == 9) {
            tft.fillRect(40, 150, 200, 20, COLOR_BG);
        }
        
        // 연결 중 LED 애니메이션
        pixels.setPixelColor(attempts % NEOPIXEL_COUNT, pixels.Color(0, 0, 255));
        pixels.show();
        
        attempts++;
    }
    
    // LED 클리어
    pixels.clear();
    pixels.show();
    
    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("\nWiFi Connected!");
        Serial.print("IP: ");
        Serial.println(WiFi.localIP());
        
        // TFT 표시
        tftClear();
        tftDrawCentered("WiFi OK", 50, COLOR_SUCCESS, 3);
        
        char ipStr[20];
        sprintf(ipStr, "%s", WiFi.localIP().toString().c_str());
        tftDrawCentered(ipStr, 100, COLOR_TEXT, 2);
        
        tftDrawCentered(wifiSSID.substring(0, 16).c_str(), 140, TFT_DARKGREY, 2);
        
        // 성공 표시 (초록색)
        for (int i = 0; i < NEOPIXEL_COUNT; i++) {
            pixels.setPixelColor(i, pixels.Color(0, 255, 0));
        }
        pixels.show();
        setCydLed(false, true, false);
        delay(1500);
    } else {
        Serial.println("\nWiFi connection failed!");
        Serial.println("Entering setup mode...");
        
        // TFT 표시
        tftClear();
        tftDrawCentered("WiFi FAIL", 60, COLOR_ERROR, 3);
        tftDrawCentered("Entering", 110, COLOR_TEXT, 2);
        tftDrawCentered("Setup Mode...", 140, COLOR_TEXT, 2);
        
        // 실패 표시 (빨간색)
        for (int i = 0; i < NEOPIXEL_COUNT; i++) {
            pixels.setPixelColor(i, pixels.Color(255, 0, 0));
        }
        pixels.show();
        setCydLed(true, false, false);
        delay(2000);
        
        // 설정 모드로 전환
        startSetupMode();
    }
}

// ===== WebSocket 이벤트 핸들러 =====
void webSocketEvent(WStype_t type, uint8_t* payload, size_t length) {
    switch (type) {
        case WStype_DISCONNECTED:
            Serial.println("[WS] Disconnected");
            isConnected = false;
            
            tftClear();
            tftDrawCentered("DISCONNECTED", 80, COLOR_WARNING, 2);
            tftDrawCentered("Reconnecting...", 120, COLOR_TEXT, 2);
            tftDrawStatusBar("OFFLINE", COLOR_ERROR);
            
            for (int i = 0; i < NEOPIXEL_COUNT; i++) {
                pixels.setPixelColor(i, pixels.Color(255, 165, 0));
            }
            pixels.show();
            setCydLed(true, true, false);  // 주황색
            break;
            
        case WStype_CONNECTED:
            Serial.println("[WS] Connected!");
            isConnected = true;
            
            sendHello();
            
            tftClear();
            tftDrawCentered("CONNECTED", 80, COLOR_SUCCESS, 3);
            tftDrawCentered(deviceId.c_str(), 130, TFT_DARKGREY, 2);
            tftDrawStatusBar("ONLINE", COLOR_SUCCESS);
            
            for (int i = 0; i < NEOPIXEL_COUNT; i++) {
                pixels.setPixelColor(i, pixels.Color(0, 255, 0));
            }
            pixels.show();
            setCydLed(false, true, false);
            delay(500);
            
            showStandby();
            break;
            
        case WStype_TEXT:
            Serial.printf("[WS] Received: %s\n", payload);
            handleMessage((char*)payload);
            break;
            
        case WStype_ERROR:
            Serial.println("[WS] Error!");
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
    Serial.println("[WS] Hello sent: " + json);
}

// ===== Done 메시지 전송 =====
void sendDone() {
    if (bindedBinId.length() == 0) {
        Serial.println("[WS] No BIN binding, not sending done");
        return;
    }
    
    StaticJsonDocument<128> doc;
    doc["type"] = "done";
    doc["bin_id"] = bindedBinId;
    doc["device_id"] = deviceId;
    
    String json;
    serializeJson(doc, json);
    webSocket.sendTXT(json);
    Serial.println("[WS] Done sent: " + json);
    
    // 완료 애니메이션
    for (int i = 0; i < 3; i++) {
        for (int j = 0; j < NEOPIXEL_COUNT; j++) {
            pixels.setPixelColor(j, pixels.Color(0, 255, 0));
        }
        pixels.show();
        tft.fillScreen(COLOR_SUCCESS);
        delay(100);
        for (int j = 0; j < NEOPIXEL_COUNT; j++) {
            pixels.setPixelColor(j, 0);
        }
        pixels.show();
        tft.fillScreen(COLOR_BG);
        delay(100);
    }
    
    showStandby();
}

// ===== 메시지 처리 =====
void handleMessage(const char* payload) {
    StaticJsonDocument<256> doc;
    DeserializationError error = deserializeJson(doc, payload);
    
    if (error) {
        Serial.println("JSON parsing error!");
        return;
    }
    
    String msgType = doc["type"].as<String>();
    
    if (msgType == "bind") {
        bindedBinId = doc["bin_id"].as<String>();
        Serial.println("Bound to: " + bindedBinId);
        
        tftClear();
        tftDrawCentered("BOUND TO", 60, COLOR_TITLE, 2);
        tftDrawCentered(bindedBinId.c_str(), 100, COLOR_SUCCESS, 3);
        tftDrawStatusBar("READY", COLOR_SUCCESS);
        
    } else if (msgType == "display") {
        currentMode = doc["mode"].as<String>();
        String binId = doc["bin"].as<String>();
        String color = doc["color"].as<String>();
        currentQty = doc["qty"].as<int>();
        blinkEnabled = doc["blink"] | false;
        
        Serial.printf("Display: bin=%s, color=%s, qty=%d, blink=%d\n",
                      binId.c_str(), color.c_str(), currentQty, blinkEnabled);
        
        // TFT 표시
        uint16_t tftColor = getTftColor(color);
        
        tftClear();
        
        // 상단 헤더 (색상 배경)
        tft.fillRect(0, 0, tft.width(), 45, tftColor);
        tftDrawCentered(binId.c_str(), 10, TFT_WHITE, 3);
        
        // 수량 (큰 숫자)
        tftDrawCentered("QTY", 60, COLOR_TEXT, 2);
        tftDrawBigNumber(currentQty, 90, tftColor);
        
        // 모드 표시
        if (currentMode.length() > 0) {
            tftDrawCentered(currentMode.c_str(), 180, TFT_DARKGREY, 2);
        }
        
        // 상태바
        tftDrawStatusBar("PICKING", tftColor);
        
        // NeoPixel LED
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
    tftClear();
    
    tft.fillRect(0, 0, tft.width(), 45, TFT_DARKGREY);
    tftDrawCentered("READY", 10, TFT_WHITE, 3);
    
    if (bindedBinId.length() > 0) {
        tftDrawCentered("Assigned BIN:", 70, COLOR_TEXT, 2);
        tftDrawCentered(bindedBinId.c_str(), 100, COLOR_SUCCESS, 3);
    } else {
        tftDrawCentered("(unbound)", 90, TFT_DARKGREY, 2);
    }
    
    // 장치 ID
    tftDrawCentered(deviceId.c_str(), 150, TFT_DARKGREY, 1);
    
    // IP 주소
    if (WiFi.status() == WL_CONNECTED) {
        char ipStr[20];
        sprintf(ipStr, "%s", WiFi.localIP().toString().c_str());
        tftDrawCentered(ipStr, 170, TFT_DARKGREY, 1);
    }
    
    tftDrawStatusBar("STANDBY", TFT_DARKGREY);
    
    for (int i = 0; i < NEOPIXEL_COUNT; i++) {
        pixels.setPixelColor(i, pixels.Color(10, 10, 10));
    }
    pixels.show();
    setCydLed(false, false, false);
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
            
            Serial.println("\nButton held 5s - Entering setup mode!");
            
            // TFT 피드백
            tftClear();
            tftDrawCentered("ENTERING", 80, COLOR_SETUP, 3);
            tftDrawCentered("SETUP MODE", 120, COLOR_SETUP, 3);
            
            // LED로 피드백 (보라색 깜빡임)
            for (int i = 0; i < 3; i++) {
                for (int j = 0; j < NEOPIXEL_COUNT; j++) {
                    pixels.setPixelColor(j, pixels.Color(128, 0, 128));
                }
                pixels.show();
                setCydLed(true, false, true);
                delay(200);
                pixels.clear();
                pixels.show();
                setCydLed(false, false, false);
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
                    
                    Serial.println("Button pressed!");
                    
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
    // 전원 안정화 대기 (노이즈 방지)
    delay(500);
    
    Serial.begin(115200);
    Serial.println("\n\n========================================");
    Serial.println("  ESP32 CYD Picking Device");
    Serial.println("  Hold button 5s = WiFi Setup Mode");
    Serial.println("========================================");
    
    // CYD 내장 LED 핀 설정
    pinMode(CYD_LED_RED, OUTPUT);
    pinMode(CYD_LED_GREEN, OUTPUT);
    pinMode(CYD_LED_BLUE, OUTPUT);
    setCydLed(false, false, false);
    
    // 버튼 핀 설정 (BOOT 버튼 GPIO 0)
    pinMode(BUTTON_PIN, INPUT_PULLUP);
    
    // TFT 백라이트
    pinMode(TFT_BL, OUTPUT);
    digitalWrite(TFT_BL, HIGH);
    
    // TFT 초기화
    delay(200);  // TFT 전원 안정화
    tft.init();
    delay(200);  // init 후 안정화
    
    // 모든 rotation에서 화면 클리어 (잔상 완전 제거)
    for (int r = 0; r < 4; r++) {
        tft.setRotation(r);
        tft.fillScreen(TFT_BLACK);
        delay(50);
    }
    
    // 최종 rotation 설정
    tft.setRotation(2);  // 세로 모드
    delay(50);
    tft.fillScreen(TFT_BLACK);
    delay(50);
    tft.fillScreen(COLOR_BG);
    tft.setTextWrap(false);
    
    // 시작 화면
    tftDrawCentered("AutoMach", 60, COLOR_TITLE, 3);
    tftDrawCentered("Picking Device", 100, COLOR_TEXT, 2);
    tftDrawCentered("Initializing...", 160, TFT_DARKGREY, 2);
    
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
        Serial.println("Button held during boot - Setup mode!");
        
        tftClear();
        tftDrawCentered("Release button", 80, COLOR_WARNING, 2);
        tftDrawCentered("for setup mode", 110, COLOR_WARNING, 2);
        
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
        Serial.println("Connecting WebSocket: " + wsHost + ":" + String(wsPort));
        
        webSocket.begin(wsHost.c_str(), wsPort, "/");
        webSocket.onEvent(webSocketEvent);
        webSocket.setReconnectInterval(5000);
        
        tftClear();
        tftDrawCentered("Connecting", 60, COLOR_TITLE, 3);
        tftDrawCentered("WebSocket...", 100, COLOR_TEXT, 2);
        tftDrawCentered(wsHost.c_str(), 140, TFT_DARKGREY, 2);
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
        Serial.println("WiFi reconnecting...");
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
