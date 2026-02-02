@echo off
chcp 65001 > nul
echo ==========================================
echo AutoMach 방화벽 설정
echo ==========================================
echo.

REM 관리자 권한 확인
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo 관리자 권한이 필요합니다.
    echo 관리자 권한으로 다시 실행합니다...
    echo.
    
    REM 관리자 권한으로 재실행
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

echo 관리자 권한으로 실행 중...
echo.

REM WebSocket 서버 포트 (TCP 8765) - 인바운드
echo [1/3] WebSocket 서버 포트 설정 (TCP 8765)...
netsh advfirewall firewall show rule name="AutoMach WebSocket Server (TCP 8765)" >nul 2>&1
if %errorLevel% neq 0 (
    netsh advfirewall firewall add rule name="AutoMach WebSocket Server (TCP 8765)" dir=in action=allow protocol=TCP localport=8765 enable=yes
    if %errorLevel% equ 0 (
        echo   ✓ 규칙 추가 완료
    ) else (
        echo   ✗ 규칙 추가 실패
    )
) else (
    echo   - 이미 설정됨
)
echo.

REM UDP Discovery 포트 (UDP 8764) - 인바운드
echo [2/3] UDP Discovery 포트 설정 (UDP 8764 IN)...
netsh advfirewall firewall show rule name="AutoMach UDP Discovery (UDP 8764)" >nul 2>&1
if %errorLevel% neq 0 (
    netsh advfirewall firewall add rule name="AutoMach UDP Discovery (UDP 8764)" dir=in action=allow protocol=UDP localport=8764 enable=yes
    if %errorLevel% equ 0 (
        echo   ✓ 규칙 추가 완료
    ) else (
        echo   ✗ 규칙 추가 실패
    )
) else (
    echo   - 이미 설정됨
)
echo.

REM UDP Discovery 포트 (UDP 8764) - 아웃바운드
echo [3/3] UDP Discovery Broadcast 설정 (UDP 8764 OUT)...
netsh advfirewall firewall show rule name="AutoMach UDP Discovery Broadcast (UDP 8764 OUT)" >nul 2>&1
if %errorLevel% neq 0 (
    netsh advfirewall firewall add rule name="AutoMach UDP Discovery Broadcast (UDP 8764 OUT)" dir=out action=allow protocol=UDP localport=8764 enable=yes
    if %errorLevel% equ 0 (
        echo   ✓ 규칙 추가 완료
    ) else (
        echo   ✗ 규칙 추가 실패
    )
) else (
    echo   - 이미 설정됨
)
echo.

echo ==========================================
echo 방화벽 설정 완료!
echo ==========================================
echo.
echo 설정된 포트:
echo   • TCP 8765 - ESP32 WebSocket 통신
echo   • UDP 8764 - ESP32 자동 발견
echo.

REM 설정 확인
echo [설정 확인]
netsh advfirewall firewall show rule name="AutoMach WebSocket Server (TCP 8765)" | findstr "규칙 이름" >nul 2>&1
if %errorLevel% equ 0 (
    echo   ✓ TCP 8765 활성화됨
) else (
    netsh advfirewall firewall show rule name="AutoMach WebSocket Server (TCP 8765)" | findstr "Rule Name" >nul 2>&1
    if %errorLevel% equ 0 (
        echo   ✓ TCP 8765 활성화됨
    ) else (
        echo   ✗ TCP 8765 미설정
    )
)

netsh advfirewall firewall show rule name="AutoMach UDP Discovery (UDP 8764)" | findstr "규칙 이름" >nul 2>&1
if %errorLevel% equ 0 (
    echo   ✓ UDP 8764 활성화됨
) else (
    netsh advfirewall firewall show rule name="AutoMach UDP Discovery (UDP 8764)" | findstr "Rule Name" >nul 2>&1
    if %errorLevel% equ 0 (
        echo   ✓ UDP 8764 활성화됨
    ) else (
        echo   ✗ UDP 8764 미설정
    )
)
echo.

pause
