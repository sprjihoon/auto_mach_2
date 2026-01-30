"""
자동출고 프로그램 - 메인 진입점
=====================================

제품 바코드를 스캔하면:
1) 엑셀에서 해당 제품의 tracking_no(송장번호)를 역매칭하여 찾고
2) EzAuto 프로그램에 자동으로 키입력을 보내고
3) tracking_no 단위로 qty/scanned_qty를 실시간 추적하고
4) 구성 수량이 모두 충족되면 PDF 송장 라벨을 자동 출력
5) 출력된 tracking_no는 used=1로 저장하여 재스캔 및 재출력 금지

사용법:
    python main.py

빌드:
    pyinstaller -F -w main.py
"""

import sys
import os

# PyInstaller 빌드 시 경로 설정
if getattr(sys, 'frozen', False):
    # PyInstaller로 빌드된 경우
    os.chdir(os.path.dirname(sys.executable))
else:
    # 개발 환경
    os.chdir(os.path.dirname(os.path.abspath(__file__)))


def show_splash():
    """스플래시 화면 표시"""
    from PySide6.QtWidgets import QApplication, QSplashScreen, QLabel
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QPixmap, QPainter, QColor, QFont
    
    # QApplication이 없으면 생성
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    
    # 스플래시 이미지 생성 (코드로 그리기)
    splash_width = 400
    splash_height = 200
    pixmap = QPixmap(splash_width, splash_height)
    pixmap.fill(QColor(45, 52, 54))  # 어두운 배경
    
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    
    # 테두리
    painter.setPen(QColor(0, 184, 148))  # 민트색 테두리
    painter.drawRect(2, 2, splash_width - 4, splash_height - 4)
    
    # 제목
    font = QFont("맑은 고딕", 24, QFont.Bold)
    painter.setFont(font)
    painter.setPen(QColor(255, 255, 255))
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "AutoMach")
    
    # 로딩 메시지
    font = QFont("맑은 고딕", 11)
    painter.setFont(font)
    painter.setPen(QColor(178, 190, 195))
    loading_rect = pixmap.rect()
    loading_rect.setTop(loading_rect.center().y() + 30)
    painter.drawText(loading_rect, Qt.AlignHCenter | Qt.AlignTop, "프로그램을 로딩 중입니다...")
    
    # 버전
    font = QFont("맑은 고딕", 9)
    painter.setFont(font)
    painter.setPen(QColor(99, 110, 114))
    version_rect = pixmap.rect()
    version_rect.setTop(splash_height - 30)
    painter.drawText(version_rect, Qt.AlignHCenter | Qt.AlignTop, "v1.0.0")
    
    painter.end()
    
    # 스플래시 화면 생성
    splash = QSplashScreen(pixmap)
    splash.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.SplashScreen)
    splash.show()
    
    # 이벤트 처리
    app.processEvents()
    
    return app, splash


def main():
    """메인 함수"""
    # 스플래시 화면 표시
    app, splash = show_splash()
    
    # 스플래시 메시지 업데이트
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor
    splash.showMessage("모듈 로딩 중...", Qt.AlignBottom | Qt.AlignHCenter, QColor(178, 190, 195))
    app.processEvents()
    
    # 메인 윈도우 임포트 및 생성
    from ui_main import MainWindow
    
    splash.showMessage("UI 초기화 중...", Qt.AlignBottom | Qt.AlignHCenter, QColor(178, 190, 195))
    app.processEvents()
    
    window = MainWindow()
    
    splash.showMessage("완료!", Qt.AlignBottom | Qt.AlignHCenter, QColor(0, 184, 148))
    app.processEvents()
    
    # 스플래시 직접 닫기 (설정 팝업보다 먼저 닫히도록)
    splash.close()
    
    # 메인 윈도우 표시
    window.show()
    
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

