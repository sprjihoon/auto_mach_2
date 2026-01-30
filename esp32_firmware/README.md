# ESP32 피킹 디바이스 펌웨어

## ESP32-2432S028 (Cheap Yellow Display) 전용

2.8인치 TFT 컬러 디스플레이가 내장된 ESP32 보드를 위한 펌웨어입니다.

## 주요 기능

- WiFi로 PC WebSocket 서버에 연결
- **TFT 컬러 디스플레이**에 BIN ID, 수량 표시
- NeoPixel LED로 색상 표시 (선택사항)
- 내장 RGB LED 지원
- 버튼 누르면 완료 신호 전송
- **버튼 5초 길게 누르면 WiFi 설정 모드 진입** (Arduino IDE 없이 설정 가능!)

## 필요 하드웨어

| 부품 | 설명 |
|------|------|
| ESP32-2432S028 | Cheap Yellow Display (CYD) 보드 |
| WS2812B NeoPixel | 색상 LED (선택사항, GPIO27) |

### CYD 보드 내장 기능
- 2.8인치 TFT 320x240 (ILI9341)
- RGB LED (GPIO 4, 16, 17)
- BOOT 버튼 (GPIO 0)
- 터치스크린 (미사용)

## WiFi 설정 모드 (핵심 기능!)

개발 환경 없이도 스마트폰만으로 WiFi 설정 가능!

### 설정 모드 진입 방법

**방법 1: 버튼 5초 누르기**
```
운영 중 BOOT 버튼 5초 길게 누름
→ LED 보라색 깜빡임
→ 설정 모드 진입
```

**방법 2: 버튼 누른 채 전원 켜기**
```
BOOT 버튼 누른 상태로 USB 연결
→ "Release button" 표시
→ 버튼 떼면 설정 모드 진입
```

**방법 3: WiFi 연결 실패 시 자동 진입**
```
저장된 WiFi에 연결 실패
→ 자동으로 설정 모드 진입
```

### 설정 방법

```
1. ESP32가 "AutoMach_Setup" 핫스팟 생성
   (화면에 "SETUP MODE / 192.168.4.1" 표시)
        ↓
2. 스마트폰/PC에서 "AutoMach_Setup" WiFi 연결
        ↓
3. 브라우저에서 http://192.168.4.1 접속
        ↓
4. 설정 페이지에서 입력:
   - WiFi 이름 (SSID)
   - WiFi 비밀번호
   - PC IP 주소
   - 포트 번호 (기본 8765)
        ↓
5. "Save & Reboot" 클릭
        ↓
6. ESP32 자동 재부팅 → 새 WiFi로 연결
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
| TFT_eSPI | TFT_eSPI | Bodmer |
| ArduinoJson | ArduinoJson | Benoit Blanchon |
| WebSockets | WebSockets | Markus Sattler |
| Adafruit NeoPixel | Adafruit NeoPixel | Adafruit |

### 3. TFT_eSPI 설정 (중요!)

TFT_eSPI 라이브러리는 CYD 보드에 맞게 **반드시** 설정해야 합니다!

#### 방법 A: User_Setup.h 교체 (권장)

1. 이 폴더의 `User_Setup.h` 파일을 복사
2. TFT_eSPI 라이브러리 폴더로 이동:
   - Windows: `C:\Users\<사용자명>\Documents\Arduino\libraries\TFT_eSPI\`
   - Mac: `~/Documents/Arduino/libraries/TFT_eSPI/`
3. 기존 `User_Setup.h`를 백업 후 새 파일로 **교체**

#### 방법 B: User_Setup_Select.h 수정

1. `TFT_eSPI/User_Setup_Select.h` 파일 열기
2. 기본 `#include <User_Setup.h>` 줄 주석 처리
3. 아래 줄 추가 (또는 주석 해제):
```cpp
#include <User_Setups/Setup66_Cheap_Yellow_Display_ESP32-2432S028.h>
```

### 4. 업로드

1. ESP32를 USB로 연결
2. **도구** → **포트**에서 COM 포트 선택
3. 보드 설정:
   - Board: ESP32 Dev Module
   - Flash Size: 4MB
   - Partition Scheme: Default 4MB with spiffs
4. **업로드** 버튼 클릭

#### 업로드 문제 시
- BOOT 버튼을 누른 상태로 EN 버튼을 눌렀다 놓기
- CH340 드라이버 설치 확인

## 화면 표시 예시

### 대기 상태
```
┌────────────────────┐
│      READY         │  ← 회색 헤더
├────────────────────┤
│                    │
│   Assigned BIN:    │
│     A-01-01        │  ← 초록색
│                    │
│   esp32_AABBCC     │  ← 회색 (장치 ID)
│   192.168.0.150    │  ← 회색 (IP)
│                    │
├────────────────────┤
│      STANDBY       │  ← 상태바
└────────────────────┘
```

