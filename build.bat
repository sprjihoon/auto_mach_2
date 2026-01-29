@echo off
chcp 65001 > nul
echo ==========================================
echo AutoMach 빌드 스크립트
echo ==========================================
echo.

REM 가상환경 활성화 (있는 경우)
if exist "venv\Scripts\activate.bat" (
    echo 가상환경 활성화 중...
    call venv\Scripts\activate.bat
)

REM PyInstaller 설치 확인
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo PyInstaller가 설치되지 않았습니다. 설치 중...
    pip install pyinstaller
)

REM 이전 빌드 정리
echo.
echo 이전 빌드 정리 중...
if exist "dist" rmdir /s /q dist
if exist "build" rmdir /s /q build

REM 빌드 실행
echo.
echo 빌드 시작...
echo.
pyinstaller build.spec --clean

if errorlevel 1 (
    echo.
    echo ==========================================
    echo 빌드 실패!
    echo ==========================================
    pause
    exit /b 1
)

echo.
echo ==========================================
echo 빌드 완료!
echo 출력 위치: dist\AutoMach.exe
echo ==========================================
echo.

REM 빌드 결과 확인
if exist "dist\AutoMach.exe" (
    echo 파일 크기:
    for %%A in ("dist\AutoMach.exe") do echo   %%~zA bytes
    echo.
    
    set /p OPEN_FOLDER="dist 폴더를 열까요? (Y/N): "
    if /i "%OPEN_FOLDER%"=="Y" (
        explorer dist
    )
)

pause
