# ESP32 피킹 디바이스 펌웨어

## 필요 하드웨어

| 부품 | 설명 | 연결 |
|------|------|------|
| ESP32 DevKit | 메인 보드 | - |
| I2C LCD 16x2 | 정보 표시 | SDA→GPIO21, SCL→GPIO22 |
| WS2812B NeoPixel | 색상 LED | DATA→GPIO15 |
| 푸시 버튼 | 완료 버튼 | GPIO4 (내장 풀업 사용) |

## 회로 연결

```
ESP32 DevKit
┌─────────────────────────────┐
│                             │
│  GPIO4  ────────○ 버튼 ─── GND
│                             │
│  GPIO15 ──────── NeoPixel DATA
│  3.3V   ──────── NeoPixel VCC
│  GND    ──────── NeoPixel GND
│                             │
│  GPIO21 (SDA) ── LCD SDA
│  GPIO22 (SCL) ── LCD SCL
│  3.3V   ──────── LCD VCC
│  GND    ──────── LCD GND
│                             │
└─────────────────────────────┘
```

## Arduino IDE 설정

### 1. ESP32 보드 추가

1. **파일** → **기본설정** → **추가 보드 관리자 URL**에 추가:
   ```
   https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
   ```

2. **도구** → **보드** → **보드 관리자**에서 `esp32` 검색 후 설치

3. **도구** → **보드**에서 `ESP32 Dev Module` 선택

### 2. 필요 라이브러리 설치

**스케치** → **라이브러리 포함** → **라이브러리 관리**에서:

| 라이브러리 | 검색어 | 제작자 |
|-----------|--------|--------|
| ArduinoJson | ArduinoJson | Benoit Blanchon |
| WebSockets | WebSockets | Markus Sattler |
| Adafruit NeoPixel | Adafruit NeoPixel | Adafruit |
| LiquidCrystal_I2C | LiquidCrystal I2C | Frank de Brabander |

### 3. WiFi 설정 수정

`esp32_firmware.ino` 파일에서 다음 부분 수정:

```cpp
// ===== WiFi 설정 (수정 필요!) =====
const char* WIFI_SSID = "YOUR_WIFI_SSID";      // WiFi 이름
const char* WIFI_PASSWORD = "YOUR_WIFI_PASS";  // WiFi 비밀번호
const char* WS_HOST = "192.168.0.100";         // PC IP 주소
const int WS_PORT = 8765;                       // WebSocket 포트
```

**PC IP 주소 확인 방법:**
```powershell
ipconfig
```
→ IPv4 주소 확인 (예: 192.168.0.100)

### 4. 업로드

1. ESP32를 USB로 연결
2. **도구** → **포트**에서 COM 포트 선택 (예: COM3)
3. **업로드** 버튼 클릭

## 동작 흐름

```
1. ESP32 전원 ON
   ↓
2. WiFi 연결
   ↓
3. PC WebSocket 서버 연결 (ws://PC_IP:8765)
   ↓
4. hello 메시지 전송 → PC가 장치 인식
   ↓
5. PC에서 bind 명령 → BIN ID 할당
   ↓
6. PC에서 display 명령 → LCD/LED 표시
   ↓
7. 버튼 누름 → done 메시지 전송 → PC가 완료 처리
```

## 통신 프로토콜

### ESP32 → PC

```json
// 연결 시
{ "type": "hello", "device_id": "esp32_A1B2C3" }

// 버튼 눌림 (완료)
{ "type": "done", "bin_id": "BIN-01", "device_id": "esp32_A1B2C3" }
```

### PC → ESP32

```json
// BIN 바인딩
{ "type": "bind", "bin_id": "BIN-01" }

// 디스플레이 표시
{ "type": "display", "mode": "full_pick", "bin": "BIN-01", "color": "purple", "qty": 3, "blink": false }

// 끄기
{ "type": "off", "bin": "BIN-01" }
```

## LED 색상

| 색상명 | 한글 | RGB |
|--------|------|-----|
| purple | 보라 | (128, 0, 128) |
| green | 초록 | (0, 255, 0) |
| red | 빨강 | (255, 0, 0) |
| blue | 파랑 | (0, 0, 255) |
| yellow | 노랑 | (255, 255, 0) |
| orange | 주황 | (255, 165, 0) |
| white | 흰색 | (255, 255, 255) |
| cyan | 청록 | (0, 255, 255) |

## 트러블슈팅

### WiFi 연결 안됨
- SSID/Password 확인
- 2.4GHz WiFi인지 확인 (5GHz 안됨)
- 공유기 재부팅

### WebSocket 연결 안됨
- PC IP 주소 확인 (`ipconfig`)
- PC에서 서버 실행 중인지 확인
- 방화벽에서 8765 포트 허용

### LCD 표시 안됨
- I2C 주소 확인 (0x27 또는 0x3F)
- SDA/SCL 배선 확인

### 버튼 동작 안됨
- GPIO4 연결 확인
- 버튼 → GND 연결 확인

## 시리얼 모니터

업로드 후 **도구** → **시리얼 모니터** (115200 baud)에서 디버그 메시지 확인 가능:

```
=== ESP32 피킹 디바이스 시작 ===
Device ID: esp32_A1B2C3
WiFi 연결 중...
WiFi 연결됨!
IP: 192.168.0.150
[WS] 연결됨!
[WS] Hello 전송: {"type":"hello","device_id":"esp32_A1B2C3"}
```
