"""
프린터 관리 모듈
Windows 프린터 목록 조회, 설정 저장/로드, PDF 출력 기능 제공
"""
import os
import json
from pathlib import Path
from typing import Optional, List, Dict
import tempfile
from datetime import datetime


def get_log_path() -> Path:
    """로그 파일 경로 반환"""
    base_path = Path(__file__).parent
    return base_path / "printer_log.txt"


def write_log(message: str):
    """로그 파일에 메시지 기록"""
    try:
        log_path = get_log_path()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")
    except Exception:
        pass  # 로그 기록 실패해도 무시


def clear_log():
    """로그 파일 초기화 (새 세션 시작 시)"""
    try:
        log_path = get_log_path()
        # 파일이 너무 크면 (1MB 이상) 초기화
        if log_path.exists() and log_path.stat().st_size > 1024 * 1024:
            log_path.unlink()
    except Exception:
        pass

# win32api, win32print는 선택적 (pywin32 설치 시에만 사용)
try:
    import win32api
    import win32print
    HAS_WIN32API = True
except ImportError:
    HAS_WIN32API = False
    print("[printer_manager] pywin32 패키지가 설치되지 않았습니다. pip install pywin32")

# win32ui, win32con은 PDF 직접 출력에 필요
try:
    import win32ui
    import win32con
    HAS_WIN32UI = True
except ImportError:
    HAS_WIN32UI = False
    print("[printer_manager] win32ui/win32con을 사용할 수 없습니다.")

# PIL은 이미지 처리에 필요
try:
    from PIL import Image, ImageWin
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("[printer_manager] Pillow 패키지가 설치되지 않았습니다. pip install Pillow")

# PyMuPDF는 PDF 렌더링에 필요
try:
    import fitz
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False
    print("[printer_manager] PyMuPDF 패키지가 설치되지 않았습니다. pip install PyMuPDF")


def get_settings_path() -> Path:
    """설정 파일 경로 반환"""
    base_path = Path(__file__).parent
    return base_path / "settings.json"


def get_default_settings() -> dict:
    """
    기본 설정값 반환
    
    Returns:
        기본 설정 딕셔너리
    """
    return {
        # 프린터 설정
        "label_printer": None,
        "a4_printer": None,
        "label_rotation": 270,
        
        # BIN 설정
        "bin_settings": {
            "max_qty_per_bin": 50,
            "min_qty_threshold": 10,
            "max_sku_per_shared_bin": 2,
            "dedicated_qty_threshold": 30
        },
        
        # ESP32 WebSocket 설정
        "esp32_settings": {
            "host": "0.0.0.0",
            "port": 8765,
            "enabled": True
        },
        
        # EzAuto 설정
        "ezauto_settings": {
            "window_title": "이지오토",
            "enabled": True,
            "use_clipboard": False,
            "delay_after_tracking": 0.8,
            "delay_after_barcode": 0.3
        },
        
        # 앱 설정
        "app_settings": {
            "first_run": True,
            "version": "1.0.0",
            "last_excel_path": None,
            "last_pdf_path": None
        }
    }


