/**
 * ESP32 시리얼 테스트 펌웨어
 * 
 * WiFi 없이 USB 시리얼로 테스트
 * PC에서 JSON 명령 전송 → ESP32 동작 확인
 * 
 * 테스트 명령 (시리얼 모니터에서 입력):
 *   {"type":"display","bin":"A01","color":"purple","qty":5}
 *   {"type":"display","bin":"B02","color":"green","qty":3,"blink":true}
 *   {"type":"off"}
 *   {"type":"test"}  ← LED/LCD 전체 테스트
 */

#include <ArduinoJson.h>
#include <Adafruit_NeoPixel.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>

// ===== 핀 설정 =====
#define BUTTON_PIN      4      // 완료 버튼 (풀업)
#define NEOPIXEL_PIN    15     // NeoPixel 데이터 핀
#define NEOPIXEL_COUNT  8      // NeoPixel LED 개수
#define I2C_SDA         21     // I2C SDA
#define I2C_SCL         22     // I2C SCL

// ===== 객체 생성 =====
Adafruit_NeoPixel pixels(NEOPIXEL_COUNT, NEOPIXEL_PIN, NEO_GRB + NEO_KHZ800);
LiquidCrystal_I2C lcd(0x27, 16, 2);  // I2C 주소 0x27, 16x2 LCD

// ===== 상태 변수 =====
String deviceId = "esp32_TEST";
String currentBin = "";
bool buttonPressed = false;
unsigned long lastButtonTime = 0;
const unsigned long DEBOUNCE_TIME = 300;

// 깜빡임 관련
bool blinkEnabled = false;
unsigned long lastBlinkTime = 0;
bool blinkState = true;
const unsigned long BLINK_INTERVAL = 500;
uint32_t currentColor = 0;

// 시리얼 버퍼
String serialBuffer = "";

// LCD 존재 여부
bool lcdAvailable = false;

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

// ===== LCD 초기화 (존재 확인) =====
bool initLCD() {
    Wire.beginTransmission(0x27);
    if (Wire.endTransmission() == 0) {
        lcd.init();
        lcd.backlight();.




        
        return true;
    }
    // 0x3F 주소도 시도
    Wire.beginTransmission(0x3F);
    if (Wire.endTransmission() == 0) {
        LiquidCrystal_I2C lcd2(0x3F, 16, 2);
        lcd2.init();
        lcd2.backlight();
        return true;
    }
    return false;
}

// ===== 메시지 처리 =====
void handleMessage(String payload) {
    StaticJsonDocument<256> doc;
    DeserializationError error = deserializeJson(doc, payload);
    
    if (error) {
        Serial.println("{\"error\":\"JSON parse error\"}");
        return;
    }
    
    String msgType = doc["type"].as<String>();
    
    if (msgType == "display") {
        // 디스플레이 명령
        String binId = doc["bin"].as<String>();
        String color = doc["color"].as<String>();
        int qty = doc["qty"] | 0;
        blinkEnabled = doc["blink"] | false;
        
        currentBin = binId;
        
        Serial.print("{\"status\":\"display\",\"bin\":\"");
        Serial.print(binId);
        Serial.print("\",\"color\":\"");
        Serial.print(color);
        Serial.print("\",\"qty\":");
        Serial.print(qty);
        Serial.println("}");
        
        // LCD 표시
        if (lcdAvailable) {
            lcd.clear();
            lcd.setCursor(0, 0);
            lcd.print("BIN: ");
            lcd.print(binId);
            lcd.setCursor(0, 1);
            lcd.print("Qty: ");
            lcd.print(qty);
        }
        
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
        Serial.println("{\"status\":\"off\"}");
        
        blinkEnabled = false;
        currentColor = 0;
        currentBin = "";
        
        for (int i = 0; i < NEOPIXEL_COUNT; i++) {
            pixels.setPixelColor(i, 0);
        }
        pixels.show();
        
        if (lcdAvailable) {
            lcd.clear();
            lcd.setCursor(0, 0);
            lcd.print("Ready");
        }
        
    } else if (msgType == "test") {
        // 전체 테스트
        runFullTest();
        
    } else {
        Serial.println("{\"error\":\"unknown type\"}");
    }
}

