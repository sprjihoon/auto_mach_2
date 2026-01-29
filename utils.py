"""
공통 유틸리티 함수
"""
import os
import sys
import ctypes
from datetime import datetime
from pathlib import Path
from typing import Optional, List


def get_timestamp() -> str:
    """현재 타임스탬프 반환"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ============================================================
# 관리자 권한 관련
# ============================================================

def is_admin() -> bool:
    """
    현재 프로세스가 관리자 권한으로 실행 중인지 확인
    
    Returns:
        관리자 권한 여부
    """
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def request_admin_restart() -> bool:
    """
    관리자 권한으로 프로그램 재시작 요청
    
    Returns:
        재시작 요청 성공 여부 (성공 시 현재 프로세스 종료됨)
    """
    try:
        if getattr(sys, 'frozen', False):
            # PyInstaller로 빌드된 EXE
            executable = sys.executable
        else:
            # Python 스크립트
            executable = sys.executable
            # Python 인터프리터로 현재 스크립트 실행
        
        # ShellExecute로 관리자 권한 요청
        ret = ctypes.windll.shell32.ShellExecuteW(
            None,           # 부모 윈도우 핸들
            "runas",        # 관리자 권한으로 실행
            executable,     # 실행 파일
            " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "",  # 인자
            None,           # 작업 디렉토리
            1               # SW_SHOWNORMAL
        )
        
        # 반환값이 32보다 크면 성공
        return ret > 32
    except Exception:
        return False


def get_admin_status_message() -> str:
    """
    관리자 권한 상태 메시지 반환
    
    Returns:
        상태 메시지
    """
    if is_admin():
        return "✓ 관리자 권한으로 실행 중"
    else:
        return "⚠️ 일반 권한으로 실행 중 (일부 기능 제한)"


# ============================================================
# 한글 폰트 탐색
# ============================================================

def find_korean_font() -> Optional[str]:
    """
    시스템에서 사용 가능한 한글 폰트 경로 탐색
    
    Returns:
        폰트 파일 경로 또는 None
    """
    # 우선순위 순서대로 한글 폰트 탐색
    korean_fonts = [
        # Windows 기본 한글 폰트
        "C:/Windows/Fonts/malgun.ttf",      # 맑은 고딕
        "C:/Windows/Fonts/malgunbd.ttf",    # 맑은 고딕 Bold
        "C:/Windows/Fonts/NanumGothic.ttf", # 나눔고딕
        "C:/Windows/Fonts/gulim.ttc",       # 굴림
        "C:/Windows/Fonts/batang.ttc",      # 바탕
        "C:/Windows/Fonts/dotum.ttc",       # 돋움
        "C:/Windows/Fonts/ngulim.ttf",      # 새굴림
        # 사용자 폰트 폴더
        os.path.expanduser("~/AppData/Local/Microsoft/Windows/Fonts/malgun.ttf"),
        os.path.expanduser("~/AppData/Local/Microsoft/Windows/Fonts/NanumGothic.ttf"),
    ]
    
    for font_path in korean_fonts:
        if os.path.exists(font_path):
            return font_path
    
    # Windows 폰트 폴더에서 한글 폰트 검색
    fonts_dir = Path("C:/Windows/Fonts")
    if fonts_dir.exists():
        # 한글 폰트 패턴 검색
        korean_patterns = ["malgun", "nanum", "gulim", "batang", "dotum", "gungsuh"]
        for font_file in fonts_dir.glob("*.ttf"):
            for pattern in korean_patterns:
                if pattern in font_file.name.lower():
                    return str(font_file)
        
        # .ttc 파일도 검색
        for font_file in fonts_dir.glob("*.ttc"):
            for pattern in korean_patterns:
                if pattern in font_file.name.lower():
                    return str(font_file)
    
    return None


def get_available_korean_fonts() -> List[str]:
    """
    사용 가능한 모든 한글 폰트 목록 반환
    
    Returns:
        폰트 파일 경로 리스트
    """
    fonts = []
    fonts_dir = Path("C:/Windows/Fonts")
    
    if not fonts_dir.exists():
        return fonts
    
    korean_patterns = ["malgun", "nanum", "gulim", "batang", "dotum", "gungsuh"]
    
    for font_file in fonts_dir.glob("*.ttf"):
        for pattern in korean_patterns:
            if pattern in font_file.name.lower():
                fonts.append(str(font_file))
                break
    
    for font_file in fonts_dir.glob("*.ttc"):
        for pattern in korean_patterns:
            if pattern in font_file.name.lower():
                fonts.append(str(font_file))
                break
    
    return fonts


def get_base_path() -> Path:
    """실행 파일 기준 경로 반환 (PyInstaller 호환)"""
    if getattr(sys, 'frozen', False):
        # PyInstaller로 빌드된 경우
        return Path(sys.executable).parent
    else:
        # 개발 환경
        return Path(__file__).parent


def get_labels_path() -> Path:
    """라벨 PDF 폴더 경로"""
    labels_dir = get_base_path() / "labels"
    labels_dir.mkdir(exist_ok=True)
    return labels_dir


def get_pdf_path(tracking_no: str) -> Path:
    """송장번호로 PDF 파일 경로 반환"""
    return get_labels_path() / f"{tracking_no}.pdf"


def pdf_exists(tracking_no: str) -> bool:
    """PDF 파일 존재 여부 확인"""
    return get_pdf_path(tracking_no).exists()


def format_log_message(level: str, message: str) -> str:
    """로그 메시지 포맷팅"""
    timestamp = get_timestamp()
    return f"[{timestamp}] [{level}] {message}"


def sanitize_barcode(barcode: str) -> str:
    """바코드 문자열 정리"""
    # 앞뒤 공백 제거, 특수문자 정리
    return barcode.strip().replace('\r', '').replace('\n', '')

