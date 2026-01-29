# ESP32 피킹 디바이스 펌웨어

## 주요 기능

- WiFi로 PC WebSocket 서버에 연결
- LCD에 BIN ID, 수량 표시
- NeoPixel LED로 색상 표시
- 버튼 누르면 완료 신호 전송
- **버튼 5초 길게 누르면 WiFi 설정 모드 진입** (Arduino IDE 없이 설정 가능!)

## WiFi 설정 모드 (핵심 기능!)

개발 환경 없이도 스마트폰만으로 WiFi 설정 가능!

### 설정 모드 진입 방법

**방법 1: 버튼 5초 누르기**
```
운영 중 버튼 5초 길게 누름
→ LED 보라색 깜빡임
→ 설정 모드 진입
```

**방법 2: 버튼 누른 채 전원 켜기**
```
버튼 누른 상태로 USB 연결
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
   (LCD에 "Setup Mode / 192.168.4.1" 표시)
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
5. "설정 저장 및 재부팅" 클릭
        ↓
6. ESP32 자동 재부팅 → 새 WiFi로 연결
```

### 설정 페이지 화면

```
┌─────────────────────────────┐
│     🔧 AutoMach 설정        │
│   ESP32 피킹 디바이스 WiFi   │
│                             │
│   [esp32_A1B2C3]            │
│                             │
│   ─── WiFi 연결 ───         │
│   WiFi 이름: [          ]   │
│   비밀번호:  [          ]   │
│                             │
│   ─── 서버 연결 ───         │
│   PC IP 주소: [192.168.0.x] │
│   포트 번호:  [8765       ] │
│                             │
│   [💾 설정 저장 및 재부팅]   │
└─────────────────────────────┘
```

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

### 3. 업로드

1. ESP32를 USB로 연결
2. **도구** → **포트**에서 COM 포트 선택 (예: COM3)
3. **업로드** 버튼 클릭
4. 첫 업로드 후에는 **Arduino IDE 없이** 설정 모드로 WiFi 변경 가능!

## 동작 흐름

```
1. ESP32 전원 ON
   ↓
2. 저장된 설정 로드 (NVS 메모리)
   ↓
3. WiFi 연결 시도
   ├─ 성공 → WebSocket 서버 연결 → 정상 동작
   └─ 실패 → 설정 모드 자동 진입
   ↓
4. PC에서 bind 명령 → BIN ID 할당
   ↓
5. PC에서 display 명령 → LCD/LED 표시
   ↓
6. 버튼 누름 → done 메시지 전송 → PC가 완료 처리
   
언제든지 버튼 5초 누름 → 설정 모드 진입 가능!
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

## LED 상태 표시

| 상태 | LED 색상 |
|------|----------|
| 부팅 중 | 파란색 순차 점등 |
| WiFi 연결 성공 | 초록색 |
| WiFi 연결 실패 | 빨간색 |
| WebSocket 연결 해제 | 주황색 |
| 설정 모드 | 파란색 순환 애니메이션 |
| 설정 모드 진입 중 | 보라색 깜빡임 |
| 버튼 완료 | 초록색 깜빡임 |

## LED 색상 (피킹 시)

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
- SSID/Password 확인 (설정 모드에서 재설정)
- 2.4GHz WiFi인지 확인 (5GHz 안됨!)
- 공유기 재부팅
- 버튼 5초 눌러서 설정 모드 진입 후 재설정

### WebSocket 연결 안됨
- PC IP 주소 확인 (`ipconfig`)
- PC에서 서버 실행 중인지 확인
- 방화벽에서 8765 포트 허용
- 설정 모드에서 PC IP 재확인

### LCD 표시 안됨
- I2C 주소 확인 (0x27 또는 0x3F)
- SDA/SCL 배선 확인

### 버튼 동작 안됨
- GPIO4 연결 확인
- 버튼 → GND 연결 확인

### 설정 모드 진입 안됨
- 버튼을 5초 이상 누르고 있어야 함
- 또는 버튼 누른 채로 전원 켜기

## 시리얼 모니터

업로드 후 **도구** → **시리얼 모니터** (115200 baud)에서 디버그 메시지 확인:

```
========================================
  ESP32 피킹 디바이스 시작
  버튼 5초 누르기 = WiFi 설정 모드
========================================
Device ID: esp32_A1B2C3
=== 저장된 설정 ===
WiFi SSID: MyWiFi
WS Host: 192.168.0.100
WS Port: 8765
WiFi 연결 중: MyWiFi
......
WiFi 연결됨!
IP: 192.168.0.150
WebSocket 연결 중: 192.168.0.100:8765
[WS] 연결됨!
[WS] Hello 전송: {"type":"hello","device_id":"esp32_A1B2C3"}
```
