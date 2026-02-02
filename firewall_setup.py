"""
Windows 방화벽 자동 설정 모듈
=====================================

ESP32 장치와의 통신을 위해 필요한 포트를 자동으로 방화벽에 등록합니다.
- WebSocket 서버: TCP 8765
- UDP Discovery: UDP 8764
"""

import subprocess
import ctypes
import sys
import os


# 방화벽 규칙 설정
FIREWALL_RULES = [
    {
        "name": "AutoMach WebSocket Server (TCP 8765)",
        "protocol": "TCP",
        "port": 8765,
        "direction": "in"
    },
    {
        "name": "AutoMach UDP Discovery (UDP 8764)",
        "protocol": "UDP",
        "port": 8764,
        "direction": "in"
    },
    {
        "name": "AutoMach UDP Discovery Broadcast (UDP 8764 OUT)",
        "protocol": "UDP",
        "port": 8764,
        "direction": "out"
    }
]


def is_admin() -> bool:
    """관리자 권한 확인"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


def check_firewall_rule_exists(rule_name: str) -> bool:
    """방화벽 규칙 존재 여부 확인"""
    try:
        result = subprocess.run(
            ["netsh", "advfirewall", "firewall", "show", "rule", f"name={rule_name}"],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        # 규칙이 없으면 "지정된 조건과 일치하는 규칙이 없습니다" 또는 "No rules match" 반환
        return result.returncode == 0 and "일치하는 규칙이 없습니다" not in result.stdout and "No rules match" not in result.stdout
    except Exception as e:
        print(f"[Firewall] 규칙 확인 오류: {e}")
        return False


def add_firewall_rule(name: str, protocol: str, port: int, direction: str = "in") -> bool:
    """
    방화벽 규칙 추가
    
    Args:
        name: 규칙 이름
        protocol: TCP 또는 UDP
        port: 포트 번호
        direction: "in" (인바운드) 또는 "out" (아웃바운드)
    
    Returns:
        성공 여부
    """
    try:
        dir_param = "dir=in" if direction == "in" else "dir=out"
        
        result = subprocess.run(
            [
                "netsh", "advfirewall", "firewall", "add", "rule",
                f"name={name}",
                dir_param,
                "action=allow",
                f"protocol={protocol}",
                f"localport={port}",
                "enable=yes"
            ],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        
        if result.returncode == 0:
            print(f"[Firewall] 규칙 추가 완료: {name}")
            return True
        else:
            print(f"[Firewall] 규칙 추가 실패: {name}")
            print(f"  오류: {result.stderr or result.stdout}")
            return False
    except Exception as e:
        print(f"[Firewall] 규칙 추가 오류: {e}")
        return False


def check_all_rules() -> dict:
    """
    모든 필요한 방화벽 규칙 확인
    
    Returns:
        dict: {"missing": [누락된 규칙들], "exists": [존재하는 규칙들]}
    """
    missing = []
    exists = []
    
    for rule in FIREWALL_RULES:
        if check_firewall_rule_exists(rule["name"]):
            exists.append(rule)
        else:
            missing.append(rule)
    
    return {"missing": missing, "exists": exists}


def setup_all_firewall_rules() -> bool:
    """
    모든 필요한 방화벽 규칙 설정 (관리자 권한 필요)
    
    Returns:
        성공 여부
    """
    if not is_admin():
        print("[Firewall] 관리자 권한이 필요합니다.")
        return False
    
    all_success = True
    
    for rule in FIREWALL_RULES:
        if not check_firewall_rule_exists(rule["name"]):
            success = add_firewall_rule(
                rule["name"],
                rule["protocol"],
                rule["port"],
                rule.get("direction", "in")
            )
            if not success:
                all_success = False
        else:
            print(f"[Firewall] 규칙 이미 존재: {rule['name']}")
    
    return all_success


def request_admin_and_setup():
    """
    관리자 권한 요청 후 방화벽 설정 (UAC 프롬프트)
    
    현재 프로세스가 관리자가 아니면 UAC 프롬프트를 띄워서
    관리자 권한으로 방화벽 설정 스크립트를 실행합니다.
    """
    if is_admin():
        # 이미 관리자면 바로 설정
        return setup_all_firewall_rules()
    
    # 관리자 권한으로 별도 프로세스 실행
    # PyInstaller 빌드 시와 개발 환경 모두 지원
    if getattr(sys, 'frozen', False):
        # 빌드된 exe인 경우
        script_path = os.path.join(os.path.dirname(sys.executable), "setup_firewall.bat")
    else:
        # 개발 환경인 경우
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "setup_firewall.bat")
    
    if os.path.exists(script_path):
        # 배치 파일이 있으면 관리자 권한으로 실행
        try:
            ctypes.windll.shell32.ShellExecuteW(
                None,
                "runas",  # 관리자 권한으로 실행
                "cmd.exe",
                f'/c "{script_path}"',
                None,
                1  # SW_SHOWNORMAL
            )
            return True
        except Exception as e:
            print(f"[Firewall] 관리자 권한 요청 실패: {e}")
            return False
    else:
        # 배치 파일이 없으면 Python 스크립트 직접 실행
        try:
            if getattr(sys, 'frozen', False):
                # 빌드된 exe에서는 직접 명령 실행
                commands = []
                for rule in FIREWALL_RULES:
                    dir_param = "dir=in" if rule.get("direction", "in") == "in" else "dir=out"
                    cmd = (
                        f'netsh advfirewall firewall add rule '
                        f'name="{rule["name"]}" {dir_param} action=allow '
                        f'protocol={rule["protocol"]} localport={rule["port"]} enable=yes'
                    )
                    commands.append(cmd)
                
                full_cmd = " && ".join(commands)
                
                ctypes.windll.shell32.ShellExecuteW(
                    None,
                    "runas",
                    "cmd.exe",
                    f'/c {full_cmd}',
                    None,
                    1
                )
                return True
            else:
                # 개발 환경에서는 Python으로 실행
                ctypes.windll.shell32.ShellExecuteW(
                    None,
                    "runas",
                    sys.executable,
                    f'"{__file__}" --setup',
                    None,
                    1
                )
                return True
        except Exception as e:
            print(f"[Firewall] 관리자 권한 요청 실패: {e}")
            return False


def ensure_firewall_configured(show_dialog: bool = True) -> bool:
    """
    방화벽이 올바르게 설정되어 있는지 확인하고, 필요하면 설정
    
    Args:
        show_dialog: True면 누락된 규칙이 있을 때 사용자에게 확인
    
    Returns:
        True: 모든 규칙이 설정됨 (또는 사용자가 거부)
        False: 설정 실패
    """
    status = check_all_rules()
    
    if not status["missing"]:
        # 모든 규칙이 이미 존재
        print("[Firewall] 모든 방화벽 규칙이 이미 설정되어 있습니다.")
        return True
    
    # 누락된 규칙이 있음
    missing_names = [r["name"] for r in status["missing"]]
    print(f"[Firewall] 누락된 방화벽 규칙: {missing_names}")
    
    if show_dialog:
        # GUI 다이얼로그로 확인 (PySide6 사용 가능할 때)
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox
            
            app = QApplication.instance()
            if app is None:
                # 임시 앱 생성
                temp_app = QApplication([])
                created_app = True
            else:
                created_app = False
            
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Question)
            msg.setWindowTitle("방화벽 설정")
            msg.setText("ESP32 장치와 통신하려면 방화벽 설정이 필요합니다.")
            msg.setInformativeText(
                "다음 포트를 방화벽에서 허용합니다:\n"
                "• TCP 8765 (WebSocket 서버)\n"
                "• UDP 8764 (장치 자동 발견)\n\n"
                "설정하시겠습니까? (관리자 권한 필요)"
            )
            msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            msg.setDefaultButton(QMessageBox.Yes)
            
            result = msg.exec()
            
            if created_app:
                temp_app.quit()
            
            if result == QMessageBox.Yes:
                return request_admin_and_setup()
            else:
                print("[Firewall] 사용자가 방화벽 설정을 건너뜀")
                return True  # 사용자가 거부했지만 프로그램 계속 실행
                
        except ImportError:
            # PySide6 없으면 그냥 진행
            return request_admin_and_setup()
    else:
        return request_admin_and_setup()


def get_firewall_status_text() -> str:
    """방화벽 상태를 문자열로 반환 (UI 표시용)"""
    status = check_all_rules()
    
    lines = []
    lines.append("=== 방화벽 상태 ===")
    
    if status["exists"]:
        lines.append("\n[설정됨]")
        for rule in status["exists"]:
            lines.append(f"  ✓ {rule['name']}")
    
    if status["missing"]:
        lines.append("\n[미설정]")
        for rule in status["missing"]:
            lines.append(f"  ✗ {rule['name']}")
    
    return "\n".join(lines)


# 직접 실행 시 방화벽 설정
if __name__ == "__main__":
    if "--setup" in sys.argv:
        # 관리자 권한으로 실행됨
        print("=== AutoMach 방화벽 설정 ===")
        success = setup_all_firewall_rules()
        if success:
            print("\n모든 방화벽 규칙이 설정되었습니다.")
        else:
            print("\n일부 규칙 설정에 실패했습니다.")
        input("\n엔터를 눌러 종료...")
    elif "--check" in sys.argv:
        # 상태만 확인
        print(get_firewall_status_text())
    else:
        # 기본: 확인 후 설정
        ensure_firewall_configured(show_dialog=False)
