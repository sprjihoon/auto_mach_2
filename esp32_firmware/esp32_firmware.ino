/**
 * ESP32 피킹 디바이스 펌웨어
 * 
 * 하드웨어: ESP32-2432S028 (Cheap Yellow Display)
 * - 2.8" TFT 320x240 ILI9341
 * - 터치스크린 (XPT2046) - 활성화
 * - RGB LED
 * 
 * 기능:
 * - WiFi로 PC WebSocket 서버에 연결
 * - TFT에 BIN ID, 수량 표시
 * - NeoPixel LED로 색상 표시
 * - 화면 터치 또는 버튼 누르면 완료 신호 전송
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
#include <WiFiUdp.h>       // UDP 자동 발견용
#include <WebServer.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>
#include <Adafruit_NeoPixel.h>
#include <Preferences.h>
#include <TFT_eSPI.h>
#include <SPI.h>
#include <Update.h>        // OTA 업데이트용
#include <HTTPClient.h>    // HTTP OTA 다운로드용

// ===== CYD 터치 전용 SPI (XPT2046) =====
// TFT_eSPI 내장 터치 대신 직접 SPI 통신
#define TOUCH_SPI_CLK   25
#define TOUCH_SPI_MISO  39
#define TOUCH_SPI_MOSI  32
#define TOUCH_SPI_CS    33
#define TOUCH_IRQ_PIN   36

SPIClass touchSPI(VSPI);  // 터치용 별도 SPI 버스

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
// ★ 기본값 - SmartConfig로 자동 설정되면 NVS에 저장됨
String wifiSSID = "";                  // WiFi 이름 (빈값 = SmartConfig 사용)
String wifiPassword = "";              // WiFi 비밀번호
String wsHost = "";                    // PC IP (자동 발견)
int wsPort = 8765;
int deviceNumber = 0;  // 장치 번호 (0=자동, 1~99=수동 지정)

// ===== 서버 자동 발견 설정 =====
#define DISCOVERY_PORT 8764           // UDP 브로드캐스트 수신 포트
#define DISCOVERY_TIMEOUT 30000       // 자동 발견 타임아웃 (30초)
bool autoDiscoveryEnabled = true;     // 자동 발견 활성화

// ===== SmartConfig 설정 =====
#define SMARTCONFIG_TIMEOUT 120000    // SmartConfig 타임아웃 (2분)
bool useSmartConfig = true;           // SmartConfig 사용 여부

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

// 터치 관련
bool touchEnabled = true;
unsigned long lastTouchTime = 0;
const unsigned long TOUCH_DEBOUNCE = 500;  // 터치 디바운스 시간 (ms)

// 터치 테스트 관련
bool touchTestPending = false;       // 터치 테스트 대기 중
bool touchTestPassed = false;        // 터치 테스트 통과 여부
unsigned long touchTestStartTime = 0; // 터치 테스트 시작 시간

// OTA 업데이트 관련
bool otaInProgress = false;
String otaUrl = "";
const char* FIRMWARE_VERSION = "1.0.0";  // 펌웨어 버전

// ===== OTA 업데이트 함수 =====
void showOtaProgress(int percent, const char* status) {
    tft.fillScreen(TFT_BLUE);
    tft.setTextColor(TFT_WHITE, TFT_BLUE);
    
    tft.setTextSize(2);
    tft.setCursor(30, 30);
    tft.print("FIRMWARE UPDATE");
    
    tft.setTextSize(1);
    tft.setCursor(20, 70);
    tft.print(status);
    
    // 프로그레스 바
    int barWidth = 200;
    int barHeight = 25;
    int barX = (tft.width() - barWidth) / 2;
    int barY = 120;
    
    tft.drawRect(barX, barY, barWidth, barHeight, TFT_WHITE);
    int fillWidth = (barWidth - 4) * percent / 100;
    tft.fillRect(barX + 2, barY + 2, fillWidth, barHeight - 4, TFT_GREEN);
    
    // 퍼센트 표시
    char percentStr[10];
    sprintf(percentStr, "%d%%", percent);
    tft.setTextSize(3);
    int textWidth = strlen(percentStr) * 6 * 3;
    tft.setCursor((tft.width() - textWidth) / 2, 170);
    tft.print(percentStr);
    
    tft.setTextSize(1);
    tft.setCursor(40, 220);
    tft.print("DO NOT POWER OFF!");
}

void performOtaUpdate(String url) {
    otaInProgress = true;
    Serial.println("[OTA] Starting update from: " + url);
    
    showOtaProgress(0, "Connecting...");
    
    // LED 파란색
    for (int i = 0; i < NEOPIXEL_COUNT; i++) {
        pixels.setPixelColor(i, pixels.Color(0, 0, 255));
    }
    pixels.show();
    
    HTTPClient http;
    http.begin(url);
    http.setTimeout(30000);
    
    int httpCode = http.GET();
    
    if (httpCode != HTTP_CODE_OK) {
        Serial.printf("[OTA] HTTP error: %d\n", httpCode);
        showOtaProgress(0, "Download failed!");
        tft.setTextColor(TFT_RED, TFT_BLUE);
        tft.setCursor(50, 250);
        tft.print("Error: ");
        tft.print(httpCode);
        delay(3000);
        otaInProgress = false;
        showStandby();
        return;
    }
    
    int contentLength = http.getSize();
    Serial.printf("[OTA] Firmware size: %d bytes\n", contentLength);
    
    if (contentLength <= 0) {
        Serial.println("[OTA] Invalid content length");
        showOtaProgress(0, "Invalid firmware!");
        delay(3000);
        otaInProgress = false;
        showStandby();
        return;
    }
    
    showOtaProgress(5, "Downloading...");
    
    // OTA 시작
    if (!Update.begin(contentLength)) {
        Serial.println("[OTA] Not enough space!");
        showOtaProgress(0, "Not enough space!");
        delay(3000);
        otaInProgress = false;
        showStandby();
        return;
    }
    
    WiFiClient* stream = http.getStreamPtr();
    
    uint8_t buff[1024];
    int totalRead = 0;
    int lastPercent = 0;
    
    while (http.connected() && totalRead < contentLength) {
        size_t available = stream->available();
        if (available) {
            int readBytes = stream->readBytes(buff, min(available, sizeof(buff)));
            Update.write(buff, readBytes);
            totalRead += readBytes;
            
            int percent = (totalRead * 100) / contentLength;
            if (percent != lastPercent && percent % 5 == 0) {
                lastPercent = percent;
                showOtaProgress(percent, "Downloading...");
                Serial.printf("[OTA] Progress: %d%%\n", percent);
            }
        }
        delay(1);
    }
    
    http.end();
    
    showOtaProgress(95, "Verifying...");
    
    if (Update.end(true)) {
        Serial.println("[OTA] Update successful!");
        showOtaProgress(100, "Update complete!");
        
        // LED 녹색
        for (int i = 0; i < NEOPIXEL_COUNT; i++) {
            pixels.setPixelColor(i, pixels.Color(0, 255, 0));
        }
        pixels.show();
        
        tft.setTextSize(2);
        tft.setCursor(50, 260);
        tft.print("Rebooting...");
        
        delay(2000);
        ESP.restart();
    } else {
        Serial.printf("[OTA] Update failed: %s\n", Update.errorString());
        showOtaProgress(0, "Update failed!");
        tft.setCursor(20, 250);
        tft.print(Update.errorString());
        
        // LED 빨간색
        for (int i = 0; i < NEOPIXEL_COUNT; i++) {
            pixels.setPixelColor(i, pixels.Color(255, 0, 0));
        }
        pixels.show();
        
        delay(5000);
        otaInProgress = false;
        showStandby();
    }
}

// ===== XPT2046 직접 통신 함수 =====
uint16_t touchReadChannel(uint8_t channel) {
    // XPT2046 명령어: 0x90 = Y축, 0xD0 = X축
    digitalWrite(TOUCH_SPI_CS, LOW);
    touchSPI.transfer(channel);
    uint8_t hi = touchSPI.transfer(0x00);
    uint8_t lo = touchSPI.transfer(0x00);
    digitalWrite(TOUCH_SPI_CS, HIGH);
    return ((hi << 8) | lo) >> 3;  // 12비트 값
}

bool readTouch(uint16_t* x, uint16_t* y, uint16_t* z) {
    // IRQ 핀 체크 (LOW = 터치됨)
    if (digitalRead(TOUCH_IRQ_PIN) == HIGH) {
        return false;  // 터치 안 됨
    }
    
    // 터치 좌표 읽기
    uint16_t rawX = touchReadChannel(0xD0);  // X축
    uint16_t rawY = touchReadChannel(0x90);  // Y축
    
    // 압력 계산 (Z1, Z2)
    uint16_t z1 = touchReadChannel(0xB0);
    uint16_t z2 = touchReadChannel(0xC0);
    
    // 유효한 터치인지 확인
    if (z1 > 50 && rawX > 100 && rawX < 4000 && rawY > 100 && rawY < 4000) {
        // 캘리브레이션 적용 (CYD 2.8" rotation 2 기준)
        *x = map(rawX, 200, 3900, 0, 240);
        *y = map(rawY, 200, 3900, 0, 320);
        *z = z1;
        return true;
    }
    
    return false;
}

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

// ===== 디바이스 ID 생성 =====
String getDeviceId() {
    uint8_t mac[6];
    WiFi.macAddress(mac);
    char macStr[24];
    
    if (deviceNumber > 0 && deviceNumber < 100) {
        // 수동 지정 장치 번호 사용
        sprintf(macStr, "esp32_DEV%02d", deviceNumber);
    } else {
        // 전체 MAC 주소 6바이트 사용 (중복 방지)
        sprintf(macStr, "esp32_%02X%02X%02X%02X%02X%02X", 
                mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
    }
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
    String html = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AutoMach ESP32 Setup</title>
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
        input, select { width: 100%; padding: 14px; border: 2px solid #e0e0e0; border-radius: 10px; font-size: 16px; transition: border-color 0.2s; background: white; }
        input:focus, select:focus { outline: none; border-color: #667eea; }
        .hint { font-size: 12px; color: #888; margin-top: 5px; }
        button { width: 100%; padding: 16px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; border-radius: 10px; font-size: 16px; font-weight: 600; cursor: pointer; transition: transform 0.2s, box-shadow 0.2s; }
        button:hover { transform: translateY(-2px); box-shadow: 0 5px 20px rgba(102,126,234,0.4); }
        button:active { transform: translateY(0); }
        .divider { border-top: 1px solid #eee; margin: 25px 0; }
        .section-title { font-size: 12px; color: #888; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 15px; }
        .scan-btn { padding: 10px 16px; font-size: 14px; margin-bottom: 10px; background: linear-gradient(135deg, #28a745 0%, #20c997 100%); }
        .scan-btn:disabled { background: #ccc; cursor: not-allowed; transform: none; }
        .wifi-select { margin-bottom: 10px; }
        .manual-toggle { font-size: 13px; color: #667eea; cursor: pointer; text-decoration: underline; margin-top: 8px; display: inline-block; }
        .manual-input { display: none; margin-top: 10px; }
        .manual-input.show { display: block; }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <h1>AutoMach Setup</h1>
            <p class="subtitle">ESP32 Picking Device WiFi Setup</p>
            <div class="device-id">)rawliteral";
    html += deviceId;
    html += R"rawliteral(</div>
            
            <form action="/save" method="POST">
                <div class="section-title">WiFi Connection</div>
                
                <div class="form-group">
                    <label>WiFi Name (SSID)</label>
                    <button type="button" class="scan-btn" id="scanBtn" onclick="scanWifi()">Scan WiFi Networks</button>
                    <select class="wifi-select" id="wifiSelect" name="ssid" onchange="onWifiSelect()">
                        <option value="">-- Click Scan to find networks --</option>
                    </select>
                    <span class="manual-toggle" onclick="toggleManual()">+ Enter manually</span>
                    <div class="manual-input" id="manualInput">
                        <input type="text" id="manualSsid" placeholder="Enter SSID manually" value=")rawliteral";
    html += wifiSSID;
    html += R"rawliteral(">
                    </div>
                </div>
                
                <div class="form-group">
                    <label>WiFi Password</label>
                    <input type="password" name="password" value=")rawliteral";
    html += wifiPassword;
    html += R"rawliteral(" placeholder="Enter password">
                    <div class="hint">Leave empty for open network</div>
                </div>
                
                <div class="divider"></div>
                <div class="section-title">Server Connection</div>
                
                <div class="form-group">
                    <label>PC IP Address</label>
                    <input type="text" name="host" value=")rawliteral";
    html += wsHost;
    html += R"rawliteral(" required placeholder="e.g. 192.168.0.100">
                    <div class="hint">Run ipconfig on PC to find</div>
                </div>
                
                <div class="form-group">
                    <label>Port Number</label>
                    <input type="number" name="port" value=")rawliteral";
    html += String(wsPort);
    html += R"rawliteral(" required placeholder="8765">
                    <div class="hint">Default: 8765</div>
                </div>
                
                <button type="submit">Save & Reboot</button>
            </form>
        </div>
    </div>
    <script>
        let manualMode = false;
        
        function scanWifi() {
            const btn = document.getElementById('scanBtn');
            const select = document.getElementById('wifiSelect');
            
            btn.disabled = true;
            btn.textContent = 'Scanning...';
            select.innerHTML = '<option value="">Scanning...</option>';
            
            fetch('/scan')
                .then(r => r.json())
                .then(data => {
                    select.innerHTML = '<option value="">-- Select WiFi Network --</option>';
                    data.sort((a, b) => b.rssi - a.rssi);
                    
                    data.forEach(ap => {
                        const opt = document.createElement('option');
                        opt.value = ap.ssid;
                        let signal = '';
                        if (ap.rssi >= -50) signal = '****';
                        else if (ap.rssi >= -60) signal = '*** ';
                        else if (ap.rssi >= -70) signal = '**  ';
                        else signal = '*   ';
                        const lock = ap.secure ? 'L' : 'O';
                        opt.textContent = ap.ssid + ' [' + lock + '] ' + signal + ' (' + ap.rssi + 'dBm)';
                        select.appendChild(opt);
                    });
                    
                    if (data.length === 0) {
                        select.innerHTML = '<option value="">No networks found</option>';
                    }
                    
                    btn.disabled = false;
                    btn.textContent = 'Scan Again';
                })
                .catch(err => {
                    select.innerHTML = '<option value="">Scan failed - try again</option>';
                    btn.disabled = false;
                    btn.textContent = 'Scan WiFi Networks';
                });
        }
        
        function onWifiSelect() {
            const select = document.getElementById('wifiSelect');
            if (select.value && manualMode) {
                document.getElementById('manualInput').classList.remove('show');
                manualMode = false;
            }
        }
        
        function toggleManual() {
            manualMode = !manualMode;
            const manualDiv = document.getElementById('manualInput');
            const select = document.getElementById('wifiSelect');
            if (manualMode) {
                manualDiv.classList.add('show');
                select.value = '';
            } else {
                manualDiv.classList.remove('show');
            }
        }
        
        document.querySelector('form').addEventListener('submit', function(e) {
            if (manualMode) {
                const manualSsid = document.getElementById('manualSsid').value;
                if (manualSsid) {
                    document.getElementById('wifiSelect').innerHTML = '<option value="' + manualSsid + '" selected>' + manualSsid + '</option>';
                }
            }
        });
        
        setTimeout(scanWifi, 500);
    </script>
</body>
</html>
)rawliteral";
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

// ===== WiFi 스캔 핸들러 =====
void handleScan() {
    Serial.println("WiFi 스캔 시작...");
    
    int n = WiFi.scanNetworks();
    String json = "[";
    
    for (int i = 0; i < n; i++) {
        if (i > 0) json += ",";
        json += "{";
        json += "\"ssid\":\"" + WiFi.SSID(i) + "\",";
        json += "\"rssi\":" + String(WiFi.RSSI(i)) + ",";
        json += "\"secure\":" + String(WiFi.encryptionType(i) != WIFI_AUTH_OPEN);
        json += "}";
    }
    json += "]";
    
    WiFi.scanDelete();
    
    server.send(200, "application/json", json);
    Serial.println("스캔 완료: " + String(n) + "개 AP 발견");
}

// ===== 설정 모드 시작 =====
void startSetupMode() {
    setupMode = true;
    
    Serial.println("\n========================================");
    Serial.println("  WiFi Setup Mode!");
    Serial.println("========================================");
    
    // AP+STA 모드로 전환 (AP 역할 + WiFi 스캔 가능)
    WiFi.mode(WIFI_AP_STA);
    WiFi.softAP(AP_SSID, AP_PASSWORD);
    
    IPAddress IP = WiFi.softAPIP();
    Serial.print("AP IP: ");
    Serial.println(IP);
    
    // 웹서버 설정
    server.on("/", handleRoot);
    server.on("/save", HTTP_POST, handleSave);
    server.on("/scan", HTTP_GET, handleScan);
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

// ===== SmartConfig로 WiFi 설정 =====
bool startSmartConfig() {
    Serial.println("\n========================================");
    Serial.println("  SmartConfig Mode - Use ESP-TOUCH App");
    Serial.println("========================================");
    
    // TFT 표시
    tft.fillScreen(TFT_CYAN);
    tft.setTextColor(TFT_BLACK, TFT_CYAN);
    tft.setTextSize(2);
    tft.setCursor(25, 20);
    tft.print("SMARTCONFIG");
    
    tft.setTextSize(1);
    tft.setCursor(10, 60);
    tft.print("Use ESP-TOUCH app to");
    tft.setCursor(10, 75);
    tft.print("configure WiFi");
    
    tft.setTextSize(2);
    tft.setCursor(10, 110);
    tft.print("1.Open ESP-TOUCH");
    tft.setCursor(10, 135);
    tft.print("2.Enter WiFi info");
    tft.setCursor(10, 160);
    tft.print("3.Press Confirm");
    
    tft.setTextSize(1);
    tft.setCursor(20, 200);
    tft.print("Waiting for config...");
    
    // LED 청록색 깜빡임
    for (int i = 0; i < NEOPIXEL_COUNT; i++) {
        pixels.setPixelColor(i, pixels.Color(0, 255, 255));
    }
    pixels.show();
    
    WiFi.mode(WIFI_STA);
    WiFi.beginSmartConfig();
    
    unsigned long startTime = millis();
    int dotCount = 0;
    
    while (!WiFi.smartConfigDone()) {
        delay(500);
        Serial.print(".");
        
        // 타임아웃 체크
        if (millis() - startTime > SMARTCONFIG_TIMEOUT) {
            Serial.println("\nSmartConfig timeout!");
            WiFi.stopSmartConfig();
            return false;
        }
        
        // 진행 애니메이션
        dotCount++;
        int ledIdx = dotCount % NEOPIXEL_COUNT;
        pixels.clear();
        pixels.setPixelColor(ledIdx, pixels.Color(0, 255, 255));
        pixels.setPixelColor((ledIdx + 1) % NEOPIXEL_COUNT, pixels.Color(0, 128, 128));
        pixels.show();
        
        // 버튼 체크 (설정 모드로 전환)
        if (digitalRead(BUTTON_PIN) == LOW) {
            delay(100);
            if (digitalRead(BUTTON_PIN) == LOW) {
                Serial.println("\nButton pressed - entering setup mode");
                WiFi.stopSmartConfig();
                return false;
            }
        }
    }
    
    Serial.println("\nSmartConfig received!");
    
    // WiFi 연결 대기
    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 30) {
        delay(500);
        Serial.print("*");
        attempts++;
    }
    
    if (WiFi.status() == WL_CONNECTED) {
        // SmartConfig로 받은 정보 저장
        wifiSSID = WiFi.SSID();
        wifiPassword = WiFi.psk();
        saveSettings();
        
        Serial.println("\nWiFi connected via SmartConfig!");
        Serial.println("SSID: " + wifiSSID);
        return true;
    }
    
    return false;
}

// ===== 서버 자동 발견 (UDP) =====
bool discoverServer() {
    if (!autoDiscoveryEnabled) return false;
    if (wsHost.length() > 0) return true;  // 이미 설정됨
    
    Serial.println("[Discovery] Looking for AutoMach server...");
    
    // TFT 표시
    tftClear();
    tftDrawCentered("SEARCHING", 50, COLOR_INFO, 2);
    tftDrawCentered("for PC server...", 80, COLOR_TEXT, 2);
    
    WiFiUDP udp;
    udp.begin(DISCOVERY_PORT);
    
    unsigned long startTime = millis();
    char packetBuffer[255];
    
    while (millis() - startTime < DISCOVERY_TIMEOUT) {
        int packetSize = udp.parsePacket();
        if (packetSize > 0) {
            int len = udp.read(packetBuffer, 254);
            if (len > 0) {
                packetBuffer[len] = 0;
                String packet = String(packetBuffer);
                
                // "AUTOMACH:IP:PORT" 형식
                if (packet.startsWith("AUTOMACH:")) {
                    int firstColon = packet.indexOf(':', 9);
                    if (firstColon > 0) {
                        wsHost = packet.substring(9, firstColon);
                        wsPort = packet.substring(firstColon + 1).toInt();
                        
                        Serial.printf("[Discovery] Found server: %s:%d\n", wsHost.c_str(), wsPort);
                        
                        tftClear();
                        tftDrawCentered("SERVER FOUND!", 60, COLOR_SUCCESS, 2);
                        tftDrawCentered(wsHost.c_str(), 100, COLOR_INFO, 2);
                        delay(1000);
                        
                        udp.stop();
                        return true;
                    }
                }
            }
        }
        
        // 애니메이션
        static int animIdx = 0;
        animIdx = (animIdx + 1) % NEOPIXEL_COUNT;
        pixels.clear();
        pixels.setPixelColor(animIdx, pixels.Color(255, 165, 0));
        pixels.show();
        
        delay(100);
    }
    
    udp.stop();
    Serial.println("[Discovery] Server not found (timeout)");
    return false;
}

// ===== WiFi 연결 =====
void connectWiFi() {
    // WiFi 설정이 없으면 SmartConfig 시도
    if (wifiSSID.length() == 0 && useSmartConfig) {
        Serial.println("No WiFi settings - trying SmartConfig...");
        
        if (!startSmartConfig()) {
            Serial.println("SmartConfig failed - entering setup mode");
            startSetupMode();
            return;
        }
    }
    
    // 여전히 설정 없으면 설정 모드
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
    StaticJsonDocument<200> doc;
    doc["type"] = "hello";
    doc["device_id"] = deviceId;
    doc["firmware_version"] = FIRMWARE_VERSION;
    doc["ip"] = WiFi.localIP().toString();
    
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
        
        // BIN 할당 표시
        tftClear();
        tftDrawCentered("BOUND TO", 60, COLOR_TITLE, 2);
        tftDrawCentered(bindedBinId.c_str(), 100, COLOR_SUCCESS, 3);
        tftDrawStatusBar("TESTING...", COLOR_WARNING);
        
        // 잠시 표시 후 터치 테스트 시작
        delay(1000);
        
        // ★ 터치 테스트 화면으로 이동 (터치 통과해야 READY)
        touchTestPassed = false;  // 테스트 초기화
        showTouchTest();
        
    } else if (msgType == "display") {
        currentMode = doc["mode"].as<String>();
        String binId = doc["bin"].as<String>();
        String color = doc["color"].as<String>();
        currentQty = doc["qty"].as<int>();
        blinkEnabled = doc["blink"] | false;
        
        Serial.printf("Display: bin=%s, color=%s, qty=%d, blink=%d, mode=%s\n",
                      binId.c_str(), color.c_str(), currentQty, blinkEnabled, currentMode.c_str());
        
        // TFT 색상
        uint16_t tftColor = getTftColor(color);
        
        // ★ 전체 배경을 모드 색상으로 채우기 (시인성 향상)
        tft.fillScreen(tftColor);
        
        // 모드 라벨 결정
        const char* modeLabel;
        if (currentMode == "full_pick") {
            modeLabel = "FULL PICK";
        } else if (currentMode == "pre_pick") {
            modeLabel = "PRE PICK";
        } else if (currentMode == "shipment") {
            modeLabel = "SHIPMENT";
        } else {
            modeLabel = "PICKING";
        }
        
        // 상단 모드 라벨 (흰색 텍스트)
        tft.setTextColor(TFT_WHITE, tftColor);
        tft.setTextSize(2);
        int modeLabelWidth = strlen(modeLabel) * 6 * 2;
        tft.setCursor((tft.width() - modeLabelWidth) / 2, 15);
        tft.print(modeLabel);
        
        // BIN ID (중앙 상단, 큰 흰색 글씨)
        tft.setTextColor(TFT_WHITE, tftColor);
        tft.setTextSize(3);
        int binWidth = binId.length() * 6 * 3;
        tft.setCursor((tft.width() - binWidth) / 2, 50);
        tft.print(binId);
        
        // 구분선
        tft.drawFastHLine(20, 85, tft.width() - 40, TFT_WHITE);
        
        // 수량 (매우 큰 흰색 숫자) - 화면 중앙
        char qtyStr[16];
        sprintf(qtyStr, "%d", currentQty);
        tft.setTextColor(TFT_WHITE, tftColor);
        tft.setTextSize(10);  // 매우 큰 숫자
        int qtyWidth = strlen(qtyStr) * 6 * 10;
        int qtyX = (tft.width() - qtyWidth) / 2;
        int qtyY = 100;
        tft.setCursor(qtyX, qtyY);
        tft.print(qtyStr);
        
        // 하단 "TOUCH TO COMPLETE" 안내
        tft.setTextColor(TFT_WHITE, tftColor);
        tft.setTextSize(1);
        tft.setCursor(55, tft.height() - 20);
        tft.print("TOUCH TO COMPLETE");
        
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
        
    } else if (msgType == "ota") {
        // OTA 업데이트 명령
        String firmwareUrl = doc["url"].as<String>();
        Serial.println("[OTA] Update command received: " + firmwareUrl);
        
        // 비동기로 OTA 시작 (다음 루프에서 처리)
        otaUrl = firmwareUrl;
        
    } else if (msgType == "version") {
        // 버전 정보 요청
        StaticJsonDocument<128> response;
        response["type"] = "version_info";
        response["device_id"] = deviceId;
        response["firmware_version"] = FIRMWARE_VERSION;
        response["free_heap"] = ESP.getFreeHeap();
        
        String json;
        serializeJson(response, json);
        webSocket.sendTXT(json);
        Serial.println("[Version] Sent: " + json);
        
    } else if (msgType == "reboot") {
        // 재부팅 명령
        Serial.println("[Reboot] Rebooting...");
        tft.fillScreen(TFT_ORANGE);
        tftDrawCentered("REBOOTING...", 100, TFT_WHITE, 2);
        delay(1000);
        ESP.restart();
    }
}

// ===== 터치 테스트 화면 표시 =====
void showTouchTest() {
    touchTestPending = true;
    touchTestStartTime = millis();
    
    // 노란색 배경으로 주의 표시
    tft.fillScreen(TFT_YELLOW);
    
    // 제목
    tft.setTextColor(TFT_BLACK, TFT_YELLOW);
    tft.setTextSize(3);
    tft.setCursor(35, 30);
    tft.print("TOUCH TEST");
    
    // 안내 메시지
    tft.setTextSize(2);
    tft.setCursor(20, 90);
    tft.print("Please touch the");
    tft.setCursor(20, 115);
    tft.print("screen to verify");
    tft.setCursor(20, 140);
    tft.print("touch is working");
    
    // 큰 터치 아이콘/영역 표시
    tft.drawRect(60, 175, 120, 50, TFT_BLACK);
    tft.drawRect(62, 177, 116, 46, TFT_BLACK);
    tft.setTextSize(2);
    tft.setCursor(75, 190);
    tft.print("TOUCH ME");
    
    // LED 노란색 깜빡임
    for (int i = 0; i < NEOPIXEL_COUNT; i++) {
        pixels.setPixelColor(i, pixels.Color(255, 200, 0));
    }
    pixels.show();
    setCydLed(true, true, false);  // 노란색
    
    Serial.println("[Touch Test] Waiting for touch...");
}

// ===== 터치 테스트 통과 표시 =====
void showTouchTestPassed() {
    touchTestPending = false;
    touchTestPassed = true;
    
    // 녹색 배경으로 성공 표시
    tft.fillScreen(TFT_GREEN);
    
    tft.setTextColor(TFT_WHITE, TFT_GREEN);
    tft.setTextSize(3);
    tft.setCursor(70, 60);
    tft.print("TOUCH");
    tft.setCursor(95, 100);
    tft.print("OK!");
    
    tft.setTextSize(2);
    tft.setCursor(30, 160);
    tft.print("Touch verified!");
    
    // LED 녹색
    for (int i = 0; i < NEOPIXEL_COUNT; i++) {
        pixels.setPixelColor(i, pixels.Color(0, 255, 0));
    }
    pixels.show();
    setCydLed(false, true, false);
    
    Serial.println("[Touch Test] PASSED!");
    
    // 1.5초 후 대기 화면으로
    delay(1500);
    showStandby();
}

// ===== 대기 상태 표시 =====
void showStandby() {
    tftClear();
    
    tft.fillRect(0, 0, tft.width(), 45, TFT_DARKGREY);
    tftDrawCentered("READY", 10, TFT_WHITE, 3);
    
    if (bindedBinId.length() > 0) {
        tftDrawCentered("Assigned BIN:", 70, COLOR_TEXT, 2);
        tftDrawCentered(bindedBinId.c_str(), 100, COLOR_SUCCESS, 3);
        
        // 터치 테스트 통과 여부 표시
        if (touchTestPassed) {
            tftDrawCentered("Touch: OK", 135, COLOR_SUCCESS, 1);
        }
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

// ===== 터치 처리 =====
void handleTouch() {
    if (!touchEnabled || setupMode) return;
    if (!isConnected) return;
    
    uint16_t x, y, z;
    
    // 터치 테스트 중에는 IRQ 상태도 출력
    if (touchTestPending) {
        static unsigned long lastDebug = 0;
        if (millis() - lastDebug > 1000) {
            lastDebug = millis();
            bool irqState = digitalRead(TOUCH_IRQ_PIN);
            Serial.printf("[Touch Debug] IRQ pin: %s\n", irqState ? "HIGH (no touch)" : "LOW (touched!)");
        }
    }
    
    // ★ 직접 SPI로 터치 읽기 (CYD 전용)
    bool touched = readTouch(&x, &y, &z);
    
    if (touched) {
        unsigned long now = millis();
        
        // 디바운스 체크
        if (now - lastTouchTime > TOUCH_DEBOUNCE) {
            lastTouchTime = now;
            
            Serial.printf("[Touch] Detected: x=%d, y=%d, z=%d\n", x, y, z);
            
            // ★ 터치 테스트 모드일 때
            if (touchTestPending) {
                Serial.println("[Touch Test] Touch detected - PASSED!");
                showTouchTestPassed();
                return;
            }
            
            // 바인딩 안 됐으면 무시 (터치 테스트 후 대기 상태)
            if (bindedBinId.length() == 0) return;
            
            // 일반 모드: 화면 어디든 터치하면 완료 처리
            sendDone();
        }
    }
}

// 터치 디버그 - 원시 터치 값 확인용 (setup 모드에서만 사용)
void debugRawTouch() {
    uint16_t x, y;
    uint8_t z;
    
    // 원시 터치 값 읽기
    z = tft.getTouchRaw(&x, &y);
    if (z > 0) {
        Serial.printf("[Raw Touch] x=%d, y=%d, z=%d\n", x, y, z);
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
                    
                    // ★ 터치 테스트 실패 후 버튼 누르면 재시도
                    if (!touchTestPending && !touchTestPassed && bindedBinId.length() > 0) {
                        Serial.println("[Touch Test] Retrying...");
                        showTouchTest();
                        buttonPressStart = 0;
                        buttonHeldForSetup = false;
                        return;
                    }
                    
                    // ★ 터치 테스트 중 버튼 누르면 통과 (백업용)
                    if (touchTestPending) {
                        Serial.println("[Touch Test] Passed via button (backup)");
                        showTouchTestPassed();
                        buttonPressStart = 0;
                        buttonHeldForSetup = false;
                        return;
                    }
                    
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
    
    // ===== CYD 터치 SPI 초기화 (별도 SPI 버스) =====
    pinMode(TOUCH_SPI_CS, OUTPUT);
    digitalWrite(TOUCH_SPI_CS, HIGH);
    pinMode(TOUCH_IRQ_PIN, INPUT);
    
    // 터치용 SPI 시작 (VSPI)
    touchSPI.begin(TOUCH_SPI_CLK, TOUCH_SPI_MISO, TOUCH_SPI_MOSI, TOUCH_SPI_CS);
    touchSPI.setFrequency(2000000);  // 2MHz
    
    Serial.println("[Touch] Custom SPI initialized");
    Serial.printf("[Touch] Pins - CLK:%d, MISO:%d, MOSI:%d, CS:%d, IRQ:%d\n", 
                  TOUCH_SPI_CLK, TOUCH_SPI_MISO, TOUCH_SPI_MOSI, TOUCH_SPI_CS, TOUCH_IRQ_PIN);
    
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
    
    // ★ WiFi 초기화 (MAC 주소 읽기 전에 필요!)
    WiFi.mode(WIFI_STA);
    delay(100);  // WiFi 초기화 대기
    
    // 디바이스 ID 생성 (WiFi 초기화 후)
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
    
    // 설정 모드가 아니면 서버 발견 후 WebSocket 연결
    if (!setupMode && WiFi.status() == WL_CONNECTED) {
        // ★ PC 서버 자동 발견
        if (wsHost.length() == 0) {
            if (!discoverServer()) {
                // 서버 못 찾으면 수동 설정 안내
                tftClear();
                tftDrawCentered("SERVER NOT", 50, COLOR_WARNING, 2);
                tftDrawCentered("FOUND", 80, COLOR_WARNING, 2);
                tftDrawCentered("Start server on PC", 130, COLOR_TEXT, 1);
                tftDrawCentered("or press BOOT for", 150, COLOR_TEXT, 1);
                tftDrawCentered("manual setup", 170, COLOR_TEXT, 1);
                
                // 5초 대기 후 재시도 또는 설정 모드
                delay(5000);
                ESP.restart();
                return;
            }
        }
        
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
    
    // 터치 처리
    handleTouch();
    
    // ★ 터치 테스트 타임아웃 체크 (30초)
    if (touchTestPending && (millis() - touchTestStartTime > 30000)) {
        // 터치 테스트 실패 표시
        tft.fillScreen(TFT_RED);
        tft.setTextColor(TFT_WHITE, TFT_RED);
        tft.setTextSize(2);
        tft.setCursor(40, 60);
        tft.print("TOUCH FAILED!");
        tft.setCursor(20, 100);
        tft.print("Touch not working");
        tft.setCursor(30, 140);
        tft.print("Check firmware &");
        tft.setCursor(30, 165);
        tft.print("User_Setup.h");
        tft.setTextSize(1);
        tft.setCursor(20, 210);
        tft.print("Press BOOT button to retry");
        
        // LED 빨간색
        for (int i = 0; i < NEOPIXEL_COUNT; i++) {
            pixels.setPixelColor(i, pixels.Color(255, 0, 0));
        }
        pixels.show();
        
        touchTestPending = false;  // 타임아웃 상태
        Serial.println("[Touch Test] TIMEOUT - Touch not working!");
    }
    
    // ★ OTA 업데이트 처리
    if (otaUrl.length() > 0 && !otaInProgress) {
        String url = otaUrl;
        otaUrl = "";  // 클리어
        performOtaUpdate(url);
    }
    
    // 깜빡임 처리
    handleBlink();
}
