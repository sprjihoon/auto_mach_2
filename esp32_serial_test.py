"""
ESP32 시리얼 테스트 스크립트

사용법:
    python esp32_serial_test.py

명령어:
    test     - LED/LCD 전체 테스트
    on       - 디스플레이 켜기 (보라색, 수량 5)
    off      - 디스플레이 끄기
    red      - 빨간색
    green    - 초록색
    blue     - 파란색
    purple   - 보라색
    blink    - 깜빡임 모드
    quit     - 종료
"""

import serial
import serial.tools.list_ports
import json
import threading
import time


def find_esp32_port():
    """ESP32 (CH340) 포트 자동 찾기"""
    ports = serial.tools.list_ports.comports()
    for port in ports:
        if 'CH340' in port.description or 'USB' in port.description:
            return port.device
    return None


def serial_reader(ser, running):
    """시리얼 수신 스레드"""
    while running[0]:
        try:
            if ser.in_waiting:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    print(f"[ESP32] {line}")
        except Exception as e:
            if running[0]:
                print(f"[오류] {e}")
        time.sleep(0.01)


def send_command(ser, cmd_dict):
    """명령 전송"""
    json_str = json.dumps(cmd_dict) + '\n'
    ser.write(json_str.encode())
    print(f"[전송] {json_str.strip()}")


def main():
    # 포트 찾기
    port = find_esp32_port()
    if not port:
        print("ESP32를 찾을 수 없습니다.")
        print("사용 가능한 포트:")
        for p in serial.tools.list_ports.comports():
            print(f"  {p.device}: {p.description}")
        port = input("포트 입력 (예: COM6): ").strip()
    
    print(f"\n포트: {port}")
    print("연결 중...")
    
    try:
        ser = serial.Serial(port, 115200, timeout=0.1)
        time.sleep(2)  # ESP32 리셋 대기
        print("연결됨!\n")
    except Exception as e:
        print(f"연결 실패: {e}")
        return
    
    # 수신 스레드 시작
    running = [True]
    reader_thread = threading.Thread(target=serial_reader, args=(ser, running))
    reader_thread.daemon = True
    reader_thread.start()
    
    # 명령어 안내
    print("=" * 50)
    print("ESP32 시리얼 테스트")
    print("=" * 50)
    print("명령어:")
    print("  test   - LED/LCD 전체 테스트")
    print("  on     - 디스플레이 ON (보라, 수량 5)")
    print("  off    - 디스플레이 OFF")
    print("  red    - 빨간색")
    print("  green  - 초록색")
    print("  blue   - 파란색")
    print("  purple - 보라색")
    print("  blink  - 깜빡임")
    print("  quit   - 종료")
    print("  또는 직접 JSON 입력")
    print("=" * 50)
    print()
    
    try:
        while True:
            cmd = input("> ").strip().lower()
            
            if not cmd:
                continue
            elif cmd == 'quit' or cmd == 'q':
                break
            elif cmd == 'test':
                send_command(ser, {"type": "test"})
            elif cmd == 'on':
                send_command(ser, {"type": "display", "bin": "A01", "color": "purple", "qty": 5})
            elif cmd == 'off':
                send_command(ser, {"type": "off"})
            elif cmd == 'red':
                send_command(ser, {"type": "display", "bin": "A01", "color": "red", "qty": 1})
            elif cmd == 'green':
                send_command(ser, {"type": "display", "bin": "A01", "color": "green", "qty": 1})
            elif cmd == 'blue':
                send_command(ser, {"type": "display", "bin": "A01", "color": "blue", "qty": 1})
            elif cmd == 'purple':
                send_command(ser, {"type": "display", "bin": "A01", "color": "purple", "qty": 1})
            elif cmd == 'blink':
                send_command(ser, {"type": "display", "bin": "A01", "color": "purple", "qty": 5, "blink": True})
            elif cmd.startswith('{'):
                # JSON 직접 입력
                try:
                    json.loads(cmd)  # 유효성 검사
                    ser.write((cmd + '\n').encode())
                    print(f"[전송] {cmd}")
                except json.JSONDecodeError:
                    print("[오류] 잘못된 JSON 형식")
            else:
                print(f"알 수 없는 명령: {cmd}")
    
    except KeyboardInterrupt:
        print("\n중단됨")
    
    finally:
        running[0] = False
        ser.close()
        print("연결 종료")


if __name__ == "__main__":
    main()
