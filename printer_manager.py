"""
프린터 관리 모듈
Windows 프린터 목록 조회, 설정 저장/로드, PDF 출력 기능 제공
"""
import os
import json
from pathlib import Path
from typing import Optional, List, Dict
import tempfile

# win32api, win32print는 선택적 (pywin32 설치 시에만 사용)
try:
    import win32api
    import win32print
    HAS_WIN32API = True
except ImportError:
    HAS_WIN32API = False


def get_settings_path() -> Path:
    """설정 파일 경로 반환"""
    base_path = Path(__file__).parent
    return base_path / "settings.json"


def get_printers() -> List[str]:
    """
    Windows에 설치된 프린터 목록 반환
    
    Returns:
        프린터 이름 리스트
    """
    printers = []
    if not HAS_WIN32API:
        return printers
    
    try:
        # 로컬 및 네트워크 프린터 모두 조회
        printer_info = win32print.EnumPrinters(
            win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        )
        printers = [info[2] for info in printer_info]
    except Exception as e:
        print(f"프린터 목록 조회 오류: {str(e)}")
    
    return printers


def save_printer_settings(label_printer: Optional[str] = None, a4_printer: Optional[str] = None) -> bool:
    """
    settings.json에 두 프린터 이름 저장
    
    Args:
        label_printer: 라벨 프린터 이름
        a4_printer: A4 프린터 이름
    
    Returns:
        저장 성공 여부
    """
    settings_path = get_settings_path()
    
    # 기존 설정 로드
    settings = {}
    if settings_path.exists():
        try:
            with open(settings_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)
        except Exception:
            settings = {}
    
    # 새 설정 업데이트
    if label_printer is not None:
        settings["label_printer"] = label_printer
    if a4_printer is not None:
        settings["a4_printer"] = a4_printer
    
    # 저장
    try:
        with open(settings_path, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"설정 저장 오류: {str(e)}")
        return False


def load_printer_settings() -> Dict[str, Optional[str]]:
    """
    settings.json에서 프린터 이름 로드
    
    Returns:
        {"label_printer": str or None, "a4_printer": str or None}
    """
    settings_path = get_settings_path()
    
    if not settings_path.exists():
        return {"label_printer": None, "a4_printer": None}
    
    try:
        with open(settings_path, 'r', encoding='utf-8') as f:
            settings = json.load(f)
        
        return {
            "label_printer": settings.get("label_printer"),
            "a4_printer": settings.get("a4_printer")
        }
    except Exception as e:
        print(f"설정 로드 오류: {str(e)}")
        return {"label_printer": None, "a4_printer": None}


