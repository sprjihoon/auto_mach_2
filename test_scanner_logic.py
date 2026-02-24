"""
스캐너 없이 바코드 버퍼 로직 검증 (앞글자 누락 방지)
실제 스캐너처럼 "1~2번째 키 간격이 긴" 입력을 시뮬레이션해 전체 바코드가 유지되는지 확인
"""
from __future__ import annotations
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ScannerListener와 동일한 상수
SCAN_SPEED_THRESHOLD_MS = 120
SCAN_HEAD_PROTECT_LEN = 10
MIN_BARCODE_LENGTH = 4


def simulate_buffer_decision(buffer: str, buffer_len: int, key_name: str, time_diff_ms: float) -> tuple[str, str]:
    """
    ScannerListener와 동일한 규칙으로 append vs replace 결정.
    Returns (new_buffer, emitted_barcode or "").
    """
    if key_name == "enter":
        if buffer_len >= MIN_BARCODE_LENGTH:
            return "", buffer.strip()
        return "", ""
    if key_name == "backspace":
        return "", ""
    if len(key_name) != 1:
        return buffer, ""
    # 일반 문자
    if buffer_len == 0:
        return key_name, ""
    if buffer_len < SCAN_HEAD_PROTECT_LEN:
        return buffer + key_name, ""
    if time_diff_ms <= SCAN_SPEED_THRESHOLD_MS:
        return buffer + key_name, ""
    return key_name, ""


def run_sequence(keys_with_delays: list[tuple[str, float]]) -> str:
    """(key_name, time_diff_ms) 리스트로 시뮬레이션 후 Enter 시점의 바코드 반환"""
    buffer = ""
    now_ms = 0.0
    for key_name, time_diff_ms in keys_with_delays:
        now_ms += time_diff_ms
        new_buffer, emitted = simulate_buffer_decision(buffer, len(buffer), key_name, time_diff_ms)
        if emitted:
            return emitted
        buffer = new_buffer
    return buffer  # Enter 없이 끝나면 버퍼 내용 반환


def test_slow_second_key():
    """1~2번째 키 간격이 150ms(임계값 초과)인 경우: 앞글자 유지되어야 함"""
    barcode = "1234567890123"
    # 첫 키 후 150ms 뒤 2번째 키 (과거 로직이면 여기서 버퍼 교체로 '1' 손실)
    keys = [(c, 150.0 if i == 1 else 10.0) for i, c in enumerate(barcode)]
    keys.append(("enter", 10.0))
    result = run_sequence(keys)
    assert result == barcode, f"Expected {barcode!r}, got {result!r}"
    print("[OK] test_slow_second_key: 전체 바코드 유지됨")


def test_slow_third_and_fourth():
    """2번째, 3번째 키도 간격이 큰 경우"""
    barcode = "ABC1234567890"
    # 0ms: A, 200ms: B, 200ms: C, 이후 10ms 간격
    keys = [("A", 0.0), ("B", 200.0), ("C", 200.0)]
    keys += [(c, 10.0) for c in "1234567890"]
    keys.append(("enter", 10.0))
    result = run_sequence(keys)
    assert result == barcode, f"Expected {barcode!r}, got {result!r}"
    print("[OK] test_slow_third_and_fourth: 앞 10글자 보호로 전체 유지됨")


def test_after_10_chars_slow_reset():
    """10글자 이상 쌓인 뒤 느린 입력은 교체(사람 타이핑)로 동작해야 함"""
    # "1234567890" (10글자) + 200ms 후 'X' → 버퍼가 'X'로 교체, 이후 빠르게 WXYZ + Enter → "XWYZ" (4자 이상만 emit)
    keys = [(c, 10.0) for c in "1234567890"]
    keys.append(("X", 200.0))
    keys += [("W", 10.0), ("Y", 10.0), ("Z", 10.0)]
    keys.append(("enter", 10.0))
    result = run_sequence(keys)
    assert result == "XWYZ", f"Expected 'XWYZ' (replace then append), got {result!r}"
    print("[OK] test_after_10_chars_slow_reset: 10글자 이후 느린 입력은 교체됨")


if __name__ == "__main__":
    test_slow_second_key()
    test_slow_third_and_fourth()
    test_after_10_chars_slow_reset()
    print("\n모든 테스트 통과 (스캐너 앞글자 누락 방지 로직 정상)")