### 피킹 상태
```
┌────────────────────┐
│      A-01-01       │  ← 색상 배경 (BIN ID)
├────────────────────┤
│        QTY         │
│                    │
│        5           │  ← 큰 숫자
│                    │
│       선별         │  ← 모드
│                    │
├────────────────────┤
│      PICKING       │  ← 색상 상태바
└────────────────────┘
```

### 설정 모드
```
┌────────────────────┐
│    SETUP MODE      │  ← 보라색 헤더
├────────────────────┤
│                    │
│  Connect to WiFi:  │
│   AutoMach_Setup   │  ← 노란색
│                    │
│     Then open:     │
│   192.168.4.1      │  ← 초록색
│                    │
│   esp32_AABBCC     │
│                    │
└────────────────────┘
```

## 핀 설정

### CYD 내장 핀 (변경 불가)

| 기능 | GPIO |
|------|------|
| TFT MISO | 12 |
| TFT MOSI | 13 |
| TFT SCLK | 14 |
| TFT CS | 15 |
| TFT DC | 2 |
| TFT 백라이트 | 21 |
| 내장 LED R | 4 |
| 내장 LED G | 16 |
| 내장 LED B | 17 |
| BOOT 버튼 | 0 |

### 외부 연결 (선택)

| 기능 | GPIO |
|------|------|
| NeoPixel | 27 |

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

## LED 상태 표시

| 상태 | LED 색상 | TFT 표시 |
|------|----------|----------|
| 부팅 중 | 파란색 순차 점등 | Initializing... |
| WiFi 연결 성공 | 초록색 | WiFi OK + IP |
| WiFi 연결 실패 | 빨간색 | WiFi FAIL |
| WebSocket 연결 해제 | 주황색 | DISCONNECTED |
| 설정 모드 | 파란색 순환 | SETUP MODE |
| 설정 모드 진입 중 | 보라색 깜빡임 | ENTERING SETUP |
| 버튼 완료 | 초록색 깜빡임 | 초록색 플래시 |

## 지원 색상

| 색상명 | 한글 | LED RGB | TFT |
|--------|------|---------|-----|
| purple | 보라 | (128, 0, 128) | 보라 |
| green | 초록 | (0, 255, 0) | 초록 |
| red | 빨강 | (255, 0, 0) | 빨강 |
| blue | 파랑 | (0, 0, 255) | 파랑 |
| yellow | 노랑 | (255, 255, 0) | 노랑 |
| orange | 주황 | (255, 165, 0) | 주황 |
| white | 흰색 | (255, 255, 255) | 흰색 |
| cyan | 청록 | (0, 255, 255) | 청록 |

## 트러블슈팅

### 화면이 안 나와요
- TFT_eSPI User_Setup.h 설정 확인 (가장 중요!)
- User_Setup.h를 교체했는지 확인
- Arduino IDE 재시작 후 다시 업로드

### 색상이 이상해요 (반전됨)
- User_Setup.h에서 아래 설정 시도:
```cpp
#define TFT_INVERSION_ON
// 또는
#define TFT_INVERSION_OFF
```
- RGB/BGR 순서 변경:
```cpp
#define TFT_RGB_ORDER TFT_RGB
// 또는
#define TFT_RGB_ORDER TFT_BGR
```

### 화면이 거꾸로 나와요
- 펌웨어의 `tft.setRotation()` 값 변경:
  - 0: 세로 (기본)
  - 1: 가로 (시계방향 90도)
  - 2: 세로 (180도)
  - 3: 가로 (반시계방향 90도)

### WiFi 연결 안됨
- SSID/Password 확인 (설정 모드에서 재설정)
- 2.4GHz WiFi인지 확인 (5GHz 안됨!)
- 버튼 5초 눌러서 설정 모드 진입 후 재설정

### WebSocket 연결 안됨
- PC IP 주소 확인 (`ipconfig`)
- PC에서 서버 실행 중인지 확인
- 방화벽에서 8765 포트 허용
- 설정 모드에서 PC IP 재확인

### 버튼 동작 안됨
- BOOT 버튼 (GPIO 0) 사용
- 터치스크린 버튼 아님!

## 시리얼 모니터

업로드 후 **도구** → **시리얼 모니터** (115200 baud)에서 디버그 확인:

```
========================================
  ESP32 CYD Picking Device
  Hold button 5s = WiFi Setup Mode
========================================
Device ID: esp32_A1B2C3
=== 저장된 설정 ===
WiFi SSID: spring303
WS Host: 192.168.0.100
WS Port: 8765
Connecting to WiFi: spring303
......
WiFi Connected!
IP: 192.168.0.150
Connecting WebSocket: 192.168.0.100:8765
[WS] Connected!
[WS] Hello sent: {"type":"hello","device_id":"esp32_A1B2C3"}
```

## 파일 목록

| 파일 | 설명 |
|------|------|
| esp32_firmware.ino | 메인 펌웨어 |
| User_Setup.h | TFT_eSPI 설정 (라이브러리에 복사) |
| README.md | 이 문서 |