// ===== 전체 테스트 =====
void runFullTest() {
    Serial.println("{\"status\":\"test_start\"}");
    
    // LCD 테스트
    if (lcdAvailable) {
        lcd.clear();
        lcd.setCursor(0, 0);
        lcd.print("LCD TEST OK!");
        Serial.println("{\"test\":\"lcd\",\"result\":\"ok\"}");
    } else {
        Serial.println("{\"test\":\"lcd\",\"result\":\"not_found\"}");
    }
    
    // LED 색상 테스트
    String colors[] = {"red", "green", "blue", "purple", "yellow", "cyan", "white"};
    String colorNames[] = {"빨강", "초록", "파랑", "보라", "노랑", "청록", "흰색"};
    
    for (int c = 0; c < 7; c++) {
        uint32_t color = getColor(colors[c]);
        for (int i = 0; i < NEOPIXEL_COUNT; i++) {
            pixels.setPixelColor(i, color);
        }
        pixels.show();
        
        if (lcdAvailable) {
            lcd.setCursor(0, 1);
            lcd.print("LED: ");
            lcd.print(colorNames[c]);
            lcd.print("    ");
        }
        
        Serial.print("{\"test\":\"led\",\"color\":\"");
        Serial.print(colors[c]);
        Serial.println("\"}");
        
        delay(500);
    }
    
    // LED 끄기
    for (int i = 0; i < NEOPIXEL_COUNT; i++) {
        pixels.setPixelColor(i, 0);
    }
    pixels.show();
    
    // 버튼 테스트 안내
    if (lcdAvailable) {
        lcd.clear();
        lcd.setCursor(0, 0);
        lcd.print("Press BUTTON");
        lcd.setCursor(0, 1);
        lcd.print("to test...");
    }
    Serial.println("{\"test\":\"button\",\"message\":\"press button now\"}");
    
    Serial.println("{\"status\":\"test_end\"}");
}

// ===== Done 메시지 전송 =====
void sendDone() {
    StaticJsonDocument<128> doc;
    doc["type"] = "done";
    doc["bin_id"] = currentBin.length() > 0 ? currentBin : "none";
    doc["device_id"] = deviceId;
    
    String json;
    serializeJson(doc, json);
    Serial.println(json);
    
    // 완료 표시 (초록색 깜빡임)
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
    
    if (lcdAvailable) {
        lcd.clear();
        lcd.setCursor(0, 0);
        lcd.print("DONE!");
        delay(500);
        lcd.clear();
        lcd.setCursor(0, 0);
        lcd.print("Ready");
    }
}

// ===== 버튼 처리 =====
void handleButton() {
    bool currentState = digitalRead(BUTTON_PIN) == LOW;
    unsigned long now = millis();
    
    if (currentState && !buttonPressed && (now - lastButtonTime > DEBOUNCE_TIME)) {
        buttonPressed = true;
        lastButtonTime = now;
        sendDone();
    } else if (!currentState) {
        buttonPressed = false;
    }
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

// ===== 시리얼 입력 처리 =====
void handleSerial() {
    while (Serial.available()) {
        char c = Serial.read();
        if (c == '\n' || c == '\r') {
            if (serialBuffer.length() > 0) {
                handleMessage(serialBuffer);
                serialBuffer = "";
            }
        } else {
            serialBuffer += c;
        }
    }
}

// ===== 설정 =====
void setup() {
    Serial.begin(115200);
    delay(1000);
    
    Serial.println();
    Serial.println("======================================");
    Serial.println("  ESP32 Serial Test Mode");
    Serial.println("======================================");
    
    // 버튼 핀 설정
    pinMode(BUTTON_PIN, INPUT_PULLUP);
    
    // I2C 초기화
    Wire.begin(I2C_SDA, I2C_SCL);
    
    // LCD 초기화
    lcdAvailable = initLCD();
    if (lcdAvailable) {
        lcd.clear();
        lcd.setCursor(0, 0);
        lcd.print("Serial Test");
        lcd.setCursor(0, 1);
        lcd.print("Mode Ready!");
        Serial.println("{\"lcd\":\"found\"}");
    } else {
        Serial.println("{\"lcd\":\"not_found\"}");
    }
    
    // NeoPixel 초기화
    pixels.begin();
    pixels.setBrightness(50);
    pixels.clear();
    pixels.show();
    
    // 시작 애니메이션 (파란색 웨이브)
    for (int i = 0; i < NEOPIXEL_COUNT; i++) {
        pixels.setPixelColor(i, pixels.Color(0, 0, 255));
        pixels.show();
        delay(50);
    }
    delay(200);
    for (int i = 0; i < NEOPIXEL_COUNT; i++) {
        pixels.setPixelColor(i, 0);
        pixels.show();
        delay(50);
    }
    
    Serial.println();
    Serial.println("{\"status\":\"ready\",\"device_id\":\"esp32_TEST\"}");
    Serial.println();
    Serial.println("Commands:");
    Serial.println("  {\"type\":\"test\"}");
    Serial.println("  {\"type\":\"display\",\"bin\":\"A01\",\"color\":\"purple\",\"qty\":5}");
    Serial.println("  {\"type\":\"display\",\"bin\":\"B02\",\"color\":\"green\",\"qty\":3,\"blink\":true}");
    Serial.println("  {\"type\":\"off\"}");
    Serial.println();
}

// ===== 메인 루프 =====
void loop() {
    handleSerial();
    handleButton();
    handleBlink();
}
