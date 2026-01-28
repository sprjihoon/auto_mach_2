"""
EzAuto 자동입력 모듈
클립보드 방식으로 빠르고 안정적인 입력 지원
"""
import time
from typing import Optional
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

# pyautogui - 키 입력용 (Ctrl+V, Enter)
try:
    import pyautogui
    # FAILSAFE: 마우스를 화면 모서리로 이동하면 프로그램 중지 (안전 기능)
    # 다른 PC에서 예상치 못한 동작 시 긴급 중지 가능
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.02
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False
    pyautogui = None
    print("[ezauto_input] pyautogui 패키지가 설치되지 않았습니다. pip install pyautogui")
except Exception as e:
    HAS_PYAUTOGUI = False
    pyautogui = None
    print(f"[ezauto_input] pyautogui 초기화 오류: {e}")

# pygetwindow - 창 제어용
try:
    import pygetwindow as gw
    HAS_PYGETWINDOW = True
except ImportError:
    HAS_PYGETWINDOW = False
    gw = None
    print("[ezauto_input] pygetwindow 패키지가 설치되지 않았습니다. pip install pygetwindow")

# win32 - 백그라운드 입력용 (선택적)
try:
    import win32gui
    import win32con
    import win32api
    import win32clipboard
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False
    print("[ezauto_input] pywin32가 설치되지 않았습니다. 백그라운드 입력 불가")