def ensure_settings_file() -> bool:
    """
    settings.json 파일이 없으면 기본값으로 생성
    기존 설정 파일이 있으면 누락된 키 추가
    
    Returns:
        새로 생성되었으면 True, 이미 존재하면 False
    """
    settings_path = get_settings_path()
    default_settings = get_default_settings()
    
    if not settings_path.exists():
        # 새로 생성
        try:
            with open(settings_path, 'w', encoding='utf-8') as f:
                json.dump(default_settings, f, ensure_ascii=False, indent=2)
            print(f"[printer_manager] 기본 설정 파일 생성됨: {settings_path}")
            return True
        except Exception as e:
            print(f"[printer_manager] 설정 파일 생성 실패: {e}")
            return False
    
    # 기존 설정 파일이 있으면 누락된 키 추가
    try:
        with open(settings_path, 'r', encoding='utf-8') as f:
            settings = json.load(f)
        
        # 누락된 키 추가
        updated = False
        for key, value in default_settings.items():
            if key not in settings:
                settings[key] = value
                updated = True
            elif isinstance(value, dict):
                # 중첩된 딕셔너리의 경우
                if not isinstance(settings[key], dict):
                    settings[key] = value
                    updated = True
                else:
                    for sub_key, sub_value in value.items():
                        if sub_key not in settings[key]:
                            settings[key][sub_key] = sub_value
                            updated = True
        
        if updated:
            with open(settings_path, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
            print(f"[printer_manager] 설정 파일 업데이트됨 (누락된 키 추가)")
        
        return False  # 기존 파일이 있었음
        
    except Exception as e:
        print(f"[printer_manager] 설정 파일 업데이트 실패: {e}")
        return False


def is_first_run() -> bool:
    """
    첫 실행인지 확인
    
    Returns:
        첫 실행이면 True
    """
    settings_path = get_settings_path()
    
    if not settings_path.exists():
        return True
    
    try:
        with open(settings_path, 'r', encoding='utf-8') as f:
            settings = json.load(f)
        
        app_settings = settings.get("app_settings", {})
        return app_settings.get("first_run", True)
    except Exception:
        return True


def set_first_run_complete() -> bool:
    """
    첫 실행 완료 표시
    
    Returns:
        저장 성공 여부
    """
    return save_app_setting("first_run", False)


def save_app_setting(key: str, value) -> bool:
    """
    app_settings에 설정 저장
    
    Args:
        key: 설정 키
        value: 설정 값
    
    Returns:
        저장 성공 여부
    """
    settings_path = get_settings_path()
    
    settings = {}
    if settings_path.exists():
        try:
            with open(settings_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)
        except Exception:
            settings = {}
    
    if "app_settings" not in settings:
        settings["app_settings"] = {}
    
    settings["app_settings"][key] = value
    
    try:
        with open(settings_path, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"앱 설정 저장 오류: {str(e)}")
        return False


def load_app_setting(key: str, default=None):
    """
    app_settings에서 설정 로드
    
    Args:
        key: 설정 키
        default: 기본값
    
    Returns:
        설정 값
    """
    settings_path = get_settings_path()
    
    if not settings_path.exists():
        return default
    
    try:
        with open(settings_path, 'r', encoding='utf-8') as f:
            settings = json.load(f)
        
        return settings.get("app_settings", {}).get(key, default)
    except Exception:
        return default


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
    write_log(f"========== 출력 시작 ==========")
    write_log(f"PDF 경로: {pdf_path}")
    write_log(f"요청된 프린터: {printer_name}")
    
    # 시스템 정보 로깅
    try:
        import platform
        write_log(f"시스템: {platform.system()} {platform.release()}")
        write_log(f"컴퓨터 이름: {platform.node()}")
    except Exception:
        pass
    
    if not os.path.exists(pdf_path):
        msg = f"PDF 파일 없음: {pdf_path}"
        print(msg)
        write_log(f"[오류] {msg}")
        return False
    
    # 필수 모듈 확인
    if not HAS_FITZ:
        msg = "PyMuPDF가 설치되지 않아 PDF 출력을 할 수 없습니다. pip install PyMuPDF"
        print(msg)
        write_log(f"[오류] {msg}")
        return False
    
    if not HAS_PIL:
        msg = "Pillow가 설치되지 않아 PDF 출력을 할 수 없습니다. pip install Pillow"
        print(msg)
        write_log(f"[오류] {msg}")
        return False
    
    if not HAS_WIN32UI or not HAS_WIN32API:
        msg = "pywin32가 설치되지 않아 PDF 출력을 할 수 없습니다. pip install pywin32"
        print(msg)
        write_log(f"[오류] {msg}")
        # 대안: os.startfile 사용
        try:
            os.startfile(pdf_path, "print")
            msg = f"기본 프로그램으로 출력 시도: {pdf_path}"
            print(msg)
            write_log(f"[대체] {msg}")
            return True
        except Exception as e:
            msg = f"대체 출력 실패: {e}"
            print(msg)
            write_log(f"[오류] {msg}")
            return False
    
    # 사용 가능한 프린터 목록 로깅
    printers = get_printers()
    write_log(f"사용 가능한 프린터 목록: {printers}")
    
    # 프린터 이름이 없으면 기본 프린터 사용
    if not printer_name and HAS_WIN32API:
        try:
            printer_name = win32print.GetDefaultPrinter()
            write_log(f"기본 프린터 사용: {printer_name}")
        except Exception as e:
            write_log(f"[오류] 기본 프린터 가져오기 실패: {e}")
            pass
    
    # 프린터 존재 확인
    if printer_name and HAS_WIN32API:
        if printer_name not in printers:
            msg = f"프린터를 찾을 수 없습니다: {printer_name}"
            print(msg)
            write_log(f"[오류] {msg}")
            write_log(f"[힌트] 설정에서 프린터를 다시 선택해주세요. 사용 가능: {printers}")
            return False
    
    # PyMuPDF + win32ui로 직접 출력 (1장만 출력되도록 최적화)
    try:
        import ctypes
        
        msg = f"=== print_pdf_with_printer 호출: {printer_name} ==="
        print(msg)
        write_log(msg)
        
        # PDF 열기
        doc = fitz.open(pdf_path)
        msg = f"PDF 페이지 수: {len(doc)}"
        print(msg)
        write_log(msg)
        
        # 첫 페이지만 출력
        if len(doc) > 0:
            page = doc[0]
            
            # 프린터 DEVMODE 가져오기 및 수정
            write_log(f"프린터 열기 시도: {printer_name}")
            printer_handle = win32print.OpenPrinter(printer_name)
            try:
                printer_info = win32print.GetPrinter(printer_handle, 2)
                devmode = printer_info['pDevMode']
                
                # 용지 정보 로그
                paper_width = devmode.PaperWidth/10 if devmode.PaperWidth else 'N/A'
                paper_length = devmode.PaperLength/10 if devmode.PaperLength else 'N/A'
                msg = f"프린터 용지: {paper_width}mm x {paper_length}mm"
                print(msg)
                write_log(msg)
                
            finally:
                win32print.ClosePrinter(printer_handle)
            
            # 프린터 DC 생성 (DEVMODE 적용)
            write_log("프린터 DC 생성 중...")
            hdc = win32ui.CreateDC()
            hdc.CreatePrinterDC(printer_name)
            
            # 프린터 DPI
            printer_dpi_x = hdc.GetDeviceCaps(win32con.LOGPIXELSX)
            printer_dpi_y = hdc.GetDeviceCaps(win32con.LOGPIXELSY)
            
            # ★ 실제 용지 크기 (픽셀) - 여백 포함 전체 용지
            try:
                paper_width = hdc.GetDeviceCaps(win32con.PHYSICALWIDTH)
                paper_height = hdc.GetDeviceCaps(win32con.PHYSICALHEIGHT)
            except:
                # 실제 용지 크기를 못 가져오면 인쇄 가능 영역 사용
                paper_width = hdc.GetDeviceCaps(win32con.HORZRES)
                paper_height = hdc.GetDeviceCaps(win32con.VERTRES)
            
            # ★ 물리적 오프셋 (비인쇄 영역) - 왼쪽 상단 정렬을 위해 필요
            try:
                offset_x = hdc.GetDeviceCaps(win32con.PHYSICALOFFSETX)
                offset_y = hdc.GetDeviceCaps(win32con.PHYSICALOFFSETY)
            except:
                offset_x = 0
                offset_y = 0
            
            # 인쇄 가능 영역 (참고용)
            printable_width = hdc.GetDeviceCaps(win32con.HORZRES)
            printable_height = hdc.GetDeviceCaps(win32con.VERTRES)
            
            # 용지 크기를 mm로도 계산 (참고용)
            paper_width_mm = paper_width / printer_dpi_x * 25.4
            paper_height_mm = paper_height / printer_dpi_y * 25.4
            
            msg = f"[용지] {paper_width}x{paper_height}px ({paper_width_mm:.1f}x{paper_height_mm:.1f}mm)"
            print(msg)
            write_log(msg)
            msg = f"[인쇄가능] {printable_width}x{printable_height}px, DPI: {printer_dpi_x}x{printer_dpi_y}, offset: ({offset_x}, {offset_y})"
            print(msg)
            write_log(msg)
            
            # PDF를 프린터 DPI로 렌더링
            zoom_x = printer_dpi_x / 72
            zoom_y = printer_dpi_y / 72
            mat = fitz.Matrix(zoom_x, zoom_y)
            pix = page.get_pixmap(matrix=mat)
            
            # PIL Image로 변환
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            
            print(f"이미지: {img.width}x{img.height} → ", end="")
            
            # ★ 이미지를 실제 용지 크기에 맞춤 (비율 유지, PDF가 이미 용지 크기에 맞게 생성됨)
            scale = min(paper_width / img.width, paper_height / img.height)
            final_width = int(img.width * scale)
            final_height = int(img.height * scale)
            
            # 이미지 크기를 mm로도 계산
            img_width_mm = img.width / printer_dpi_x * 25.4
            img_height_mm = img.height / printer_dpi_y * 25.4
            final_width_mm = final_width / printer_dpi_x * 25.4
            final_height_mm = final_height / printer_dpi_y * 25.4
            
            msg = f"[이미지] {img.width}x{img.height}px ({img_width_mm:.1f}x{img_height_mm:.1f}mm) -> {final_width}x{final_height}px ({final_width_mm:.1f}x{final_height_mm:.1f}mm) (scale: {scale:.3f})"
            print(f"{final_width}x{final_height} (scale: {scale:.3f})")
            write_log(msg)
            
            # 이미지를 용지 크기에 맞게 리사이즈 (비율 유지)
            img_resized = img.resize((final_width, final_height), Image.LANCZOS)
            
            # 출력
            write_log("StartDoc 호출...")
            hdc.StartDoc("Label")
            write_log("StartPage 호출...")
            hdc.StartPage()
            
            dib = ImageWin.Dib(img_resized)
            write_log("이미지 그리기...")
            
            # ★ PDF가 이미 용지 크기에 맞게 만들어졌으므로, 위치 조정 없이 (0,0)에서 시작
            # 물리적 오프셋만 보정하여 용지 왼쪽 상단에서 시작
            draw_x = -offset_x
            draw_y = -offset_y
            
            write_log(f"용지: {paper_width}x{paper_height}, 이미지: {final_width}x{final_height}")
            write_log(f"1:1 출력: ({draw_x}, {draw_y}) -> ({draw_x + final_width}, {draw_y + final_height})")
            dib.draw(hdc.GetHandleOutput(), (draw_x, draw_y, draw_x + final_width, draw_y + final_height))
            
            write_log("EndPage 호출...")
            hdc.EndPage()
            write_log("EndDoc 호출...")
            hdc.EndDoc()
            hdc.DeleteDC()
            
            print(f"출력 완료")
            write_log("출력 완료")
        
        doc.close()
        msg = f"직접 출력 성공: {pdf_path} → {printer_name}"
        print(msg)
        write_log(f"[성공] {msg}")
        return True
        
    except Exception as e:
        import traceback
        error_msg = f"출력 실패: {str(e)}"
        error_traceback = traceback.format_exc()
        print(error_msg)
        traceback.print_exc()
        write_log(f"[오류] {error_msg}")
        write_log(f"[상세오류]\n{error_traceback}")
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


def validate_printer_settings() -> dict:
    """
    현재 설정된 프린터들이 시스템에 존재하는지 검증
    
    Returns:
        {
            "label_printer": {"name": str or None, "exists": bool},
            "a4_printer": {"name": str or None, "exists": bool},
            "available_printers": list,
            "has_any_printer": bool
        }
    """
    settings = load_printer_settings()
    available_printers = get_printers()
    
    label_printer = settings.get("label_printer")
    a4_printer = settings.get("a4_printer")
    
    return {
        "label_printer": {
            "name": label_printer,
            "exists": label_printer in available_printers if label_printer else False
        },
        "a4_printer": {
            "name": a4_printer,
            "exists": a4_printer in available_printers if a4_printer else False
        },
        "available_printers": available_printers,
        "has_any_printer": len(available_printers) > 0
    }


def get_printer_status_message() -> str:
    """
    프린터 상태 메시지 생성 (UI 표시용)
    
    Returns:
        상태 메시지 문자열
    """
    validation = validate_printer_settings()
    messages = []
    
    if not validation["has_any_printer"]:
        return "⚠️ 시스템에 프린터가 설치되어 있지 않습니다."
    
    label = validation["label_printer"]
    if label["name"]:
        if label["exists"]:
            messages.append(f"✓ 라벨 프린터: {label['name']}")
        else:
            messages.append(f"✗ 라벨 프린터 '{label['name']}'를 찾을 수 없습니다. 프린터 설정을 확인하세요.")
    else:
        messages.append("⚠️ 라벨 프린터가 설정되지 않았습니다.")
    
    a4 = validation["a4_printer"]
    if a4["name"]:
        if a4["exists"]:
            messages.append(f"✓ A4 프린터: {a4['name']}")
        else:
            messages.append(f"✗ A4 프린터 '{a4['name']}'를 찾을 수 없습니다. 프린터 설정을 확인하세요.")
    else:
        messages.append("⚠️ A4 프린터가 설정되지 않았습니다.")
    
    return "\n".join(messages)


def auto_select_default_printer() -> bool:
    """
    프린터가 설정되지 않은 경우 기본 프린터를 자동 선택
    
    Returns:
        변경 여부
    """
    settings = load_printer_settings()
    available = get_printers()
    
    if not available:
        return False
    
    changed = False
    
    # 라벨 프린터가 없거나 존재하지 않으면 첫 번째 프린터로 설정
    if not settings.get("label_printer") or settings.get("label_printer") not in available:
        # 기본 프린터 가져오기
        default_printer = None
        if HAS_WIN32API:
            try:
                default_printer = win32print.GetDefaultPrinter()
            except:
                pass
        
        # 기본 프린터가 있으면 사용, 없으면 첫 번째 프린터
        new_printer = default_printer if default_printer and default_printer in available else available[0]
        save_printer_settings(label_printer=new_printer)
        print(f"[printer_manager] 라벨 프린터 자동 설정: {new_printer}")
        changed = True
    
    return changed


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


# ============================================================
# 송장 회전 설정 저장/로드
# ============================================================

def save_label_rotation(rotation: int) -> bool:
    """
    settings.json에 송장 회전 설정 저장
    
    Args:
        rotation: 회전 각도 (0, 90, 180, 270)
    
    Returns:
        저장 성공 여부
    """
    # 유효한 회전 값만 허용
    if rotation not in [0, 90, 180, 270]:
        print(f"유효하지 않은 회전 값: {rotation} (0, 90, 180, 270만 허용)")
        return False
    
    settings_path = get_settings_path()
    
    # 기존 설정 로드
    settings = {}
    if settings_path.exists():
        try:
            with open(settings_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)
        except Exception:
            settings = {}
    
    # 회전 설정 업데이트
    settings["label_rotation"] = rotation
    
    # 저장
    try:
        with open(settings_path, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        print(f"송장 회전 설정 저장: {rotation}도")
        return True
    except Exception as e:
        print(f"회전 설정 저장 오류: {str(e)}")
        return False


def load_label_rotation() -> int:
    """
    settings.json에서 송장 회전 설정 로드
    
    Returns:
        회전 각도 (기본값: 270)
    """
    settings_path = get_settings_path()
    
    # 기본값: 270도 (기존 동작과 동일)
    default_rotation = 270
    
    if not settings_path.exists():
        return default_rotation
    
    try:
        with open(settings_path, 'r', encoding='utf-8') as f:
            settings = json.load(f)
        
        rotation = settings.get("label_rotation", default_rotation)
        
        # 유효성 검사
        if rotation not in [0, 90, 180, 270]:
            return default_rotation
        
        return rotation
    except Exception as e:
        print(f"회전 설정 로드 오류: {str(e)}")
        return default_rotation


# ============================================================
# ESP32 설정 저장/로드
# ============================================================

def save_esp32_settings(host: str = None, port: int = None, enabled: bool = None) -> bool:
    """
    settings.json에 ESP32 WebSocket 설정 저장
    
    Args:
        host: WebSocket 서버 호스트
        port: WebSocket 서버 포트
        enabled: ESP32 기능 활성화 여부
    
    Returns:
        저장 성공 여부
    """
    settings_path = get_settings_path()
    
    settings = {}
    if settings_path.exists():
        try:
            with open(settings_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)
        except Exception:
            settings = {}
    
    if "esp32_settings" not in settings:
        settings["esp32_settings"] = {}
    
    if host is not None:
        settings["esp32_settings"]["host"] = host
    if port is not None:
        settings["esp32_settings"]["port"] = port
    if enabled is not None:
        settings["esp32_settings"]["enabled"] = enabled
    
    try:
        with open(settings_path, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"ESP32 설정 저장 오류: {str(e)}")
        return False


def load_esp32_settings() -> Dict:
    """
    settings.json에서 ESP32 설정 로드
    
    Returns:
        {
            "host": str (기본값: "0.0.0.0"),
            "port": int (기본값: 8765),
            "enabled": bool (기본값: True)
        }
    """
    settings_path = get_settings_path()
    
    default_settings = {
        "host": "0.0.0.0",
        "port": 8765,
        "enabled": True
    }
    
    if not settings_path.exists():
        return default_settings
    
    try:
        with open(settings_path, 'r', encoding='utf-8') as f:
            settings = json.load(f)
        
        esp32_settings = settings.get("esp32_settings", {})
        
        return {
            "host": esp32_settings.get("host", "0.0.0.0"),
            "port": esp32_settings.get("port", 8765),
            "enabled": esp32_settings.get("enabled", True)
        }
    except Exception as e:
        print(f"ESP32 설정 로드 오류: {str(e)}")
        return default_settings


# ============================================================
# EzAuto 설정 저장/로드
# ============================================================

def save_ezauto_settings(window_title: str = None, enabled: bool = None, 
                         use_clipboard: bool = None, delay_after_tracking: float = None,
                         delay_after_barcode: float = None) -> bool:
    """
    settings.json에 EzAuto 설정 저장
    
    Args:
        window_title: EzAuto 창 제목
        enabled: EzAuto 입력 활성화 여부
        use_clipboard: 클립보드 방식 사용 여부
        delay_after_tracking: 송장번호 입력 후 대기 시간
        delay_after_barcode: 바코드 입력 후 대기 시간
    
    Returns:
        저장 성공 여부
    """
    settings_path = get_settings_path()
    
    settings = {}
    if settings_path.exists():
        try:
            with open(settings_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)
        except Exception:
            settings = {}
    
    if "ezauto_settings" not in settings:
        settings["ezauto_settings"] = {}
    
    if window_title is not None:
        settings["ezauto_settings"]["window_title"] = window_title
    if enabled is not None:
        settings["ezauto_settings"]["enabled"] = enabled
    if use_clipboard is not None:
        settings["ezauto_settings"]["use_clipboard"] = use_clipboard
    if delay_after_tracking is not None:
        settings["ezauto_settings"]["delay_after_tracking"] = delay_after_tracking
    if delay_after_barcode is not None:
        settings["ezauto_settings"]["delay_after_barcode"] = delay_after_barcode
    
    try:
        with open(settings_path, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"EzAuto 설정 저장 오류: {str(e)}")
        return False


def load_ezauto_settings() -> Dict:
    """
    settings.json에서 EzAuto 설정 로드
    
    Returns:
        {
            "window_title": str (기본값: "이지오토"),
            "enabled": bool (기본값: True),
            "use_clipboard": bool (기본값: False),
            "delay_after_tracking": float (기본값: 0.8),
            "delay_after_barcode": float (기본값: 0.3)
        }
    """
    settings_path = get_settings_path()
    
    default_settings = {
        "window_title": "이지오토",
        "enabled": True,
        "use_clipboard": False,
        "delay_after_tracking": 0.8,
        "delay_after_barcode": 0.3
    }
    
    if not settings_path.exists():
        return default_settings
    
    try:
        with open(settings_path, 'r', encoding='utf-8') as f:
            settings = json.load(f)
        
        ezauto_settings = settings.get("ezauto_settings", {})
        
        return {
            "window_title": ezauto_settings.get("window_title", "이지오토"),
            "enabled": ezauto_settings.get("enabled", True),
            "use_clipboard": ezauto_settings.get("use_clipboard", False),
            "delay_after_tracking": ezauto_settings.get("delay_after_tracking", 0.8),
            "delay_after_barcode": ezauto_settings.get("delay_after_barcode", 0.3)
        }
    except Exception as e:
        print(f"EzAuto 설정 로드 오류: {str(e)}")
        return default_settings


# ============================================================
# 시스템 진단 기능
# ============================================================

def get_system_diagnosis() -> Dict:
    """
    시스템 상태 진단 (다른 PC에서 실행 시 문제 파악용)
    
    Returns:
        진단 결과 딕셔너리
    """
    from utils import is_admin, find_korean_font
    
    diagnosis = {
        "admin_rights": is_admin(),
        "printers": {
            "available": get_printers(),
            "has_any": len(get_printers()) > 0,
            "validation": validate_printer_settings()
        },
        "dependencies": {
            "win32api": HAS_WIN32API,
            "win32ui": HAS_WIN32UI,
            "pil": HAS_PIL,
            "fitz": HAS_FITZ
        },
        "fonts": {
            "korean_font": find_korean_font(),
            "has_korean_font": find_korean_font() is not None
        },
        "settings": {
            "file_exists": get_settings_path().exists(),
            "first_run": is_first_run()
        }
    }
    
    return diagnosis


def get_diagnosis_report() -> str:
    """
    시스템 진단 보고서 생성 (사용자 표시용)
    
    Returns:
        진단 보고서 문자열
    """
    diagnosis = get_system_diagnosis()
    
    report = []
    report.append("=" * 50)
    report.append("시스템 진단 보고서")
    report.append("=" * 50)
    
    # 관리자 권한
    if diagnosis["admin_rights"]:
        report.append("✓ 관리자 권한: 정상")
    else:
        report.append("⚠️ 관리자 권한: 없음 (바코드 스캐너 기능 제한)")
    
    # 프린터
    printers = diagnosis["printers"]
    if printers["has_any"]:
        report.append(f"✓ 프린터: {len(printers['available'])}개 발견")
        validation = printers["validation"]
        if validation["label_printer"]["name"]:
            if validation["label_printer"]["exists"]:
                report.append(f"  - 라벨 프린터: {validation['label_printer']['name']} ✓")
            else:
                report.append(f"  - 라벨 프린터: {validation['label_printer']['name']} ✗ (없음)")
        else:
            report.append("  - 라벨 프린터: 미설정")
    else:
        report.append("✗ 프린터: 발견되지 않음")
    
    # 의존성
    deps = diagnosis["dependencies"]
    missing_deps = []
    if not deps["win32api"]:
        missing_deps.append("pywin32")
    if not deps["pil"]:
        missing_deps.append("Pillow")
    if not deps["fitz"]:
        missing_deps.append("PyMuPDF")
    
    if missing_deps:
        report.append(f"⚠️ 누락된 패키지: {', '.join(missing_deps)}")
    else:
        report.append("✓ 모든 패키지 설치됨")
    
    # 한글 폰트
    if diagnosis["fonts"]["has_korean_font"]:
        report.append(f"✓ 한글 폰트: {diagnosis['fonts']['korean_font']}")
    else:
        report.append("⚠️ 한글 폰트: 없음 (PDF에서 한글 깨짐 가능)")
    
    # 설정 파일
    if diagnosis["settings"]["first_run"]:
        report.append("ℹ️ 첫 실행: 설정이 필요합니다")
    else:
        report.append("✓ 설정 파일: 존재")
    
    report.append("=" * 50)
    
    return "\n".join(report)