def print_pdf_with_printer(pdf_path: str, printer_name: Optional[str] = None) -> bool:
    """
    지정된 프린터로 PDF 출력 (PyMuPDF + win32ui로 직접 출력 - 대화상자 없음)
    
    Args:
        pdf_path: 출력할 PDF 파일 경로
        printer_name: 프린터 이름 (None이면 기본 프린터 사용)
    
    Returns:
        출력 성공 여부
    """
    if not os.path.exists(pdf_path):
        print(f"PDF 파일 없음: {pdf_path}")
        return False
    
    # 프린터 이름이 없으면 기본 프린터 사용
    if not printer_name and HAS_WIN32API:
        try:
            printer_name = win32print.GetDefaultPrinter()
        except Exception:
            pass
    
    # 프린터 존재 확인
    if printer_name and HAS_WIN32API:
        printers = get_printers()
        if printer_name not in printers:
            print(f"프린터를 찾을 수 없습니다: {printer_name}")
            return False
    
    # PyMuPDF + win32ui로 직접 출력 (1장만 출력되도록 최적화)
    try:
        import fitz  # PyMuPDF
        from PIL import Image, ImageWin
        import win32ui
        import win32con
        import win32print
        import ctypes
        
        print(f"=== print_pdf_with_printer 호출: {printer_name} ===")
        
        # PDF 열기
        doc = fitz.open(pdf_path)
        print(f"PDF 페이지 수: {len(doc)}")
        
        # 첫 페이지만 출력
        if len(doc) > 0:
            page = doc[0]
            
            # 프린터 DEVMODE 가져오기 및 수정
            printer_handle = win32print.OpenPrinter(printer_name)
            try:
                printer_info = win32print.GetPrinter(printer_handle, 2)
                devmode = printer_info['pDevMode']
                
                # 용지 정보 로그
                print(f"프린터 용지: {devmode.PaperWidth/10 if devmode.PaperWidth else 'N/A'}mm x {devmode.PaperLength/10 if devmode.PaperLength else 'N/A'}mm")
                
            finally:
                win32print.ClosePrinter(printer_handle)
            
            # 프린터 DC 생성 (DEVMODE 적용)
            hdc = win32ui.CreateDC()
            hdc.CreatePrinterDC(printer_name)
            
            # 프린터 인쇄 가능 영역 (픽셀)
            printer_width = hdc.GetDeviceCaps(win32con.HORZRES)
            printer_height = hdc.GetDeviceCaps(win32con.VERTRES)
            printer_dpi_x = hdc.GetDeviceCaps(win32con.LOGPIXELSX)
            printer_dpi_y = hdc.GetDeviceCaps(win32con.LOGPIXELSY)
            
            print(f"프린터 영역: {printer_width}x{printer_height}, DPI: {printer_dpi_x}x{printer_dpi_y}")
            
            # PDF를 프린터 DPI로 렌더링
            zoom_x = printer_dpi_x / 72
            zoom_y = printer_dpi_y / 72
            mat = fitz.Matrix(zoom_x, zoom_y)
            pix = page.get_pixmap(matrix=mat)
            
            # PIL Image로 변환 (PDF가 이미 270도 회전되어 있으므로 추가 회전 불필요)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            
            print(f"이미지: {img.width}x{img.height} → ", end="")
            
            # 이미지를 프린터 영역에 맞게 스케일링
            # 높이를 프린터 높이에 정확히 맞춤 (1장만 출력되도록)
            scale = min(printer_width / img.width, printer_height / img.height)
            final_width = int(img.width * scale)
            final_height = int(img.height * scale)
            
            print(f"{final_width}x{final_height} (scale: {scale:.2f})")
            
            # 이미지를 최종 크기로 리사이즈
            img_resized = img.resize((final_width, final_height), Image.LANCZOS)
            
            # 출력
            hdc.StartDoc("Label")
            hdc.StartPage()
            
            dib = ImageWin.Dib(img_resized)
            dib.draw(hdc.GetHandleOutput(), (0, 0, final_width, final_height))
            
            hdc.EndPage()
            hdc.EndDoc()
            hdc.DeleteDC()
            
            print(f"출력 완료")
        
        doc.close()
        print(f"직접 출력 성공: {pdf_path} → {printer_name}")
        return True
        
    except Exception as e:
        print(f"출력 실패: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def check_printer_exists(printer_name: str) -> bool:
    """
    프린터가 시스템에 존재하는지 확인
    
    Args:
        printer_name: 확인할 프린터 이름
    
    Returns:
        존재 여부
    """
    if not printer_name:
        return False
    
    printers = get_printers()
    return printer_name in printers


# ============================================================
# BIN 설정 저장/로드
# ============================================================

def save_bin_settings(max_qty_per_bin: int = None, min_qty_threshold: int = None, 
                      max_sku_per_shared_bin: int = None, dedicated_qty_threshold: int = None) -> bool:
    """
    settings.json에 BIN 설정 저장
    
    Args:
        max_qty_per_bin: BIN당 최대 수량
        min_qty_threshold: 최소 수량 임계값 (이하면 공유 BIN)
        max_sku_per_shared_bin: 공유 BIN당 최대 SKU 개수
        dedicated_qty_threshold: 전용 BIN 수량 임계값 (이상이면 중복금지, 0=비활성)
    
    Returns:
        저장 성공 여부
    """
    settings_path = get_settings_path()
    
    # 기존 설정 로드
    settings = {}
    if settings_path.exists():
        try:
            with open(settings_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)
        except Exception:
            settings = {}
    
    # BIN 설정 업데이트
    if "bin_settings" not in settings:
        settings["bin_settings"] = {}
    
    if max_qty_per_bin is not None:
        settings["bin_settings"]["max_qty_per_bin"] = max_qty_per_bin
    if min_qty_threshold is not None:
        settings["bin_settings"]["min_qty_threshold"] = min_qty_threshold
    if max_sku_per_shared_bin is not None:
        settings["bin_settings"]["max_sku_per_shared_bin"] = max_sku_per_shared_bin
    if dedicated_qty_threshold is not None:
        settings["bin_settings"]["dedicated_qty_threshold"] = dedicated_qty_threshold
    
    # 저장
    try:
        with open(settings_path, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"BIN 설정 저장 오류: {str(e)}")
        return False


def load_bin_settings() -> Dict[str, int]:
    """
    settings.json에서 BIN 설정 로드
    
    Returns:
        {
            "max_qty_per_bin": int (기본값: 100),
            "min_qty_threshold": int (기본값: 10),
            "max_sku_per_shared_bin": int (기본값: 5),
            "dedicated_qty_threshold": int (기본값: 0, 비활성)
        }
    """
    settings_path = get_settings_path()
    
    # 기본값
    default_settings = {
        "max_qty_per_bin": 100,
        "min_qty_threshold": 10,
        "max_sku_per_shared_bin": 5,
        "dedicated_qty_threshold": 0
    }
    
    if not settings_path.exists():
        return default_settings
    
    try:
        with open(settings_path, 'r', encoding='utf-8') as f:
            settings = json.load(f)
        
        bin_settings = settings.get("bin_settings", {})
        
        return {
            "max_qty_per_bin": bin_settings.get("max_qty_per_bin", 100),
            "min_qty_threshold": bin_settings.get("min_qty_threshold", 10),
            "max_sku_per_shared_bin": bin_settings.get("max_sku_per_shared_bin", 5),
            "dedicated_qty_threshold": bin_settings.get("dedicated_qty_threshold", 0)
        }
    except Exception as e:
        print(f"BIN 설정 로드 오류: {str(e)}")
        return default_settings