class EzAutoInput(QObject):
    """EzAuto 프로그램 자동 입력 클래스"""
    
    # 시그널
    input_success = Signal(str)  # 성공 메시지
    input_error = Signal(str)    # 오류 메시지
    
    def __init__(self):
        super().__init__()
        self._enabled = True
        self._typing_interval = 0.02      # 문자 간 입력 간격
        self._delay_after_tracking = 0.8  # tracking_no 입력 후 대기 시간
        self._delay_after_barcode = 0.3   # barcode 입력 후 대기 시간
        self._window_title = "이지오토"   # EzAuto 창 제목 (부분 매칭)
        self._use_clipboard = False       # typewrite 방식 사용 (EzAuto 호환성)
        self._return_focus = True         # 입력 후 원래 창으로 복귀
        self._original_hwnd = None        # 원래 창 핸들
    
    @property
    def enabled(self) -> bool:
        return self._enabled
    
    @enabled.setter
    def enabled(self, value: bool):
        self._enabled = value
    
    def set_window_title(self, title: str):
        """EzAuto 창 제목 설정"""
        self._window_title = title
    
    def set_delays(self, after_tracking: float = 0.5, after_barcode: float = 0.2):
        """대기 시간 설정"""
        self._delay_after_tracking = after_tracking
        self._delay_after_barcode = after_barcode
    
    def set_use_clipboard(self, use: bool):
        """클립보드 방식 사용 설정"""
        self._use_clipboard = use
    
    def set_return_focus(self, return_focus: bool):
        """입력 후 원래 창으로 복귀 설정"""
        self._return_focus = return_focus
    
    def _save_current_focus(self):
        """현재 포커스된 창 저장"""
        if HAS_WIN32:
            try:
                self._original_hwnd = win32gui.GetForegroundWindow()
            except Exception:
                self._original_hwnd = None
    
    def _restore_focus(self):
        """원래 창으로 포커스 복귀"""
        if not self._return_focus:
            return
        
        if HAS_WIN32 and self._original_hwnd:
            try:
                # 원래 창으로 포커스 복귀
                win32gui.SetForegroundWindow(self._original_hwnd)
            except Exception:
                pass
        elif HAS_PYGETWINDOW:
            # pygetwindow로 우리 프로그램 창 찾아서 활성화
            try:
                windows = gw.getWindowsWithTitle("자동출고")
                if not windows:
                    windows = gw.getWindowsWithTitle("auto_mach")
                if windows:
                    windows[0].activate()
            except Exception:
                pass
    
    def _find_ezauto_hwnd(self) -> Optional[int]:
        """EzAuto 창 핸들 찾기"""
        if not HAS_WIN32:
            return None
        
        try:
            def enum_windows_callback(hwnd, results):
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if self._window_title.lower() in title.lower():
                        results.append(hwnd)
                return True
            
            results = []
            win32gui.EnumWindows(enum_windows_callback, results)
            
            if results:
                return results[0]
            return None
        except Exception:
            return None
    
    def find_and_activate_ezauto(self) -> bool:
        """EzAuto 창을 찾아서 활성화"""
        if not HAS_PYGETWINDOW:
            self.input_error.emit("pygetwindow 패키지가 설치되지 않았습니다")
            return False
        
        try:
            # 창 제목에 EzAuto가 포함된 창 찾기
            windows = gw.getWindowsWithTitle(self._window_title)
            
            if not windows:
                # 대소문자 구분 없이 재시도
                all_windows = gw.getAllWindows()
                for win in all_windows:
                    if self._window_title.lower() in win.title.lower():
                        windows = [win]
                        break
            
            if windows:
                win = windows[0]
                # 최소화되어 있으면 복원
                if win.isMinimized:
                    win.restore()
                # 창 활성화
                win.activate()
                time.sleep(0.1)  # 활성화 대기
                return True
            else:
                self.input_error.emit(f"'{self._window_title}' 창을 찾을 수 없습니다")
                return False
                
        except Exception as e:
            self.input_error.emit(f"창 활성화 오류: {str(e)}")
            return False
    
    def _clipboard_paste(self, text: str) -> bool:
        """클립보드에 텍스트 복사 후 붙여넣기"""
        try:
            # win32clipboard 사용 (스레드 안전)
            if HAS_WIN32:
                try:
                    win32clipboard.OpenClipboard()
                    win32clipboard.EmptyClipboard()
                    win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
                    win32clipboard.CloseClipboard()
                except Exception:
                    # 실패 시 Qt 클립보드로 폴백
                    clipboard = QApplication.clipboard()
                    clipboard.setText(text)
            else:
                # win32 없으면 Qt 클립보드 사용
                clipboard = QApplication.clipboard()
                clipboard.setText(text)
            
            time.sleep(0.1)  # 클립보드 설정 대기 (늘림)
            
            # Ctrl+V로 붙여넣기
            pyautogui.hotkey('ctrl', 'v')
            time.sleep(0.1)  # 붙여넣기 후 대기 (늘림)
            return True
        except Exception as e:
            self.input_error.emit(f"클립보드 붙여넣기 오류: {str(e)}")
            return False
    
    def _type_text(self, text: str) -> bool:
        """텍스트 입력 (타이핑 또는 클립보드)"""
        if self._use_clipboard:
            return self._clipboard_paste(text)
        else:
            # 타이핑 방식 (EzAuto 호환성 높음)
            try:
                pyautogui.typewrite(text, interval=self._typing_interval)
                return True
            except Exception as e:
                self.input_error.emit(f"타이핑 오류: {str(e)}")
                return False
    
    def send_input(self, tracking_no: str, barcode: str) -> bool:
        """
        EzAuto에 입력 전송 (클립보드 방식)
        순서: 원래 창 저장 → EzAuto 활성화 → 입력 → 원래 창 복귀
        """
        if not self._enabled:
            self.input_error.emit("EzAuto 입력이 비활성화되어 있습니다")
            return False
        
        if not HAS_PYAUTOGUI:
            self.input_error.emit("pyautogui 패키지가 설치되지 않았습니다")
            return False
        
        try:
            # 0. 현재 포커스된 창 저장
            self._save_current_focus()
            print(f"[EzAuto] 입력 시작: {tracking_no} / {barcode}")
            
            # 1. EzAuto 창 찾아서 활성화
            if not self.find_and_activate_ezauto():
                print("[EzAuto] 창 활성화 실패")
                return False
            print("[EzAuto] 창 활성화 성공")
            
            time.sleep(0.2)  # 창 활성화 대기 (늘림)
            
            # 2. tracking_no 입력 (클립보드 방식)
            print(f"[EzAuto] 송장번호 입력 중: {tracking_no}")
            if not self._type_text(tracking_no):
                print("[EzAuto] 송장번호 입력 실패")
                return False
            time.sleep(0.05)  # 입력 후 잠시 대기
            pyautogui.press('enter')
            print("[EzAuto] 송장번호 Enter 완료")
            
            # 3. 잠시 대기 (EzAuto 처리 시간)
            time.sleep(self._delay_after_tracking)
            
            # 4. barcode 입력
            print(f"[EzAuto] 바코드 입력 중: {barcode}")
            if not self._type_text(barcode):
                print("[EzAuto] 바코드 입력 실패")
                return False
            time.sleep(0.05)  # 입력 후 잠시 대기
            pyautogui.press('enter')
            print("[EzAuto] 바코드 Enter 완료")
            
            # 5. 완료 대기
            time.sleep(self._delay_after_barcode)
            
            # 6. 원래 창으로 복귀
            self._restore_focus()
            print("[EzAuto] 원래 창으로 복귀 완료")
            
            self.input_success.emit(f"EzAuto 입력 완료: {tracking_no} / {barcode}")
            return True
            
        except Exception as e:
            # 에러 발생해도 원래 창으로 복귀 시도
            self._restore_focus()
            
            error_msg = str(e)
            if "FailSafe" in error_msg:
                self.input_error.emit(
                    "⚠️ 안전 모드 발동: 마우스가 화면 모서리로 이동됨\n"
                    "다시 시도하려면 마우스를 화면 중앙으로 이동하세요."
                )
            elif "could not find" in error_msg.lower():
                self.input_error.emit(
                    f"⚠️ EzAuto 창을 찾을 수 없습니다.\n"
                    f"'{self._window_title}' 프로그램이 실행 중인지 확인하세요."
                )
            elif "permission" in error_msg.lower() or "access" in error_msg.lower():
                self.input_error.emit(
                    "⚠️ 입력 권한 오류\n"
                    "관리자 권한으로 프로그램을 실행해 보세요."
                )
            else:
                self.input_error.emit(f"⚠️ EzAuto 입력 오류: {error_msg}")
            return False
    
    def send_tracking_only(self, tracking_no: str) -> bool:
        """tracking_no만 입력"""
        if not self._enabled or not HAS_PYAUTOGUI:
            return False
        
        try:
            self._save_current_focus()
            
            if not self.find_and_activate_ezauto():
                return False
            
            time.sleep(0.1)
            
            if not self._type_text(tracking_no):
                return False
            pyautogui.press('enter')
            time.sleep(self._delay_after_tracking)
            
            self._restore_focus()
            return True
            
        except Exception as e:
            self._restore_focus()
            self.input_error.emit(f"tracking_no 입력 오류: {str(e)}")
            return False
    
    def send_barcode_only(self, barcode: str) -> bool:
        """barcode만 입력 (EzAuto가 이미 활성화된 상태에서)"""
        if not self._enabled or not HAS_PYAUTOGUI:
            return False
        
        try:
            self._save_current_focus()
            
            # EzAuto 창이 이미 활성화되어 있다고 가정
            # 하지만 안전을 위해 다시 활성화
            if not self.find_and_activate_ezauto():
                return False
            
            time.sleep(0.05)
            
            if not self._type_text(barcode):
                return False
            pyautogui.press('enter')
            time.sleep(self._delay_after_barcode)
            
            self._restore_focus()
            return True
            
        except Exception as e:
            self._restore_focus()
            self.input_error.emit(f"barcode 입력 오류: {str(e)}")
            return False


class EzAutoInputBackground(EzAutoInput):
    """
    백그라운드 EzAuto 입력 (창 활성화 없이)
    Windows 메시지를 사용하여 직접 텍스트 전송
    
    주의: EzAuto의 입력 필드 구조에 따라 동작하지 않을 수 있음
    """
    
    def __init__(self):
        super().__init__()
        self._ezauto_hwnd = None
    
    def send_input(self, tracking_no: str, barcode: str) -> bool:
        """백그라운드로 입력 전송 (창 활성화 없이)"""
        if not self._enabled:
            self.input_error.emit("EzAuto 입력이 비활성화되어 있습니다")
            return False
        
        if not HAS_WIN32:
            # win32가 없으면 기본 방식으로 폴백
            return super().send_input(tracking_no, barcode)
        
        try:
            # EzAuto 창 핸들 찾기
            ezauto_hwnd = self._find_ezauto_hwnd()
            if not ezauto_hwnd:
                self.input_error.emit(f"'{self._window_title}' 창을 찾을 수 없습니다")
                return False
            
            # 입력 필드에 직접 텍스트 전송 시도
            # WM_SETTEXT 또는 EM_REPLACESEL 메시지 사용
            
            # 방법 1: 클립보드 + WM_PASTE
            # 창을 활성화하지 않고 클립보드에 복사 후 붙여넣기 메시지 전송
            
            # tracking_no 전송
            self._send_text_via_clipboard(ezauto_hwnd, tracking_no)
            self._send_key(ezauto_hwnd, win32con.VK_RETURN)
            time.sleep(self._delay_after_tracking)
            
            # barcode 전송
            self._send_text_via_clipboard(ezauto_hwnd, barcode)
            self._send_key(ezauto_hwnd, win32con.VK_RETURN)
            time.sleep(self._delay_after_barcode)
            
            self.input_success.emit(f"[백그라운드] EzAuto 입력 완료: {tracking_no} / {barcode}")
            return True
            
        except Exception as e:
            self.input_error.emit(f"백그라운드 입력 오류: {str(e)}")
            # 실패하면 기본 방식으로 폴백
            return super().send_input(tracking_no, barcode)
    
    def _send_text_via_clipboard(self, hwnd: int, text: str):
        """클립보드를 통해 텍스트 전송"""
        # 클립보드에 텍스트 복사
        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
        finally:
            win32clipboard.CloseClipboard()
        
        # 붙여넣기 메시지 전송 (Ctrl+V)
        win32api.PostMessage(hwnd, win32con.WM_PASTE, 0, 0)
        time.sleep(0.1)
    
    def _send_key(self, hwnd: int, vk_code: int):
        """키 입력 메시지 전송"""
        win32api.PostMessage(hwnd, win32con.WM_KEYDOWN, vk_code, 0)
        time.sleep(0.02)
        win32api.PostMessage(hwnd, win32con.WM_KEYUP, vk_code, 0)


class EzAutoInputAsync(EzAutoInput):
    """비동기 EzAuto 입력 (별도 스레드에서 실행)"""
    
    def __init__(self):
        super().__init__()
        self._is_busy = False
    
    @property
    def is_busy(self) -> bool:
        return self._is_busy
    
    def send_input_async(self, tracking_no: str, barcode: str):
        """비동기로 입력 전송 (스레드에서 호출)"""
        import threading
        
        if self._is_busy:
            self.input_error.emit("이전 입력이 진행 중입니다")
            return
        
        def _run():
            self._is_busy = True
            try:
                self.send_input(tracking_no, barcode)
            finally:
                self._is_busy = False
        
        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
