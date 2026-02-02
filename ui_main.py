"""
PySide6 UI 화면
"""
import sys
import os
import re
from pathlib import Path
from typing import Optional, Dict
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QTextEdit, QPushButton,
    QLabel, QLineEdit, QFileDialog, QGroupBox, QSplitter,
    QHeaderView, QMessageBox, QFrame, QCheckBox, QDialog,
    QScrollArea, QGridLayout, QListWidget, QListWidgetItem,
    QRadioButton, QButtonGroup, QComboBox, QTabWidget, QSpinBox
)
from PySide6.QtCore import Qt, Slot, QTimer, QPropertyAnimation, QEasingCurve, Signal
from PySide6.QtGui import QFont, QColor, QPalette, QIcon
import pandas as pd

from models import ScanResult, ScanEvent
from excel_loader import ExcelLoader
from normalize_pdf import normalize_pdf
from mode_manager import ModeManager, WorkMode, FullPickState, PrePickState
from device_registry import DeviceRegistry
from esp32_transport import Esp32Transport
from full_pick_engine import FullPickEngine
from pre_pick_engine import PrePickEngine, SlotState
from work_session import WorkSessionManager, WorkSession

# 대화상자 임포트
from ui_dialogs import SummaryDialog, SetupWizardDialog, SupplierSelectDialog, BinSettingsDialog


class _SummaryDialog_REMOVED(QDialog):
    """구성 요약 다이얼로그 (카드 형태)"""
    
    def __init__(self, df: pd.DataFrame, parent=None):
        super().__init__(parent)
        self.df = df
        self.setWindowTitle("📦 구성 요약")
        self.setMinimumSize(800, 600)
        self._init_ui()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        # 헤더
        header = QLabel()
        pending = self.df[self.df['used'] == 0]
        total = len(self.df['tracking_no'].unique())
        pending_count = len(pending['tracking_no'].unique())
        header.setText(f"<h2>📦 총 {total}건 중 미처리 {pending_count}건</h2>")
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)
        
        # 스크롤 영역
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        # 카드 컨테이너
        container = QWidget()
        grid = QGridLayout(container)
        grid.setSpacing(15)
        
        # 구성별 카드 생성
        combo_data = self._get_combo_data(pending)
        
        row, col = 0, 0
        max_cols = 3
        
        for combo_info in combo_data:
            card = self._create_card(combo_info)
            grid.addWidget(card, row, col)
            col += 1
            if col >= max_cols:
                col = 0
                row += 1
        
        scroll.setWidget(container)
        layout.addWidget(scroll)
        
        # 닫기 버튼
        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.close)
        close_btn.setMaximumWidth(200)
        layout.addWidget(close_btn, alignment=Qt.AlignCenter)
    
    def _get_combo_data(self, pending):
        """구성별 데이터 추출 (수량 포함)"""
        tracking_groups = pending.groupby('tracking_no')
        combo_counts = {}
        
        for tracking_no, group in tracking_groups:
            barcodes = sorted(group['barcode'].unique())
            combo_key = tuple(barcodes)
            
            if combo_key not in combo_counts:
                combo_counts[combo_key] = {
                    'count': 0,
                    'products': [],
                    'barcodes': barcodes
                }
                for _, row in group.iterrows():
                    product_name = str(row['product_name']) if pd.notna(row['product_name']) else ''
                    option_name = str(row['option_name']) if pd.notna(row['option_name']) else ''
                    qty = int(row['qty']) if pd.notna(row['qty']) else 1
                    
                    product_info = product_name
                    if option_name and option_name != 'nan':
                        product_info += f" ({option_name})"
                    
                    # 수량 뒤에 표시: 1개, 2개, 3개...
                    product_info += f" {qty}개"
                    
                    if product_info and product_info not in combo_counts[combo_key]['products']:
                        combo_counts[combo_key]['products'].append(product_info)
            
            combo_counts[combo_key]['count'] += 1
        
        # 개수 내림차순 정렬
        sorted_combos = sorted(combo_counts.values(), key=lambda x: -x['count'])
        return sorted_combos
    
    def _create_card(self, combo_info):
        """카드 위젯 생성 (전체 품목 가로 나열)"""
        card = QFrame()
        card.setFrameShape(QFrame.StyledPanel)
        card.setMinimumWidth(230)
        card.setMaximumWidth(350)
        
        # 개수에 따른 색상
        count = combo_info['count']
        if count >= 10:
            bg_color = "#FFEBEE"  # 빨강 계열
            border_color = "#EF5350"
            count_color = "#D32F2F"
        elif count >= 5:
            bg_color = "#FFF3E0"  # 주황 계열
            border_color = "#FF9800"
            count_color = "#E65100"
        elif count >= 3:
            bg_color = "#E3F2FD"  # 파랑 계열
            border_color = "#2196F3"
            count_color = "#1565C0"
        else:
            bg_color = "#F5F5F5"  # 회색 계열
            border_color = "#9E9E9E"
            count_color = "#616161"
        
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_color};
                border: 2px solid {border_color};
                border-radius: 10px;
                padding: 10px;
            }}
        """)
        
        layout = QVBoxLayout(card)
        layout.setSpacing(8)
        
        # 개수 배지 (3자리 지원)
        count_label = QLabel(f"<span style='font-size:24px; font-weight:bold; color:{count_color};'>{count}건</span>")
        count_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(count_label)
        
        # 구분선
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"background-color: {border_color};")
        layout.addWidget(line)
        
        # 상품 목록 (◆ 구분자로 명확히 구분)
        products = combo_info['products']
        products_text = "  ◆  ".join(products)
        
        prod_label = QLabel(products_text)
        prod_label.setWordWrap(True)
        prod_label.setStyleSheet("font-size: 11px; color: #333; line-height: 1.4;")
        layout.addWidget(prod_label)
        
        layout.addStretch()
        
        return card
from scanner_listener import ScannerListener
from ezauto_input import EzAutoInput
from pdf_printer import PDFPrinter
from order_processor import OrderProcessor
from utils import get_timestamp
from printer_manager import (
    get_printers, save_printer_settings, load_printer_settings,
    print_pdf_with_printer, check_printer_exists,
    save_bin_settings, load_bin_settings,
    validate_printer_settings, get_printer_status_message, auto_select_default_printer,
    ensure_settings_file, is_first_run, set_first_run_complete,
    get_diagnosis_report, load_esp32_settings, save_esp32_settings,
    load_ezauto_settings, save_ezauto_settings
)
from utils import is_admin, get_admin_status_message
from pdf_search import find_pdf_by_tracking_or_order
from reprint_pdf_extractor import extract_pages_from_pdf, extract_reprint_page_to_temp
from bin_manager import BinManager


class _SetupWizardDialog_REMOVED(QDialog):
    """첫 실행 설정 마법사 다이얼로그 - ui_dialogs.py로 이동됨"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🚀 AutoMach 초기 설정")
        self.setMinimumSize(600, 500)
        self.setModal(True)
        self._init_ui()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # 헤더
        header = QLabel("<h2>🚀 AutoMach 초기 설정</h2>")
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)
        
        # 환영 메시지
        welcome = QLabel(
            "AutoMach를 처음 실행합니다.\n"
            "원활한 사용을 위해 아래 설정을 확인해 주세요."
        )
        welcome.setStyleSheet("color: #666; padding: 10px; background: #f5f5f5; border-radius: 5px;")
        welcome.setWordWrap(True)
        welcome.setAlignment(Qt.AlignCenter)
        layout.addWidget(welcome)
        
        # 탭 위젯
        tabs = QTabWidget()
        
        # 1. 시스템 진단 탭
        diagnosis_tab = QWidget()
        diagnosis_layout = QVBoxLayout(diagnosis_tab)
        
        self.diagnosis_text = QTextEdit()
        self.diagnosis_text.setReadOnly(True)
        self.diagnosis_text.setFont(QFont("Consolas", 10))
        diagnosis_layout.addWidget(self.diagnosis_text)
        
        refresh_btn = QPushButton("🔄 다시 진단")
        refresh_btn.clicked.connect(self._refresh_diagnosis)
        diagnosis_layout.addWidget(refresh_btn)
        
        tabs.addTab(diagnosis_tab, "📋 시스템 진단")
        
        # 2. 프린터 설정 탭
        printer_tab = QWidget()
        printer_layout = QVBoxLayout(printer_tab)
        
        # 라벨 프린터
        label_group = QGroupBox("🏷️ 라벨 프린터 (송장 출력)")
        label_layout = QVBoxLayout(label_group)
        self.label_printer_combo = QComboBox()
        self.label_printer_combo.setMinimumWidth(300)
        label_layout.addWidget(self.label_printer_combo)
        printer_layout.addWidget(label_group)
        
        # A4 프린터
        a4_group = QGroupBox("📄 A4 프린터 (주문서 출력)")
        a4_layout = QVBoxLayout(a4_group)
        self.a4_printer_combo = QComboBox()
        self.a4_printer_combo.setMinimumWidth(300)
        a4_layout.addWidget(self.a4_printer_combo)
        printer_layout.addWidget(a4_group)
        
        printer_layout.addStretch()
        tabs.addTab(printer_tab, "🖨️ 프린터 설정")
        
        # 3. EzAuto 설정 탭
        ezauto_tab = QWidget()
        ezauto_layout = QVBoxLayout(ezauto_tab)
        
        ezauto_group = QGroupBox("🖥️ EzAuto 창 제목")
        ezauto_inner = QVBoxLayout(ezauto_group)
        
        ezauto_desc = QLabel(
            "EzAuto 프로그램의 창 제목을 입력하세요.\n"
            "창 제목에 포함된 문자열로 검색합니다."
        )
        ezauto_desc.setWordWrap(True)
        ezauto_inner.addWidget(ezauto_desc)
        
        self.ezauto_title_edit = QLineEdit()
        self.ezauto_title_edit.setPlaceholderText("예: 이지오토, EzAuto")
        ezauto_inner.addWidget(self.ezauto_title_edit)
        
        ezauto_layout.addWidget(ezauto_group)
        
        # ESP32 설정
        esp32_group = QGroupBox("📡 ESP32 WebSocket 포트")
        esp32_inner = QVBoxLayout(esp32_group)
        
        esp32_desc = QLabel("ESP32 장치 연결용 WebSocket 서버 포트:")
        esp32_inner.addWidget(esp32_desc)
        
        self.esp32_port_spin = QSpinBox()
        self.esp32_port_spin.setRange(1024, 65535)
        self.esp32_port_spin.setValue(8765)
        esp32_inner.addWidget(self.esp32_port_spin)
        
        ezauto_layout.addWidget(esp32_group)
        ezauto_layout.addStretch()
        
        tabs.addTab(ezauto_tab, "⚙️ 기타 설정")
        
        layout.addWidget(tabs)
        
        # 관리자 권한 경고
        if not is_admin():
            admin_warning = QLabel(
                "⚠️ 관리자 권한으로 실행하지 않았습니다.\n"
                "바코드 스캐너 기능이 제한될 수 있습니다.\n"
                "프로그램을 우클릭하여 '관리자 권한으로 실행'을 권장합니다."
            )
            admin_warning.setStyleSheet(
                "color: #D32F2F; padding: 10px; background: #FFEBEE; "
                "border: 1px solid #EF5350; border-radius: 5px;"
            )
            admin_warning.setWordWrap(True)
            layout.addWidget(admin_warning)
        
        # 버튼
        btn_layout = QHBoxLayout()
        
        save_btn = QPushButton("✅ 설정 저장 후 시작")
        save_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 10px;")
        save_btn.clicked.connect(self._save_and_close)
        btn_layout.addWidget(save_btn)
        
        skip_btn = QPushButton("나중에 설정")
        skip_btn.clicked.connect(self.accept)
        btn_layout.addWidget(skip_btn)
        
        layout.addLayout(btn_layout)
        
        # 초기화
        self._load_printers()
        self._load_settings()
        self._refresh_diagnosis()
    
    def _load_printers(self):
        """프린터 목록 로드"""
        printers = get_printers()
        
        self.label_printer_combo.clear()
        self.a4_printer_combo.clear()
        
        self.label_printer_combo.addItem("(선택 안함)", None)
        self.a4_printer_combo.addItem("(선택 안함)", None)
        
        for printer in printers:
            self.label_printer_combo.addItem(printer, printer)
            self.a4_printer_combo.addItem(printer, printer)
        
        # 현재 설정 로드
        settings = load_printer_settings()
        if settings.get("label_printer"):
            idx = self.label_printer_combo.findData(settings["label_printer"])
            if idx >= 0:
                self.label_printer_combo.setCurrentIndex(idx)
        
        if settings.get("a4_printer"):
            idx = self.a4_printer_combo.findData(settings["a4_printer"])
            if idx >= 0:
                self.a4_printer_combo.setCurrentIndex(idx)
    
    def _load_settings(self):
        """기존 설정 로드"""
        # EzAuto 설정
        ezauto_settings = load_ezauto_settings()
        self.ezauto_title_edit.setText(ezauto_settings.get("window_title", "이지오토"))
        
        # ESP32 설정
        esp32_settings = load_esp32_settings()
        self.esp32_port_spin.setValue(esp32_settings.get("port", 8765))
    
    def _refresh_diagnosis(self):
        """시스템 진단 새로고침"""
        report = get_diagnosis_report()
        self.diagnosis_text.setPlainText(report)
    
    def _save_and_close(self):
        """설정 저장 후 닫기"""
        # 프린터 설정 저장
        label_printer = self.label_printer_combo.currentData()
        a4_printer = self.a4_printer_combo.currentData()
        save_printer_settings(label_printer, a4_printer)
        
        # EzAuto 설정 저장
        ezauto_title = self.ezauto_title_edit.text().strip()
        if ezauto_title:
            save_ezauto_settings(window_title=ezauto_title)
        
        # ESP32 설정 저장
        esp32_port = self.esp32_port_spin.value()
        save_esp32_settings(port=esp32_port)
        
        # 첫 실행 완료 표시
        set_first_run_complete()
        
        self.accept()


class _SupplierSelectDialog_REMOVED(QDialog):
    """업체(공급처) 선택 다이얼로그 - ui_dialogs.py로 이동됨"""
    
    def __init__(self, supplier_summary: list, parent=None, current_suppliers: list = None):
        """
        Args:
            supplier_summary: [{"supplier": "업체A", "order_count": 10, "item_count": 50}, ...]
            current_suppliers: 현재 선택된 업체 리스트 (업체 변경 시 사용)
        """
        super().__init__(parent)
        self.supplier_summary = supplier_summary
        self.selected_suppliers = []  # 다중 선택 지원
        self.current_suppliers = current_suppliers or []
        self.setWindowTitle("🏢 업체 선택")
        self.setMinimumSize(550, 450)
        self._init_ui()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # 헤더
        header = QLabel("<h2>🏢 작업할 업체를 선택하세요</h2>")
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)
        
        # 설명
        desc = QLabel(
            "여러 업체를 선택하면 동일한 BIN 시스템을 공유합니다.\n"
            "선택한 업체들의 SKU가 같은 BIN에 배정됩니다."
        )
        desc.setStyleSheet("color: #666; padding: 10px; background: #f5f5f5; border-radius: 5px;")
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignCenter)
        layout.addWidget(desc)
        
        # 전체 선택/해제 버튼
        select_btn_layout = QHBoxLayout()
        
        select_all_btn = QPushButton("✅ 전체 선택")
        select_all_btn.clicked.connect(self._select_all)
        select_btn_layout.addWidget(select_all_btn)
        
        deselect_all_btn = QPushButton("⬜ 전체 해제")
        deselect_all_btn.clicked.connect(self._deselect_all)
        select_btn_layout.addWidget(deselect_all_btn)
        
        select_btn_layout.addStretch()
        layout.addLayout(select_btn_layout)
        
        # 업체 목록 (체크박스 - 다중 선택)
        list_group = QGroupBox("업체 목록 (여러 업체 선택 가능)")
        list_layout = QVBoxLayout(list_group)
        
        # 스크롤 영역
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(8)
        
        # 총계 표시
        total_orders = sum(s["order_count"] for s in self.supplier_summary)
        total_items = sum(s["item_count"] for s in self.supplier_summary)
        
        total_label = QLabel(f"📊 전체: {len(self.supplier_summary)}개 업체, {total_orders}건, {total_items}개")
        total_label.setStyleSheet("font-weight: bold; font-size: 12px; color: #2196F3; padding: 5px; background: #E3F2FD; border-radius: 3px;")
        scroll_layout.addWidget(total_label)
        
        # 구분선
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background-color: #ddd;")
        scroll_layout.addWidget(line)
        
        # 각 업체별 체크박스
        self.supplier_checkboxes = []
        for idx, item in enumerate(self.supplier_summary):
            supplier = item["supplier"]
            order_count = item["order_count"]
            item_count = item["item_count"]
            
            checkbox = QCheckBox(f"{supplier}  ({order_count}건, {item_count}개)")
            checkbox.setStyleSheet("font-size: 12px; padding: 6px;")
            checkbox.setProperty("supplier", supplier)
            checkbox.setProperty("order_count", order_count)
            checkbox.setProperty("item_count", item_count)
            checkbox.stateChanged.connect(self._update_selection_summary)
            
            # 현재 선택된 업체면 체크
            if supplier in self.current_suppliers or not self.current_suppliers:
                checkbox.setChecked(not self.current_suppliers)  # 처음이면 전부 미체크
            if supplier in self.current_suppliers:
                checkbox.setChecked(True)
            
            self.supplier_checkboxes.append(checkbox)
            scroll_layout.addWidget(checkbox)
        
        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        list_layout.addWidget(scroll)
        
        layout.addWidget(list_group, 1)
        
        # 선택 요약 표시
        self.selection_summary = QLabel("선택: 0개 업체, 0건, 0개")
        self.selection_summary.setStyleSheet("font-weight: bold; padding: 8px; background: #FFF3E0; border-radius: 5px;")
        self.selection_summary.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.selection_summary)
        self._update_selection_summary()
        
        # 버튼 영역
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        cancel_btn = QPushButton("취소")
        cancel_btn.setMinimumWidth(100)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        select_btn = QPushButton("선택 완료")
        select_btn.setMinimumWidth(120)
        select_btn.setStyleSheet("background: #4CAF50; color: white; font-weight: bold;")
        select_btn.clicked.connect(self._on_select)
        btn_layout.addWidget(select_btn)
        
        layout.addLayout(btn_layout)
    
    def _select_all(self):
        """전체 선택"""
        for cb in self.supplier_checkboxes:
            cb.setChecked(True)
    
    def _deselect_all(self):
        """전체 해제"""
        for cb in self.supplier_checkboxes:
            cb.setChecked(False)
    
    def _update_selection_summary(self):
        """선택 요약 업데이트"""
        selected_count = 0
        selected_orders = 0
        selected_items = 0
        
        for cb in self.supplier_checkboxes:
            if cb.isChecked():
                selected_count += 1
                selected_orders += cb.property("order_count")
                selected_items += cb.property("item_count")
        
        if selected_count == 0:
            self.selection_summary.setText("⚠️ 선택된 업체가 없습니다")
            self.selection_summary.setStyleSheet("font-weight: bold; padding: 8px; background: #FFCDD2; border-radius: 5px; color: #C62828;")
        elif selected_count == len(self.supplier_checkboxes):
            self.selection_summary.setText(f"✅ 전체 선택: {selected_count}개 업체, {selected_orders}건, {selected_items}개")
            self.selection_summary.setStyleSheet("font-weight: bold; padding: 8px; background: #C8E6C9; border-radius: 5px; color: #2E7D32;")
        else:
            self.selection_summary.setText(f"📦 선택: {selected_count}개 업체, {selected_orders}건, {selected_items}개")
            self.selection_summary.setStyleSheet("font-weight: bold; padding: 8px; background: #FFF3E0; border-radius: 5px; color: #E65100;")
    
    def _on_select(self):
        """업체 선택 확정"""
        self.selected_suppliers = []
        for cb in self.supplier_checkboxes:
            if cb.isChecked():
                self.selected_suppliers.append(cb.property("supplier"))
        
        if not self.selected_suppliers:
            QMessageBox.warning(self, "경고", "최소 1개 이상의 업체를 선택해주세요.")
            return
        
        self.accept()
    
    def get_selected_suppliers(self) -> list:
        """선택된 업체 리스트 반환"""
        return self.selected_suppliers
    
    # 하위 호환성을 위해 단일 선택 메서드 유지
    def get_selected_supplier(self) -> str:
        """선택된 업체 반환 (첫 번째 또는 '전체')"""
        if not self.selected_suppliers:
            return None
        if len(self.selected_suppliers) == len(self.supplier_summary):
            return "전체"
        return self.selected_suppliers[0] if len(self.selected_suppliers) == 1 else None


class _BinSettingsDialog_REMOVED(QDialog):
    """BIN 설정 다이얼로그 - ui_dialogs.py로 이동됨"""
    
    def __init__(self, bin_manager, parent=None):
        super().__init__(parent)
        self.bin_manager = bin_manager
        self.setWindowTitle("🗃️ BIN 설정")
        self.setMinimumSize(450, 350)
        self._init_ui()
        self._load_settings()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # 헤더
        header = QLabel("<h3>🗃️ BIN 배정 설정</h3>")
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)
        
        # 설명
        desc = QLabel(
            "BIN 배정 방식을 설정합니다.\n"
            "• 대량 SKU: 최대수량 초과 시 여러 BIN에 분산\n"
            "• 소량 SKU: 여러 SKU를 하나의 BIN에 묶음"
        )
        desc.setStyleSheet("color: #666; padding: 10px; background: #f5f5f5; border-radius: 5px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)
        
        # 설정 그룹
        settings_group = QGroupBox("BIN 설정")
        settings_layout = QGridLayout(settings_group)
        settings_layout.setSpacing(10)
        
        # 1. BIN당 최대 수량
        row = 0
        settings_layout.addWidget(QLabel("BIN당 최대 수량:"), row, 0)
        self.max_qty_spin = QSpinBox()
        self.max_qty_spin.setRange(1, 9999)
        self.max_qty_spin.setValue(100)
        self.max_qty_spin.setSuffix(" 개")
        self.max_qty_spin.setToolTip("하나의 BIN에 담을 수 있는 최대 수량입니다.\n초과 시 다음 BIN으로 분산됩니다.")
        settings_layout.addWidget(self.max_qty_spin, row, 1)
        
        hint1 = QLabel("(초과 시 다음 BIN으로 분산)")
        hint1.setStyleSheet("color: #888; font-size: 11px;")
        settings_layout.addWidget(hint1, row, 2)
        
        # 2. 최소 수량 임계값
        row = 1
        settings_layout.addWidget(QLabel("소량 SKU 기준:"), row, 0)
        self.min_qty_spin = QSpinBox()
        self.min_qty_spin.setRange(0, 9999)
        self.min_qty_spin.setValue(10)
        self.min_qty_spin.setSuffix(" 개 이하")
        self.min_qty_spin.setToolTip("이 수량 이하인 SKU는 '소량 SKU'로 분류되어\n다른 소량 SKU들과 함께 공유 BIN에 배정됩니다.")
        settings_layout.addWidget(self.min_qty_spin, row, 1)
        
        hint2 = QLabel("(이하면 공유 BIN 배정)")
        hint2.setStyleSheet("color: #888; font-size: 11px;")
        settings_layout.addWidget(hint2, row, 2)
        
        # 3. 공유 BIN당 최대 SKU 개수
        row = 2
        settings_layout.addWidget(QLabel("공유 BIN 최대 SKU:"), row, 0)
        self.max_sku_spin = QSpinBox()
        self.max_sku_spin.setRange(1, 99)
        self.max_sku_spin.setValue(5)
        self.max_sku_spin.setSuffix(" 종류")
        self.max_sku_spin.setToolTip("하나의 공유 BIN에 담을 수 있는 최대 SKU 종류 수입니다.\n초과 시 새로운 공유 BIN이 생성됩니다.")
        settings_layout.addWidget(self.max_sku_spin, row, 1)
        
        hint3 = QLabel("(공유 BIN에 묶을 최대 SKU 수)")
        hint3.setStyleSheet("color: #888; font-size: 11px;")
        settings_layout.addWidget(hint3, row, 2)
        
        # 4. 전용 BIN 수량 임계값 (중복금지 룰)
        row = 3
        settings_layout.addWidget(QLabel("중복금지 수량:"), row, 0)
        self.dedicated_qty_spin = QSpinBox()
        self.dedicated_qty_spin.setRange(0, 9999)
        self.dedicated_qty_spin.setValue(0)
        self.dedicated_qty_spin.setSuffix(" 개 이상")
        self.dedicated_qty_spin.setToolTip("단일 SKU 수량이 이 값 이상이면 전용 BIN 배정 (중복금지)\n0 = 비활성")
        settings_layout.addWidget(self.dedicated_qty_spin, row, 1)
        
        hint4 = QLabel("(이상이면 전용 BIN, 0=비활성)")
        hint4.setStyleSheet("color: #888; font-size: 11px;")
        settings_layout.addWidget(hint4, row, 2)
        
        layout.addWidget(settings_group)
        
        # 현재 상태 표시
        self.status_label = QLabel()
        self.status_label.setStyleSheet("padding: 10px; background: #E3F2FD; border-radius: 5px;")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self._update_status()
        
        # 값 변경 시 상태 업데이트
        self.max_qty_spin.valueChanged.connect(self._update_status)
        self.min_qty_spin.valueChanged.connect(self._update_status)
        self.max_sku_spin.valueChanged.connect(self._update_status)
        self.dedicated_qty_spin.valueChanged.connect(self._update_status)
        
        # 버튼
        btn_layout = QHBoxLayout()
        
        reset_btn = QPushButton("기본값 복원")
        reset_btn.clicked.connect(self._reset_to_default)
        btn_layout.addWidget(reset_btn)
        
        btn_layout.addStretch()
        
        cancel_btn = QPushButton("취소")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        apply_btn = QPushButton("적용")
        apply_btn.setStyleSheet("background: #2196F3; color: white; font-weight: bold;")
        apply_btn.clicked.connect(self._apply_settings)
        btn_layout.addWidget(apply_btn)
        
        layout.addLayout(btn_layout)
    
    def _load_settings(self):
        """설정 로드"""
        settings = load_bin_settings()
        self.max_qty_spin.setValue(settings.get("max_qty_per_bin", 100))
        self.min_qty_spin.setValue(settings.get("min_qty_threshold", 10))
        self.max_sku_spin.setValue(settings.get("max_sku_per_shared_bin", 5))
        self.dedicated_qty_spin.setValue(settings.get("dedicated_qty_threshold", 0))
    
    def _update_status(self):
        """상태 레이블 업데이트"""
        max_qty = self.max_qty_spin.value()
        min_qty = self.min_qty_spin.value()
        max_sku = self.max_sku_spin.value()
        dedicated_qty = self.dedicated_qty_spin.value()
        
        dedicated_rule = f"• 중복금지: {dedicated_qty}개 이상 SKU는 전용 BIN<br>" if dedicated_qty > 0 else ""
        
        status_text = (
            f"📊 <b>현재 설정 요약</b><br>"
            f"{dedicated_rule}"
            f"• 대량 SKU ({min_qty}개 초과): 각각 별도 BIN, {max_qty}개 초과 시 분산<br>"
            f"• 소량 SKU ({min_qty}개 이하): 최대 {max_sku}종류까지 공유 BIN에 묶음"
        )
        self.status_label.setText(status_text)
    
    def _reset_to_default(self):
        """기본값 복원"""
        self.max_qty_spin.setValue(100)
        self.min_qty_spin.setValue(10)
        self.max_sku_spin.setValue(5)
        self.dedicated_qty_spin.setValue(0)
    
    def _apply_settings(self):
        """설정 적용"""
        max_qty = self.max_qty_spin.value()
        min_qty = self.min_qty_spin.value()
        max_sku = self.max_sku_spin.value()
        dedicated_qty = self.dedicated_qty_spin.value()
        
        # BinManager에 설정 적용
        self.bin_manager.set_config(
            max_qty_per_bin=max_qty,
            min_qty_threshold=min_qty,
            max_sku_per_shared_bin=max_sku,
            dedicated_qty_threshold=dedicated_qty
        )
        
        # 설정 파일에 저장
        save_bin_settings(
            max_qty_per_bin=max_qty,
            min_qty_threshold=min_qty,
            max_sku_per_shared_bin=max_sku,
            dedicated_qty_threshold=dedicated_qty
        )
        
        self.accept()
    
    def get_settings(self):
        """현재 설정 반환"""
        return {
            "max_qty_per_bin": self.max_qty_spin.value(),
            "min_qty_threshold": self.min_qty_spin.value(),
            "max_sku_per_shared_bin": self.max_sku_spin.value(),
            "dedicated_qty_threshold": self.dedicated_qty_spin.value()
        }


class MainWindow(QMainWindow):
    """메인 윈도우"""
    
    # 재출력 검색 완료 시그널
    reprint_search_completed = Signal(object, bool)  # (search_result, cancelled)
    
    def __init__(self):
        super().__init__()
        
        # 모듈 초기화
        self.excel_loader = ExcelLoader()
        self.scanner = ScannerListener()
        self.ezauto = EzAutoInput()
        self.pdf_printer = PDFPrinter()
        self.processor = OrderProcessor(
            self.excel_loader,
            self.ezauto,
            self.pdf_printer
        )
        
        # BIN 관리자 초기화
        self.bin_manager = BinManager()
        
        # 제외 송장 목록 초기화
        self._excluded_tracking_numbers: set = set()
        
        # 작업 차수 관리 (1차, 2차 피킹 등) - 각 탭별 독립 관리
        self._work_session: int = 0  # 업체 선택/변경 시마다 증가 (기본/출고용)
        self._work_session_supplier: str = ""  # 현재 작업 차수의 업체명
        
        # 각 탭별 독립적인 세션 ID
        self._shipment_session_id: int = 0  # 출고 탭 선택 세션
        self._fp_session_id: int = 0  # 전체피킹 탭 선택 세션
        self._pp_session_id: int = 0  # 미리피킹 탭 선택 세션
        
        # 출고 탭 - 출력된 송장 추적 (세션별)
        self._printed_tracking_nos: Dict[int, set] = {}  # {session_id: {tracking_no, ...}}
        
        # 우선순위 규칙 초기화 (기본값: 단품 우선)
        from priority_engine import get_default_rules
        self.processor.set_priority_rules(get_default_rules())
        
        # ===== 전체피킹 모드 관련 모듈 초기화 =====
        # 모드 관리자
        self.mode_manager = ModeManager()
        
        # ESP32 장치 레지스트리
        self.device_registry = DeviceRegistry()
        
        # ESP32 WebSocket 서버
        self.esp32_transport = Esp32Transport()
        
        # 전체피킹 엔진
        self.full_pick_engine = FullPickEngine(
            device_registry=self.device_registry,
            esp32_transport=self.esp32_transport
        )
        
        # 미리피킹 엔진
        self.pre_pick_engine = PrePickEngine()
        # 미리피킹에도 ESP32 연동 설정
        self.pre_pick_engine.set_esp32(self.device_registry, self.esp32_transport)
        
        # ★ 출고 모드에도 ESP32 연동 설정 (합포장 빈 표시)
        self.processor.set_esp32(
            device_registry=self.device_registry,
            esp32_transport=self.esp32_transport,
            bin_manager=self.bin_manager
        )
        
        # 작업 세션 관리자
        self.session_manager = WorkSessionManager()
        
        # UI 초기화
        self._init_ui()
        self._connect_signals()
        
        # 재출력 검색 완료 시그널 연결
        self.reprint_search_completed.connect(self._on_reprint_search_completed)
        
        # 프린터 설정 로드 및 UI 반영
        self._load_printer_settings_to_ui()
        
        # 스캐너 자동 시작 (프로그램 시작 시 항상 활성화)
        self._scanner_active = False
        if self.scanner.start():
            self._scanner_active = True
            if hasattr(self, 'status_scanner'):
                self.status_scanner.setText("스캐너: 활성")
            self._add_log("스캐너 자동 시작됨")
        
        # 첫 실행 체크 및 설정 마법사 표시
        self._check_first_run()
    
    def _check_first_run(self):
        """첫 실행 체크 및 설정 마법사 표시"""
        # 설정 파일 확인/생성
        ensure_settings_file()
        
        # 첫 실행인 경우 마법사 표시
        if is_first_run():
            self._add_log("첫 실행 감지 - 초기 설정 마법사 표시")
            QTimer.singleShot(500, self._show_setup_wizard)
        else:
            # 시스템 진단 결과 로그
            self._add_log(get_admin_status_message())
            
            # 프린터 유효성 검사
            validation = validate_printer_settings()
            if not validation["label_printer"]["exists"] and validation["label_printer"]["name"]:
                self._add_log(f"⚠️ 설정된 라벨 프린터를 찾을 수 없습니다: {validation['label_printer']['name']}")
            if not validation["a4_printer"]["exists"] and validation["a4_printer"]["name"]:
                self._add_log(f"⚠️ 설정된 A4 프린터를 찾을 수 없습니다: {validation['a4_printer']['name']}")
    
    def _show_setup_wizard(self):
        """초기 설정 마법사 표시"""
        dialog = SetupWizardDialog(self)
        dialog.exec()
        
        # 마법사 완료 후 프린터 설정 UI 갱신
        self._load_printer_settings_to_ui()
        
        # EzAuto 설정 갱신
        ezauto_settings = load_ezauto_settings()
        self.ezauto.set_window_title(ezauto_settings.get("window_title", "이지오토"))
    
    def _init_ui(self):
        """UI 초기화"""
        self.setWindowTitle("자동출고 프로그램 v1.0")
        self.setMinimumSize(1200, 800)
        
        # 중앙 위젯
        central = QWidget()
        self.setCentralWidget(central)
        
        # 메인 레이아웃
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(15, 15, 15, 15)
        
        # === 탭 위젯 생성 ===
        self.tab_widget = QTabWidget()
        
        # 출고 탭 (기존 UI)
        self.shipment_tab = self._create_shipment_tab()
        self.tab_widget.addTab(self.shipment_tab, "출고")
        
        # 전체피킹 탭
        self.fullpick_tab = self._create_fullpick_tab()
        self.tab_widget.addTab(self.fullpick_tab, "🚀 전체피킹")
        
        # 미리피킹 탭
        self.prepick_tab = self._create_prepick_tab()
        self.tab_widget.addTab(self.prepick_tab, "📦 미리피킹")
        
        # 재출력 탭
        self.reprint_tab = self._create_reprint_tab()
        self.tab_widget.addTab(self.reprint_tab, "재출력")
        
        # ESP32 설정 탭
        self.esp32_tab = self._create_esp32_tab()
        self.tab_widget.addTab(self.esp32_tab, "📡 ESP32")
        
        # 설정 탭
        self.settings_tab = self._create_settings_tab()
        self.tab_widget.addTab(self.settings_tab, "⚙️ 설정")
        
        main_layout.addWidget(self.tab_widget, 1)
        
        # === 하단: 상태바 ===
        self._create_status_bar()
        
        # 스타일 적용
        self._apply_styles()
    
    def _create_shipment_tab(self) -> QWidget:
        """출고 탭 생성 (기존 UI 내용)"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # === 최상단: 작업 차수 표시 ===
        session_widget = self._create_session_display()
        layout.addWidget(session_widget)
        
        # === 상단: 파일 로드 및 설정 ===
        top_group = self._create_top_section()
        layout.addWidget(top_group)
        
        # === 중간: 스플리터 (테이블들 + 우선순위 설정 + 로그) ===
        splitter = QSplitter(Qt.Vertical)
        
        # 테이블 영역
        tables_widget = self._create_tables_section()
        splitter.addWidget(tables_widget)
        
        # 우선순위 설정 영역 (우선순위 설정 + 우선 송장 관리)
        priority_section = self._create_priority_section()
        splitter.addWidget(priority_section)
        
        # 로그 영역
        log_group = self._create_log_section()
        splitter.addWidget(log_group)
        
        splitter.setSizes([400, 200, 200])
        layout.addWidget(splitter, 1)
        
        return tab
    
    def _create_session_display(self) -> QWidget:
        """작업 차수 표시 영역 (출고 탭 상단)"""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(10, 5, 10, 5)
        
        # 현재 작업 차수 표시
        session_frame = QFrame()
        session_frame.setStyleSheet("""
            QFrame {
                background-color: #E8EAF6;
                border: 2px solid #3F51B5;
                border-radius: 8px;
                padding: 5px;
            }
        """)
        session_layout = QHBoxLayout(session_frame)
        session_layout.setContentsMargins(10, 5, 10, 5)
        
        # 차수 라벨
        self.session_display_label = QLabel("📋 작업 대기")
        self.session_display_label.setFont(QFont("Arial", 14, QFont.Bold))
        self.session_display_label.setStyleSheet("color: #3F51B5; border: none;")
        session_layout.addWidget(self.session_display_label)
        
        # 구분선
        separator = QLabel("|")
        separator.setStyleSheet("color: #9E9E9E; border: none;")
        session_layout.addWidget(separator)
        
        # 업체 라벨
        self.session_supplier_label = QLabel("🏢 업체: 미선택")
        self.session_supplier_label.setFont(QFont("Arial", 12))
        self.session_supplier_label.setStyleSheet("color: #FF9800; border: none;")
        session_layout.addWidget(self.session_supplier_label)
        
        # 구분선
        separator2 = QLabel("|")
        separator2.setStyleSheet("color: #9E9E9E; border: none;")
        session_layout.addWidget(separator2)
        
        # 주문/SKU 정보
        self.session_info_label = QLabel("📦 0건, 0 SKU")
        self.session_info_label.setFont(QFont("Arial", 11))
        self.session_info_label.setStyleSheet("color: #666; border: none;")
        session_layout.addWidget(self.session_info_label)
        
        # 구분선
        separator3 = QLabel("|")
        separator3.setStyleSheet("color: #9E9E9E; border: none;")
        session_layout.addWidget(separator3)
        
        # 출력 진행 상태 (전체/출력/남음)
        self.session_print_status_label = QLabel("🖨️ 0/0 (남음: 0)")
        self.session_print_status_label.setFont(QFont("Arial", 11))
        self.session_print_status_label.setStyleSheet("color: #4CAF50; border: none;")
        session_layout.addWidget(self.session_print_status_label)
        
        # 남은 송장 전체 출력 버튼
        self.print_remaining_btn = QPushButton("📤 남은 송장 전체 출력")
        self.print_remaining_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF5722;
                color: white;
                font-weight: bold;
                padding: 5px 10px;
                border-radius: 4px;
                border: none;
            }
            QPushButton:hover {
                background-color: #E64A19;
            }
            QPushButton:disabled {
                background-color: #BDBDBD;
            }
        """)
        self.print_remaining_btn.clicked.connect(self._on_print_remaining)
        self.print_remaining_btn.setEnabled(False)
        session_layout.addWidget(self.print_remaining_btn)
        
        layout.addWidget(session_frame)
        
        # 세션 목록 드롭다운
        layout.addWidget(QLabel("저장된 차수:"))
        self.session_combo = QComboBox()
        self.session_combo.setMinimumWidth(250)
        self.session_combo.addItem("-- 선택 --", 0)
        self.session_combo.currentIndexChanged.connect(self._on_session_combo_changed)
        layout.addWidget(self.session_combo)
        
        # 새로고침 버튼 (차수 선택 해제 + 목록 갱신)
        self.session_refresh_btn = QPushButton("🔄")
        self.session_refresh_btn.setMaximumWidth(40)
        self.session_refresh_btn.setToolTip("차수 선택 해제 및 목록 새로고침")
        self.session_refresh_btn.clicked.connect(self._on_refresh_shipment_session)
        layout.addWidget(self.session_refresh_btn)
        
        layout.addStretch()
        
        return widget
    
    def _update_session_display(self):
        """작업 차수 표시 업데이트"""
        # 출고 탭의 독립적인 세션 ID 사용
        session = self.session_manager.get_session(self._shipment_session_id) if self._shipment_session_id > 0 else None
        
        if session:
            self.session_display_label.setText(f"📋 {session.session_id}차 작업")
            self.session_supplier_label.setText(f"🏢 업체: {session.supplier_display}")
            self.session_info_label.setText(f"📦 {session.order_count}건, {session.sku_count} SKU, {session.bin_count} BIN")
            
            # 작업 차수 변수도 업데이트
            self._work_session = session.session_id
            self._work_session_supplier = session.supplier_display
            
            # 출력 진행 상태 업데이트
            self._update_print_status()
        else:
            self.session_display_label.setText("📋 작업 대기")
            self.session_supplier_label.setText("🏢 업체: 미선택")
            self.session_info_label.setText("📦 0건, 0 SKU")
            self.session_print_status_label.setText("🖨️ 0/0 (남음: 0)")
            self.print_remaining_btn.setEnabled(False)
    
    def _update_print_status(self):
        """출력 진행 상태 업데이트"""
        session_id = self._shipment_session_id
        if session_id <= 0:
            self.session_print_status_label.setText("🖨️ 0/0 (남음: 0)")
            self.print_remaining_btn.setEnabled(False)
            return
        
        session = self.session_manager.get_session(session_id)
        if not session:
            return
        
        # 해당 세션의 전체 송장 목록 가져오기
        all_tracking_nos = self._get_session_tracking_nos(session_id)
        total_count = len(all_tracking_nos)
        
        # 출력된 송장 수
        printed_set = self._printed_tracking_nos.get(session_id, set())
        printed_count = len(printed_set & all_tracking_nos)  # 교집합으로 정확한 수 계산
        
        # 남은 송장 수
        remaining_count = total_count - printed_count
        
        # 상태 표시 업데이트
        if remaining_count == 0 and total_count > 0:
            self.session_print_status_label.setText(f"✅ {printed_count}/{total_count} (완료!)")
            self.session_print_status_label.setStyleSheet("color: #4CAF50; border: none; font-weight: bold;")
            self.print_remaining_btn.setEnabled(False)
        elif remaining_count > 0:
            self.session_print_status_label.setText(f"🖨️ {printed_count}/{total_count} (남음: {remaining_count})")
            self.session_print_status_label.setStyleSheet("color: #FF9800; border: none;")
            self.print_remaining_btn.setEnabled(True)
        else:
            self.session_print_status_label.setText(f"🖨️ 0/{total_count} (남음: {total_count})")
            self.session_print_status_label.setStyleSheet("color: #666; border: none;")
            self.print_remaining_btn.setEnabled(total_count > 0)
    
    def _get_session_tracking_nos(self, session_id: int, normalized: bool = True) -> set:
        """세션의 전체 송장번호 목록 가져오기
        
        Args:
            session_id: 세션 ID
            normalized: True면 정규화된 형태(하이픈 제거), False면 원본
        """
        session = self.session_manager.get_session(session_id)
        if not session:
            return set()
        
        # 해당 세션의 업체 기반으로 데이터 필터링
        filtered_df = self.excel_loader.get_filtered_by_suppliers(session.suppliers)
        if filtered_df is None or filtered_df.empty:
            return set()
        
        # 송장번호 목록
        if 'tracking_no' in filtered_df.columns:
            raw_tracking_nos = filtered_df['tracking_no'].dropna().astype(str).unique()
            if normalized:
                # 정규화된 형태로 반환 (하이픈/공백 제거)
                return set(re.sub(r'[-–—\s]', '', t) for t in raw_tracking_nos)
            else:
                return set(raw_tracking_nos)
        return set()
    
    def _get_session_tracking_nos_map(self, session_id: int) -> dict:
        """세션의 송장번호 매핑 (정규화 → 원본)"""
        session = self.session_manager.get_session(session_id)
        if not session:
            return {}
        
        filtered_df = self.excel_loader.get_filtered_by_suppliers(session.suppliers)
        if filtered_df is None or filtered_df.empty:
            return {}
        
        if 'tracking_no' not in filtered_df.columns:
            return {}
        
        # 정규화된 형태 → 원본 매핑
        mapping = {}
        for t in filtered_df['tracking_no'].dropna().astype(str).unique():
            clean = re.sub(r'[-–—\s]', '', t)
            mapping[clean] = t
        return mapping
    
    def _mark_as_printed(self, tracking_no: str):
        """송장을 출력됨으로 표시"""
        # 하이픈 제거한 정규화된 형태로 저장
        clean_tracking = re.sub(r'[-–—\s]', '', tracking_no)
        
        # ★ order_processor에도 출력 완료 알림 (세션과 무관하게 중복 출력 방지)
        if hasattr(self, 'processor'):
            self.processor.add_printed_tracking_no(clean_tracking)
        
        session_id = self._shipment_session_id
        if session_id <= 0:
            return
        
        if session_id not in self._printed_tracking_nos:
            self._printed_tracking_nos[session_id] = set()
        
        self._printed_tracking_nos[session_id].add(clean_tracking)
        
        # 상태 업데이트
        self._update_print_status()
    
    def _on_print_remaining(self):
        """남은 송장 전체 출력"""
        session_id = self._shipment_session_id
        if session_id <= 0:
            QMessageBox.warning(self, "알림", "먼저 차수를 선택해주세요.")
            return
        
        # 전체 송장 목록 (정규화된 형태)
        all_tracking_nos = self._get_session_tracking_nos(session_id, normalized=True)
        if not all_tracking_nos:
            QMessageBox.warning(self, "알림", "출력할 송장이 없습니다.")
            return
        
        # 정규화 → 원본 매핑
        tracking_map = self._get_session_tracking_nos_map(session_id)
        
        # 출력된 송장 제외 (정규화된 형태로 비교)
        printed_set = self._printed_tracking_nos.get(session_id, set())
        remaining_nos = all_tracking_nos - printed_set
        
        if not remaining_nos:
            QMessageBox.information(self, "완료", "모든 송장이 이미 출력되었습니다.")
            return
        
        # 확인 대화상자
        reply = QMessageBox.question(
            self,
            "남은 송장 전체 출력",
            f"남은 {len(remaining_nos)}건의 송장을 모두 출력하시겠습니까?\n\n"
            f"⚠️ 많은 양의 출력은 시간이 걸릴 수 있습니다.",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        # 일괄 출력 시작
        self._add_log(f"<b style='color:#FF5722'>[일괄출력] {len(remaining_nos)}건 출력 시작...</b>", html=True)
        
        success_count = 0
        fail_count = 0
        total = len(remaining_nos)
        
        for idx, clean_tracking_no in enumerate(sorted(remaining_nos), 1):
            # 원본 송장번호 가져오기 (PDF 인덱스 매칭용)
            original_tracking_no = tracking_map.get(clean_tracking_no, clean_tracking_no)
            
            try:
                # PDF 출력
                if self.pdf_printer.enabled:
                    # 정규화된 형태와 원본 모두 시도
                    result = self.pdf_printer.print_pdf(clean_tracking_no)
                    if not result and original_tracking_no != clean_tracking_no:
                        result = self.pdf_printer.print_pdf(original_tracking_no)
                    
                    if result:
                        self._mark_as_printed(clean_tracking_no)
                        success_count += 1
                    else:
                        self._add_log(f"[일괄출력] PDF 없음: {original_tracking_no}")
                        fail_count += 1
                else:
                    # PDF 출력 비활성화 시 EzAuto만
                    if self.ezauto.enabled:
                        self.ezauto.send_tracking_number(original_tracking_no)
                    self._mark_as_printed(clean_tracking_no)
                    success_count += 1
                
                # 10개마다 진행 상황 로그
                if idx % 10 == 0:
                    self._add_log(f"[일괄출력] 진행 중... {idx}/{total}")
                    # UI 업데이트를 위한 이벤트 처리
                    QApplication.processEvents()
                    
            except Exception as e:
                self._add_log(f"[일괄출력] 오류: {original_tracking_no} - {str(e)}")
                fail_count += 1
        
        # 결과 표시
        self._add_log(f"<b style='color:#4CAF50'>[일괄출력] 완료: 성공 {success_count}건, 실패 {fail_count}건</b>", html=True)
        
        QMessageBox.information(
            self,
            "일괄 출력 완료",
            f"출력 완료!\n\n"
            f"✅ 성공: {success_count}건\n"
            f"❌ 실패: {fail_count}건"
        )
    
    def _update_session_combo(self):
        """출고 탭 세션 드롭다운 업데이트 (독립적)"""
        self.session_combo.blockSignals(True)
        self.session_combo.clear()
        self.session_combo.addItem("-- 선택 --", 0)
        
        for session_id, display_name in self.session_manager.get_session_choices():
            self.session_combo.addItem(display_name, session_id)
        
        # 출고 탭 자체 세션 ID 기반으로 선택
        if self._shipment_session_id > 0:
            for i in range(self.session_combo.count()):
                if self.session_combo.itemData(i) == self._shipment_session_id:
                    self.session_combo.setCurrentIndex(i)
                    break
        
        self.session_combo.blockSignals(False)
        
        # 전체피킹/미리피킹 세션 콤보도 업데이트 (각자 독립적으로)
        if hasattr(self, 'fp_session_combo'):
            self._update_fp_session_combo()
        if hasattr(self, 'pp_session_combo'):
            self._update_pp_session_combo()
    
    @Slot(int)
    def _on_session_combo_changed(self, index: int):
        """출고 탭 세션 드롭다운 변경 (독립적)"""
        session_id = self.session_combo.itemData(index)
        if session_id and session_id > 0:
            self._shipment_session_id = session_id
            session = self.session_manager.get_session(session_id)
            if session:
                self._load_shipment_session(session)
    
    def _load_shipment_session(self, session: WorkSession):
        """출고 탭용 세션 로드 (독립적)"""
        # 출고 탭 전용 세션 ID 저장
        self._shipment_session_id = session.session_id
        
        # 업체 필터 적용
        if session.suppliers:
            if len(session.suppliers) == 1:
                self.excel_loader.filter_by_supplier(session.suppliers[0])
            else:
                self.excel_loader.filter_by_supplier(session.suppliers)
        
        # 출고 탭 전용 작업 차수 업데이트
        self._work_session = session.session_id
        self._work_session_supplier = session.supplier_display
        
        # 출고 탭 UI만 업데이트 (다른 탭에 영향 없음)
        self._update_session_display()
        self._update_tables()
        
        self._add_log(f"<b style='color:#3F51B5'>[출고] {session.session_id}차 작업 선택 - {session.supplier_display}</b>", html=True)
    
    @Slot()
    def _on_refresh_shipment_session(self):
        """출고 탭 - 차수 선택 해제 및 새로고침"""
        # 출고 탭 세션 선택 해제
        self._shipment_session_id = 0
        self._work_session = 0
        self._work_session_supplier = ""
        
        # 콤보박스 초기화
        self.session_combo.blockSignals(True)
        self.session_combo.setCurrentIndex(0)
        self.session_combo.blockSignals(False)
        
        # UI 업데이트
        self._update_session_combo()
        self._update_session_display()
        
        self._add_log("[출고] 차수 선택이 해제되었습니다. 다른 차수를 선택하세요.")
    
    def _create_reprint_tab(self) -> QWidget:
        """재출력 탭 생성"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # 제목
        title = QLabel("📄 재출력")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        layout.addWidget(title)
        
        # 설명
        desc = QLabel("송장번호 또는 주문번호를 입력하여 송장/주문서를 재출력할 수 있습니다.")
        desc.setWordWrap(True)
        layout.addWidget(desc)
        
        layout.addSpacing(10)
        
        # 입력 영역
        input_group = QGroupBox("입력")
        input_layout = QVBoxLayout(input_group)
        
        # 송장번호/주문번호 입력
        input_layout.addWidget(QLabel("송장번호 또는 주문번호:"))
        input_row = QHBoxLayout()
        self.reprint_input = QLineEdit()
        self.reprint_input.setPlaceholderText("송장번호 또는 주문번호 입력 (하이픈 포함 가능)")
        self.reprint_input.returnPressed.connect(self._on_reprint_search)  # Enter 키로 검색 시작
        input_row.addWidget(self.reprint_input)
        
        # 멀티코어 사용 체크박스
        self.reprint_multicore_check = QCheckBox("멀티코어 사용")
        self.reprint_multicore_check.setChecked(True)  # 기본 체크
        self.reprint_multicore_check.setToolTip("체크 시 CPU 코어의 70%를 사용하여 빠른 검색")
        input_row.addWidget(self.reprint_multicore_check)
        
        input_layout.addLayout(input_row)
        
        layout.addWidget(input_group)
        
        # 출력 옵션 영역
        options_group = QGroupBox("출력 옵션")
        options_layout = QVBoxLayout(options_group)
        
        # 송장(라벨) 옵션
        label_option_layout = QHBoxLayout()
        self.reprint_label_check = QCheckBox("송장(라벨)")
        self.reprint_label_check.setChecked(True)  # 기본 체크
        label_option_layout.addWidget(self.reprint_label_check)
        
        # 송장 검색 폴더 선택
        label_option_layout.addWidget(QLabel("검색 폴더:"))
        self.reprint_label_folder_edit = QLineEdit()
        self.reprint_label_folder_edit.setPlaceholderText("labels")
        self.reprint_label_folder_edit.setText("labels")  # 기본값
        self.reprint_label_folder_edit.setMaximumWidth(200)
        label_option_layout.addWidget(self.reprint_label_folder_edit)
        
        self.reprint_label_folder_btn = QPushButton("폴더 선택")
        self.reprint_label_folder_btn.setMaximumWidth(80)
        self.reprint_label_folder_btn.clicked.connect(self._on_browse_label_folder)
        label_option_layout.addWidget(self.reprint_label_folder_btn)
        
        label_option_layout.addStretch()
        options_layout.addLayout(label_option_layout)
        
        # 주문서(A4) 옵션
        order_option_layout = QHBoxLayout()
        self.reprint_order_check = QCheckBox("주문서(A4)")
        self.reprint_order_check.setChecked(False)  # 기본 미체크
        order_option_layout.addWidget(self.reprint_order_check)
        
        # 주문서 검색 폴더 선택
        order_option_layout.addWidget(QLabel("검색 폴더:"))
        self.reprint_order_folder_edit = QLineEdit()
        self.reprint_order_folder_edit.setPlaceholderText("orders")
        self.reprint_order_folder_edit.setText("orders")  # 기본값
        self.reprint_order_folder_edit.setMaximumWidth(200)
        order_option_layout.addWidget(self.reprint_order_folder_edit)
        
        self.reprint_order_folder_btn = QPushButton("폴더 선택")
        self.reprint_order_folder_btn.setMaximumWidth(80)
        self.reprint_order_folder_btn.clicked.connect(self._on_browse_order_folder)
        order_option_layout.addWidget(self.reprint_order_folder_btn)
        
        order_option_layout.addStretch()
        options_layout.addLayout(order_option_layout)
        
        layout.addWidget(options_group)
        
        # 검색 및 재출력 버튼 영역
        button_group = QGroupBox("작업")
        button_layout = QHBoxLayout(button_group)
        
        # 검색 버튼
        self.reprint_search_btn = QPushButton("🔍 검색")
        self.reprint_search_btn.setMinimumHeight(40)
        self.reprint_search_btn.setFont(QFont("Arial", 12, QFont.Bold))
        self.reprint_search_btn.clicked.connect(self._on_reprint_search)
        button_layout.addWidget(self.reprint_search_btn)
        
        # 중단 버튼
        self.reprint_cancel_btn = QPushButton("⏹ 중단")
        self.reprint_cancel_btn.setMinimumHeight(40)
        self.reprint_cancel_btn.setFont(QFont("Arial", 12, QFont.Bold))
        self.reprint_cancel_btn.setEnabled(False)
        self.reprint_cancel_btn.clicked.connect(self._on_reprint_cancel)
        button_layout.addWidget(self.reprint_cancel_btn)
        
        # 재출력 버튼
        self.reprint_execute_btn = QPushButton("📄 재출력")
        self.reprint_execute_btn.setMinimumHeight(40)
        self.reprint_execute_btn.setFont(QFont("Arial", 12, QFont.Bold))
        self.reprint_execute_btn.setEnabled(False)  # 초기 비활성화
        self.reprint_execute_btn.clicked.connect(self._on_reprint_execute)
        button_layout.addWidget(self.reprint_execute_btn)
        
        layout.addWidget(button_group)
        
        # 검색 상태 표시 영역
        status_group = QGroupBox("검색 상태")
        status_layout = QVBoxLayout(status_group)
        self.reprint_status_label = QLabel("검색 대기 중...")
        self.reprint_status_label.setWordWrap(True)
        self.reprint_status_label.setStyleSheet("color: #666; font-size: 11px; padding: 5px;")
        status_layout.addWidget(self.reprint_status_label)
        layout.addWidget(status_group)
        
        # 검색 결과 저장
        self._reprint_search_result = None
        self._reprint_search_cancelled = False
        
        layout.addStretch()
        
        return tab
    
    def _create_fullpick_tab(self) -> QWidget:
        """전체피킹 탭 생성"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # ===== 상단 1행: 작업 차수 선택 =====
        session_layout = QHBoxLayout()
        
        # 작업 차수 선택 드롭다운
        session_select_group = QGroupBox("📋 작업 차수 선택")
        session_select_layout = QHBoxLayout(session_select_group)
        
        self.fp_session_combo = QComboBox()
        self.fp_session_combo.setMinimumWidth(300)
        self.fp_session_combo.setFont(QFont("Arial", 12))
        self.fp_session_combo.addItem("-- 출고 탭에서 업체 선택 필요 --", 0)
        self.fp_session_combo.currentIndexChanged.connect(self._on_fp_session_combo_changed)
        session_select_layout.addWidget(self.fp_session_combo)
        
        # 새로고침 버튼 (선택 해제 + 목록 갱신)
        self.fp_refresh_session_btn = QPushButton("🔄")
        self.fp_refresh_session_btn.setMaximumWidth(40)
        self.fp_refresh_session_btn.setToolTip("차수 선택 해제 및 목록 새로고침")
        self.fp_refresh_session_btn.clicked.connect(self._on_refresh_fp_session)
        session_select_layout.addWidget(self.fp_refresh_session_btn)
        
        session_layout.addWidget(session_select_group)
        
        # 현재 선택된 차수 표시
        current_group = QGroupBox("🎯 현재 작업")
        current_layout = QHBoxLayout(current_group)
        self.fp_session_label = QLabel("미선택")
        self.fp_session_label.setFont(QFont("Arial", 14, QFont.Bold))
        self.fp_session_label.setStyleSheet("color: #9C27B0;")
        current_layout.addWidget(self.fp_session_label)
        session_layout.addWidget(current_group)
        
        # 현재 업체 표시
        supplier_group = QGroupBox("🏢 업체")
        supplier_grp_layout = QHBoxLayout(supplier_group)
        self.fp_supplier_label = QLabel("업체 미선택")
        self.fp_supplier_label.setFont(QFont("Arial", 12, QFont.Bold))
        self.fp_supplier_label.setStyleSheet("color: #FF9800;")
        supplier_grp_layout.addWidget(self.fp_supplier_label)
        session_layout.addWidget(supplier_group)
        
        # 데이터 상태
        data_group = QGroupBox("📦 데이터")
        data_grp_layout = QHBoxLayout(data_group)
        self.fp_data_status = QLabel("엑셀 미로드")
        self.fp_data_status.setFont(QFont("Arial", 11))
        data_grp_layout.addWidget(self.fp_data_status)
        session_layout.addWidget(data_group)
        
        layout.addLayout(session_layout)
        
        # ===== 상단 2행: 서버 상태 =====
        top_layout = QHBoxLayout()
        
        # ESP32 서버 상태
        server_group = QGroupBox("📡 ESP32 서버")
        server_layout = QHBoxLayout(server_group)
        
        self.fp_server_status = QLabel("⚫ 중지됨")
        self.fp_server_status.setMinimumWidth(120)
        server_layout.addWidget(self.fp_server_status)
        
        self.fp_device_count = QLabel("연결: 0대")
        server_layout.addWidget(self.fp_device_count)
        
        self.fp_esp32_settings_btn = QPushButton("⚙️ ESP32 설정")
        self.fp_esp32_settings_btn.setToolTip("ESP32 탭에서 서버 시작/중지")
        self.fp_esp32_settings_btn.clicked.connect(self._go_to_esp32_tab)
        server_layout.addWidget(self.fp_esp32_settings_btn)
        
        top_layout.addWidget(server_group)
        
        # 상태
        state_group = QGroupBox("📊 피킹 상태")
        state_layout = QHBoxLayout(state_group)
        self.fp_state_label = QLabel("SKU 스캔 대기")
        self.fp_state_label.setFont(QFont("Arial", 12))
        state_layout.addWidget(self.fp_state_label)
        top_layout.addWidget(state_group)
        
        layout.addLayout(top_layout)
        
        # ===== 중단: SKU 스캔 및 BIN 목록 =====
        main_splitter = QSplitter(Qt.Horizontal)
        
        # 왼쪽: SKU 스캔 영역
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        # SKU 스캔 입력
        scan_group = QGroupBox("📦 SKU 스캔")
        scan_layout = QVBoxLayout(scan_group)
        
        scan_row = QHBoxLayout()
        self.fp_sku_input = QLineEdit()
        self.fp_sku_input.setPlaceholderText("SKU 바코드 스캔 또는 입력")
        self.fp_sku_input.setFont(QFont("Arial", 14))
        self.fp_sku_input.setMinimumHeight(50)
        self.fp_sku_input.returnPressed.connect(self._on_fp_sku_scan)
        scan_row.addWidget(self.fp_sku_input)
        
        self.fp_scan_btn = QPushButton("스캔")
        self.fp_scan_btn.setMinimumHeight(50)
        self.fp_scan_btn.setMinimumWidth(80)
        self.fp_scan_btn.clicked.connect(self._on_fp_sku_scan)
        scan_row.addWidget(self.fp_scan_btn)
        
        scan_layout.addLayout(scan_row)
        
        # 현재 SKU 정보
        self.fp_current_sku = QLabel("현재 SKU: -")
        self.fp_current_sku.setFont(QFont("Arial", 12, QFont.Bold))
        scan_layout.addWidget(self.fp_current_sku)
        
        self.fp_total_qty = QLabel("총 수량: 0개")
        self.fp_total_qty.setFont(QFont("Arial", 11))
        scan_layout.addWidget(self.fp_total_qty)
        
        left_layout.addWidget(scan_group)
        
        # 진행 상황
        progress_group = QGroupBox("📈 진행 상황")
        progress_layout = QVBoxLayout(progress_group)
        
        self.fp_progress_label = QLabel("완료: 0 / 0 BIN")
        self.fp_progress_label.setFont(QFont("Arial", 12))
        progress_layout.addWidget(self.fp_progress_label)
        
        self.fp_completed_qty = QLabel("피킹 완료: 0개 / 0개")
        self.fp_completed_qty.setFont(QFont("Arial", 11))
        progress_layout.addWidget(self.fp_completed_qty)
        
        # 취소 버튼
        self.fp_cancel_btn = QPushButton("❌ 현재 SKU 취소")
        self.fp_cancel_btn.setMinimumHeight(40)
        self.fp_cancel_btn.setEnabled(False)
        self.fp_cancel_btn.clicked.connect(self._on_fp_cancel_session)
        progress_layout.addWidget(self.fp_cancel_btn)
        
        left_layout.addWidget(progress_group)
        left_layout.addStretch()
        
        main_splitter.addWidget(left_widget)
        
        # 오른쪽: BIN 목록
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        # ★ 스캔 히스토리 테이블 (최근 스캔 SKU 목록)
        history_group = QGroupBox("📋 스캔 히스토리 (최근 스캔 SKU)")
        history_layout = QVBoxLayout(history_group)
        
        self.fp_scan_history_table = QTableWidget()
        self.fp_scan_history_table.setColumnCount(5)
        self.fp_scan_history_table.setHorizontalHeaderLabels(["SKU 바코드", "총 수량", "BIN 수", "상태", "시간"])
        self.fp_scan_history_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.fp_scan_history_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.fp_scan_history_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.fp_scan_history_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.fp_scan_history_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
        self.fp_scan_history_table.setColumnWidth(1, 70)   # 총 수량
        self.fp_scan_history_table.setColumnWidth(2, 60)   # BIN 수
        self.fp_scan_history_table.setColumnWidth(3, 80)   # 상태
        self.fp_scan_history_table.setColumnWidth(4, 80)   # 시간
        self.fp_scan_history_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.fp_scan_history_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.fp_scan_history_table.setMaximumHeight(150)
        self.fp_scan_history_table.verticalHeader().setDefaultSectionSize(30)
        self.fp_scan_history_table.itemClicked.connect(self._on_fp_history_item_clicked)
        history_layout.addWidget(self.fp_scan_history_table)
        
        # 히스토리 초기화 버튼
        history_btn_row = QHBoxLayout()
        self.fp_clear_history_btn = QPushButton("🗑️ 히스토리 초기화")
        self.fp_clear_history_btn.clicked.connect(self._on_fp_clear_history)
        history_btn_row.addWidget(self.fp_clear_history_btn)
        history_btn_row.addStretch()
        history_layout.addLayout(history_btn_row)
        
        right_layout.addWidget(history_group)
        
        # 스캔 히스토리 데이터 저장용
        self._fp_scan_history = []  # [(barcode, total_qty, bin_count, status, time), ...]
        
        bin_group = QGroupBox("🗃️ BIN 피킹 목록 (현재 SKU)")
        bin_layout = QVBoxLayout(bin_group)
        
        # BIN 테이블
        self.fp_bin_table = QTableWidget()
        self.fp_bin_table.setColumnCount(4)
        self.fp_bin_table.setHorizontalHeaderLabels(["BIN", "수량", "상태", "완료"])
        self.fp_bin_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.fp_bin_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.fp_bin_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.fp_bin_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.fp_bin_table.setColumnWidth(1, 60)   # 수량
        self.fp_bin_table.setColumnWidth(2, 60)   # 상태
        self.fp_bin_table.setColumnWidth(3, 80)   # 완료 버튼
        self.fp_bin_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.fp_bin_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.fp_bin_table.setMinimumHeight(200)
        self.fp_bin_table.verticalHeader().setDefaultSectionSize(40)  # 행 높이
        bin_layout.addWidget(self.fp_bin_table)
        
        # 수동 완료 버튼
        manual_row = QHBoxLayout()
        self.fp_manual_complete_btn = QPushButton("✅ 선택 BIN 수동 완료")
        self.fp_manual_complete_btn.setMinimumHeight(40)
        self.fp_manual_complete_btn.setEnabled(False)
        self.fp_manual_complete_btn.clicked.connect(self._on_fp_manual_complete)
        manual_row.addWidget(self.fp_manual_complete_btn)
        bin_layout.addLayout(manual_row)
        
        right_layout.addWidget(bin_group)
        
        main_splitter.addWidget(right_widget)
        main_splitter.setSizes([400, 500])
        
        layout.addWidget(main_splitter, 1)
        
        # ===== 하단: 로그 =====
        log_group = QGroupBox("📝 로그")
        log_layout = QVBoxLayout(log_group)
        
        self.fp_log = QTextEdit()
        self.fp_log.setReadOnly(True)
        self.fp_log.setMaximumHeight(150)
        self.fp_log.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4; font-family: Consolas;")
        log_layout.addWidget(self.fp_log)
        
        layout.addWidget(log_group)
        
        # ===== ESP32 장치 관리 =====
        device_group = QGroupBox("🔌 ESP32 장치 관리")
        device_group.setMaximumHeight(120)
        device_layout = QHBoxLayout(device_group)
        
        # 연결된 장치 목록
        self.fp_device_list = QListWidget()
        self.fp_device_list.setMaximumHeight(80)
        device_layout.addWidget(self.fp_device_list)
        
        # 장치 관리 버튼
        device_btn_layout = QVBoxLayout()
        self.fp_refresh_devices_btn = QPushButton("새로고침")
        self.fp_refresh_devices_btn.clicked.connect(self._on_fp_refresh_devices)
        device_btn_layout.addWidget(self.fp_refresh_devices_btn)
        
        self.fp_clear_bindings_btn = QPushButton("바인딩 초기화")
        self.fp_clear_bindings_btn.clicked.connect(self._on_fp_clear_bindings)
        device_btn_layout.addWidget(self.fp_clear_bindings_btn)
        
        device_layout.addLayout(device_btn_layout)
        
        layout.addWidget(device_group)
        
        # ===== 시그널 연결 =====
        self._connect_fullpick_signals()
        
        return tab
    
    def _create_prepick_tab(self) -> QWidget:
        """미리피킹 탭 생성"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # ===== 상단 1행: 작업 차수 선택 =====
        session_layout = QHBoxLayout()
        
        # 작업 차수 선택 드롭다운
        session_select_group = QGroupBox("📋 작업 차수 선택")
        session_select_layout = QHBoxLayout(session_select_group)
        
        self.pp_session_combo = QComboBox()
        self.pp_session_combo.setMinimumWidth(300)
        self.pp_session_combo.setFont(QFont("Arial", 12))
        self.pp_session_combo.addItem("-- 출고 탭에서 업체 선택 필요 --", 0)
        self.pp_session_combo.currentIndexChanged.connect(self._on_pp_session_combo_changed)
        session_select_layout.addWidget(self.pp_session_combo)
        
        # 새로고침 버튼 (선택 해제 + 목록 갱신)
        self.pp_refresh_session_btn = QPushButton("🔄")
        self.pp_refresh_session_btn.setMaximumWidth(40)
        self.pp_refresh_session_btn.setToolTip("차수 선택 해제 및 목록 새로고침")
        self.pp_refresh_session_btn.clicked.connect(self._on_refresh_pp_session)
        session_select_layout.addWidget(self.pp_refresh_session_btn)
        
        session_layout.addWidget(session_select_group)
        
        # 현재 선택된 차수 표시
        current_group = QGroupBox("🎯 현재 작업")
        current_layout = QHBoxLayout(current_group)
        self.pp_session_label = QLabel("미선택")
        self.pp_session_label.setFont(QFont("Arial", 14, QFont.Bold))
        self.pp_session_label.setStyleSheet("color: #9C27B0;")
        current_layout.addWidget(self.pp_session_label)
        session_layout.addWidget(current_group)
        
        # 현재 업체 표시
        supplier_group = QGroupBox("🏢 업체")
        supplier_grp_layout = QHBoxLayout(supplier_group)
        self.pp_supplier_label = QLabel("업체 미선택")
        self.pp_supplier_label.setFont(QFont("Arial", 12, QFont.Bold))
        self.pp_supplier_label.setStyleSheet("color: #FF9800;")
        supplier_grp_layout.addWidget(self.pp_supplier_label)
        session_layout.addWidget(supplier_group)
        
        # 데이터 상태
        data_group = QGroupBox("📦 데이터")
        data_grp_layout = QHBoxLayout(data_group)
        self.pp_data_status = QLabel("엑셀 미로드")
        self.pp_data_status.setFont(QFont("Arial", 11))
        data_grp_layout.addWidget(self.pp_data_status)
        session_layout.addWidget(data_group)
        
        layout.addLayout(session_layout)
        
        # ===== 상단 2행: 주문 스캔 영역 =====
        scan_group = QGroupBox("📦 주문 스캔")
        scan_layout = QVBoxLayout(scan_group)
        
        scan_row = QHBoxLayout()
        self.pp_order_input = QLineEdit()
        self.pp_order_input.setPlaceholderText("송장번호 또는 주문번호 스캔/입력")
        self.pp_order_input.setFont(QFont("Arial", 16))
        self.pp_order_input.setMinimumHeight(50)
        self.pp_order_input.returnPressed.connect(self._on_pp_order_scan)
        scan_row.addWidget(self.pp_order_input)
        
        self.pp_scan_btn = QPushButton("스캔")
        self.pp_scan_btn.setMinimumHeight(50)
        self.pp_scan_btn.setMinimumWidth(100)
        self.pp_scan_btn.clicked.connect(self._on_pp_order_scan)
        scan_row.addWidget(self.pp_scan_btn)
        
        scan_layout.addLayout(scan_row)
        
        # 상태 표시 및 설정
        status_row = QHBoxLayout()
        self.pp_status_label = QLabel("주문 스캔 대기...")
        self.pp_status_label.setFont(QFont("Arial", 12))
        self.pp_status_label.setStyleSheet("color: #666;")
        status_row.addWidget(self.pp_status_label)
        status_row.addStretch()
        
        # 슬롯 개수 설정
        status_row.addWidget(QLabel("슬롯 사용:"))
        self.pp_slot_count_combo = QComboBox()
        self.pp_slot_count_combo.addItem("1개 (슬롯1)", 1)
        self.pp_slot_count_combo.addItem("2개 (슬롯1~2)", 2)
        self.pp_slot_count_combo.addItem("3개 (슬롯1~3)", 3)
        self.pp_slot_count_combo.setCurrentIndex(2)  # 기본값: 3개
        self.pp_slot_count_combo.currentIndexChanged.connect(self._on_pp_slot_count_changed)
        self.pp_slot_count_combo.setMinimumWidth(120)
        status_row.addWidget(self.pp_slot_count_combo)
        
        status_row.addWidget(QLabel("  "))  # 구분자
        
        # 완료된 슬롯 정리 버튼
        self.pp_clear_done_btn = QPushButton("완료 슬롯 정리")
        self.pp_clear_done_btn.clicked.connect(self._on_pp_clear_done_slots)
        status_row.addWidget(self.pp_clear_done_btn)
        
        # 전체 초기화 버튼
        self.pp_reset_btn = QPushButton("전체 초기화")
        self.pp_reset_btn.setStyleSheet("background-color: #f44336; color: white;")
        self.pp_reset_btn.clicked.connect(self._on_pp_reset)
        status_row.addWidget(self.pp_reset_btn)
        
        scan_layout.addLayout(status_row)
        layout.addWidget(scan_group)
        
        # ===== 중앙: 슬롯 영역 (3개) =====
        slots_layout = QHBoxLayout()
        
        self.pp_slot_widgets = {}
        self.pp_slot_complete_btns = {}
        self.pp_slot_cancel_btns = {}
        
        for slot_id in [1, 2, 3]:
            slot_widget, complete_btn, cancel_btn = self._create_slot_widget(slot_id)
            slots_layout.addWidget(slot_widget)
            self.pp_slot_widgets[slot_id] = slot_widget
            self.pp_slot_complete_btns[slot_id] = complete_btn
            self.pp_slot_cancel_btns[slot_id] = cancel_btn
        
        # 버튼 클릭 연결 (람다 캡처 문제 방지)
        self.pp_slot_complete_btns[1].clicked.connect(lambda: self._on_pp_slot_complete(1))
        self.pp_slot_complete_btns[2].clicked.connect(lambda: self._on_pp_slot_complete(2))
        self.pp_slot_complete_btns[3].clicked.connect(lambda: self._on_pp_slot_complete(3))
        self.pp_slot_cancel_btns[1].clicked.connect(lambda: self._on_pp_slot_cancel(1))
        self.pp_slot_cancel_btns[2].clicked.connect(lambda: self._on_pp_slot_cancel(2))
        self.pp_slot_cancel_btns[3].clicked.connect(lambda: self._on_pp_slot_cancel(3))
        
        layout.addLayout(slots_layout, 1)
        
        # ===== 하단: 로그 =====
        log_group = QGroupBox("📝 로그")
        log_layout = QVBoxLayout(log_group)
        
        self.pp_log = QTextEdit()
        self.pp_log.setReadOnly(True)
        self.pp_log.setMaximumHeight(120)
        self.pp_log.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4; font-family: Consolas;")
        log_layout.addWidget(self.pp_log)
        
        layout.addWidget(log_group)
        
        # ===== 시그널 연결 =====
        self._connect_prepick_signals()
        
        return tab
    
    def _create_esp32_tab(self) -> QWidget:
        """ESP32 설정 탭 생성 - WebSocket 서버, 장치 관리"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # ===== 1. 서버 설정 섹션 =====
        server_settings_group = QGroupBox("📡 WebSocket 서버 설정")
        server_settings_layout = QVBoxLayout(server_settings_group)
        server_settings_layout.setSpacing(15)
        
        # 포트 설정
        port_row = QHBoxLayout()
        port_row.addWidget(QLabel("서버 포트:"))
        self.esp32_port_input = QSpinBox()
        self.esp32_port_input.setRange(1024, 65535)
        self.esp32_port_input.setValue(8765)
        self.esp32_port_input.setMinimumWidth(100)
        port_row.addWidget(self.esp32_port_input)
        port_row.addWidget(QLabel("(기본: 8765)"))
        port_row.addStretch()
        server_settings_layout.addLayout(port_row)
        
        # 호스트 설정
        host_row = QHBoxLayout()
        host_row.addWidget(QLabel("서버 호스트:"))
        self.esp32_host_input = QLineEdit()
        self.esp32_host_input.setText("0.0.0.0")
        self.esp32_host_input.setMaximumWidth(150)
        self.esp32_host_input.setToolTip("0.0.0.0 = 모든 인터페이스에서 접속 허용")
        host_row.addWidget(self.esp32_host_input)
        host_row.addWidget(QLabel("(0.0.0.0 = 모든 IP)"))
        host_row.addStretch()
        server_settings_layout.addLayout(host_row)
        
        # 설정 저장 버튼
        save_row = QHBoxLayout()
        save_row.addStretch()
        self.esp32_save_settings_btn = QPushButton("💾 설정 저장")
        self.esp32_save_settings_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        self.esp32_save_settings_btn.clicked.connect(self._on_esp32_save_settings)
        save_row.addWidget(self.esp32_save_settings_btn)
        server_settings_layout.addLayout(save_row)
        
        layout.addWidget(server_settings_group)
        
        # ===== 2. 서버 상태 및 제어 섹션 =====
        server_control_group = QGroupBox("🎛️ 서버 제어")
        server_control_layout = QVBoxLayout(server_control_group)
        server_control_layout.setSpacing(15)
        
        # 서버 상태 표시
        status_row = QHBoxLayout()
        status_row.addWidget(QLabel("서버 상태:"))
        self.esp32_server_status = QLabel("⚫ 중지됨")
        self.esp32_server_status.setFont(QFont("Arial", 14, QFont.Bold))
        self.esp32_server_status.setMinimumWidth(200)
        status_row.addWidget(self.esp32_server_status)
        status_row.addStretch()
        server_control_layout.addLayout(status_row)
        
        # 서버 시작/중지 버튼
        btn_row = QHBoxLayout()
        self.esp32_start_btn = QPushButton("▶️ 서버 시작")
        self.esp32_start_btn.setMinimumHeight(50)
        self.esp32_start_btn.setMinimumWidth(150)
        self.esp32_start_btn.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold; font-size: 14px;")
        self.esp32_start_btn.clicked.connect(self._on_esp32_toggle_server)
        btn_row.addWidget(self.esp32_start_btn)
        
        self.esp32_stop_btn = QPushButton("⏹️ 서버 중지")
        self.esp32_stop_btn.setMinimumHeight(50)
        self.esp32_stop_btn.setMinimumWidth(150)
        self.esp32_stop_btn.setStyleSheet("background-color: #f44336; color: white; font-weight: bold; font-size: 14px;")
        self.esp32_stop_btn.clicked.connect(self._on_esp32_stop_server)
        self.esp32_stop_btn.setEnabled(False)
        btn_row.addWidget(self.esp32_stop_btn)
        
        btn_row.addStretch()
        server_control_layout.addLayout(btn_row)
        
        # 연결 정보
        info_row = QHBoxLayout()
        info_row.addWidget(QLabel("연결 정보:"))
        self.esp32_connection_info = QLabel("서버가 시작되면 연결 정보가 표시됩니다")
        self.esp32_connection_info.setStyleSheet("color: #666; padding: 5px; background: #f5f5f5; border-radius: 3px;")
        self.esp32_connection_info.setWordWrap(True)
        info_row.addWidget(self.esp32_connection_info, 1)
        server_control_layout.addLayout(info_row)
        
        layout.addWidget(server_control_group)
        
        # ===== 3. 연결된 장치 목록 섹션 =====
        device_group = QGroupBox("🔌 연결된 ESP32 장치")
        device_layout = QVBoxLayout(device_group)
        device_layout.setSpacing(10)
        
        # 장치 수 표시
        count_row = QHBoxLayout()
        count_row.addWidget(QLabel("연결된 장치:"))
        self.esp32_device_count = QLabel("0대")
        self.esp32_device_count.setFont(QFont("Arial", 14, QFont.Bold))
        self.esp32_device_count.setStyleSheet("color: #4CAF50;")
        count_row.addWidget(self.esp32_device_count)
        count_row.addStretch()
        device_layout.addLayout(count_row)
        
        # 장치 테이블
        self.esp32_device_table = QTableWidget()
        self.esp32_device_table.setColumnCount(4)
        self.esp32_device_table.setHorizontalHeaderLabels(["장치 ID", "BIN 바인딩", "상태", "연결 시간"])
        self.esp32_device_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.esp32_device_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.esp32_device_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.esp32_device_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.esp32_device_table.setColumnWidth(1, 100)
        self.esp32_device_table.setColumnWidth(2, 80)
        self.esp32_device_table.setColumnWidth(3, 120)
        self.esp32_device_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.esp32_device_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.esp32_device_table.setMinimumHeight(200)
        device_layout.addWidget(self.esp32_device_table)
        
        # 장치 관리 버튼
        device_btn_row = QHBoxLayout()
        self.esp32_refresh_btn = QPushButton("🔄 새로고침")
        self.esp32_refresh_btn.clicked.connect(self._on_esp32_refresh_devices)
        device_btn_row.addWidget(self.esp32_refresh_btn)
        
        self.esp32_clear_bindings_btn = QPushButton("🗑️ 바인딩 초기화")
        self.esp32_clear_bindings_btn.clicked.connect(self._on_esp32_clear_bindings)
        device_btn_row.addWidget(self.esp32_clear_bindings_btn)
        
        self.esp32_test_all_btn = QPushButton("🔔 전체 장치 테스트")
        self.esp32_test_all_btn.setToolTip("연결된 모든 장치에 테스트 신호 전송")
        self.esp32_test_all_btn.clicked.connect(self._on_esp32_test_all_devices)
        device_btn_row.addWidget(self.esp32_test_all_btn)
        
        device_btn_row.addStretch()
        device_layout.addLayout(device_btn_row)
        
        layout.addWidget(device_group)
        
        # ===== 4. OTA 펌웨어 업데이트 섹션 =====
        ota_group = QGroupBox("📦 OTA 펌웨어 업데이트 (무선)")
        ota_layout = QVBoxLayout(ota_group)
        
        # 펌웨어 파일 선택
        ota_file_row = QHBoxLayout()
        ota_file_row.addWidget(QLabel("펌웨어 파일:"))
        self.ota_firmware_path = QLineEdit()
        self.ota_firmware_path.setPlaceholderText("firmware.bin 파일 선택...")
        self.ota_firmware_path.setReadOnly(True)
        ota_file_row.addWidget(self.ota_firmware_path, 1)
        
        self.ota_browse_btn = QPushButton("📂 찾아보기")
        self.ota_browse_btn.clicked.connect(self._on_ota_browse_firmware)
        ota_file_row.addWidget(self.ota_browse_btn)
        ota_layout.addLayout(ota_file_row)
        
        # OTA 버튼
        ota_btn_row = QHBoxLayout()
        self.ota_update_all_btn = QPushButton("🚀 전체 장치 업데이트")
        self.ota_update_all_btn.setToolTip("연결된 모든 ESP32에 펌웨어 업데이트")
        self.ota_update_all_btn.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold;")
        self.ota_update_all_btn.clicked.connect(self._on_ota_update_all)
        ota_btn_row.addWidget(self.ota_update_all_btn)
        
        self.ota_reboot_all_btn = QPushButton("🔄 전체 재부팅")
        self.ota_reboot_all_btn.setToolTip("연결된 모든 ESP32 재부팅")
        self.ota_reboot_all_btn.clicked.connect(self._on_ota_reboot_all)
        ota_btn_row.addWidget(self.ota_reboot_all_btn)
        
        ota_btn_row.addStretch()
        
        # 상태 표시
        self.ota_status_label = QLabel("대기 중")
        self.ota_status_label.setStyleSheet("color: #666;")
        ota_btn_row.addWidget(self.ota_status_label)
        
        ota_layout.addLayout(ota_btn_row)
        
        # 안내 메시지
        ota_info = QLabel("💡 펌웨어 파일(.bin)을 선택 후 '전체 장치 업데이트'를 클릭하면\n   연결된 모든 ESP32에 무선으로 펌웨어가 업데이트됩니다.")
        ota_info.setStyleSheet("color: #888; font-size: 11px;")
        ota_layout.addWidget(ota_info)
        
        layout.addWidget(ota_group)
        
        # ===== 5. 서버 로그 섹션 =====
        log_group = QGroupBox("📝 ESP32 서버 로그")
        log_layout = QVBoxLayout(log_group)
        
        self.esp32_log = QTextEdit()
        self.esp32_log.setReadOnly(True)
        self.esp32_log.setMaximumHeight(200)
        self.esp32_log.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4; font-family: Consolas;")
        log_layout.addWidget(self.esp32_log)
        
        # 로그 버튼
        log_btn_row = QHBoxLayout()
        self.esp32_clear_log_btn = QPushButton("🗑️ 로그 지우기")
        self.esp32_clear_log_btn.clicked.connect(lambda: self.esp32_log.clear())
        log_btn_row.addWidget(self.esp32_clear_log_btn)
        log_btn_row.addStretch()
        log_layout.addLayout(log_btn_row)
        
        layout.addWidget(log_group)
        
        # 여백
        layout.addStretch()
        
        # 초기 설정 로드
        QTimer.singleShot(100, self._load_esp32_settings)
        
        # ESP32 시그널 연결
        self._connect_esp32_signals()
        
        return tab
    
    def _load_esp32_settings(self):
        """ESP32 설정 로드"""
        from printer_manager import load_esp32_settings
        settings = load_esp32_settings()
        self.esp32_port_input.setValue(settings.get("port", 8765))
        self.esp32_host_input.setText(settings.get("host", "0.0.0.0"))
    
    def _on_esp32_save_settings(self):
        """ESP32 설정 저장"""
        from printer_manager import save_esp32_settings
        port = self.esp32_port_input.value()
        host = self.esp32_host_input.text().strip() or "0.0.0.0"
        
        if save_esp32_settings(host=host, port=port):
            self._add_esp32_log(f"설정 저장됨 - 호스트: {host}, 포트: {port}")
            QMessageBox.information(self, "저장 완료", f"ESP32 설정이 저장되었습니다.\n\n호스트: {host}\n포트: {port}")
        else:
            QMessageBox.warning(self, "저장 실패", "ESP32 설정 저장에 실패했습니다.")
    
    def _on_esp32_toggle_server(self):
        """ESP32 서버 시작"""
        if not self.esp32_transport.is_running:
            # 설정된 포트 적용
            port = self.esp32_port_input.value()
            host = self.esp32_host_input.text().strip() or "0.0.0.0"
            
            # 서버 설정 업데이트
            self.esp32_transport.host = host
            self.esp32_transport.port = port
            
            if self.esp32_transport.start():
                self._add_esp32_log(f"ESP32 서버 시작 시도... (호스트: {host}, 포트: {port})")
            else:
                self._add_esp32_log("[오류] 서버 시작 실패")
                QMessageBox.warning(self, "오류", "ESP32 서버 시작 실패\nwebsockets 패키지가 설치되어 있는지 확인하세요.")
    
    def _on_esp32_stop_server(self):
        """ESP32 서버 중지"""
        if self.esp32_transport.is_running:
            self.esp32_transport.stop()
    
    def _on_esp32_refresh_devices(self):
        """ESP32 장치 목록 새로고침"""
        self._update_esp32_device_table()
    
    def _on_esp32_clear_bindings(self):
        """ESP32 장치 바인딩 초기화 및 재할당"""
        reply = QMessageBox.question(
            self, "확인", 
            "모든 장치 바인딩을 초기화하고 다시 할당하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            # 1. 기존 바인딩 모두 초기화
            self.device_registry.clear_all_bindings()
            self.device_registry.reset_auto_bind_counter()
            self._add_esp32_log("기존 바인딩 초기화됨")
            
            # 2. 연결된 장치들 순서대로 다시 바인딩
            connected_devices = self.device_registry.get_connected_devices()
            self._add_esp32_log(f"연결된 장치 {len(connected_devices)}대 재바인딩 시작...")
            
            for device in connected_devices:
                device_id = device.device_id
                bin_id = self.device_registry.auto_bind_device(device_id)
                if bin_id:
                    # ESP32에 새 바인딩 전송
                    self.esp32_transport.send_bind(device_id, bin_id)
                    self._add_esp32_log(f"재바인딩: {device_id} → {bin_id}")
                else:
                    self._add_esp32_log(f"[경고] 재바인딩 실패: {device_id}")
            
            self._update_esp32_device_table()
            self._add_esp32_log("바인딩 초기화 완료!")
    
    def _on_esp32_test_all_devices(self):
        """모든 ESP32 장치에 테스트 신호 전송"""
        devices = self.device_registry.get_all_devices()
        if not devices:
            QMessageBox.information(self, "알림", "연결된 장치가 없습니다.")
            return
        
        for device_id in devices:
            # 테스트 LED 깜빡임 명령 전송
            self.esp32_transport.send_command(device_id, {"cmd": "test"})
        
        self._add_esp32_log(f"테스트 신호 전송: {len(devices)}대 장치")
    
    def _add_esp32_log(self, message: str):
        """ESP32 로그 추가"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.esp32_log.append(f"[{timestamp}] {message}")
        # 전체피킹 탭 로그에도 동기화
        if hasattr(self, 'fp_log'):
            self.fp_log.append(f"[{timestamp}] [ESP32] {message}")
    
    # ===== OTA 업데이트 관련 =====
    
    def _on_ota_browse_firmware(self):
        """펌웨어 파일 선택"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "펌웨어 파일 선택",
            "",
            "Binary Files (*.bin);;All Files (*)"
        )
        if file_path:
            self.ota_firmware_path.setText(file_path)
            self._add_esp32_log(f"[OTA] 펌웨어 선택: {file_path}")
    
    def _on_ota_update_all(self):
        """모든 연결된 장치에 OTA 업데이트"""
        firmware_path = self.ota_firmware_path.text().strip()
        
        if not firmware_path:
            QMessageBox.warning(self, "경고", "먼저 펌웨어 파일(.bin)을 선택해주세요.")
            return
        
        if not os.path.exists(firmware_path):
            QMessageBox.warning(self, "경고", "선택한 펌웨어 파일이 존재하지 않습니다.")
            return
        
        connected = self.esp32_transport.get_connected_devices()
        if not connected:
            QMessageBox.warning(self, "경고", "연결된 ESP32 장치가 없습니다.")
            return
        
        reply = QMessageBox.question(
            self, "OTA 업데이트 확인",
            f"연결된 {len(connected)}대 장치에 펌웨어 업데이트를 시작하시겠습니까?\n\n"
            f"파일: {os.path.basename(firmware_path)}\n"
            f"크기: {os.path.getsize(firmware_path):,} bytes\n\n"
            f"⚠️ 업데이트 중 전원을 끄지 마세요!",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        # HTTP 서버 시작하여 펌웨어 제공
        self._start_ota_server(firmware_path, connected)
    
    def _start_ota_server(self, firmware_path: str, devices: list):
        """OTA용 HTTP 서버 시작 및 OTA 명령 전송"""
        import threading
        from http.server import HTTPServer, SimpleHTTPRequestHandler
        import socket
        import shutil
        import tempfile
        import time
        
        self.ota_status_label.setText("서버 준비 중...")
        self._add_esp32_log("[OTA] HTTP 서버 시작 중...")
        
        # PC의 IP 주소 가져오기
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            pc_ip = s.getsockname()[0]
            s.close()
        except:
            pc_ip = "127.0.0.1"
        
        ota_port = 8766  # OTA용 별도 포트
        firmware_url = f"http://{pc_ip}:{ota_port}/firmware.bin"
        
        # 펌웨어 파일을 임시 위치로 복사
        temp_dir = tempfile.mkdtemp()
        temp_firmware = os.path.join(temp_dir, "firmware.bin")
        shutil.copy(firmware_path, temp_firmware)
        
        self._ota_temp_dir = temp_dir  # 나중에 정리용
        
        # 커스텀 핸들러
        class FirmwareHandler(SimpleHTTPRequestHandler):
            def __init__(handler_self, *args, **kwargs):
                super().__init__(*args, directory=temp_dir, **kwargs)
            
            def log_message(handler_self, format, *args):
                pass  # 로그 비활성화
        
        # HTTP 서버 시작 (별도 스레드)
        def run_server():
            try:
                server = HTTPServer((pc_ip, ota_port), FirmwareHandler)
                server.timeout = 5
                
                # 요청 처리 (최대 3분)
                start_time = time.time()
                while time.time() - start_time < 180:
                    server.handle_request()
                
                server.server_close()
            except Exception as e:
                print(f"[OTA] Server error: {e}")
            finally:
                # 임시 파일 정리
                try:
                    shutil.rmtree(temp_dir)
                except:
                    pass
        
        threading.Thread(target=run_server, daemon=True).start()
        
        # 서버 시작 후 잠시 대기
        time.sleep(0.5)
        
        # OTA 명령 전송
        self._add_esp32_log(f"[OTA] 펌웨어 URL: {firmware_url}")
        self.ota_status_label.setText(f"업데이트 중... ({len(devices)}대)")
        
        success = 0
        for device_id in devices:
            if self.esp32_transport.send_ota_update(device_id, firmware_url):
                self._add_esp32_log(f"[OTA] 명령 전송: {device_id}")
                success += 1
            else:
                self._add_esp32_log(f"[OTA] 명령 전송 실패: {device_id}")
        
        self._add_esp32_log(f"[OTA] {success}/{len(devices)}대 장치에 업데이트 명령 전송")
        self.ota_status_label.setText(f"전송 완료 ({success}대)")
        
        QMessageBox.information(
            self, "OTA 업데이트",
            f"OTA 업데이트 명령이 전송되었습니다.\n\n"
            f"전송: {success}/{len(devices)}대\n\n"
            f"ESP32 화면에서 업데이트 진행 상황을 확인하세요.\n"
            f"업데이트 완료 후 자동으로 재부팅됩니다."
        )
    
    def _on_ota_reboot_all(self):
        """모든 장치 재부팅"""
        connected = self.esp32_transport.get_connected_devices()
        if not connected:
            QMessageBox.warning(self, "경고", "연결된 ESP32 장치가 없습니다.")
            return
        
        reply = QMessageBox.question(
            self, "재부팅 확인",
            f"연결된 {len(connected)}대 장치를 재부팅하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            count = self.esp32_transport.send_reboot_all()
            self._add_esp32_log(f"[Reboot] {count}대 장치에 재부팅 명령 전송")
            QMessageBox.information(self, "재부팅", f"{count}대 장치에 재부팅 명령을 전송했습니다.")
    
    def _update_esp32_device_table(self):
        """ESP32 장치 테이블 업데이트"""
        devices = self.device_registry.get_all_devices()
        
        self.esp32_device_table.setRowCount(len(devices))
        self.esp32_device_count.setText(f"{len(devices)}대")
        
        for row, device in enumerate(devices):
            # 장치 ID
            self.esp32_device_table.setItem(row, 0, QTableWidgetItem(device.device_id))
            
            # BIN 바인딩
            bin_id = device.bin_id or "미할당"
            self.esp32_device_table.setItem(row, 1, QTableWidgetItem(bin_id))
            
            # 상태
            status = "🟢 연결됨" if device.connected else "🔴 연결 끊김"
            self.esp32_device_table.setItem(row, 2, QTableWidgetItem(status))
            
            # 연결 시간
            if device.last_seen:
                time_str = device.last_seen.strftime("%H:%M:%S")
            else:
                time_str = "-"
            self.esp32_device_table.setItem(row, 3, QTableWidgetItem(time_str))
        
        # 전체피킹 탭 장치 수 동기화
        if hasattr(self, 'fp_device_count'):
            self.fp_device_count.setText(f"연결: {len(devices)}대")
    
    def _connect_esp32_signals(self):
        """ESP32 탭 시그널 연결"""
        # ESP32 서버 시그널
        self.esp32_transport.device_hello.connect(self._on_esp32_device_hello)
        self.esp32_transport.device_disconnected.connect(self._on_esp32_device_disconnected)
        self.esp32_transport.server_started.connect(self._on_esp32_server_started)
        self.esp32_transport.server_stopped.connect(self._on_esp32_server_stopped)
    
    @Slot(str)
    def _on_esp32_device_hello(self, device_id: str):
        """ESP32 장치 연결 (ESP32 탭용) - 자동 바인딩 포함"""
        self._add_esp32_log(f"장치 연결: {device_id}")
        
        # 장치 등록
        self.device_registry.register_device(device_id)
        
        # 자동 바인딩
        bin_id = self.device_registry.auto_bind_device(device_id)
        if bin_id:
            # 바인딩 명령 전송 (ESP32에 BIN 번호 알림)
            self.esp32_transport.send_bind(device_id, bin_id)
            self._add_esp32_log(f"자동 바인딩: {device_id} → {bin_id}")
        else:
            self._add_esp32_log(f"[경고] 자동 바인딩 실패: {device_id}")
        
        self._update_esp32_device_table()
    
    @Slot(str)
    def _on_esp32_device_disconnected(self, device_id: str):
        """ESP32 장치 연결 해제 (ESP32 탭용)"""
        self._add_esp32_log(f"장치 연결 해제: {device_id}")
        self._update_esp32_device_table()
    
    @Slot(int)
    def _on_esp32_server_started(self, port: int):
        """ESP32 서버 시작됨 (ESP32 탭용)"""
        self.esp32_server_status.setText(f"🟢 실행중 (포트: {port})")
        self.esp32_server_status.setStyleSheet("color: green; font-weight: bold;")
        self.esp32_start_btn.setEnabled(False)
        self.esp32_stop_btn.setEnabled(True)
        
        # 연결 정보 업데이트
        import socket
        try:
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
        except:
            local_ip = "알 수 없음"
        
        self.esp32_connection_info.setText(
            f"ESP32 펌웨어에서 다음 주소로 연결:\n"
            f"ws://{local_ip}:{port}"
        )
        self.esp32_connection_info.setStyleSheet("color: #2196F3; padding: 10px; background: #E3F2FD; border-radius: 5px; font-weight: bold;")
        
        self._add_esp32_log(f"서버 시작됨 - ws://{local_ip}:{port}")
        
        # 전체피킹 탭 동기화
        if hasattr(self, 'fp_server_status'):
            self.fp_server_status.setText(f"🟢 실행중 (:{port})")
            self.fp_server_status.setStyleSheet("color: green;")
    
    @Slot()
    def _on_esp32_server_stopped(self):
        """ESP32 서버 중지됨 (ESP32 탭용)"""
        self.esp32_server_status.setText("⚫ 중지됨")
        self.esp32_server_status.setStyleSheet("color: gray;")
        self.esp32_start_btn.setEnabled(True)
        self.esp32_stop_btn.setEnabled(False)
        
        self.esp32_connection_info.setText("서버가 시작되면 연결 정보가 표시됩니다")
        self.esp32_connection_info.setStyleSheet("color: #666; padding: 5px; background: #f5f5f5; border-radius: 3px;")
        
        self._add_esp32_log("서버 중지됨")
        
        # 전체피킹 탭 동기화
        if hasattr(self, 'fp_server_status'):
            self.fp_server_status.setText("⚫ 중지됨")
            self.fp_server_status.setStyleSheet("color: gray;")
    
    def _create_settings_tab(self) -> QWidget:
        """설정 탭 생성 - 데이터 업로드, 프린터 설정, BIN 설정, 저장 위치 등"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # 스크롤 영역 (설정이 많아질 경우 대비)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(20)
        
        # ===== 1. 데이터 업로드 섹션 =====
        upload_group = QGroupBox("📁 데이터 업로드")
        upload_layout = QVBoxLayout(upload_group)
        upload_layout.setSpacing(15)
        
        # 엑셀 파일 업로드
        excel_row = QHBoxLayout()
        excel_row.addWidget(QLabel("📊 엑셀 파일:"))
        self.settings_excel_path = QLineEdit()
        self.settings_excel_path.setPlaceholderText("주문 엑셀 파일 선택 (.xlsx)")
        self.settings_excel_path.setReadOnly(True)
        excel_row.addWidget(self.settings_excel_path, 1)
        self.settings_excel_browse_btn = QPushButton("찾아보기")
        self.settings_excel_browse_btn.clicked.connect(self._on_settings_browse_excel)
        excel_row.addWidget(self.settings_excel_browse_btn)
        self.settings_excel_load_btn = QPushButton("불러오기")
        self.settings_excel_load_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        self.settings_excel_load_btn.clicked.connect(self._on_settings_load_excel)
        excel_row.addWidget(self.settings_excel_load_btn)
        upload_layout.addLayout(excel_row)
        
        # 송장(라벨) PDF 업로드
        label_pdf_row = QHBoxLayout()
        label_pdf_row.addWidget(QLabel("🏷️ 송장 PDF:"))
        self.settings_label_pdf_path = QLineEdit()
        self.settings_label_pdf_path.setPlaceholderText("송장(라벨) PDF 파일 선택")
        self.settings_label_pdf_path.setReadOnly(True)
        label_pdf_row.addWidget(self.settings_label_pdf_path, 1)
        self.settings_label_pdf_btn = QPushButton("파일 선택")
        self.settings_label_pdf_btn.clicked.connect(self._on_settings_browse_label_pdf)
        label_pdf_row.addWidget(self.settings_label_pdf_btn)
        upload_layout.addLayout(label_pdf_row)
        
        # 주문서(A4) PDF 업로드
        order_pdf_row = QHBoxLayout()
        order_pdf_row.addWidget(QLabel("📄 주문서 PDF:"))
        self.settings_order_pdf_path = QLineEdit()
        self.settings_order_pdf_path.setPlaceholderText("주문서(A4) PDF 파일 선택")
        self.settings_order_pdf_path.setReadOnly(True)
        order_pdf_row.addWidget(self.settings_order_pdf_path, 1)
        self.settings_order_pdf_btn = QPushButton("파일 선택")
        self.settings_order_pdf_btn.clicked.connect(self._on_settings_browse_order_pdf)
        order_pdf_row.addWidget(self.settings_order_pdf_btn)
        upload_layout.addLayout(order_pdf_row)
        
        scroll_layout.addWidget(upload_group)
        
        # ===== 2. 차수 관리 섹션 =====
        session_group = QGroupBox("📋 차수 관리")
        session_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #3F51B5;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 15px;
                background-color: #E8EAF6;
            }
            QGroupBox::title {
                color: #3F51B5;
            }
        """)
        session_layout = QVBoxLayout(session_group)
        session_layout.setSpacing(15)
        
        # 설명
        session_desc = QLabel(
            "엑셀 로드 후 업체를 선택하여 작업 차수를 생성합니다.\n"
            "여러 업체를 선택하면 동일한 BIN 시스템을 공유합니다."
        )
        session_desc.setStyleSheet("color: #555; padding: 5px; background: white; border-radius: 3px;")
        session_desc.setWordWrap(True)
        session_layout.addWidget(session_desc)
        
        # 업체 선택 영역 (체크박스 리스트)
        supplier_label = QLabel("🏢 업체 선택 (다중 선택 가능):")
        session_layout.addWidget(supplier_label)
        
        self.settings_supplier_list = QListWidget()
        self.settings_supplier_list.setMaximumHeight(120)
        self.settings_supplier_list.setStyleSheet("""
            QListWidget {
                background-color: white;
                border: 1px solid #ccc;
                border-radius: 4px;
            }
            QListWidget::item {
                padding: 5px;
            }
        """)
        session_layout.addWidget(self.settings_supplier_list)
        
        # 전체 선택/해제 + 차수 생성 버튼
        supplier_btn_row = QHBoxLayout()
        
        self.settings_select_all_btn = QPushButton("✅ 전체 선택")
        self.settings_select_all_btn.clicked.connect(self._on_settings_select_all_suppliers)
        supplier_btn_row.addWidget(self.settings_select_all_btn)
        
        self.settings_deselect_all_btn = QPushButton("⬜ 전체 해제")
        self.settings_deselect_all_btn.clicked.connect(self._on_settings_deselect_all_suppliers)
        supplier_btn_row.addWidget(self.settings_deselect_all_btn)
        
        supplier_btn_row.addStretch()
        
        self.settings_create_session_btn = QPushButton("✅ 차수 생성")
        self.settings_create_session_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        self.settings_create_session_btn.clicked.connect(self._on_settings_create_session)
        self.settings_create_session_btn.setEnabled(False)
        supplier_btn_row.addWidget(self.settings_create_session_btn)
        
        session_layout.addLayout(supplier_btn_row)
        
        # 호환성을 위한 숨김 콤보박스
        self.settings_supplier_combo = QComboBox()
        self.settings_supplier_combo.hide()
        
        # 생성된 차수 목록
        session_list_label = QLabel("📝 생성된 차수 목록:")
        session_layout.addWidget(session_list_label)
        
        self.settings_session_list = QListWidget()
        self.settings_session_list.setMaximumHeight(150)
        self.settings_session_list.setStyleSheet("""
            QListWidget {
                background-color: white;
                border: 1px solid #ccc;
                border-radius: 4px;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #eee;
            }
            QListWidget::item:selected {
                background-color: #E3F2FD;
                color: #1976D2;
            }
        """)
        session_layout.addWidget(self.settings_session_list)
        
        # 차수 관리 버튼들
        session_btn_row = QHBoxLayout()
        
        self.settings_delete_session_btn = QPushButton("🗑️ 선택 차수 삭제")
        self.settings_delete_session_btn.clicked.connect(self._on_settings_delete_session)
        session_btn_row.addWidget(self.settings_delete_session_btn)
        
        self.settings_clear_sessions_btn = QPushButton("🔄 전체 초기화")
        self.settings_clear_sessions_btn.setStyleSheet("background-color: #f44336; color: white;")
        self.settings_clear_sessions_btn.clicked.connect(self._on_settings_clear_sessions)
        session_btn_row.addWidget(self.settings_clear_sessions_btn)
        
        session_btn_row.addStretch()
        session_layout.addLayout(session_btn_row)
        
        scroll_layout.addWidget(session_group)
        
        # ===== 3. BIN 설정 섹션 =====
        bin_group = QGroupBox("🗃️ BIN 설정")
        bin_layout = QVBoxLayout(bin_group)
        bin_layout.setSpacing(15)
        
        # BIN당 최대 수량
        max_qty_row = QHBoxLayout()
        max_qty_row.addWidget(QLabel("BIN당 최대 수량:"))
        self.settings_bin_max_qty = QSpinBox()
        self.settings_bin_max_qty.setRange(1, 9999)
        self.settings_bin_max_qty.setValue(100)
        self.settings_bin_max_qty.setSuffix(" 개")
        max_qty_row.addWidget(self.settings_bin_max_qty)
        max_qty_row.addWidget(QLabel("(초과 시 다음 BIN으로 분산)"))
        max_qty_row.addStretch()
        bin_layout.addLayout(max_qty_row)
        
        # 소량 SKU 기준
        min_qty_row = QHBoxLayout()
        min_qty_row.addWidget(QLabel("소량 SKU 기준:"))
        self.settings_bin_min_qty = QSpinBox()
        self.settings_bin_min_qty.setRange(0, 9999)
        self.settings_bin_min_qty.setValue(10)
        self.settings_bin_min_qty.setSuffix(" 개 이하")
        min_qty_row.addWidget(self.settings_bin_min_qty)
        min_qty_row.addWidget(QLabel("(이하면 공유 BIN 배정)"))
        min_qty_row.addStretch()
        bin_layout.addLayout(min_qty_row)
        
        # 공유 BIN 최대 SKU
        max_sku_row = QHBoxLayout()
        max_sku_row.addWidget(QLabel("공유 BIN 최대 SKU:"))
        self.settings_bin_max_sku = QSpinBox()
        self.settings_bin_max_sku.setRange(1, 99)
        self.settings_bin_max_sku.setValue(5)
        self.settings_bin_max_sku.setSuffix(" 종류")
        max_sku_row.addWidget(self.settings_bin_max_sku)
        max_sku_row.addWidget(QLabel("(공유 BIN에 묶을 최대 SKU 수)"))
        max_sku_row.addStretch()
        bin_layout.addLayout(max_sku_row)
        
        # 중복금지 수량 (전용 BIN 임계값)
        dedicated_qty_row = QHBoxLayout()
        dedicated_qty_row.addWidget(QLabel("중복금지 수량:"))
        self.settings_bin_dedicated_qty = QSpinBox()
        self.settings_bin_dedicated_qty.setRange(0, 9999)
        self.settings_bin_dedicated_qty.setValue(0)
        self.settings_bin_dedicated_qty.setSuffix(" 개 이상")
        dedicated_qty_row.addWidget(self.settings_bin_dedicated_qty)
        dedicated_qty_row.addWidget(QLabel("(이상이면 전용 BIN, 0=비활성)"))
        dedicated_qty_row.addStretch()
        bin_layout.addLayout(dedicated_qty_row)
        
        # BIN 설정 저장 버튼
        bin_btn_row = QHBoxLayout()
        bin_btn_row.addStretch()
        self.settings_bin_save_btn = QPushButton("BIN 설정 저장")
        self.settings_bin_save_btn.clicked.connect(self._on_settings_save_bin)
        bin_btn_row.addWidget(self.settings_bin_save_btn)
        bin_layout.addLayout(bin_btn_row)
        
        scroll_layout.addWidget(bin_group)
        
        # ===== 4. 저장 위치 / 피킹리스트 차수 섹션 =====
        path_group = QGroupBox("📂 저장 위치 / 피킹리스트")
        path_layout = QVBoxLayout(path_group)
        path_layout.setSpacing(15)
        
        # 저장 위치
        save_path_row = QHBoxLayout()
        save_path_row.addWidget(QLabel("저장 위치:"))
        self.settings_save_path = QLineEdit()
        self.settings_save_path.setPlaceholderText("엑셀/PDF 저장 위치 선택")
        save_path_row.addWidget(self.settings_save_path, 1)
        self.settings_save_path_btn = QPushButton("위치 선택")
        self.settings_save_path_btn.clicked.connect(self._on_settings_browse_save_path)
        save_path_row.addWidget(self.settings_save_path_btn)
        path_layout.addLayout(save_path_row)
        
        # 피킹리스트 차수 선택
        picking_session_row = QHBoxLayout()
        picking_session_row.addWidget(QLabel("📋 피킹리스트 차수:"))
        self.settings_picking_session_combo = QComboBox()
        self.settings_picking_session_combo.setMinimumWidth(250)
        self.settings_picking_session_combo.addItem("-- 차수 선택 --", 0)
        picking_session_row.addWidget(self.settings_picking_session_combo, 1)
        
        self.settings_refresh_picking_combo_btn = QPushButton("🔄")
        self.settings_refresh_picking_combo_btn.setMaximumWidth(40)
        self.settings_refresh_picking_combo_btn.setToolTip("차수 목록 새로고침")
        self.settings_refresh_picking_combo_btn.clicked.connect(self._update_settings_picking_session_combo)
        picking_session_row.addWidget(self.settings_refresh_picking_combo_btn)
        path_layout.addLayout(picking_session_row)
        
        # 피킹리스트 관련 버튼
        picking_row = QHBoxLayout()
        self.settings_save_excel_btn = QPushButton("📊 엑셀 저장")
        self.settings_save_excel_btn.clicked.connect(self._on_settings_save_excel)
        picking_row.addWidget(self.settings_save_excel_btn)
        
        self.settings_save_pdf_btn = QPushButton("📄 피킹리스트 PDF 저장")
        self.settings_save_pdf_btn.clicked.connect(self._on_settings_save_pdf)
        picking_row.addWidget(self.settings_save_pdf_btn)
        
        self.settings_open_pdf_btn = QPushButton("📂 피킹리스트 열기")
        self.settings_open_pdf_btn.clicked.connect(self._on_settings_open_pdf)
        self.settings_open_pdf_btn.setEnabled(False)
        picking_row.addWidget(self.settings_open_pdf_btn)
        
        picking_row.addStretch()
        path_layout.addLayout(picking_row)
        
        # 저장된 피킹리스트 목록
        saved_pdf_label = QLabel("📁 저장된 피킹리스트:")
        path_layout.addWidget(saved_pdf_label)
        
        self.settings_saved_pdf_list = QListWidget()
        self.settings_saved_pdf_list.setMaximumHeight(100)
        self.settings_saved_pdf_list.setStyleSheet("""
            QListWidget {
                background-color: white;
                border: 1px solid #ccc;
                border-radius: 4px;
            }
            QListWidget::item {
                padding: 5px;
            }
            QListWidget::item:selected {
                background-color: #E3F2FD;
            }
        """)
        self.settings_saved_pdf_list.itemDoubleClicked.connect(self._on_settings_open_saved_pdf)
        path_layout.addWidget(self.settings_saved_pdf_list)
        
        scroll_layout.addWidget(path_group)
        
        # ===== 5. 프린터 설정 섹션 =====
        printer_group = QGroupBox("🖨️ 프린터 설정")
        printer_layout = QVBoxLayout(printer_group)
        printer_layout.setSpacing(15)
        
        # 라벨 프린터
        label_printer_row = QHBoxLayout()
        label_printer_row.addWidget(QLabel("라벨 프린터:"))
        self.settings_label_printer = QComboBox()
        self.settings_label_printer.setMinimumWidth(250)
        label_printer_row.addWidget(self.settings_label_printer, 1)
        self.settings_label_test_btn = QPushButton("테스트 출력")
        self.settings_label_test_btn.clicked.connect(self._on_settings_test_label_printer)
        label_printer_row.addWidget(self.settings_label_test_btn)
        printer_layout.addLayout(label_printer_row)
        
        # A4 프린터
        a4_printer_row = QHBoxLayout()
        a4_printer_row.addWidget(QLabel("A4 프린터:"))
        self.settings_a4_printer = QComboBox()
        self.settings_a4_printer.setMinimumWidth(250)
        a4_printer_row.addWidget(self.settings_a4_printer, 1)
        self.settings_a4_test_btn = QPushButton("테스트 출력")
        self.settings_a4_test_btn.clicked.connect(self._on_settings_test_a4_printer)
        a4_printer_row.addWidget(self.settings_a4_test_btn)
        printer_layout.addLayout(a4_printer_row)
        
        # 회전 설정
        rotation_row = QHBoxLayout()
        rotation_row.addWidget(QLabel("송장 회전:"))
        self.settings_rotation = QComboBox()
        self.settings_rotation.addItems(["0°", "90°", "180°", "270°"])
        self.settings_rotation.setMaximumWidth(100)
        self.settings_rotation.currentIndexChanged.connect(self._on_settings_rotation_changed)
        rotation_row.addWidget(self.settings_rotation)
        rotation_row.addStretch()
        printer_layout.addLayout(rotation_row)
        
        # 프린터 저장 버튼
        printer_btn_row = QHBoxLayout()
        printer_btn_row.addStretch()
        self.settings_refresh_printers_btn = QPushButton("🔄 새로고침")
        self.settings_refresh_printers_btn.clicked.connect(self._on_settings_refresh_printers)
        printer_btn_row.addWidget(self.settings_refresh_printers_btn)
        
        self.settings_save_printers_btn = QPushButton("💾 프린터 설정 저장")
        self.settings_save_printers_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        self.settings_save_printers_btn.clicked.connect(self._on_settings_save_printers)
        printer_btn_row.addWidget(self.settings_save_printers_btn)
        printer_layout.addLayout(printer_btn_row)
        
        scroll_layout.addWidget(printer_group)
        
        # ===== 6. 출력 옵션 섹션 =====
        output_group = QGroupBox("⚙️ 출력 옵션")
        output_layout = QVBoxLayout(output_group)
        output_layout.setSpacing(10)
        
        # 첫 번째 줄: EzAuto 관련
        ezauto_row = QHBoxLayout()
        ezauto_row.addWidget(QLabel("EzAuto 창 제목:"))
        self.settings_ezauto_title = QLineEdit()
        self.settings_ezauto_title.setText("이지오토")
        self.settings_ezauto_title.setMaximumWidth(100)
        self.settings_ezauto_title.textChanged.connect(self._on_settings_ezauto_title_changed)
        ezauto_row.addWidget(self.settings_ezauto_title)
        ezauto_row.addSpacing(20)
        
        self.settings_ezauto_check = QCheckBox("EzAuto 입력")
        self.settings_ezauto_check.setChecked(True)
        self.settings_ezauto_check.setToolTip("체크 시 스캔된 바코드를 EzAuto 프로그램에 자동 입력합니다")
        self.settings_ezauto_check.toggled.connect(self._on_settings_toggle_ezauto)
        ezauto_row.addWidget(self.settings_ezauto_check)
        ezauto_row.addStretch()
        output_layout.addLayout(ezauto_row)
        
        # 두 번째 줄: PDF 출력 관련
        pdf_row = QHBoxLayout()
        self.settings_pdf_check = QCheckBox("송장(라벨) PDF 출력")
        self.settings_pdf_check.setChecked(True)
        self.settings_pdf_check.setToolTip("체크 해제 시 송장 PDF가 출력되지 않습니다 (EzAuto 입력만 할 때 사용)")
        self.settings_pdf_check.toggled.connect(self._on_settings_toggle_pdf)
        pdf_row.addWidget(self.settings_pdf_check)
        pdf_row.addSpacing(20)
        
        self.settings_order_sheet_check = QCheckBox("주문서(A4) 동시 출력")
        self.settings_order_sheet_check.setChecked(False)
        self.settings_order_sheet_check.setToolTip("체크 시 송장과 함께 주문서 PDF를 A4 프린터로 출력합니다")
        self.settings_order_sheet_check.toggled.connect(self._on_settings_toggle_order_sheet)
        pdf_row.addWidget(self.settings_order_sheet_check)
        pdf_row.addStretch()
        output_layout.addLayout(pdf_row)
        
        # 세 번째 줄: 임시 파일 보관
        temp_row = QHBoxLayout()
        self.settings_keep_temp_check = QCheckBox("임시 파일 보관")
        self.settings_keep_temp_check.setChecked(False)
        self.settings_keep_temp_check.setToolTip("체크 시 출력 후 추출된 PDF 임시 파일을 삭제하지 않고 보관합니다")
        self.settings_keep_temp_check.toggled.connect(self._on_settings_toggle_keep_temp)
        temp_row.addWidget(self.settings_keep_temp_check)
        temp_row.addStretch()
        output_layout.addLayout(temp_row)
        
        scroll_layout.addWidget(output_group)
        
        # 여백
        scroll_layout.addStretch()
        
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)
        
        # 프린터 목록 로드
        QTimer.singleShot(100, self._load_settings_tab_data)
        
        return tab
    
    def _load_settings_tab_data(self):
        """설정 탭 초기 데이터 로드"""
        # 프린터 목록 로드
        printers = get_printers()
        self.settings_label_printer.clear()
        self.settings_a4_printer.clear()
        for printer in printers:
            self.settings_label_printer.addItem(printer)
            self.settings_a4_printer.addItem(printer)
        
        # 저장된 프린터 설정 로드
        settings = load_printer_settings()
        if settings.get("label_printer"):
            idx = self.settings_label_printer.findText(settings["label_printer"])
            if idx >= 0:
                self.settings_label_printer.setCurrentIndex(idx)
        if settings.get("a4_printer"):
            idx = self.settings_a4_printer.findText(settings["a4_printer"])
            if idx >= 0:
                self.settings_a4_printer.setCurrentIndex(idx)
        
        # 회전 설정 로드 (load_label_rotation 사용)
        from printer_manager import load_label_rotation
        rotation = load_label_rotation()
        rotation_idx = rotation // 90
        if 0 <= rotation_idx < 4:
            self.settings_rotation.blockSignals(True)
            self.settings_rotation.setCurrentIndex(rotation_idx)
            self.settings_rotation.blockSignals(False)
        
        # BIN 설정 로드
        bin_settings = load_bin_settings()
        self.settings_bin_max_qty.setValue(bin_settings.get("max_qty_per_bin", 100))
        self.settings_bin_min_qty.setValue(bin_settings.get("min_qty_threshold", 10))
        self.settings_bin_max_sku.setValue(bin_settings.get("max_sku_per_shared_bin", 5))
        self.settings_bin_dedicated_qty.setValue(bin_settings.get("dedicated_qty_threshold", 0))
        
        # 저장 경로 로드
        save_path = settings.get("save_path", "")
        if save_path:
            self.settings_save_path.setText(save_path)
        
        # 피킹리스트 차수 콤보박스 업데이트
        self._update_settings_picking_session_combo()
    
    # ===== 설정 탭 이벤트 핸들러 =====
    
    def _on_settings_browse_excel(self):
        """설정 탭 - 엑셀 파일 찾아보기"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "엑셀 파일 선택", "", "Excel Files (*.xlsx *.xls)"
        )
        if file_path:
            self.settings_excel_path.setText(file_path)
            # 출고 탭에도 동기화
            self.excel_path_edit.setText(file_path)
    
    def _on_settings_load_excel(self):
        """설정 탭 - 엑셀 파일 불러오기"""
        file_path = self.settings_excel_path.text()
        if not file_path:
            QMessageBox.warning(self, "경고", "먼저 엑셀 파일을 선택하세요.")
            return
        # 출고 탭의 로드 함수 호출
        self.excel_path_edit.setText(file_path)
        self._on_load_excel()
    
    def _on_settings_browse_label_pdf(self):
        """설정 탭 - 송장 PDF 파일 선택"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "송장 PDF 파일 선택", "", "PDF Files (*.pdf)"
        )
        if file_path:
            self.settings_label_pdf_path.setText(file_path)
            # 출고 탭에도 동기화
            self.pdf_path_edit.setText(file_path)
            
            # ★ PDF 인덱스 생성 (송장번호 매핑)
            self._add_log("PDF 스캔 중...")
            self.pdf_printer.set_pdf_file(file_path)
            
            # 엑셀에서 송장번호 목록 가져오기
            excel_tracking_numbers = None
            if self.excel_loader.df is not None:
                excel_tracking_numbers = self.excel_loader.df['tracking_no'].astype(str).tolist()
            
            count = self.pdf_printer.build_tracking_index(excel_tracking_numbers)
            self._add_log(f"✓ PDF 스캔 완료: {count}개 송장번호 발견")
    
    def _on_settings_browse_order_pdf(self):
        """설정 탭 - 주문서 PDF 파일 선택"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "주문서 PDF 파일 선택", "", "PDF Files (*.pdf)"
        )
        if file_path:
            self.settings_order_pdf_path.setText(file_path)
            # 출고 탭에도 동기화
            self.pdf_path_2_edit.setText(file_path)
            # 주문서 출력 체크박스 활성화
            self.order_sheet_check.setChecked(True)
    
    def _on_settings_test_label_printer(self):
        """설정 탭 - 라벨 프린터 테스트"""
        # 설정 탭의 콤보박스에서 프린터 이름 가져오기
        printer_name = self.settings_label_printer.currentText()
        if not printer_name or printer_name == "프린터 없음" or printer_name == "(선택 안함)":
            QMessageBox.warning(self, "경고", "라벨 프린터를 먼저 선택해주세요.")
            return
        self._on_test_label_printer(printer_name)
    
    def _on_settings_test_a4_printer(self):
        """설정 탭 - A4 프린터 테스트"""
        # 설정 탭의 콤보박스에서 프린터 이름 가져오기
        printer_name = self.settings_a4_printer.currentText()
        if not printer_name or printer_name == "프린터 없음" or printer_name == "(선택 안함)":
            QMessageBox.warning(self, "경고", "A4 프린터를 먼저 선택해주세요.")
            return
        self._on_test_a4_printer(printer_name)
    
    def _on_settings_rotation_changed(self, index: int):
        """설정 탭 - 회전 설정 변경"""
        from printer_manager import save_label_rotation
        rotation = index * 90
        if save_label_rotation(rotation):
            self._add_log(f"송장 회전 설정 변경: {rotation}°")
        # 출고 탭 회전 콤보박스 동기화
        if hasattr(self, 'rotation_combo'):
            self.rotation_combo.blockSignals(True)
            self.rotation_combo.setCurrentIndex(index)
            self.rotation_combo.blockSignals(False)
    
    def _on_settings_save_printers(self):
        """설정 탭 - 프린터 설정 저장"""
        label_printer = self.settings_label_printer.currentText()
        a4_printer = self.settings_a4_printer.currentText()
        
        if not label_printer or label_printer == "프린터 없음":
            label_printer = None
        if not a4_printer or a4_printer == "프린터 없음":
            a4_printer = None
        
        if save_printer_settings(label_printer, a4_printer):
            self._add_log(f"프린터 설정 저장됨 - 라벨: {label_printer or '없음'}, A4: {a4_printer or '없음'}")
            QMessageBox.information(self, "저장 완료", f"프린터 설정이 저장되었습니다.\n\n라벨 프린터: {label_printer or '(선택 안함)'}\nA4 프린터: {a4_printer or '(선택 안함)'}")
            
            # 출고 탭 프린터 콤보박스도 동기화
            self._load_printer_settings_to_ui()
        else:
            QMessageBox.warning(self, "저장 실패", "프린터 설정 저장에 실패했습니다.")
    
    def _on_settings_refresh_printers(self):
        """설정 탭 - 프린터 목록 새로고침"""
        printers = get_printers()
        
        # 현재 선택 저장
        current_label = self.settings_label_printer.currentText()
        current_a4 = self.settings_a4_printer.currentText()
        
        # 콤보박스 갱신
        self.settings_label_printer.clear()
        self.settings_a4_printer.clear()
        for printer in printers:
            self.settings_label_printer.addItem(printer)
            self.settings_a4_printer.addItem(printer)
        
        # 이전 선택 복원
        idx = self.settings_label_printer.findText(current_label)
        if idx >= 0:
            self.settings_label_printer.setCurrentIndex(idx)
        idx = self.settings_a4_printer.findText(current_a4)
        if idx >= 0:
            self.settings_a4_printer.setCurrentIndex(idx)
        
        # 출고 탭 프린터 콤보박스도 동기화
        self._refresh_printer_combos()
        
        QMessageBox.information(self, "프린터", f"프린터 목록을 새로고침했습니다.\n총 {len(printers)}개 프린터 발견")
    
    # ===== 출력 옵션 핸들러 =====
    
    def _on_settings_ezauto_title_changed(self, title: str):
        """설정 탭 - EzAuto 창 제목 변경"""
        self.ezauto.set_window_title(title)
        # 출고 탭과 동기화
        if hasattr(self, 'ezauto_title_edit'):
            self.ezauto_title_edit.blockSignals(True)
            self.ezauto_title_edit.setText(title)
            self.ezauto_title_edit.blockSignals(False)
    
    def _on_settings_toggle_ezauto(self, checked: bool):
        """설정 탭 - EzAuto 입력 활성화/비활성화"""
        self.ezauto.enabled = checked
        # 출고 탭과 동기화
        if hasattr(self, 'ezauto_check'):
            self.ezauto_check.blockSignals(True)
            self.ezauto_check.setChecked(checked)
            self.ezauto_check.blockSignals(False)
        self._add_log(f"EzAuto 입력: {'활성' if checked else '비활성'}")
    
    def _on_settings_toggle_pdf(self, checked: bool):
        """설정 탭 - PDF 출력 활성화/비활성화"""
        self.pdf_printer.enabled = checked
        # 출고 탭과 동기화
        if hasattr(self, 'pdf_check'):
            self.pdf_check.blockSignals(True)
            self.pdf_check.setChecked(checked)
            self.pdf_check.blockSignals(False)
        self._add_log(f"송장 PDF 출력: {'활성' if checked else '비활성'}")
    
    def _on_settings_toggle_order_sheet(self, checked: bool):
        """설정 탭 - 주문서 출력 활성화/비활성화"""
        self.pdf_printer.order_sheet_enabled = checked
        # 출고 탭과 동기화
        if hasattr(self, 'order_sheet_check'):
            self.order_sheet_check.blockSignals(True)
            self.order_sheet_check.setChecked(checked)
            self.order_sheet_check.blockSignals(False)
        
        if checked:
            # 활성화 시 주문서 PDF 파일 설정 (필수!)
            order_pdf_path = self.settings_order_pdf_path.text().strip()
            if order_pdf_path:
                self.pdf_printer.set_pdf_file_2(order_pdf_path)
                # 주문서 PDF 인덱싱
                if self.excel_loader.df is not None:
                    tracking_numbers = self.excel_loader.get_all_tracking_numbers()
                    self.pdf_printer.build_tracking_index(tracking_numbers)
                self._add_log(f"주문서 PDF 설정: {order_pdf_path}")
            else:
                self._add_log("⚠️ 주문서 PDF 파일이 설정되지 않았습니다. 데이터 업로드에서 주문서 PDF를 선택하세요.")
            
            # A4 프린터 설정 적용
            a4_printer = self.settings_a4_printer.currentText()
            if a4_printer and a4_printer != "프린터 없음":
                self.pdf_printer.set_printer_2(a4_printer)
                self._add_log(f"주문서 프린터 설정: {a4_printer}")
            else:
                self._add_log("⚠️ A4 프린터가 설정되지 않았습니다. 프린터 설정에서 A4 프린터를 선택하세요.")
            
            self._add_log("주문서(A4) 동시 출력 활성화됨")
        else:
            self.pdf_printer.set_pdf_file_2("")
            self.pdf_printer.set_printer_2("")
            self._add_log("주문서(A4) 동시 출력 비활성화됨")
    
    def _on_settings_toggle_keep_temp(self, checked: bool):
        """설정 탭 - 임시 파일 보관 옵션"""
        self.pdf_printer.keep_temp_files = checked
        # 출고 탭과 동기화
        if hasattr(self, 'pdf_keep_temp_check'):
            self.pdf_keep_temp_check.blockSignals(True)
            self.pdf_keep_temp_check.setChecked(checked)
            self.pdf_keep_temp_check.blockSignals(False)
        self._add_log(f"PDF 임시 파일: {'보관' if checked else '출력 후 삭제'}")
    
    def _on_settings_save_bin(self):
        """설정 탭 - BIN 설정 저장"""
        max_qty = self.settings_bin_max_qty.value()
        min_qty = self.settings_bin_min_qty.value()
        max_sku = self.settings_bin_max_sku.value()
        dedicated_qty = self.settings_bin_dedicated_qty.value()
        
        # BIN 매니저에 적용
        self.bin_manager.set_config(
            max_qty_per_bin=max_qty,
            min_qty_threshold=min_qty,
            max_sku_per_shared_bin=max_sku,
            dedicated_qty_threshold=dedicated_qty
        )
        
        # 설정 저장
        save_bin_settings(
            max_qty_per_bin=max_qty,
            min_qty_threshold=min_qty,
            max_sku_per_shared_bin=max_sku,
            dedicated_qty_threshold=dedicated_qty
        )
        
        QMessageBox.information(self, "BIN 설정", "BIN 설정이 저장되었습니다.")
    
    def _on_settings_browse_save_path(self):
        """설정 탭 - 저장 위치 선택"""
        folder = QFileDialog.getExistingDirectory(self, "저장 위치 선택")
        if folder:
            self.settings_save_path.setText(folder)
            # 출고 탭에도 동기화
            if hasattr(self, 'save_path_edit'):
                self.save_path_edit.setText(folder)
    
    def _on_settings_save_excel(self):
        """설정 탭 - 엑셀 저장"""
        self._on_save_excel()
    
    def _update_settings_picking_session_combo(self):
        """설정 탭 - 피킹리스트 차수 콤보박스 업데이트"""
        self.settings_picking_session_combo.blockSignals(True)
        self.settings_picking_session_combo.clear()
        
        sessions = self.session_manager.get_all_sessions()
        
        if not sessions:
            self.settings_picking_session_combo.addItem("-- 생성된 차수 없음 --", 0)
        else:
            self.settings_picking_session_combo.addItem("-- 차수 선택 --", 0)
            for session in sessions:
                display = f"{session.session_id}차 [{session.supplier_display}] - {session.order_count}건"
                self.settings_picking_session_combo.addItem(display, session.session_id)
        
        self.settings_picking_session_combo.blockSignals(False)
        
        # 저장된 PDF 목록도 업데이트
        self._update_settings_saved_pdf_list()
    
    def _update_settings_saved_pdf_list(self):
        """설정 탭 - 저장된 피킹리스트 PDF 목록 업데이트 (오늘 파일만)"""
        self.settings_saved_pdf_list.clear()
        
        # 저장 경로 확인
        save_path = self.settings_save_path.text().strip()
        if not save_path:
            save_path = os.getcwd()
        
        # PDF 파일 검색 (피킹리스트 패턴)
        import glob
        from datetime import datetime, date
        
        pdf_patterns = [
            os.path.join(save_path, "*차*피킹*.pdf"),
            os.path.join(save_path, "*picking*.pdf"),
            os.path.join(save_path, "제품별_피킹리스트*.pdf"),
        ]
        
        pdf_files = []
        for pattern in pdf_patterns:
            pdf_files.extend(glob.glob(pattern))
        
        # 중복 제거 및 최신순 정렬
        pdf_files = list(set(pdf_files))
        pdf_files.sort(key=os.path.getmtime, reverse=True)
        
        # 오늘 날짜의 파일만 필터링
        today = date.today()
        today_pdf_files = []
        for pdf_path in pdf_files:
            file_mtime = datetime.fromtimestamp(os.path.getmtime(pdf_path)).date()
            if file_mtime == today:
                today_pdf_files.append(pdf_path)
        
        for pdf_path in today_pdf_files[:10]:  # 최근 10개만 표시
            filename = os.path.basename(pdf_path)
            item = QListWidgetItem(f"📄 {filename}")
            item.setData(Qt.UserRole, pdf_path)
            item.setToolTip(pdf_path)
            self.settings_saved_pdf_list.addItem(item)
        
        if not today_pdf_files:
            item = QListWidgetItem("오늘 저장된 피킹리스트가 없습니다")
            item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
            item.setForeground(QColor("#999"))
            self.settings_saved_pdf_list.addItem(item)
    
    def _on_settings_save_pdf(self):
        """설정 탭 - 피킹리스트 PDF 저장 (차수별)"""
        # 선택된 차수 확인
        session_id = self.settings_picking_session_combo.itemData(
            self.settings_picking_session_combo.currentIndex()
        )
        
        if not session_id or session_id == 0:
            QMessageBox.warning(self, "알림", "저장할 차수를 선택해주세요.")
            return
        
        session = self.session_manager.get_session(session_id)
        if not session:
            QMessageBox.warning(self, "오류", "선택한 차수를 찾을 수 없습니다.")
            return
        
        # 해당 차수의 데이터로 피킹리스트 생성
        filtered_df = self.excel_loader.get_filtered_by_suppliers(session.suppliers)
        if filtered_df is None or filtered_df.empty:
            QMessageBox.warning(self, "오류", "해당 차수의 데이터가 없습니다.")
            return
        
        # 저장 경로
        save_path = self.settings_save_path.text().strip()
        if not save_path:
            save_path = os.getcwd()
        
        # 파일명 생성
        supplier_name = session.supplier_display.replace("/", "_").replace("\\", "_").replace(":", "_").replace(" ", "")
        if len(supplier_name) > 20:
            supplier_name = supplier_name[:20]
        filename = f"{session.session_id}차_{supplier_name}_피킹리스트.pdf"
        file_path = os.path.join(save_path, filename)
        
        try:
            # BIN 정보 가져오기
            sku_bin_map = session.sku_bin_map if session.sku_bin_map else self.bin_manager._sku_bin_map
            
            from pdf_printer import create_picking_list_pdf
            from utils import safe_save_file
            
            # Permission 오류 시 자동으로 다른 이름으로 재시도
            def save_pdf(path):
                if not create_picking_list_pdf(filtered_df, path, sku_bin_map):
                    raise Exception("PDF 생성 실패")
                return True
            
            success, actual_path, error = safe_save_file(save_pdf, file_path)
            
            if success:
                actual_filename = os.path.basename(actual_path)
                self._last_pdf_path = actual_path
                self.settings_open_pdf_btn.setEnabled(True)
                self._update_settings_saved_pdf_list()
                
                # 파일명이 변경되었으면 알림
                msg = f"피킹리스트가 저장되었습니다.\n\n차수: {session.session_id}차\n업체: {session.supplier_display}\n파일: {actual_filename}"
                if actual_path != file_path:
                    msg += f"\n\n※ 원본 파일이 사용 중이어서 다른 이름으로 저장되었습니다."
                
                QMessageBox.information(self, "저장 완료", msg)
                self._add_log(f"[피킹리스트] {session.session_id}차 PDF 저장: {actual_path}")
            else:
                QMessageBox.warning(self, "오류", f"피킹리스트 PDF 저장에 실패했습니다.\n{error if error else ''}")
        except Exception as e:
            QMessageBox.warning(self, "오류", f"PDF 저장 중 오류: {str(e)}")
    
    def _on_settings_open_pdf(self):
        """설정 탭 - 마지막 저장된 피킹리스트 열기"""
        if hasattr(self, '_last_pdf_path') and self._last_pdf_path and os.path.exists(self._last_pdf_path):
            os.startfile(self._last_pdf_path)
        else:
            QMessageBox.information(self, "알림", "열 수 있는 피킹리스트가 없습니다.\n먼저 PDF를 저장해주세요.")
    
    def _on_settings_open_saved_pdf(self, item):
        """설정 탭 - 저장된 피킹리스트 더블클릭 시 열기"""
        pdf_path = item.data(Qt.UserRole)
        if pdf_path:
            if os.path.exists(pdf_path):
                try:
                    os.startfile(pdf_path)
                    self._add_log(f"[피킹리스트] 파일 열기: {pdf_path}")
                except Exception as e:
                    QMessageBox.warning(self, "오류", f"파일 열기 실패: {str(e)}\n\n경로: {pdf_path}")
            else:
                QMessageBox.warning(self, "오류", f"파일을 찾을 수 없습니다.\n\n경로: {pdf_path}")
        else:
            QMessageBox.warning(self, "오류", "파일 경로 정보가 없습니다.")
    
    # ===== 차수 관리 이벤트 핸들러 =====
    
    def _update_settings_supplier_combo(self):
        """설정 탭 - 업체 리스트 업데이트 (체크박스)"""
        self.settings_supplier_list.clear()
        
        if self.excel_loader.df is None:
            item = QListWidgetItem("엑셀 로드 후 선택 가능")
            item.setFlags(item.flags() & ~Qt.ItemIsUserCheckable)
            self.settings_supplier_list.addItem(item)
            self.settings_create_session_btn.setEnabled(False)
            return
        
        # 업체 요약 정보 가져오기
        supplier_summary = self.excel_loader.get_supplier_summary()
        
        if not supplier_summary:
            item = QListWidgetItem("업체 정보 없음")
            item.setFlags(item.flags() & ~Qt.ItemIsUserCheckable)
            self.settings_supplier_list.addItem(item)
            self.settings_create_session_btn.setEnabled(False)
            return
        
        # 이미 차수에 할당된 업체 목록 수집
        assigned_suppliers = set()
        for session in self.session_manager.sessions.values():
            for supplier in session.suppliers:
                assigned_suppliers.add(supplier)
        
        # 각 업체별 체크박스 아이템
        available_count = 0
        for item_data in supplier_summary:
            supplier = item_data["supplier"]
            order_count = item_data["order_count"]
            item_count = item_data["item_count"]
            
            # 이미 할당된 업체인지 확인
            if supplier in assigned_suppliers:
                # 이미 할당된 업체 - 비활성화
                item = QListWidgetItem(f"✅ {supplier} ({order_count}건) - 이미 할당됨")
                item.setData(Qt.UserRole, supplier)
                item.setFlags(item.flags() & ~Qt.ItemIsUserCheckable)
                item.setForeground(QColor("#999999"))
            else:
                # 미할당 업체 - 선택 가능
                item = QListWidgetItem(f"🏢 {supplier} ({order_count}건, {item_count}개)")
                item.setData(Qt.UserRole, supplier)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Unchecked)
                available_count += 1
            
            self.settings_supplier_list.addItem(item)
        
        # 선택 가능한 업체가 있을 때만 버튼 활성화
        self.settings_create_session_btn.setEnabled(available_count > 0)
        
        # 모든 업체가 차수에 할당된 경우 완료 메시지 표시
        if available_count == 0 and len(assigned_suppliers) > 0:
            complete_item = QListWidgetItem("")
            complete_item.setFlags(complete_item.flags() & ~Qt.ItemIsUserCheckable)
            self.settings_supplier_list.insertItem(0, complete_item)
            
            complete_msg = QListWidgetItem("✅ 차수 관리 완료! 모든 업체가 등록되었습니다.")
            complete_msg.setFlags(complete_msg.flags() & ~Qt.ItemIsUserCheckable)
            complete_msg.setForeground(QColor("#2ecc71"))
            self.settings_supplier_list.insertItem(0, complete_msg)
    
    def _on_settings_select_all_suppliers(self):
        """설정 탭 - 전체 업체 선택"""
        for i in range(self.settings_supplier_list.count()):
            item = self.settings_supplier_list.item(i)
            if item.flags() & Qt.ItemIsUserCheckable:
                item.setCheckState(Qt.Checked)
    
    def _on_settings_deselect_all_suppliers(self):
        """설정 탭 - 전체 업체 해제"""
        for i in range(self.settings_supplier_list.count()):
            item = self.settings_supplier_list.item(i)
            if item.flags() & Qt.ItemIsUserCheckable:
                item.setCheckState(Qt.Unchecked)
    
    def _get_selected_suppliers(self) -> list:
        """설정 탭 - 선택된 업체 목록 가져오기"""
        selected = []
        for i in range(self.settings_supplier_list.count()):
            item = self.settings_supplier_list.item(i)
            if item.checkState() == Qt.Checked:
                supplier = item.data(Qt.UserRole)
                if supplier:
                    selected.append(supplier)
        return selected
    
    def _update_settings_session_list(self):
        """설정 탭 - 차수 목록 업데이트"""
        self.settings_session_list.clear()
        
        for session_id, display_name in self.session_manager.get_session_choices():
            session = self.session_manager.sessions.get(session_id)
            if session:
                item_text = f"{session_id}차: {session.supplier_display} ({session.order_count}건, {session.sku_count} SKU)"
                item = QListWidgetItem(item_text)
                item.setData(Qt.UserRole, session_id)
                self.settings_session_list.addItem(item)
    
    def _on_settings_create_session(self):
        """설정 탭 - 차수 생성"""
        selected_suppliers = self._get_selected_suppliers()
        
        if not selected_suppliers:
            QMessageBox.warning(self, "경고", "최소 1개 이상의 업체를 선택하세요.")
            return
        
        # 업체 필터 적용
        supplier_summary = self.excel_loader.get_supplier_summary()
        all_suppliers = [s["supplier"] for s in supplier_summary]
        
        if len(selected_suppliers) == len(all_suppliers):
            # 전체 선택
            self.excel_loader.filter_by_supplier(all_suppliers)
            supplier_display = f"전체 ({', '.join(all_suppliers)})"
            suppliers = all_suppliers
        elif len(selected_suppliers) > 1:
            # 다중 업체 - 업체명도 표시
            self.excel_loader.filter_by_supplier(selected_suppliers)
            supplier_display = f"{len(selected_suppliers)}개 업체 ({', '.join(selected_suppliers)})"
            suppliers = selected_suppliers
        else:
            # 단일 업체
            self.excel_loader.filter_by_supplier(selected_suppliers[0])
            supplier_display = selected_suppliers[0]
            suppliers = selected_suppliers
        
        # BIN 할당
        if self.excel_loader.df is not None:
            # BIN 설정 로드 및 적용
            bin_settings = load_bin_settings()
            self.bin_manager.set_config(
                max_qty_per_bin=bin_settings.get("max_qty_per_bin", 100),
                min_qty_threshold=bin_settings.get("min_qty_threshold", 10),
                max_sku_per_shared_bin=bin_settings.get("max_sku_per_shared_bin", 5),
                dedicated_qty_threshold=bin_settings.get("dedicated_qty_threshold", 0)
            )
            # BIN 리셋 후 배정
            self.bin_manager.reset()
            self.bin_manager.assign_bins_from_dataframe(self.excel_loader.df)
            self.bin_manager.build_order_bin_map(self.excel_loader.df)
        
        # 세션 생성
        filtered_df = self.excel_loader.df
        order_count = len(filtered_df['tracking_no'].unique()) if filtered_df is not None else 0
        sku_count = len(filtered_df['barcode'].unique()) if filtered_df is not None else 0
        bin_count = self.bin_manager.get_bin_count()
        
        session = self.session_manager.create_session(
            suppliers=suppliers,
            supplier_display=supplier_display,
            order_count=order_count,
            sku_count=sku_count,
            bin_count=bin_count,
            sku_bin_map=self.bin_manager._sku_bin_map.copy()
        )
        
        # 작업 차수 업데이트
        self._work_session = session.session_id
        self._work_session_supplier = supplier_display
        
        # UI 업데이트
        self._update_session_display()
        self._update_session_combo()
        self._update_settings_session_list()
        self._update_settings_supplier_combo()  # 업체 목록 새로고침 (중복 방지)
        self._update_settings_picking_session_combo()  # 피킹리스트 차수 콤보박스 업데이트
        self._update_tables()
        
        QMessageBox.information(
            self, 
            "차수 생성", 
            f"{session.session_id}차 작업이 생성되었습니다.\n\n"
            f"업체: {supplier_display}\n"
            f"주문: {order_count}건\n"
            f"SKU: {sku_count}종\n"
            f"BIN: {bin_count}개"
        )
        
        self._add_log(f"<b style='color:#4CAF50'>[차수 생성] {session.session_id}차 - {supplier_display} ({order_count}건)</b>", html=True)
    
    def _on_settings_delete_session(self):
        """설정 탭 - 선택 차수 삭제"""
        current_item = self.settings_session_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "경고", "삭제할 차수를 선택하세요.")
            return
        
        session_id = current_item.data(Qt.UserRole)
        
        reply = QMessageBox.question(
            self,
            "차수 삭제",
            f"{session_id}차 작업을 삭제하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # delete_session 메서드 사용
            if self.session_manager.delete_session(session_id):
                self._update_session_combo()
                self._update_settings_session_list()
                self._update_settings_supplier_combo()  # 업체 목록 새로고침 (삭제된 업체 다시 선택 가능)
                self._update_settings_picking_session_combo()  # 피킹리스트 차수 콤보박스 업데이트
                self._update_session_display()
                self._add_log(f"[차수 삭제] {session_id}차 작업이 삭제되었습니다.")
    
    def _on_settings_clear_sessions(self):
        """설정 탭 - 전체 차수 초기화"""
        if not self.session_manager.sessions:
            QMessageBox.information(self, "알림", "삭제할 차수가 없습니다.")
            return
        
        reply = QMessageBox.question(
            self,
            "전체 초기화",
            "모든 작업 차수를 삭제하시겠습니까?\n\n이 작업은 되돌릴 수 없습니다.",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.session_manager.clear_all_sessions()
            # 모든 세션 ID 초기화
            self._work_session = 0
            self._work_session_supplier = ""
            self._shipment_session_id = 0
            self._fp_session_id = 0
            self._pp_session_id = 0
            # UI 업데이트
            self._update_session_display()
            self._update_session_combo()
            self._update_settings_session_list()
            self._update_settings_supplier_combo()  # 업체 목록 새로고침 (모든 업체 다시 선택 가능)
            self._update_settings_picking_session_combo()  # 피킹리스트 차수 콤보박스 업데이트
            self._update_fp_session_info()
            if hasattr(self, 'pp_session_label'):
                self._update_pp_session_info()
            self._add_log("[차수] 모든 작업 차수가 초기화되었습니다.")
    
    def _refresh_printer_combos(self):
        """출고 탭 프린터 콤보박스 새로고침"""
        printers = get_printers()
        
        # 라벨 프린터 콤보박스
        if hasattr(self, 'label_printer_combo'):
            current = self.label_printer_combo.currentText()
            self.label_printer_combo.clear()
            for printer in printers:
                self.label_printer_combo.addItem(printer)
            idx = self.label_printer_combo.findText(current)
            if idx >= 0:
                self.label_printer_combo.setCurrentIndex(idx)
        
        # A4 프린터 콤보박스
        if hasattr(self, 'a4_printer_combo'):
            current = self.a4_printer_combo.currentText()
            self.a4_printer_combo.clear()
            for printer in printers:
                self.a4_printer_combo.addItem(printer)
            idx = self.a4_printer_combo.findText(current)
            if idx >= 0:
                self.a4_printer_combo.setCurrentIndex(idx)
    
    # 슬롯별 고유 색상 정의
    SLOT_COLORS = {
        1: {"color": "#4CAF50", "bg": "#E8F5E9", "name": "녹색"},    # 녹색
        2: {"color": "#2196F3", "bg": "#E3F2FD", "name": "파란색"},  # 파란색
        3: {"color": "#FFC107", "bg": "#FFF8E1", "name": "노란색"},  # 노란색
    }
    
    def _create_slot_widget(self, slot_id: int):
        """슬롯 위젯 생성 - (slot_group, complete_btn, cancel_btn) 반환"""
        slot_color = self.SLOT_COLORS.get(slot_id, {"color": "#ccc", "bg": "#fff"})
        
        slot_group = QGroupBox(f"슬롯 {slot_id}")
        slot_group.setMinimumWidth(350)
        slot_group.setStyleSheet(f"""
            QGroupBox {{
                font-size: 16px;
                font-weight: bold;
                border: 3px solid {slot_color['color']};
                border-radius: 10px;
                margin-top: 10px;
                padding-top: 15px;
                background-color: {slot_color['bg']};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 5px;
                color: {slot_color['color']};
            }}
        """)
        
        layout = QVBoxLayout(slot_group)
        layout.setSpacing(10)
        
        # 주문번호 표시
        tracking_label = QLabel("주문: -")
        tracking_label.setObjectName(f"pp_slot_{slot_id}_tracking")
        tracking_label.setFont(QFont("Arial", 14, QFont.Bold))
        tracking_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(tracking_label)
        
        # 상태 표시
        state_label = QLabel("EMPTY")
        state_label.setObjectName(f"pp_slot_{slot_id}_state")
        state_label.setFont(QFont("Arial", 11))
        state_label.setAlignment(Qt.AlignCenter)
        state_label.setStyleSheet("color: #888; padding: 5px;")
        layout.addWidget(state_label)
        
        # BIN 목록 테이블 (바코드, BIN, 수량)
        bin_table = QTableWidget()
        bin_table.setObjectName(f"pp_slot_{slot_id}_table")
        bin_table.setColumnCount(3)
        bin_table.setHorizontalHeaderLabels(["바코드", "BIN", "수량"])
        bin_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        bin_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        bin_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        bin_table.setColumnWidth(1, 80)
        bin_table.setColumnWidth(2, 60)
        bin_table.setEditTriggers(QTableWidget.NoEditTriggers)
        bin_table.setSelectionBehavior(QTableWidget.SelectRows)
        bin_table.verticalHeader().setDefaultSectionSize(35)
        bin_table.setMinimumHeight(200)
        layout.addWidget(bin_table)
        
        # 총 수량 표시
        total_label = QLabel("총 수량: 0개")
        total_label.setObjectName(f"pp_slot_{slot_id}_total")
        total_label.setFont(QFont("Arial", 12))
        total_label.setAlignment(Qt.AlignRight)
        layout.addWidget(total_label)
        
        # 버튼 영역
        btn_layout = QHBoxLayout()
        
        # 완료 버튼
        complete_btn = QPushButton("✅ 완료")
        complete_btn.setObjectName(f"pp_slot_{slot_id}_complete")
        complete_btn.setMinimumHeight(45)
        complete_btn.setFont(QFont("Arial", 12, QFont.Bold))
        complete_btn.setEnabled(False)
        complete_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border-radius: 5px;
            }
            QPushButton:disabled {
                background-color: #ccc;
            }
            QPushButton:hover:enabled {
                background-color: #45a049;
            }
        """)
        btn_layout.addWidget(complete_btn)
        
        # 취소 버튼
        cancel_btn = QPushButton("❌ 취소")
        cancel_btn.setObjectName(f"pp_slot_{slot_id}_cancel")
        cancel_btn.setMinimumHeight(45)
        cancel_btn.setEnabled(False)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border-radius: 5px;
            }
            QPushButton:disabled {
                background-color: #ccc;
            }
        """)
        btn_layout.addWidget(cancel_btn)
        
        layout.addLayout(btn_layout)
        
        return slot_group, complete_btn, cancel_btn
    
    def _connect_prepick_signals(self):
        """미리피킹 시그널 연결"""
        # 미리피킹 엔진 시그널
        self.pre_pick_engine.order_assigned.connect(self._on_pp_order_assigned)
        self.pre_pick_engine.order_completed.connect(self._on_pp_order_completed)
        self.pre_pick_engine.order_not_found.connect(self._on_pp_order_not_found)
        self.pre_pick_engine.already_picked.connect(self._on_pp_already_picked)
        self.pre_pick_engine.slots_full.connect(self._on_pp_slots_full)
        self.pre_pick_engine.slot_state_changed.connect(self._on_pp_slot_state_changed)
        self.pre_pick_engine.bin_completed.connect(self._on_pp_bin_completed)
        self.pre_pick_engine.log_message.connect(self._add_pp_log)
        self.pre_pick_engine.error_occurred.connect(self._on_pp_error)
    
    # ===== 미리피킹 차수 관련 함수 =====
    
    def _on_refresh_pp_session(self):
        """미리피킹 탭 - 차수 선택 해제 및 새로고침"""
        # 세션 선택 해제
        self._pp_session_id = 0
        
        # 콤보박스 초기화
        self.pp_session_combo.blockSignals(True)
        self.pp_session_combo.setCurrentIndex(0)
        self.pp_session_combo.blockSignals(False)
        
        # UI 업데이트
        self._update_pp_session_combo()
        self._update_pp_session_info()
        
        self._add_pp_log("[미리피킹] 차수 선택이 해제되었습니다.")
    
    def _update_pp_session_combo(self):
        """미리피킹 세션 드롭다운 업데이트 (독립적)"""
        self.pp_session_combo.blockSignals(True)
        self.pp_session_combo.clear()
        
        sessions = self.session_manager.get_all_sessions()
        
        if not sessions:
            self.pp_session_combo.addItem("-- 설정 탭에서 차수 생성 필요 --", 0)
        else:
            self.pp_session_combo.addItem("-- 작업 차수 선택 --", 0)
            for session_id, display_name in self.session_manager.get_session_choices():
                self.pp_session_combo.addItem(display_name, session_id)
        
        # 미리피킹 탭 자체 세션 ID 기반으로 선택
        if self._pp_session_id > 0:
            for i in range(self.pp_session_combo.count()):
                if self.pp_session_combo.itemData(i) == self._pp_session_id:
                    self.pp_session_combo.setCurrentIndex(i)
                    break
        
        self.pp_session_combo.blockSignals(False)
        self._update_pp_session_info()
    
    def _update_pp_session_info(self):
        """미리피킹 세션 정보 업데이트 (독립적)"""
        # 미리피킹 탭 자체 세션 ID 기반으로 정보 표시
        session = self.session_manager.get_session(self._pp_session_id) if self._pp_session_id > 0 else None
        
        if session:
            self.pp_session_label.setText(f"{session.session_id}차")
            self.pp_supplier_label.setText(session.supplier_display)
            self.pp_data_status.setText(f"{session.order_count}건, {session.sku_count} SKU")
        else:
            self.pp_session_label.setText("미선택")
            self.pp_supplier_label.setText("업체 미선택")
            self.pp_data_status.setText("차수 선택 필요")
    
    @Slot(int)
    def _on_pp_session_combo_changed(self, index: int):
        """미리피킹 세션 드롭다운 변경 (독립적)"""
        session_id = self.pp_session_combo.itemData(index)
        if session_id and session_id > 0:
            self._pp_session_id = session_id
            session = self.session_manager.get_session(session_id)
            if session:
                self._load_pp_session(session)
    
    def _load_pp_session(self, session):
        """미리피킹 세션 로드 (독립적 - 다른 탭에 영향 없음)"""
        # 미리피킹 전용 세션 ID 저장
        self._pp_session_id = session.session_id
        
        # 미리피킹 탭 전용: 세션의 업체 기반으로 데이터 필터링
        if session.suppliers:
            # 임시로 필터 적용 (미리피킹 엔진 용)
            filtered_df = self.excel_loader.get_filtered_by_suppliers(session.suppliers)
            if filtered_df is not None:
                self.pre_pick_engine.set_data_source(filtered_df, self.bin_manager)
        
        # 미리피킹 UI만 업데이트
        self.pp_session_label.setText(f"{session.session_id}차")
        self.pp_supplier_label.setText(session.supplier_display)
        self.pp_data_status.setText(f"{session.order_count}건, {session.sku_count} SKU")
        
        self._add_pp_log(f"[미리피킹] {session.session_id}차 작업 선택 - {session.supplier_display}")
    
    # ===== 미리피킹 UI 이벤트 핸들러 =====
    
    def _on_pp_order_scan(self):
        """주문 스캔 처리"""
        order_no = self.pp_order_input.text().strip()
        if not order_no:
            return
        
        # ★ 작업차수 선택 확인
        if self._pp_session_id <= 0:
            QMessageBox.warning(self, "경고", "먼저 작업 차수를 선택해주세요.\n\n상단의 '작업 차수 선택' 드롭다운에서 차수를 선택하세요.")
            self.pp_order_input.clear()
            return
        
        # 데이터 소스 설정 확인
        if self.excel_loader.df is not None:
            self.pre_pick_engine.set_data_source(self.excel_loader.df, self.bin_manager)
        
        # 스캔 처리
        success, message = self.pre_pick_engine.process_scan(order_no)
        
        if success:
            self.pp_status_label.setText(f"✅ {order_no} 배정 완료")
            self.pp_status_label.setStyleSheet("color: #4CAF50;")
        else:
            self.pp_status_label.setText(f"❌ {message}")
            self.pp_status_label.setStyleSheet("color: #f44336;")
        
        # 입력 필드 초기화
        self.pp_order_input.clear()
        self.pp_order_input.setFocus()
    
    def _on_pp_order_assigned(self, slot_id: int, tracking_no: str, bin_list: list):
        """주문 배정 완료"""
        self._update_pp_slot_ui(slot_id)
    
    def _on_pp_order_completed(self, slot_id: int, tracking_no: str):
        """주문 완료"""
        self._update_pp_slot_ui(slot_id)
        self.pp_status_label.setText(f"✅ 슬롯 {slot_id} 완료: {tracking_no}")
        self.pp_status_label.setStyleSheet("color: #4CAF50;")
    
    def _on_pp_order_not_found(self, tracking_no: str):
        """주문 없음"""
        self.pp_status_label.setText(f"❌ Order not found: {tracking_no}")
        self.pp_status_label.setStyleSheet("color: #f44336;")
    
    def _on_pp_already_picked(self, tracking_no: str):
        """이미 피킹 완료"""
        self.pp_status_label.setText(f"⚠️ Already picked: {tracking_no}")
        self.pp_status_label.setStyleSheet("color: #FF9800;")
    
    def _on_pp_slots_full(self):
        """슬롯 가득 참"""
        self.pp_status_label.setText("❌ All slots are busy")
        self.pp_status_label.setStyleSheet("color: #f44336;")
    
    def _on_pp_slot_state_changed(self, slot_id: int, state: SlotState):
        """슬롯 상태 변경"""
        self._update_pp_slot_ui(slot_id)
    
    @Slot(int, str)
    def _on_pp_bin_completed(self, slot_id: int, bin_id: str):
        """개별 BIN 완료 (ESP32 터치)"""
        self._update_pp_slot_ui(slot_id)
        
        # 슬롯 정보 가져오기
        slot = self.pre_pick_engine.slot_manager.get_slot(slot_id)
        if slot:
            self.pp_status_label.setText(f"✅ BIN {bin_id} 완료 ({slot.done_bins_count}/{slot.total_bins})")
            self.pp_status_label.setStyleSheet("color: #4CAF50;")
    
    def _on_pp_error(self, message: str):
        """에러 발생"""
        self.pp_status_label.setText(f"❌ {message}")
        self.pp_status_label.setStyleSheet("color: #f44336;")
    
    def _add_pp_log(self, message: str):
        """미리피킹 로그 추가"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.pp_log.append(f"[{timestamp}] {message}")
    
    def _update_pp_slot_ui(self, slot_id: int):
        """슬롯 UI 업데이트"""
        slot_widget = self.pp_slot_widgets.get(slot_id)
        if not slot_widget:
            return
        
        slot = self.pre_pick_engine.slot_manager.get_slot(slot_id)
        
        # 위젯 찾기
        tracking_label = slot_widget.findChild(QLabel, f"pp_slot_{slot_id}_tracking")
        state_label = slot_widget.findChild(QLabel, f"pp_slot_{slot_id}_state")
        bin_table = slot_widget.findChild(QTableWidget, f"pp_slot_{slot_id}_table")
        total_label = slot_widget.findChild(QLabel, f"pp_slot_{slot_id}_total")
        complete_btn = self.pp_slot_complete_btns.get(slot_id)
        cancel_btn = self.pp_slot_cancel_btns.get(slot_id)
        
        if slot is None:
            # 빈 슬롯
            tracking_label.setText("주문: -")
            state_label.setText("EMPTY")
            state_label.setStyleSheet("color: #888; padding: 5px;")
            bin_table.setRowCount(0)
            total_label.setText("총 수량: 0개")
            complete_btn.setEnabled(False)
            cancel_btn.setEnabled(False)
            
            # 슬롯별 고유 색상 유지 (빈 상태에서도)
            slot_color = self.SLOT_COLORS.get(slot_id, {"color": "#ccc", "bg": "#fff"})
            slot_widget.setStyleSheet(f"""
                QGroupBox {{
                    font-size: 16px;
                    font-weight: bold;
                    border: 3px solid {slot_color['color']};
                    border-radius: 10px;
                    margin-top: 10px;
                    padding-top: 15px;
                    background-color: {slot_color['bg']};
                }}
                QGroupBox::title {{
                    subcontrol-origin: margin;
                    left: 15px;
                    padding: 0 5px;
                    color: {slot_color['color']};
                }}
            """)
        else:
            # 주문 정보 표시
            tracking_label.setText(f"주문: {slot.tracking_no}")
            
            # 상태 표시
            state_text = slot.state.value.upper()
            state_label.setText(state_text)
            
            # 슬롯별 고유 색상 가져오기
            slot_color = self.SLOT_COLORS.get(slot_id, {"color": "#ccc", "bg": "#fff"})
            
            # 상태별 스타일 (상태 라벨만)
            if slot.state == SlotState.ACTIVE:
                state_label.setStyleSheet("color: #4CAF50; font-weight: bold; padding: 5px; background-color: #E8F5E9; border-radius: 3px;")
            elif slot.state == SlotState.WAITING:
                state_label.setStyleSheet("color: #FF9800; font-weight: bold; padding: 5px; background-color: #FFF3E0; border-radius: 3px;")
            elif slot.state == SlotState.DONE:
                state_label.setStyleSheet("color: #9E9E9E; font-weight: bold; padding: 5px; background-color: #EEEEEE; border-radius: 3px;")
            else:
                state_label.setStyleSheet("color: #888; padding: 5px;")
            
            # 슬롯 고유 색상 유지 (DONE 상태일 때만 연하게)
            if slot.state == SlotState.DONE:
                slot_widget.setStyleSheet(f"""
                    QGroupBox {{
                        font-size: 16px;
                        font-weight: bold;
                        border: 3px solid #ccc;
                        border-radius: 10px;
                        margin-top: 10px;
                        padding-top: 15px;
                        background-color: #f5f5f5;
                    }}
                    QGroupBox::title {{
                        subcontrol-origin: margin;
                        left: 15px;
                        padding: 0 5px;
                        color: #888;
                    }}
                """)
            else:
                slot_widget.setStyleSheet(f"""
                    QGroupBox {{
                        font-size: 16px;
                        font-weight: bold;
                        border: 3px solid {slot_color['color']};
                        border-radius: 10px;
                        margin-top: 10px;
                        padding-top: 15px;
                        background-color: {slot_color['bg']};
                    }}
                    QGroupBox::title {{
                        subcontrol-origin: margin;
                        left: 15px;
                        padding: 0 5px;
                        color: {slot_color['color']};
                    }}
                """)
            
            # BIN 테이블 업데이트 (바코드, BIN, 수량, 완료여부)
            bin_list = slot.bin_list
            bin_table.setRowCount(len(bin_list))
            for row, (barcodes, bin_id, qty, done) in enumerate(bin_list):
                # 바코드 (완료 시 체크 표시)
                barcode_text = f"✅ {barcodes}" if done else barcodes
                barcode_item = QTableWidgetItem(barcode_text)
                if done:
                    barcode_item.setBackground(QColor("#C8E6C9"))  # 연녹색 배경
                bin_table.setItem(row, 0, barcode_item)
                # BIN
                bin_item = QTableWidgetItem(bin_id)
                bin_item.setTextAlignment(Qt.AlignCenter)
                if done:
                    bin_item.setBackground(QColor("#C8E6C9"))
                bin_table.setItem(row, 1, bin_item)
                # 수량
                qty_item = QTableWidgetItem(str(qty))
                qty_item.setTextAlignment(Qt.AlignCenter)
                if done:
                    qty_item.setBackground(QColor("#C8E6C9"))
                bin_table.setItem(row, 2, qty_item)
            
            total_label.setText(f"총 수량: {slot.total_qty}개")
            
            # 버튼 활성화
            complete_btn.setEnabled(slot.state in [SlotState.ACTIVE, SlotState.WAITING])
            cancel_btn.setEnabled(slot.state != SlotState.DONE)
    
    def _update_all_pp_slots(self):
        """모든 슬롯 UI 업데이트"""
        for slot_id in [1, 2, 3]:
            self._update_pp_slot_ui(slot_id)
    
    def _on_pp_slot_complete(self, slot_id: int):
        """슬롯 완료 버튼 클릭 - 슬롯 비우고 중복 방지 목록에 추가"""
        from pre_pick_engine import play_slot_complete_sound
        
        slot = self.pre_pick_engine.slot_manager.get_slot(slot_id)
        if slot:
            tracking_no = slot.tracking_no
            # 완료 신호음
            play_slot_complete_sound()
            # 중복 방지 목록에 추가
            self.pre_pick_engine._completed_orders.add(tracking_no)
            # 슬롯 비우기
            self.pre_pick_engine.clear_slot(slot_id)
            self._update_pp_slot_ui(slot_id)
            self._add_pp_log(f"[완료] 슬롯 {slot_id}: {tracking_no}")
            self.pp_status_label.setText(f"✅ 슬롯 {slot_id} 완료: {tracking_no}")
            self.pp_status_label.setStyleSheet("color: #4CAF50;")
        else:
            self._add_pp_log(f"[오류] 슬롯 {slot_id}이 비어있습니다")
    
    def _on_pp_slot_cancel(self, slot_id: int):
        """슬롯 취소 버튼 클릭 - 슬롯만 비움 (다시 스캔 가능)"""
        slot = self.pre_pick_engine.slot_manager.get_slot(slot_id)
        if slot:
            tracking_no = slot.tracking_no
            # 슬롯만 비우기 (중복 방지 목록에 추가하지 않음)
            self.pre_pick_engine.clear_slot(slot_id)
            self._update_pp_slot_ui(slot_id)
            self._add_pp_log(f"[취소] 슬롯 {slot_id}: {tracking_no}")
            self.pp_status_label.setText(f"🗑️ 슬롯 {slot_id} 취소: {tracking_no}")
            self.pp_status_label.setStyleSheet("color: #666;")
        else:
            self._add_pp_log(f"[오류] 슬롯 {slot_id}이 비어있습니다")
    
    def _on_pp_clear_done_slots(self):
        """완료된 슬롯 정리"""
        self.pre_pick_engine.clear_completed_slots()
        self._update_all_pp_slots()
        self.pp_status_label.setText("🧹 완료된 슬롯 정리됨")
        self.pp_status_label.setStyleSheet("color: #666;")
    
    def _on_pp_reset(self):
        """전체 초기화"""
        reply = QMessageBox.question(
            self, "초기화 확인",
            "모든 슬롯을 초기화하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.pre_pick_engine.reset()
            self._update_all_pp_slots()
            self.pp_status_label.setText("🔄 전체 초기화됨")
            self.pp_status_label.setStyleSheet("color: #666;")
    
    def _on_pp_slot_count_changed(self, index: int):
        """슬롯 개수 변경"""
        slot_count = self.pp_slot_count_combo.itemData(index)
        
        # 사용하지 않는 슬롯에 주문이 있는지 확인
        has_orders = False
        for slot_id in range(slot_count + 1, 4):
            slot = self.pre_pick_engine.slot_manager.get_slot(slot_id)
            if slot is not None:
                has_orders = True
                break
        
        if has_orders:
            reply = QMessageBox.question(
                self, "슬롯 변경 확인",
                "사용하지 않을 슬롯에 주문이 있습니다.\n해당 슬롯을 비우고 변경하시겠습니까?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                # 이전 값으로 복원
                self.pp_slot_count_combo.blockSignals(True)
                current_count = self.pre_pick_engine.slot_manager.active_slot_count
                self.pp_slot_count_combo.setCurrentIndex(current_count - 1)
                self.pp_slot_count_combo.blockSignals(False)
                return
            
            # 해당 슬롯 비우기
            for slot_id in range(slot_count + 1, 4):
                self.pre_pick_engine.clear_slot(slot_id)
        
        # 슬롯 개수 변경
        self.pre_pick_engine.slot_manager.set_active_slot_count(slot_count)
        
        # UI 업데이트 (슬롯 표시/숨김)
        for slot_id in [1, 2, 3]:
            widget = self.pp_slot_widgets.get(slot_id)
            if widget:
                if slot_id <= slot_count:
                    widget.setVisible(True)
                else:
                    widget.setVisible(False)
        
        self._add_pp_log(f"[설정] 슬롯 개수 변경: {slot_count}개")
        self.pp_status_label.setText(f"슬롯 {slot_count}개 사용")
        self.pp_status_label.setStyleSheet("color: #666;")
    
    def _connect_fullpick_signals(self):
        """전체피킹 시그널 연결"""
        # 전체피킹 엔진 시그널
        self.full_pick_engine.session_started.connect(self._on_fp_session_started)
        self.full_pick_engine.bin_list_ready.connect(self._on_fp_bin_list_ready)
        self.full_pick_engine.bin_completed.connect(self._on_fp_bin_completed)
        self.full_pick_engine.session_completed.connect(self._on_fp_session_completed)
        self.full_pick_engine.state_changed.connect(self._on_fp_state_changed)
        self.full_pick_engine.error_occurred.connect(self._on_fp_error)
        self.full_pick_engine.log_message.connect(self._add_fp_log)
        
        # ESP32 서버 시그널은 ESP32 탭에서 통합 관리 (중복 연결 방지)
        # _connect_esp32_signals()에서 연결하고 전체피킹 탭 UI도 동기화함
    
    def _add_fp_log(self, message: str):
        """전체피킹 로그 추가"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.fp_log.append(f"[{timestamp}] {message}")
    
    def _add_fp_scan_history(self, barcode: str, total_qty: int, bin_count: int, status: str, scan_time: str):
        """스캔 히스토리에 추가 (최근 스캔이 최상단)"""
        # 이미 같은 바코드가 있으면 제거 (최신으로 갱신)
        self._fp_scan_history = [(b, q, c, s, t) for b, q, c, s, t in self._fp_scan_history if b != barcode]
        
        # 최상단에 추가
        self._fp_scan_history.insert(0, (barcode, total_qty, bin_count, status, scan_time))
        
        # 최대 20개까지만 유지
        if len(self._fp_scan_history) > 20:
            self._fp_scan_history = self._fp_scan_history[:20]
        
        # 테이블 갱신
        self._refresh_fp_scan_history_table()
    
    def _update_fp_scan_history_status(self, barcode: str, new_status: str):
        """스캔 히스토리 상태 업데이트"""
        for i, (b, q, c, s, t) in enumerate(self._fp_scan_history):
            if b == barcode:
                self._fp_scan_history[i] = (b, q, c, new_status, t)
                break
        self._refresh_fp_scan_history_table()
    
    def _refresh_fp_scan_history_table(self):
        """스캔 히스토리 테이블 갱신"""
        self.fp_scan_history_table.setRowCount(len(self._fp_scan_history))
        
        for row, (barcode, total_qty, bin_count, status, scan_time) in enumerate(self._fp_scan_history):
            # SKU 바코드
            barcode_item = QTableWidgetItem(barcode)
            barcode_item.setFont(QFont("Consolas", 10, QFont.Bold))
            self.fp_scan_history_table.setItem(row, 0, barcode_item)
            
            # 총 수량
            qty_item = QTableWidgetItem(f"{total_qty}개")
            qty_item.setTextAlignment(Qt.AlignCenter)
            qty_item.setBackground(QColor("#E1BEE7"))
            self.fp_scan_history_table.setItem(row, 1, qty_item)
            
            # BIN 수
            bin_item = QTableWidgetItem(f"{bin_count}")
            bin_item.setTextAlignment(Qt.AlignCenter)
            self.fp_scan_history_table.setItem(row, 2, bin_item)
            
            # 상태
            status_item = QTableWidgetItem(status)
            status_item.setTextAlignment(Qt.AlignCenter)
            if "완료" in status:
                status_item.setBackground(QColor("#C8E6C9"))  # 연녹색
            elif "진행" in status:
                status_item.setBackground(QColor("#FFF9C4"))  # 연노랑
            self.fp_scan_history_table.setItem(row, 3, status_item)
            
            # 시간
            time_item = QTableWidgetItem(scan_time)
            time_item.setTextAlignment(Qt.AlignCenter)
            self.fp_scan_history_table.setItem(row, 4, time_item)
            
            # 첫 번째 행(현재 진행중)은 하이라이트
            if row == 0 and "진행" in status:
                for col in range(5):
                    item = self.fp_scan_history_table.item(row, col)
                    if item:
                        item.setBackground(QColor("#BBDEFB"))  # 연파랑
    
    def _on_fp_history_item_clicked(self, item):
        """히스토리 항목 클릭 - 해당 SKU 정보 표시"""
        row = item.row()
        if row < len(self._fp_scan_history):
            barcode, total_qty, bin_count, status, _ = self._fp_scan_history[row]
            self._add_fp_log(f"[히스토리] {barcode}: {total_qty}개, {bin_count} BIN ({status})")
    
    def _on_fp_clear_history(self):
        """스캔 히스토리 초기화"""
        reply = QMessageBox.question(
            self, "확인",
            "스캔 히스토리를 초기화하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._fp_scan_history = []
            self.fp_scan_history_table.setRowCount(0)
            self._add_fp_log("[히스토리] 초기화됨")
    
    def _go_to_esp32_tab(self):
        """ESP32 설정 탭으로 이동"""
        # ESP32 탭 인덱스 찾기 (탭 순서가 바뀔 수 있으므로)
        for i in range(self.tab_widget.count()):
            if "ESP32" in self.tab_widget.tabText(i):
                self.tab_widget.setCurrentIndex(i)
                break
    
    @Slot(int)
    def _on_fp_server_started(self, port: int):
        """서버 시작 완료 - 상태 표시만"""
        self.fp_server_status.setText(f"🟢 실행중 (:{port})")
        self.fp_server_status.setStyleSheet("color: green;")
        self._add_fp_log(f"ESP32 WebSocket 서버 시작: 포트 {port}")
    
    @Slot()
    def _on_fp_server_stopped(self):
        """서버 중지 - 상태 표시만"""
        self.fp_server_status.setText("⚫ 중지됨")
        self.fp_server_status.setStyleSheet("color: gray;")
        self._add_fp_log("ESP32 서버 중지됨")
    
    @Slot(str)
    def _on_fp_device_hello(self, device_id: str):
        """ESP32 장치 연결"""
        # 장치 등록
        self.device_registry.register_device(device_id)
        
        # 자동 바인딩
        bin_id = self.device_registry.auto_bind_device(device_id)
        if bin_id:
            # 바인딩 명령 전송
            self.esp32_transport.send_bind(device_id, bin_id)
            self._add_fp_log(f"장치 연결 및 바인딩: {device_id} → {bin_id}")
        else:
            self._add_fp_log(f"장치 연결: {device_id}")
        
        self._update_fp_device_list()
    
    @Slot(str)
    def _on_fp_device_disconnected(self, device_id: str):
        """ESP32 장치 연결 해제"""
        self.device_registry.unregister_device(device_id)
        self._add_fp_log(f"장치 연결 해제: {device_id}")
        self._update_fp_device_list()
    
    def _update_fp_device_list(self):
        """장치 목록 업데이트"""
        self.fp_device_list.clear()
        
        for device in self.device_registry.get_all_devices():
            status = "🟢" if device.connected else "🔴"
            bin_text = device.bin_id or "미할당"
            item = QListWidgetItem(f"{status} {device.device_id} → {bin_text}")
            self.fp_device_list.addItem(item)
        
        self.fp_device_count.setText(f"연결: {self.device_registry.connected_count}대")
        
        # ESP32 탭 테이블도 동기화
        if hasattr(self, 'esp32_device_table'):
            self._update_esp32_device_table()
    
    @Slot()
    def _on_fp_refresh_devices(self):
        """장치 목록 새로고침"""
        self._update_fp_device_list()
        # ESP32 탭도 동기화
        if hasattr(self, 'esp32_device_table'):
            self._update_esp32_device_table()
    
    @Slot()
    def _on_fp_clear_bindings(self):
        """모든 바인딩 초기화"""
        self.device_registry.clear_all_bindings()
        self._update_fp_device_list()
        self._add_fp_log("모든 장치 바인딩 초기화됨")
        # ESP32 탭도 동기화
        if hasattr(self, 'esp32_device_table'):
            self._update_esp32_device_table()
    
    @Slot()
    def _on_fp_sku_scan(self):
        """SKU 스캔 처리"""
        barcode = self.fp_sku_input.text().strip()
        if not barcode:
            return
        
        # ★ 작업차수 선택 확인
        if self._fp_session_id <= 0:
            QMessageBox.warning(self, "경고", "먼저 작업 차수를 선택해주세요.\n\n상단의 '작업 차수 선택' 드롭다운에서 차수를 선택하세요.")
            self.fp_sku_input.clear()
            return
        
        # 데이터 소스 설정
        if self.excel_loader.df is not None:
            self.full_pick_engine.set_data_source(self.excel_loader.df, self.bin_manager)
        else:
            QMessageBox.warning(self, "경고", "먼저 출고 탭에서 엑셀 파일을 불러오세요.")
            return
        
        # 스캔 처리
        self.full_pick_engine.process_scan(barcode)
        
        # 입력 필드 초기화
        self.fp_sku_input.clear()
        self.fp_sku_input.setFocus()
    
    @Slot(str, int)
    def _on_fp_session_started(self, barcode: str, total_qty: int):
        """피킹 세션 시작"""
        self.fp_current_sku.setText(f"현재 SKU: {barcode}")
        self.fp_total_qty.setText(f"총 수량: {total_qty}개")
        self.fp_cancel_btn.setEnabled(True)
        self.fp_manual_complete_btn.setEnabled(True)
        self._add_fp_log(f"피킹 시작: {barcode} (총 {total_qty}개)")
        
        # ★ 스캔 히스토리에 추가 (최근 스캔이 최상단)
        from datetime import datetime
        current_time = datetime.now().strftime("%H:%M:%S")
        bin_count = len(self.full_pick_engine.current_session.bins) if self.full_pick_engine.current_session else 0
        self._add_fp_scan_history(barcode, total_qty, bin_count, "진행중", current_time)
    
    @Slot(list)
    def _on_fp_bin_list_ready(self, bin_list: list):
        """BIN 목록 표시"""
        self.fp_bin_table.setRowCount(len(bin_list))
        
        for row, (bin_id, qty) in enumerate(bin_list):
            # BIN ID
            bin_item = QTableWidgetItem(bin_id)
            bin_item.setTextAlignment(Qt.AlignCenter)
            bin_item.setFont(QFont("Arial", 12, QFont.Bold))
            self.fp_bin_table.setItem(row, 0, bin_item)
            
            # 수량
            qty_item = QTableWidgetItem(str(qty))
            qty_item.setTextAlignment(Qt.AlignCenter)
            qty_item.setFont(QFont("Arial", 14, QFont.Bold))
            qty_item.setBackground(QColor("#E1BEE7"))  # 연보라
            self.fp_bin_table.setItem(row, 1, qty_item)
            
            # 상태
            status_item = QTableWidgetItem("대기")
            status_item.setTextAlignment(Qt.AlignCenter)
            self.fp_bin_table.setItem(row, 2, status_item)
            
            # 완료 버튼
            complete_btn = QPushButton("✓ 완료")
            complete_btn.setMinimumWidth(70)
            complete_btn.setMinimumHeight(30)
            complete_btn.setStyleSheet("""
                QPushButton {
                    background-color: #4CAF50;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    font-weight: bold;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: #45a049;
                }
                QPushButton:disabled {
                    background-color: #cccccc;
                    color: #666666;
                }
            """)
            complete_btn.setProperty("bin_id", bin_id)
            complete_btn.clicked.connect(lambda checked, b=bin_id: self._on_fp_bin_button_clicked(b))
            self.fp_bin_table.setCellWidget(row, 3, complete_btn)
        
        self._update_fp_progress()
    
    def _on_fp_bin_button_clicked(self, bin_id: str):
        """BIN 완료 버튼 클릭"""
        self.full_pick_engine.complete_bin(bin_id)
    
    @Slot(str, int)
    def _on_fp_bin_completed(self, bin_id: str, qty: int):
        """BIN 완료"""
        # 테이블에서 해당 BIN 찾아서 상태 업데이트
        for row in range(self.fp_bin_table.rowCount()):
            item = self.fp_bin_table.item(row, 0)
            if item and item.text() == bin_id:
                # 상태 업데이트
                status_item = self.fp_bin_table.item(row, 2)
                if status_item:
                    status_item.setText("✅ 완료")
                    status_item.setBackground(QColor("#C8E6C9"))  # 연녹색
                
                # 버튼 비활성화
                btn = self.fp_bin_table.cellWidget(row, 3)
                if btn:
                    btn.setEnabled(False)
                break
        
        self._update_fp_progress()
        self._add_fp_log(f"BIN 완료: {bin_id} ({qty}개)")
    
    @Slot(str, int)
    def _on_fp_session_completed(self, barcode: str, total_qty: int):
        """피킹 세션 완료"""
        self.fp_current_sku.setText("현재 SKU: - (완료)")
        self.fp_cancel_btn.setEnabled(False)
        self.fp_manual_complete_btn.setEnabled(False)
        self._add_fp_log(f"SKU 피킹 완료: {barcode} (총 {total_qty}개)")
        
        # ★ 스캔 히스토리 상태 업데이트
        self._update_fp_scan_history_status(barcode, "✅ 완료")
        
        # 알림창 제거 - ESP32 터치로 완료하면 추가 클릭 불필요
    
    @Slot(object)
    def _on_fp_state_changed(self, state: FullPickState):
        """상태 변경"""
        state_names = {
            FullPickState.IDLE: "대기",
            FullPickState.WAIT_SKU_SCAN: "SKU 스캔 대기",
            FullPickState.BIN_ACTIVE: "피킹 진행중",
            FullPickState.BIN_DONE: "BIN 완료",
            FullPickState.SKU_DONE: "SKU 완료"
        }
        self.fp_state_label.setText(state_names.get(state, "알 수 없음"))
    
    @Slot(str)
    def _on_fp_error(self, message: str):
        """오류 발생"""
        self._add_fp_log(f"[오류] {message}")
        QMessageBox.warning(self, "오류", message)
    
    def _update_fp_progress(self):
        """진행 상황 업데이트"""
        session = self.full_pick_engine.current_session
        if session:
            self.fp_progress_label.setText(
                f"완료: {session.completed_bins} / {session.total_bins} BIN"
            )
            self.fp_completed_qty.setText(
                f"피킹 완료: {session.completed_qty}개 / {session.total_qty}개"
            )
        else:
            self.fp_progress_label.setText("완료: 0 / 0 BIN")
            self.fp_completed_qty.setText("피킹 완료: 0개 / 0개")
    
    @Slot()
    def _on_fp_cancel_session(self):
        """현재 세션 취소"""
        if self.full_pick_engine.current_session:
            barcode = self.full_pick_engine.current_session.barcode
            reply = QMessageBox.question(
                self,
                "세션 취소",
                "현재 진행중인 피킹을 취소하시겠습니까?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.full_pick_engine.cancel_session()
                self.fp_bin_table.setRowCount(0)
                self.fp_current_sku.setText("현재 SKU: -")
                self.fp_total_qty.setText("총 수량: 0개")
                self._update_fp_progress()
                self._add_fp_log("피킹 세션 취소됨")
                
                # ★ 스캔 히스토리 상태 업데이트
                self._update_fp_scan_history_status(barcode, "❌ 취소")
    
    @Slot()
    def _on_fp_manual_complete(self):
        """선택된 BIN 수동 완료"""
        selected = self.fp_bin_table.selectedItems()
        if not selected:
            QMessageBox.warning(self, "경고", "완료할 BIN을 선택해주세요.")
            return
        
        row = selected[0].row()
        bin_item = self.fp_bin_table.item(row, 0)
        if bin_item:
            bin_id = bin_item.text()
            self.full_pick_engine.complete_bin(bin_id)
    
    @Slot()
    def _on_fp_change_supplier(self):
        """전체피킹 탭에서 업체 변경 (출고 탭의 기능 연동)"""
        # 원본 데이터가 없으면 경고
        if self.excel_loader._df_original is None:
            QMessageBox.warning(self, "경고", "먼저 출고 탭에서 엑셀 파일을 불러오세요.")
            return
        
        # 공급처 컬럼이 없으면 경고
        if not self.excel_loader.has_supplier_column():
            QMessageBox.information(self, "알림", "엑셀 파일에 공급처(업체) 컬럼이 없습니다.")
            return
        
        # 업체 목록 가져오기
        supplier_summary = self.excel_loader.get_supplier_summary()
        
        if not supplier_summary:
            QMessageBox.information(self, "알림", "공급처 데이터가 없습니다.")
            return
        
        if len(supplier_summary) <= 1:
            QMessageBox.information(self, "알림", "변경할 수 있는 다른 업체가 없습니다.")
            return
        
        # 현재 선택된 업체 리스트 가져오기
        current_suppliers = self.excel_loader.get_current_suppliers() or []
        
        # 업체 선택 다이얼로그 표시
        dialog = SupplierSelectDialog(supplier_summary, self, current_suppliers)
        if dialog.exec() == QDialog.Accepted:
            selected_suppliers = dialog.get_selected_suppliers()
            
            # 선택 비교
            if set(selected_suppliers) == set(current_suppliers):
                self._add_fp_log("[업체] 동일한 업체 선택됨 - 변경 없음")
                return
            
            # ===== BIN 완전 리셋 안내 =====
            self._add_fp_log(f"━━━ 업체 변경: BIN 완전 리셋 ━━━")
            
            # 업체 변경 적용
            if len(selected_suppliers) == len(supplier_summary):
                self.excel_loader.filter_by_supplier(None)
                self._add_fp_log(f"[업체 변경] 전체 {len(selected_suppliers)}개 업체 선택")
            elif len(selected_suppliers) > 1:
                self.excel_loader.filter_by_supplier(selected_suppliers)
                self._add_fp_log(f"[업체 변경] {len(selected_suppliers)}개 업체 선택: {', '.join(selected_suppliers)}")
            else:
                self.excel_loader.filter_by_supplier(selected_suppliers[0])
                self._add_fp_log(f"[업체 변경] '{selected_suppliers[0]}' 선택됨")
            
            # BIN 및 작업 차수 재처리 (출고 탭의 로직 호출)
            file_path = self.excel_path_edit.text().strip()
            self._process_after_supplier_selection(file_path)
            
            # 전체피킹 탭 UI 업데이트
            self._update_fp_session_info()
            
            # 현재 세션 취소
            if self.full_pick_engine.current_session:
                self.full_pick_engine.cancel_session()
                self.fp_bin_table.setRowCount(0)
            
            QMessageBox.information(
                self,
                "업체 변경 완료",
                f"업체가 변경되었습니다.\n\n"
                f"작업 차수: {self._work_session}차 전체피킹\n"
                f"선택 업체: {self._work_session_supplier}\n"
                f"주문 건수: {self.excel_loader.get_filtered_order_count()}건\n\n"
                f"⚠️ BIN이 완전히 초기화되어 새로 배정되었습니다."
            )
    
    def _update_fp_session_info(self):
        """전체피킹 탭의 작업 차수/업체 정보 업데이트 (독립적)"""
        # 전체피킹 탭 자체 세션 ID 기반으로 정보 표시
        session = self.session_manager.get_session(self._fp_session_id) if self._fp_session_id > 0 else None
        
        if session:
            self.fp_session_label.setText(f"{session.session_id}차 피킹")
            self.fp_supplier_label.setText(session.supplier_display)
            self.fp_data_status.setText(f"{session.order_count}건, {session.sku_count} SKU")
        else:
            self.fp_session_label.setText("미선택")
            self.fp_supplier_label.setText("업체 미선택")
            self.fp_data_status.setText("차수 선택 필요")
        
        # 드롭다운도 업데이트
        self._update_fp_session_combo()
    
    def _on_refresh_fp_session(self):
        """전체피킹 탭 - 차수 선택 해제 및 새로고침"""
        # 세션 선택 해제
        self._fp_session_id = 0
        
        # 콤보박스 초기화
        self.fp_session_combo.blockSignals(True)
        self.fp_session_combo.setCurrentIndex(0)
        self.fp_session_combo.blockSignals(False)
        
        # UI 업데이트
        self._update_fp_session_combo()
        self._update_fp_session_info()
        
        self._add_fp_log("[전체피킹] 차수 선택이 해제되었습니다.")
    
    def _update_fp_session_combo(self):
        """전체피킹 탭의 세션 드롭다운 업데이트 (독립적)"""
        self.fp_session_combo.blockSignals(True)
        self.fp_session_combo.clear()
        
        sessions = self.session_manager.get_all_sessions()
        
        if not sessions:
            self.fp_session_combo.addItem("-- 설정 탭에서 차수 생성 필요 --", 0)
        else:
            self.fp_session_combo.addItem("-- 작업 차수 선택 --", 0)
            for session in sessions:
                display = f"{session.session_id}차 [{session.supplier_display}] - {session.order_count}건, {session.sku_count} SKU"
                self.fp_session_combo.addItem(display, session.session_id)
        
        # 전체피킹 탭 자체 세션 ID 기반으로 선택
        if self._fp_session_id > 0:
            for i in range(self.fp_session_combo.count()):
                if self.fp_session_combo.itemData(i) == self._fp_session_id:
                    self.fp_session_combo.setCurrentIndex(i)
                    break
        
        self.fp_session_combo.blockSignals(False)
    
    @Slot(int)
    def _on_fp_session_combo_changed(self, index: int):
        """전체피킹 탭 세션 드롭다운 변경 (독립적)"""
        session_id = self.fp_session_combo.itemData(index)
        if session_id and session_id > 0:
            self._fp_session_id = session_id
            session = self.session_manager.get_session(session_id)
            if session:
                self._load_fp_session(session)
    
    def _load_fp_session(self, session: WorkSession):
        """전체피킹용 세션 로드 (독립적 - 다른 탭에 영향 없음)"""
        # 전체피킹 전용 세션 ID 저장
        self._fp_session_id = session.session_id
        
        # 전체피킹 탭 전용 데이터 필터 적용 (출고 탭에 영향 없음)
        # excel_loader를 직접 변경하지 않고, 필요 시 세션 기반으로 데이터 조회
        
        # BIN 매핑 복원 (있는 경우)
        if session.sku_bin_map:
            self.bin_manager._sku_bin_map = session.sku_bin_map.copy()
            self.bin_manager._initialized = True
        
        # 전체피킹 UI만 업데이트
        self.fp_session_label.setText(f"{session.session_id}차 피킹")
        self.fp_supplier_label.setText(session.supplier_display)
        self.fp_data_status.setText(f"{session.order_count}건, {session.sku_count} SKU")
        
        self._add_fp_log(f"[전체피킹] {session.session_id}차 작업 선택 - {session.supplier_display}")
        self._add_fp_log(f"  → {session.order_count}건, {session.sku_count} SKU, {session.bin_count} BIN")
    
    @Slot()
    def _on_reprint_search(self):
        """재출력 검색 실행"""
        # 입력값 정규화 (앞뒤 공백 제거, 내부 공백/하이픈은 유지)
        input_value = self.reprint_input.text().strip()
        
        if not input_value:
            QMessageBox.warning(self, "경고", "송장번호 또는 주문번호를 입력해주세요.")
            return
        
        # 입력값에서 숫자만 추출하여 길이 확인 (최소 11자리)
        numbers_only = re.sub(r'[-–—\s]', '', input_value)
        if not numbers_only.isdigit() or len(numbers_only) < 8:
            QMessageBox.warning(
                self,
                "입력 오류",
                f"올바른 송장번호 또는 주문번호를 입력해주세요.\n\n"
                f"입력값: {input_value}\n"
                f"숫자만 추출: {numbers_only}\n\n"
                f"송장번호는 11자리 이상, 주문번호는 8자리 이상이어야 합니다."
            )
            return
        
        # 출력 옵션 확인
        print_label = self.reprint_label_check.isChecked()
        print_order = self.reprint_order_check.isChecked()
        
        if not print_label and not print_order:
            QMessageBox.warning(self, "경고", "출력할 항목을 하나 이상 선택해주세요.")
            return
        
        # 검색 폴더 확인
        label_folder = self.reprint_label_folder_edit.text().strip() if print_label else None
        order_folder = self.reprint_order_folder_edit.text().strip() if print_order else None
        
        # 검색할 폴더 리스트 구성
        search_folders = []
        if print_label and label_folder:
            search_folders.append(label_folder)
        if print_order and order_folder:
            search_folders.append(order_folder)
        
        if not search_folders:
            QMessageBox.warning(self, "경고", "검색할 폴더를 선택해주세요.")
            return
        
        # UI 상태 변경
        self.reprint_search_btn.setEnabled(False)
        self.reprint_cancel_btn.setEnabled(True)
        self.reprint_execute_btn.setEnabled(False)
        self._reprint_search_cancelled = False
        
        # 멀티코어 사용 여부 확인
        use_multicore = self.reprint_multicore_check.isChecked()
        import multiprocessing
        cpu_count = multiprocessing.cpu_count()
        worker_count = max(1, int(cpu_count * 0.7)) if use_multicore else 1
        
        # 검색 상태 표시
        if use_multicore:
            status_text = f"🔍 검색 중... (멀티스레드: {worker_count}개 워커 사용, CPU 코어 {cpu_count}개 중 {worker_count}개 활용)"
        else:
            status_text = f"🔍 검색 중... (단일스레드: CPU 코어 {cpu_count}개 중 1개 사용)"
        self.reprint_status_label.setText(status_text)
        self.reprint_status_label.setStyleSheet("color: #2196F3; font-size: 11px; padding: 5px; font-weight: bold;")
        
        # 취소 플래그 객체 생성
        class CancelFlag:
            def __init__(self):
                self.cancelled = False
        
        cancel_flag = CancelFlag()
        self._reprint_cancel_flag = cancel_flag
        
        # 멀티코어 PDF 검색 시작
        search_mode = "멀티코어" if use_multicore else "단일코어"
        self._add_log(f"[REPRINT-SEARCH] PDF 검색 시작: {input_value} ({search_mode} 검색)")
        
        # 검색을 별도 스레드에서 실행 (UI 블로킹 방지)
        import threading
        
        def search_thread():
            try:
                # 진행 상황 콜백 함수
                def progress_callback(message: str):
                    # 메인 스레드에서 안전하게 로그 및 상태 업데이트
                    from PySide6.QtCore import QTimer
                    QTimer.singleShot(0, lambda: self._add_log(f"[REPRINT-SEARCH] {message}"))
                    # 상태 라벨도 업데이트
                    if "검색 중" in message or "파일 검사" in message:
                        QTimer.singleShot(0, lambda: self.reprint_status_label.setText(f"🔍 {message}"))
                
                # 디버그 콜백 함수
                def debug_callback(message: str):
                    # 디버그 메시지도 UI에 표시
                    from PySide6.QtCore import QTimer
                    QTimer.singleShot(0, lambda: self._add_log(message))
                
                # PDF 파일 전체 검색
                search_result = find_pdf_by_tracking_or_order(
                    input_value,
                    search_folders,
                    use_multicore=use_multicore,
                    cancel_flag=cancel_flag,
                    progress_callback=progress_callback,
                    debug_callback=debug_callback
                )
                
                # 시그널로 UI 업데이트 (메인 스레드에서 안전하게 처리)
                self.reprint_search_completed.emit(search_result, cancel_flag.cancelled)
                
            except Exception as e:
                self._add_log(f"[REPRINT-SEARCH] 검색 오류: {str(e)}")
                self.reprint_search_btn.setEnabled(True)
                self.reprint_cancel_btn.setEnabled(False)
        
        thread = threading.Thread(target=search_thread, daemon=True)
        thread.start()
    
    @Slot()
    def _on_reprint_cancel(self):
        """재출력 검색 중단"""
        if hasattr(self, '_reprint_cancel_flag'):
            self._reprint_cancel_flag.cancelled = True
            self._reprint_search_cancelled = True
            self._add_log("[REPRINT-SEARCH] 검색 중단 요청")
        
        self.reprint_search_btn.setEnabled(True)
        self.reprint_cancel_btn.setEnabled(False)
        self.reprint_execute_btn.setEnabled(False)
    
    @Slot(object, bool)
    def _on_reprint_search_completed(self, search_result, cancelled):
        """재출력 검색 완료 처리 (시그널 핸들러)"""
        if cancelled:
            self._add_log("[REPRINT-SEARCH] 검색이 취소되었습니다.")
            self.reprint_status_label.setText("⏹ 검색 취소됨")
            self.reprint_status_label.setStyleSheet("color: #FF9800; font-size: 11px; padding: 5px;")
            self.reprint_search_btn.setEnabled(True)
            self.reprint_cancel_btn.setEnabled(False)
            return
        
        input_value = self.reprint_input.text().strip()
        
        if search_result:
            self._reprint_search_result = search_result
            found_pdf_path = search_result.get("pdf_path")
            result_type = search_result.get("type")
            original_format = search_result.get("original", "")
            
            if result_type == "tracking":
                tracking_no = search_result.get("tracking_no")
                # 원본 형식이 있으면 표시
                format_info = f" (원본 형식: {original_format})" if original_format else ""
                self._add_log(f"[REPRINT-SEARCH] ✓ 송장번호 '{tracking_no}' 찾았습니다!{format_info}")
                self._add_log(f"[REPRINT-SEARCH] 파일: {Path(found_pdf_path).name}")
                self._add_log(f"[REPRINT-SEARCH] 경로: {found_pdf_path}")
                
                # 검색 성공 상태 표시 및 알러트
                self.reprint_status_label.setText(f"✅ 검색 성공! 송장번호 '{tracking_no}' 찾았습니다.")
                self.reprint_status_label.setStyleSheet("color: #4CAF50; font-size: 11px; padding: 5px; font-weight: bold;")
                
                QMessageBox.information(
                    self,
                    "검색 성공",
                    f"송장번호를 찾았습니다!\n\n"
                    f"송장번호: {tracking_no}\n"
                    f"파일: {Path(found_pdf_path).name}\n"
                    f"경로: {found_pdf_path}\n\n"
                    f"재출력 버튼을 클릭하여 출력하세요."
                )
            elif result_type == "order":
                order_no = search_result.get("order_no")
                format_info = f" (원본 형식: {original_format})" if original_format else ""
                self._add_log(f"[REPRINT-SEARCH] ✓ 주문번호 '{order_no}' 찾았습니다!{format_info}")
                self._add_log(f"[REPRINT-SEARCH] 파일: {Path(found_pdf_path).name}")
                self._add_log(f"[REPRINT-SEARCH] 경로: {found_pdf_path}")
                
                # 검색 성공 상태 표시 및 알러트
                self.reprint_status_label.setText(f"✅ 검색 성공! 주문번호 '{order_no}' 찾았습니다.")
                self.reprint_status_label.setStyleSheet("color: #4CAF50; font-size: 11px; padding: 5px; font-weight: bold;")
                
                QMessageBox.information(
                    self,
                    "검색 성공",
                    f"주문번호를 찾았습니다!\n\n"
                    f"주문번호: {order_no}\n"
                    f"파일: {Path(found_pdf_path).name}\n"
                    f"경로: {found_pdf_path}\n\n"
                    f"재출력 버튼을 클릭하여 출력하세요."
                )
            
            # 재출력 버튼 활성화
            self.reprint_execute_btn.setEnabled(True)
            self._add_log("[REPRINT-SEARCH] ✅ 검색 완료! 재출력 버튼을 클릭하여 출력하세요.")
        else:
            self._add_log(f"[REPRINT-SEARCH] 검색 실패: {input_value}를 찾을 수 없습니다.")
            self.reprint_status_label.setText(f"❌ 검색 실패: '{input_value}'를 찾을 수 없습니다.")
            self.reprint_status_label.setStyleSheet("color: #F44336; font-size: 11px; padding: 5px; font-weight: bold;")
            
            QMessageBox.warning(
                self,
                "검색 실패",
                f"재출력 대상이 존재하지 않습니다.\n\n"
                f"입력값: {input_value}\n\n"
                f"확인 사항:\n"
                f"- 송장번호/주문번호가 정확한지 확인\n"
                f"- PDF 파일이 선택한 폴더에 있는지 확인\n"
                f"- 하이픈(-) 포함 여부 확인"
            )
        
        # UI 상태 복원
        self.reprint_search_btn.setEnabled(True)
        self.reprint_cancel_btn.setEnabled(False)
    
    @Slot()
    def _on_reprint_execute(self):
        """재출력 실행 (검색 결과 사용)"""
        if not self._reprint_search_result:
            QMessageBox.warning(self, "경고", "먼저 검색을 실행해주세요.")
            return
        
        search_result = self._reprint_search_result
        
        # 검색 결과에서 정보 추출
        found_pdf_path = search_result.get("pdf_path")
        result_type = search_result.get("type")
        
        tracking_no = None
        
        if result_type == "tracking":
            tracking_no = search_result.get("tracking_no")
            self._add_log(f"[REPRINT-MANUAL] 송장번호: {tracking_no} (파일: {Path(found_pdf_path).name})")
        elif result_type == "order":
            order_no = search_result.get("order_no")
            self._add_log(f"[REPRINT-MANUAL] 주문번호: {order_no} (파일: {Path(found_pdf_path).name})")
            
            # 주문번호로 tracking_no 찾기 시도
            if self.excel_loader.df is not None:
                tracking_no = self.excel_loader.find_tracking_by_order_no(order_no)
                if tracking_no:
                    self._add_log(f"[REPRINT-MANUAL] 주문번호 {order_no} → 송장번호 {tracking_no}")
                else:
                    # 엑셀에 없어도 PDF 파일명에서 추출 시도
                    pdf_name = Path(found_pdf_path).stem
                    # PDF 파일명이 송장번호일 수 있음
                    tracking_no = pdf_name
        
        # 출력 옵션 확인
        print_label = self.reprint_label_check.isChecked()
        print_order = self.reprint_order_check.isChecked()
        
        if not print_label and not print_order:
            QMessageBox.warning(self, "경고", "출력할 항목을 하나 이상 선택해주세요.")
            return
        
        # 프린터 설정 로드
        settings = load_printer_settings()
        label_printer = settings.get("label_printer")
        a4_printer = settings.get("a4_printer")
        
        success_count = 0
        fail_count = 0
        
        # 송장(라벨) 출력
        if print_label:
            # 검색된 PDF 경로 사용 또는 선택된 폴더에서 시도
            label_path = None
            label_folder = self.reprint_label_folder_edit.text().strip() or "labels"
            
            if found_pdf_path and label_folder in found_pdf_path:
                # 검색된 PDF가 선택된 폴더에 있으면 사용
                label_path = Path(found_pdf_path)
            else:
                # 선택된 폴더에서 파일 찾기
                label_path = Path(label_folder) / f"{tracking_no}.pdf"
                if not label_path.exists():
                    # 검색된 PDF가 있으면 그것 사용
                    if found_pdf_path:
                        label_path = Path(found_pdf_path)
            
            if label_path and label_path.exists():
                # 2페이지 감지 및 추출
                extract_result = extract_pages_from_pdf(label_path, tracking_no)
                
                if extract_result:
                    temp_pdf_path, page_count = extract_result
                    self._add_log(f"[REPRINT-MANUAL] 송장 {page_count}장 추출 완료: {tracking_no}")
                    
                    if label_printer:
                        success = print_pdf_with_printer(str(temp_pdf_path), label_printer)
                    else:
                        success = print_pdf_with_printer(str(temp_pdf_path), None)
                    
                    if success:
                        printer_display = label_printer if label_printer else "기본 프린터"
                        self._add_log(f"[REPRINT-MANUAL] 송장 출력 성공: {tracking_no} ({page_count}장) → {printer_display}")
                        success_count += 1
                    else:
                        self._add_log(f"[REPRINT-MANUAL] 송장 출력 실패: {tracking_no}")
                        fail_count += 1
                    
                    # 임시 파일 삭제 (keep_temp_files 설정 확인)
                    if not self.pdf_printer.keep_temp_files and temp_pdf_path.exists():
                        try:
                            temp_pdf_path.unlink()
                        except:
                            pass
                else:
                    # 추출 실패 시 원본 파일 직접 출력
                    if label_printer:
                        success = print_pdf_with_printer(str(label_path), label_printer)
                    else:
                        success = print_pdf_with_printer(str(label_path), None)
                    
                    if success:
                        printer_display = label_printer if label_printer else "기본 프린터"
                        self._add_log(f"[REPRINT-MANUAL] 송장 출력 성공: {tracking_no} (원본 파일) → {printer_display}")
                        success_count += 1
                    else:
                        self._add_log(f"[REPRINT-MANUAL] 송장 출력 실패: {tracking_no}")
                        fail_count += 1
            else:
                self._add_log(f"[REPRINT-MANUAL] 송장 PDF 파일 없음: {tracking_no}")
                fail_count += 1
        
        # 주문서(A4) 출력
        if print_order:
            # 검색된 PDF 경로 사용 또는 선택된 폴더에서 시도
            order_path = None
            order_folder = self.reprint_order_folder_edit.text().strip() or "orders"
            
            if found_pdf_path and order_folder in found_pdf_path:
                # 검색된 PDF가 선택된 폴더에 있으면 사용
                order_path = Path(found_pdf_path)
            else:
                # 선택된 폴더에서 파일 찾기
                order_path = Path(order_folder) / f"{tracking_no}.pdf"
                if not order_path.exists():
                    # 검색된 PDF가 있으면 그것 사용
                    if found_pdf_path:
                        order_path = Path(found_pdf_path)
            
            if order_path and order_path.exists():
                # 주문서는 크롭 없이 원본 전체 사용
                temp_pdf_path = extract_reprint_page_to_temp(
                    order_path,
                    tracking_no,
                    is_order_sheet=True,
                    keep_temp_files=self.pdf_printer.keep_temp_files
                )
                
                if temp_pdf_path:
                    self._add_log(f"[REPRINT-MANUAL] 주문서 추출 완료: {tracking_no} (크롭 없음, 원본 전체)")
                    
                    if a4_printer:
                        success = print_pdf_with_printer(str(temp_pdf_path), a4_printer)
                    else:
                        success = print_pdf_with_printer(str(temp_pdf_path), None)
                    
                    if success:
                        printer_display = a4_printer if a4_printer else "기본 프린터"
                        self._add_log(f"[REPRINT-MANUAL] 주문서 출력 성공: {tracking_no} → {printer_display}")
                        success_count += 1
                    else:
                        self._add_log(f"[REPRINT-MANUAL] 주문서 출력 실패: {tracking_no}")
                        fail_count += 1
                    
                    # 임시 파일 삭제 (keep_temp_files 설정 확인)
                    if not self.pdf_printer.keep_temp_files and temp_pdf_path.exists():
                        try:
                            temp_pdf_path.unlink()
                        except:
                            pass
                else:
                    # 추출 실패 시 원본 파일 직접 출력
                    if a4_printer:
                        success = print_pdf_with_printer(str(order_path), a4_printer)
                    else:
                        success = print_pdf_with_printer(str(order_path), None)
                    
                    if success:
                        printer_display = a4_printer if a4_printer else "기본 프린터"
                        self._add_log(f"[REPRINT-MANUAL] 주문서 출력 성공: {tracking_no} (원본 파일) → {printer_display}")
                        success_count += 1
                    else:
                        self._add_log(f"[REPRINT-MANUAL] 주문서 출력 실패: {tracking_no}")
                        fail_count += 1
            else:
                self._add_log(f"[REPRINT-MANUAL] 주문서 PDF 파일 없음: {tracking_no}")
                fail_count += 1
        
        # 최종 로그
        input_value = self.reprint_input.text().strip()
        self._add_log(
            f"[REPRINT-MANUAL] 완료 - "
            f"input={input_value}, "
            f"resolved_tracking={tracking_no}, "
            f"label={print_label}, "
            f"order={print_order}, "
            f"success={success_count}, "
            f"fail={fail_count}"
        )
        
        # 결과 메시지
        if fail_count == 0:
            QMessageBox.information(
                self,
                "재출력 완료",
                f"재출력이 완료되었습니다.\n\n"
                f"송장번호: {tracking_no}\n"
                f"성공: {success_count}건"
            )
        elif success_count > 0:
            QMessageBox.warning(
                self,
                "재출력 부분 실패",
                f"일부 출력이 실패했습니다.\n\n"
                f"송장번호: {tracking_no}\n"
                f"성공: {success_count}건\n"
                f"실패: {fail_count}건"
            )
        else:
            QMessageBox.critical(
                self,
                "재출력 실패",
                f"모든 출력이 실패했습니다.\n\n"
                f"송장번호: {tracking_no}\n"
                f"실패: {fail_count}건\n\n"
                f"확인 사항:\n"
                f"- PDF 파일이 존재하는지 확인\n"
                f"- 프린터 설정이 올바른지 확인"
            )
        
        # 입력 필드 초기화 (선택사항)
        # self.reprint_input.clear()
    
    def _create_top_section(self) -> QGroupBox:
        """상단 섹션: 작업 옵션 (파일 설정은 설정 탭에서)"""
        group = QGroupBox("작업 옵션")
        layout = QHBoxLayout(group)
        layout.setSpacing(10)
        
        # 설정 탭 이동 버튼
        settings_btn = QPushButton("⚙️ 파일/차수/프린터 설정")
        settings_btn.setStyleSheet("background-color: #607D8B; color: white; font-weight: bold;")
        settings_btn.setToolTip("엑셀, PDF 파일 선택, 업체/차수 관리, 프린터 설정은 설정 탭에서 관리합니다")
        settings_btn.clicked.connect(self._on_go_to_settings_tab)
        layout.addWidget(settings_btn)
        
        layout.addSpacing(10)
        
        # 구성 요약 버튼
        self.summary_btn = QPushButton("📦 구성요약")
        self.summary_btn.clicked.connect(self._on_show_summary)
        layout.addWidget(self.summary_btn)
        
        # 호환성 유지용 숨김 버튼
        self.supplier_btn = QPushButton()
        self.supplier_btn.clicked.connect(self._on_change_supplier)
        self.supplier_btn.hide()
        
        layout.addStretch()
        
        # ===== 숨김 위젯 (설정 탭으로 이동됨, 호환성 유지용) =====
        # EzAuto 창 제목
        self.ezauto_title_edit = QLineEdit()
        self.ezauto_title_edit.setText("이지오토")
        self.ezauto_title_edit.textChanged.connect(self._on_ezauto_title_changed)
        self.ezauto_title_edit.hide()
        
        # EzAuto 활성화
        self.ezauto_check = QCheckBox("EzAuto 입력")
        self.ezauto_check.setChecked(True)
        self.ezauto_check.toggled.connect(self._on_toggle_ezauto)
        self.ezauto_check.hide()
        
        # PDF 출력 활성화
        self.pdf_check = QCheckBox("PDF 출력")
        self.pdf_check.setChecked(True)
        self.pdf_check.toggled.connect(self._on_toggle_pdf)
        self.pdf_check.hide()
        
        # PDF 임시 파일 보관 옵션
        self.pdf_keep_temp_check = QCheckBox("임시 파일 보관")
        self.pdf_keep_temp_check.setChecked(False)
        self.pdf_keep_temp_check.toggled.connect(self._on_toggle_pdf_keep_temp)
        self.pdf_keep_temp_check.hide()
        
        # 주문서 출력 기능
        self.order_sheet_check = QCheckBox("주문서출력")
        self.order_sheet_check.setChecked(False)
        self.order_sheet_check.toggled.connect(self._on_toggle_order_sheet)
        self.order_sheet_check.hide()
        
        # ===== 숨김 위젯 (호환성 유지용) =====
        hidden_widget = QWidget()
        hidden_layout = QHBoxLayout(hidden_widget)
        hidden_layout.setContentsMargins(0, 0, 0, 0)
        
        self.excel_path_edit = QLineEdit()
        self.pdf_path_edit = QLineEdit()
        self.pdf_path_2_edit = QLineEdit()
        self.browse_btn = QPushButton()
        self.browse_btn.clicked.connect(self._on_browse_excel)
        self.load_btn = QPushButton()
        self.load_btn.clicked.connect(self._on_load_excel)
        self.pdf_browse_btn = QPushButton()
        self.pdf_browse_btn.clicked.connect(self._on_browse_pdf_file)
        self.pdf_browse_2_btn = QPushButton()
        self.pdf_browse_2_btn.clicked.connect(self._on_browse_pdf_file_2)
        
        hidden_layout.addWidget(self.excel_path_edit)
        hidden_layout.addWidget(self.pdf_path_edit)
        hidden_layout.addWidget(self.pdf_path_2_edit)
        hidden_layout.addWidget(self.browse_btn)
        hidden_layout.addWidget(self.load_btn)
        hidden_layout.addWidget(self.pdf_browse_btn)
        hidden_layout.addWidget(self.pdf_browse_2_btn)
        hidden_widget.hide()
        layout.addWidget(hidden_widget)
        
        return group
    
    def _create_priority_section(self) -> QWidget:
        """우선순위 설정 섹션 (우선순위 설정 + 우선 송장 관리 + 제외 송장 관리)"""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 우선순위 설정 패널
        priority_group = self._create_priority_panel()
        layout.addWidget(priority_group, 1)
        
        # 우선 송장 추가 패널
        priority_tracking_group = self._create_priority_tracking_panel()
        layout.addWidget(priority_tracking_group, 1)
        
        # 제외 송장 관리 패널
        exclude_tracking_group = self._create_exclude_tracking_panel()
        layout.addWidget(exclude_tracking_group, 1)
        
        return widget
    
    def _create_priority_panel(self) -> QGroupBox:
        """우선순위 설정 패널"""
        group = QGroupBox("우선순위 설정")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)
        layout.setContentsMargins(8, 15, 8, 8)
        
        # 상호 배타적 옵션을 라디오 버튼으로 구성
        grid = QGridLayout()
        grid.setSpacing(8)
        
        # 1. 단품/조합 선택 (라디오 버튼 그룹)
        single_combo_group = QButtonGroup(group)
        single_combo_layout = QHBoxLayout()
        single_combo_layout.addWidget(QLabel("품목 유형:"))
        
        self.priority_single_radio = QRadioButton("단품 우선")
        self.priority_single_radio.setChecked(True)  # 기본값: 단품 우선
        self.priority_single_radio.toggled.connect(self._on_priority_changed)
        single_combo_group.addButton(self.priority_single_radio, 0)
        single_combo_layout.addWidget(self.priority_single_radio)
        
        self.priority_combo_radio = QRadioButton("조합 우선")
        self.priority_combo_radio.setChecked(False)
        self.priority_combo_radio.toggled.connect(self._on_priority_changed)
        single_combo_group.addButton(self.priority_combo_radio, 1)
        single_combo_layout.addWidget(self.priority_combo_radio)
        
        # 유형 무관 옵션 추가
        self.priority_no_type_radio = QRadioButton("유형 무관")
        self.priority_no_type_radio.setChecked(False)
        self.priority_no_type_radio.toggled.connect(self._on_priority_changed)
        single_combo_group.addButton(self.priority_no_type_radio, 2)
        single_combo_layout.addWidget(self.priority_no_type_radio)
        
        single_combo_layout.addStretch()
        grid.addLayout(single_combo_layout, 0, 0, 1, 2)
        
        # 2. 수량 선택 (라디오 버튼 그룹)
        qty_group = QButtonGroup(group)
        qty_layout = QHBoxLayout()
        qty_layout.addWidget(QLabel("수량 기준:"))
        
        self.priority_small_qty_radio = QRadioButton("소량 우선")
        self.priority_small_qty_radio.setChecked(False)
        self.priority_small_qty_radio.toggled.connect(self._on_priority_changed)
        qty_group.addButton(self.priority_small_qty_radio, 0)
        qty_layout.addWidget(self.priority_small_qty_radio)
        
        self.priority_large_qty_radio = QRadioButton("대량 우선")
        self.priority_large_qty_radio.setChecked(False)
        self.priority_large_qty_radio.toggled.connect(self._on_priority_changed)
        qty_group.addButton(self.priority_large_qty_radio, 1)
        qty_layout.addWidget(self.priority_large_qty_radio)
        
        # 선택 안 함 옵션 추가
        self.priority_no_qty_radio = QRadioButton("수량 무관")
        self.priority_no_qty_radio.setChecked(True)  # 기본값: 수량 무관
        self.priority_no_qty_radio.toggled.connect(self._on_priority_changed)
        qty_group.addButton(self.priority_no_qty_radio, 2)
        qty_layout.addWidget(self.priority_no_qty_radio)
        
        qty_layout.addStretch()
        grid.addLayout(qty_layout, 1, 0, 1, 2)
        
        # 3. 주문 시간 선택 (라디오 버튼 그룹)
        order_time_group = QButtonGroup(group)
        order_time_layout = QHBoxLayout()
        order_time_layout.addWidget(QLabel("주문 시간:"))
        
        self.priority_old_order_radio = QRadioButton("오래된 주문 우선")
        self.priority_old_order_radio.setChecked(False)
        self.priority_old_order_radio.toggled.connect(self._on_priority_changed)
        order_time_group.addButton(self.priority_old_order_radio, 0)
        order_time_layout.addWidget(self.priority_old_order_radio)
        
        self.priority_new_order_radio = QRadioButton("최신 주문 우선")
        self.priority_new_order_radio.setChecked(False)
        self.priority_new_order_radio.toggled.connect(self._on_priority_changed)
        order_time_group.addButton(self.priority_new_order_radio, 1)
        order_time_layout.addWidget(self.priority_new_order_radio)
        
        # 선택 안 함 옵션 추가
        self.priority_no_time_radio = QRadioButton("시간 무관")
        self.priority_no_time_radio.setChecked(True)  # 기본값: 시간 무관
        self.priority_no_time_radio.toggled.connect(self._on_priority_changed)
        order_time_group.addButton(self.priority_no_time_radio, 2)
        order_time_layout.addWidget(self.priority_no_time_radio)
        
        order_time_layout.addStretch()
        grid.addLayout(order_time_layout, 2, 0, 1, 2)
        
        layout.addLayout(grid)
        
        # 프리셋 버튼 영역
        preset_layout = QHBoxLayout()
        preset_layout.setSpacing(5)
        
        self.preset_default_btn = QPushButton("📌 기본(단품 우선)")
        self.preset_default_btn.setMaximumHeight(30)
        self.preset_default_btn.clicked.connect(lambda: self._apply_preset("default"))
        preset_layout.addWidget(self.preset_default_btn)
        
        self.preset_backlog_btn = QPushButton("📋 밀린 주문 정리")
        self.preset_backlog_btn.setMaximumHeight(30)
        self.preset_backlog_btn.clicked.connect(lambda: self._apply_preset("backlog"))
        preset_layout.addWidget(self.preset_backlog_btn)
        
        self.preset_bulk_btn = QPushButton("📦 대량 소화")
        self.preset_bulk_btn.setMaximumHeight(30)
        self.preset_bulk_btn.clicked.connect(lambda: self._apply_preset("bulk"))
        preset_layout.addWidget(self.preset_bulk_btn)
        
        layout.addLayout(preset_layout)
        
        # 초기 우선순위 규칙 적용
        self._apply_priority_rules()
        
        return group
    
    def _create_priority_tracking_panel(self) -> QGroupBox:
        """우선 송장 추가 패널 (방식 B: 직접 입력)"""
        group = QGroupBox("⭐ 우선 송장 관리")
        layout = QVBoxLayout(group)
        layout.setSpacing(5)
        layout.setContentsMargins(8, 15, 8, 8)
        
        # 입력 영역
        input_layout = QHBoxLayout()
        
        self.priority_tracking_input = QLineEdit()
        self.priority_tracking_input.setPlaceholderText("송장번호 입력/붙여넣기 (여러 개: 줄바꿈 또는 쉼표 구분)")
        self.priority_tracking_input.returnPressed.connect(self._on_add_priority_tracking)
        input_layout.addWidget(self.priority_tracking_input)
        
        add_btn = QPushButton("추가")
        add_btn.clicked.connect(self._on_add_priority_tracking)
        add_btn.setMaximumWidth(60)
        input_layout.addWidget(add_btn)
        
        remove_btn = QPushButton("해제")
        remove_btn.clicked.connect(self._on_remove_priority_tracking)
        remove_btn.setMaximumWidth(60)
        input_layout.addWidget(remove_btn)
        
        layout.addLayout(input_layout)
        
        # 우선 송장 목록
        list_label = QLabel("우선 송장 목록:")
        layout.addWidget(list_label)
        
        self.priority_tracking_list = QListWidget()
        self.priority_tracking_list.setMaximumHeight(100)
        self.priority_tracking_list.setSelectionMode(QListWidget.SingleSelection)
        layout.addWidget(self.priority_tracking_list)
        
        # 설명 텍스트
        help_label = QLabel("💡 여러 송장번호를 한 번에 입력 가능 (줄바꿈 또는 쉼표로 구분)")
        help_label.setStyleSheet("font-size: 9px; color: #666;")
        layout.addWidget(help_label)
        
        return group
    
    def _create_exclude_tracking_panel(self) -> QGroupBox:
        """제외 송장 관리 패널"""
        group = QGroupBox("🚫 제외 송장 관리")
        layout = QVBoxLayout(group)
        layout.setSpacing(5)
        layout.setContentsMargins(8, 15, 8, 8)
        
        # 입력 영역
        input_layout = QHBoxLayout()
        
        self.exclude_tracking_input = QLineEdit()
        self.exclude_tracking_input.setPlaceholderText("제외할 송장번호 입력 (여러 개: 줄바꿈 또는 쉼표 구분)")
        self.exclude_tracking_input.returnPressed.connect(self._on_add_exclude_tracking)
        input_layout.addWidget(self.exclude_tracking_input)
        
        add_btn = QPushButton("추가")
        add_btn.setStyleSheet("background-color: #FF5722; color: white;")
        add_btn.clicked.connect(self._on_add_exclude_tracking)
        add_btn.setMaximumWidth(60)
        input_layout.addWidget(add_btn)
        
        remove_btn = QPushButton("해제")
        remove_btn.clicked.connect(self._on_remove_exclude_tracking)
        remove_btn.setMaximumWidth(60)
        input_layout.addWidget(remove_btn)
        
        layout.addLayout(input_layout)
        
        # 제외 송장 목록
        list_label = QLabel("제외 송장 목록:")
        layout.addWidget(list_label)
        
        self.exclude_tracking_list = QListWidget()
        self.exclude_tracking_list.setMaximumHeight(100)
        self.exclude_tracking_list.setSelectionMode(QListWidget.SingleSelection)
        self.exclude_tracking_list.setStyleSheet("QListWidget { background-color: #FFEBEE; }")
        layout.addWidget(self.exclude_tracking_list)
        
        # 설명 텍스트
        help_label = QLabel("⚠️ 제외된 송장은 스캔해도 처리되지 않습니다")
        help_label.setStyleSheet("font-size: 9px; color: #D32F2F;")
        layout.addWidget(help_label)
        
        return group
    
    def _create_tables_section(self) -> QWidget:
        """테이블 섹션"""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setSpacing(10)
        
        # === 왼쪽: 현재 송장 상세 ===
        left_group = QGroupBox("현재 작업 중인 송장")
        left_layout = QVBoxLayout(left_group)
        
        # 현재 tracking_no 표시 + BIN 주소
        tracking_layout = QHBoxLayout()
        tracking_layout.addWidget(QLabel("송장번호:"))
        self.current_tracking_label = QLabel("-")
        self.current_tracking_label.setFont(QFont("Consolas", 14, QFont.Bold))
        self.current_tracking_label.setStyleSheet("color: #2196F3;")
        tracking_layout.addWidget(self.current_tracking_label)
        
        # BIN 주소 표시 패널 (여러 BIN 표시 가능)
        tracking_layout.addSpacing(20)
        bin_label = QLabel("BIN:")
        bin_label.setFont(QFont("", 12, QFont.Bold))
        tracking_layout.addWidget(bin_label)
        
        # BIN 컨테이너 (여러 BIN 배지를 담는 레이아웃)
        self.bin_container = QWidget()
        self.bin_layout = QHBoxLayout(self.bin_container)
        self.bin_layout.setContentsMargins(0, 0, 0, 0)
        self.bin_layout.setSpacing(8)
        
        # 초기 BIN 미지정 레이블
        self.current_bin_label = QLabel("BIN 미지정")
        self.current_bin_label.setFont(QFont("Consolas", 16, QFont.Bold))
        self.current_bin_label.setStyleSheet("""
            QLabel {
                color: #FFFFFF;
                background-color: #9E9E9E;
                padding: 6px 12px;
                border-radius: 6px;
            }
        """)
        self.current_bin_label.setAlignment(Qt.AlignCenter)
        self.bin_layout.addWidget(self.current_bin_label)
        
        tracking_layout.addWidget(self.bin_container)
        tracking_layout.addStretch()
        
        # 남은 수량
        tracking_layout.addWidget(QLabel("남은 수량:"))
        self.remaining_label = QLabel("0")
        self.remaining_label.setFont(QFont("Consolas", 14, QFont.Bold))
        self.remaining_label.setStyleSheet("color: #FF5722;")
        tracking_layout.addWidget(self.remaining_label)
        
        # 현재 송장 취소 버튼
        tracking_layout.addSpacing(20)
        self.cancel_current_tracking_btn = QPushButton("❌ 현재 송장 취소")
        self.cancel_current_tracking_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                font-weight: bold;
                padding: 6px 12px;
                border-radius: 4px;
                border: none;
            }
            QPushButton:hover {
                background-color: #d32f2f;
            }
            QPushButton:disabled {
                background-color: #ccc;
            }
        """)
        self.cancel_current_tracking_btn.setEnabled(False)
        self.cancel_current_tracking_btn.clicked.connect(self._on_cancel_current_tracking)
        tracking_layout.addWidget(self.cancel_current_tracking_btn)
        
        left_layout.addLayout(tracking_layout)
        
        # 상세 테이블 (BIN 컬럼 추가)
        self.detail_table = QTableWidget()
        self.detail_table.setColumnCount(7)
        self.detail_table.setHorizontalHeaderLabels([
            "상품명", "옵션명", "바코드", "필요수량", "스캔수량", "남은수량", "BIN"
        ])
        self.detail_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.detail_table.setAlternatingRowColors(True)
        left_layout.addWidget(self.detail_table)
        
        layout.addWidget(left_group, 1)  # 5:5 비율
        
        # === 오른쪽: 전체 요약 ===
        right_group = QGroupBox("📦 남은 수량")
        right_layout = QVBoxLayout(right_group)
        
        # 바코드 스캔 입력 (반응형 레이아웃)
        scan_group = QGroupBox("📦 바코드 스캔")
        scan_group.setStyleSheet("""
            QGroupBox {
                font-size: 12px;
                font-weight: bold;
                border: 2px solid #2196F3;
                border-radius: 8px;
                margin-top: 8px;
                padding: 8px;
                padding-top: 20px;
                background-color: #E3F2FD;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: #2196F3;
            }
        """)
        scan_group.setMaximumHeight(80)
        scan_layout = QHBoxLayout(scan_group)
        scan_layout.setContentsMargins(5, 5, 5, 5)
        scan_layout.setSpacing(5)
        
        self.manual_barcode_edit = QLineEdit()
        self.manual_barcode_edit.setPlaceholderText("바코드 스캔/입력")
        self.manual_barcode_edit.setFont(QFont("Arial", 12))
        self.manual_barcode_edit.setMinimumHeight(35)
        self.manual_barcode_edit.returnPressed.connect(self._on_manual_scan)
        scan_layout.addWidget(self.manual_barcode_edit, 1)
        
        self.manual_scan_btn = QPushButton("스캔")
        self.manual_scan_btn.setMinimumHeight(35)
        self.manual_scan_btn.setFixedWidth(60)
        self.manual_scan_btn.clicked.connect(self._on_manual_scan)
        scan_layout.addWidget(self.manual_scan_btn)
        
        right_layout.addWidget(scan_group)
        
        # 탭으로 구성별/제품별 구분
        from PySide6.QtWidgets import QTabWidget
        self.summary_tabs = QTabWidget()
        
        # 탭1: 구성별 요약
        self.combo_scroll = QScrollArea()
        self.combo_scroll.setWidgetResizable(True)
        self.combo_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.combo_scroll.setStyleSheet("QScrollArea { border: none; background-color: #f0f0f0; }")
        
        self.summary_container = QWidget()
        self.summary_grid = QVBoxLayout(self.summary_container)
        self.summary_grid.setSpacing(8)
        self.summary_grid.setAlignment(Qt.AlignTop)
        self.combo_scroll.setWidget(self.summary_container)
        
        self.summary_tabs.addTab(self.combo_scroll, "구성별")
        
        # 탭2: 제품별 요약
        self.product_scroll = QScrollArea()
        self.product_scroll.setWidgetResizable(True)
        self.product_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.product_scroll.setStyleSheet("QScrollArea { border: none; background-color: #f5f5f5; }")
        
        self.product_container = QWidget()
        self.product_grid = QVBoxLayout(self.product_container)
        self.product_grid.setSpacing(5)
        self.product_grid.setAlignment(Qt.AlignTop)
        self.product_scroll.setWidget(self.product_container)
        
        self.summary_tabs.addTab(self.product_scroll, "제품별")
        
        right_layout.addWidget(self.summary_tabs)
        
        layout.addWidget(right_group, 1)  # 5:5 비율
        
        return widget
    
    def _create_log_section(self) -> QGroupBox:
        """로그 섹션 (간소화됨 - 상세 설정은 설정 탭에서)"""
        group = QGroupBox("로그")
        layout = QVBoxLayout(group)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        self.log_text.setMaximumHeight(200)
        layout.addWidget(self.log_text)
        
        # 로그 제어 버튼
        btn_layout = QHBoxLayout()
        
        clear_log_btn = QPushButton("로그 지우기")
        clear_log_btn.clicked.connect(lambda: self.log_text.clear())
        btn_layout.addWidget(clear_log_btn)
        
        btn_layout.addSpacing(20)
        
        # 설정 탭 이동 버튼
        settings_tab_btn = QPushButton("⚙️ 설정 탭 열기")
        settings_tab_btn.setToolTip("프린터 설정, BIN 설정, 저장 위치 등은 설정 탭에서 관리합니다")
        settings_tab_btn.setStyleSheet("background-color: #607D8B; color: white;")
        settings_tab_btn.clicked.connect(self._on_go_to_settings_tab)
        btn_layout.addWidget(settings_tab_btn)
        
        btn_layout.addStretch()
        
        # ===== 숨김 위젯 (호환성 유지용) =====
        # 기존 코드에서 참조하므로 위젯은 생성하되 숨김 처리
        hidden_widget = QWidget()
        hidden_layout = QHBoxLayout(hidden_widget)
        hidden_layout.setContentsMargins(0, 0, 0, 0)
        
        self.label_printer_combo = QComboBox()
        self.a4_printer_combo = QComboBox()
        self.rotation_combo = QComboBox()
        self.rotation_combo.addItems(["0°", "90°", "180°", "270°"])
        self.rotation_combo.currentIndexChanged.connect(self._on_rotation_change)
        self.save_path_edit = QLineEdit()
        self.open_pdf_btn = QPushButton()
        self.open_pdf_btn.clicked.connect(self._on_open_picking_pdf)
        self.open_pdf_btn.setEnabled(False)
        
        hidden_layout.addWidget(self.label_printer_combo)
        hidden_layout.addWidget(self.a4_printer_combo)
        hidden_layout.addWidget(self.rotation_combo)
        hidden_layout.addWidget(self.save_path_edit)
        hidden_layout.addWidget(self.open_pdf_btn)
        hidden_widget.hide()
        layout.addWidget(hidden_widget)
        
        # 회전 설정 로드 및 콤보박스 선택
        self._update_rotation_combo()
        
        # 마지막 저장된 PDF 경로
        self._last_pdf_path = None
        
        layout.addLayout(btn_layout)
        
        return group
    
    def _on_go_to_settings_tab(self):
        """설정 탭으로 이동"""
        # 설정 탭 인덱스 찾기
        for i in range(self.tab_widget.count()):
            if "설정" in self.tab_widget.tabText(i):
                self.tab_widget.setCurrentIndex(i)
                break
    
    def _create_status_bar(self):
        """상태바 생성"""
        status = self.statusBar()
        
        self.status_scanner = QLabel("스캐너: 대기")
        self.status_file = QLabel("파일: 없음")
        self.status_count = QLabel("처리: 0건")
        
        status.addWidget(self.status_scanner)
        status.addWidget(QLabel(" | "))
        status.addWidget(self.status_file)
        status.addWidget(QLabel(" | "))
        status.addWidget(self.status_count)
    
    def _apply_styles(self):
        """스타일 적용"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f5f5;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #ddd;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
                background-color: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QTableWidget {
                border: 1px solid #ddd;
                border-radius: 4px;
                gridline-color: #eee;
            }
            QTableWidget::item {
                padding: 5px;
            }
            QTableWidget::item:selected {
                background-color: #2196F3;
                color: white;
            }
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:pressed {
                background-color: #0D47A1;
            }
            QPushButton:checked {
                background-color: #4CAF50;
            }
            QPushButton:disabled {
                background-color: #BDBDBD;
            }
            QLineEdit {
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 6px;
            }
            QLineEdit:focus {
                border-color: #2196F3;
            }
            QTextEdit {
                border: 1px solid #ddd;
                border-radius: 4px;
                background-color: #1e1e1e;
                color: #d4d4d4;
            }
            QCheckBox {
                spacing: 5px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
        """)
    
    def _connect_signals(self):
        """시그널 연결"""
        # Excel 시그널
        self.excel_loader.data_loaded.connect(self._on_data_loaded)
        self.excel_loader.data_updated.connect(self._on_data_updated)
        self.excel_loader.error_occurred.connect(self._on_error)
        self.excel_loader.priority_cleared.connect(self._on_priority_cleared)
        
        # Scanner 시그널
        self.scanner.barcode_scanned.connect(self._on_barcode_scanned)
        self.scanner.status_changed.connect(self._add_log)
        
        # EzAuto 시그널
        self.ezauto.input_success.connect(self._add_log)
        self.ezauto.input_error.connect(self._on_error)
        
        # PDF 시그널
        self.pdf_printer.print_success.connect(self._add_log)
        self.pdf_printer.print_error.connect(self._on_error)
        self.pdf_printer.index_updated.connect(self._on_pdf_indexed)
        
        # 탭 전환 시그널 - 전체피킹 탭 정보 업데이트
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        
        # Processor 시그널 (여기서 한 번만 연결)
        self.processor.scan_processed.connect(self._on_scan_processed)
        self.processor.tracking_completed.connect(self._on_tracking_completed)
        self.processor.ui_update_required.connect(self._update_tables)
        self.processor.log_message.connect(self._add_log)
        self.processor.scanner_pause.connect(self.scanner.pause)
        self.processor.scanner_resume.connect(self.scanner.resume)
    
    @Slot(int)
    def _on_pdf_indexed(self, count: int):
        """PDF 인덱싱 완료"""
        if count > 0:
            self._add_log(f"PDF 인덱스: {count}개 송장번호")
            # 상태 표시 업데이트
            if hasattr(self, 'status_pdf'):
                self.status_pdf.setText(f"PDF: {count}개")
                self.status_pdf.setStyleSheet("color: green;")
        else:
            self._add_log("⚠️ [경고] PDF에서 송장번호를 찾지 못했습니다!")
            self._add_log("   → PDF 파일이 텍스트 선택 가능한 형식인지 확인하세요.")
            self._add_log("   → 또는 '📑 PDF 재스캔' 버튼을 눌러 다시 시도하세요.")
            if hasattr(self, 'status_pdf'):
                self.status_pdf.setText("PDF: 인덱스 없음")
                self.status_pdf.setStyleSheet("color: red;")
    
    @Slot(int)
    def _on_tab_changed(self, index: int):
        """탭 전환 이벤트 - 각 탭의 스캔 입력에 포커스"""
        # 탭 순서: 출고(0), 전체피킹(1), 미리피킹(2), 재출력(3), ESP32(4), 설정(5)
        
        # ESP32 모드 전환 처리
        self._handle_esp32_mode_switch(index)
        
        # 출고 탭 (인덱스 0)
        if index == 0:
            QTimer.singleShot(100, lambda: self.manual_barcode_edit.setFocus())
        # 전체피킹 탭 (인덱스 1)
        elif index == 1:
            self._update_fp_session_info()
            if hasattr(self, 'fp_barcode_input'):
                QTimer.singleShot(100, lambda: self.fp_barcode_input.setFocus())
        # 미리피킹 탭 (인덱스 2)
        elif index == 2:
            self._update_pp_session_info()
            QTimer.singleShot(100, lambda: self.pp_order_input.setFocus())
        # 재출력 탭 (인덱스 3)
        elif index == 3:
            QTimer.singleShot(100, lambda: self.reprint_input.setFocus())
    
    def _handle_esp32_mode_switch(self, tab_index: int):
        """탭 전환 시 ESP32 모드 전환 처리"""
        if not self.esp32_transport.is_running:
            return
        
        # 출고 탭(0)으로 전환
        if tab_index == 0:
            # 전체피킹, 미리피킹 LCD 모두 OFF
            self._turn_off_fullpick_lcds()
            self._turn_off_prepick_lcds()
            # 출고 모드에 활성 송장이 있으면 LCD 다시 표시
            if self.processor.current_tracking_no and self.processor._active_bins:
                self.processor._send_remaining_bins_display(
                    self.processor.current_tracking_no, 
                    exclude_barcode=None
                )
                self._add_esp32_log("[모드전환] 출고 모드 LCD 활성화")
        
        # 전체피킹 탭(1)으로 전환
        elif tab_index == 1:
            # 출고, 미리피킹 LCD 모두 OFF
            self._turn_off_shipment_lcds()
            self._turn_off_prepick_lcds()
            # 전체피킹에 활성 세션이 있으면 LCD 다시 표시
            if self.full_pick_engine.current_session:
                self.full_pick_engine._send_display_to_all_bins()
                self._add_esp32_log("[모드전환] 전체피킹 LCD 활성화")
        
        # 미리피킹 탭(2)으로 전환
        elif tab_index == 2:
            # 출고, 전체피킹 LCD 모두 OFF
            self._turn_off_shipment_lcds()
            self._turn_off_fullpick_lcds()
            # 미리피킹 활성 슬롯 LCD 다시 표시
            self.pre_pick_engine._update_all_lcd_displays()
            self._add_esp32_log("[모드전환] 미리피킹 LCD 활성화")
        
        # 다른 탭으로 전환 시 모든 LCD OFF
        elif tab_index not in [0, 1, 2, 4]:  # 출고, 전체피킹, 미리피킹, ESP32 탭 제외
            self._turn_off_all_lcds()
    
    def _turn_off_shipment_lcds(self):
        """출고 모드 모든 LCD OFF"""
        if not hasattr(self.processor, '_active_bins'):
            return
        
        for bin_id in list(self.processor._active_bins):
            device_id = self.device_registry.get_device_id_by_bin(bin_id)
            if device_id:
                self.esp32_transport.send_off(device_id, bin_id)
        
        # active_bins 리스트도 정리
        self.processor._active_bins.clear()
    
    def _turn_off_fullpick_lcds(self):
        """전체피킹 모든 LCD OFF"""
        if not self.full_pick_engine.current_session:
            return
        
        for bin_id, task in self.full_pick_engine.current_session.bins.items():
            if not task.done:
                device_id = self.device_registry.get_device_id_by_bin(bin_id)
                if device_id:
                    self.esp32_transport.send_off(device_id, bin_id)
    
    def _turn_off_prepick_lcds(self):
        """미리피킹 모든 LCD OFF"""
        for slot_id in range(1, self.pre_pick_engine.slot_manager.active_slot_count + 1):
            slot = self.pre_pick_engine.slot_manager.get_slot(slot_id)
            if slot and slot.state != SlotState.EMPTY:
                for bin_id in slot.bins.keys():
                    device_id = self.device_registry.get_device_id_by_bin(bin_id)
                    if device_id:
                        self.esp32_transport.send_off(device_id, bin_id)
    
    def _turn_off_all_lcds(self):
        """모든 LCD OFF"""
        self._turn_off_shipment_lcds()
        self._turn_off_fullpick_lcds()
        self._turn_off_prepick_lcds()
    
    # === 이벤트 핸들러 ===
    
    @Slot()
    def _on_browse_excel(self):
        """엑셀 파일 찾아보기"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "엑셀 파일 선택",
            "",
            "Excel Files (*.xls *.xlsx);;XLS Files (*.xls);;XLSX Files (*.xlsx);;All Files (*)"
        )
        if file_path:
            self.excel_path_edit.setText(file_path)
    
    @Slot()
    def _on_show_summary(self):
        """구성 요약 다이얼로그 표시"""
        if self.excel_loader.df is None:
            QMessageBox.warning(self, "경고", "먼저 엑셀 파일을 불러오세요.")
            return
        
        dialog = SummaryDialog(self.excel_loader.df, self)
        dialog.exec()
    
    @Slot()
    def _on_browse_pdf_file(self):
        """PDF 파일 찾아보기"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "PDF 라벨 파일 선택",
            "",
            "PDF Files (*.pdf);;All Files (*)"
        )
        if file_path:
            # PDF 크롭 처리
            try:
                import tempfile
                temp_dir = Path(tempfile.gettempdir()) / "auto_mach_labels"
                temp_dir.mkdir(exist_ok=True)
                
                # 크롭된 PDF 저장 경로
                original_path = Path(file_path)
                cropped_path = temp_dir / f"cropped_{original_path.stem}.pdf"
                
                self._add_log("PDF 크롭 처리 중... (168mm × 107mm)")
                normalize_pdf(file_path, str(cropped_path))
                self._add_log(f"✓ PDF 크롭 완료: {cropped_path}")
                
                # 크롭된 PDF 사용
                self.pdf_path_edit.setText(file_path)  # 원본 경로 표시
                self.pdf_printer.set_pdf_file(str(cropped_path))  # 크롭된 파일 사용
                self._add_log(f"PDF 파일 설정: {file_path} (크롭된 버전 사용)")
            except Exception as e:
                self._add_log(f"[오류] PDF 크롭 실패: {str(e)}. 원본 파일 사용.")
            self.pdf_path_edit.setText(file_path)
            self.pdf_printer.set_pdf_file(file_path)
            
            # 자동 인덱싱
            self._add_log("PDF 파일 스캔 중...")
            
            # 주문서 출력 활성화 시 두 번째 PDF도 인덱싱
            if self.order_sheet_check.isChecked():
                pdf_path_2 = self.pdf_path_2_edit.text().strip()
                if pdf_path_2:
                    self.pdf_printer.set_pdf_file_2(pdf_path_2)
            
            # 엑셀에서 송장번호 목록 가져오기 (이미지 PDF의 경우 순서대로 매핑)
            excel_tracking_numbers = None
            if self.excel_loader.df is not None and 'tracking_no' in self.excel_loader.df.columns:
                # 순서를 보장하기 위해 drop_duplicates 사용 (첫 번째 출현 순서 유지)
                excel_tracking_numbers = self.excel_loader.df['tracking_no'].drop_duplicates().tolist()
                self._add_log(f"엑셀 송장번호 순서: {', '.join(map(str, excel_tracking_numbers[:5]))}..." if len(excel_tracking_numbers) > 5 else f"엑셀 송장번호: {', '.join(map(str, excel_tracking_numbers))}")
            
            count = self.pdf_printer.build_tracking_index(excel_tracking_numbers)
            
            if count > 0:
                self._add_log(f"<b style='color:#4CAF50'>✓ PDF 스캔 완료: {count}개 송장번호 발견</b>", html=True)
            else:
                if excel_tracking_numbers:
                    self._add_log("[경고] PDF에서 송장번호를 찾지 못했습니다. 이미지 기반 PDF일 수 있습니다.")
                else:
                    self._add_log("[경고] PDF에서 송장번호를 찾지 못했습니다. 엑셀 파일을 먼저 로드하면 자동 매핑됩니다.")
    
    @Slot()
    def _on_load_excel(self):
        """엑셀 파일 로드 (업체 선택은 설정 탭에서)"""
        file_path = self.excel_path_edit.text().strip()
        if not file_path:
            QMessageBox.warning(self, "경고", "엑셀 파일 경로를 입력하세요.")
            return
        
        if self.excel_loader.load_excel(file_path):
            self._add_log(f"엑셀 파일 로드 성공: {file_path}")
            
            # 원본 데이터 저장 (업체 필터링 전)
            self.excel_loader.store_original_data()
            
            # 공급처(업체) 컬럼이 있는지 확인
            if self.excel_loader.has_supplier_column():
                supplier_summary = self.excel_loader.get_supplier_summary()
                
                if len(supplier_summary) > 1:
                    # 여러 업체가 있으면 설정 탭에서 차수 생성하도록 안내
                    self._add_log(f"[업체] {len(supplier_summary)}개 업체 발견: {', '.join([s['supplier'] for s in supplier_summary])}")
                    self._add_log(f"<b style='color:#3F51B5'>→ 설정 탭 > 차수 관리에서 업체를 선택하여 차수를 생성하세요.</b>", html=True)
                elif len(supplier_summary) == 1:
                    # 업체가 하나뿐이면 자동 선택
                    supplier = supplier_summary[0]["supplier"]
                    self._add_log(f"[업체] 단일 업체: '{supplier}' 자동 선택")
                else:
                    self._add_log("[업체] 공급처 데이터 없음")
            
            # 파일 상태 표시
            self.status_file.setText(f"파일: {Path(file_path).name}")
            
            # PDF 파일 처리만 수행 (BIN 배정과 세션 생성은 설정 탭에서)
            self._process_pdf_after_excel_load(file_path)
    
    def _process_pdf_after_excel_load(self, file_path: str):
        """엑셀 로드 후 PDF 처리만 수행"""
        # PDF 폴더 설정
        pdf_path = self.pdf_path_edit.text().strip()
        if pdf_path:
            self.pdf_printer.set_labels_directory(pdf_path)
        
        # PDF 파일이 설정되어 있으면 자동으로 스캔
        pdf_file_path = self.pdf_path_edit.text().strip()
        if pdf_file_path and os.path.exists(pdf_file_path):
            self.pdf_printer.set_pdf_file(pdf_file_path)
            self._add_log("PDF 스캔 중...")
            
            # 엑셀에서 송장번호 목록 가져오기 (순서 보장)
            excel_tracking_numbers = None
            if self.excel_loader.df is not None and 'tracking_no' in self.excel_loader.df.columns:
                excel_tracking_numbers = self.excel_loader.df['tracking_no'].drop_duplicates().tolist()
            
            count = self.pdf_printer.build_tracking_index(excel_tracking_numbers)
            
            if count > 0:
                self._add_log(f"<b style='color:#4CAF50'>✓ PDF 스캔 완료: {count}개 송장번호 발견</b>", html=True)
            else:
                self._add_log("[경고] PDF 스캔 실패: 송장번호를 찾지 못했습니다.")
        
        # 구성 요약 출력
        self._show_load_summary()
    
    def _process_after_supplier_selection(self, file_path: str):
        """업체 선택 후 실행되는 로직 (BIN 배정, PDF 스캔 등)"""
        # ====== 작업 차수 증가 및 업체명 저장 ======
        self._work_session += 1
        self._work_session_supplier = self.excel_loader.get_current_supplier() or "전체"
        self._add_log(f"<b style='color:#673AB7'>━━━ {self._work_session}차 피킹 작업 시작 [{self._work_session_supplier}] ━━━</b>", html=True)
        
        # ====== BIN 자동 배정 (엑셀 로드 시) ======
        # 0) BIN 설정 로드 및 적용
        bin_settings = load_bin_settings()
        self.bin_manager.set_config(
            max_qty_per_bin=bin_settings.get("max_qty_per_bin", 100),
            min_qty_threshold=bin_settings.get("min_qty_threshold", 10),
            max_sku_per_shared_bin=bin_settings.get("max_sku_per_shared_bin", 5),
            dedicated_qty_threshold=bin_settings.get("dedicated_qty_threshold", 0)
        )
        dedicated_qty = bin_settings.get("dedicated_qty_threshold", 0)
        dedicated_log = f", 중복금지={dedicated_qty}개 이상" if dedicated_qty > 0 else ""
        self._add_log(f"[BIN] 설정 적용: 최대수량={bin_settings.get('max_qty_per_bin', 100)}, "
                     f"소량기준={bin_settings.get('min_qty_threshold', 10)}이하, "
                     f"공유BIN 최대SKU={bin_settings.get('max_sku_per_shared_bin', 5)}{dedicated_log}")
        
        # 1) BIN 전체 리셋 (이전 업체의 모든 BIN 배정 초기화 - BIN-01부터 다시 시작)
        self.bin_manager.reset()
        self._add_log("<b style='color:#9C27B0'>[BIN] ✓ 모든 BIN 완전 초기화 (BIN-01부터 새로 배정)</b>", html=True)
        self._update_bin_display(["BIN 미지정"])
        
        # 제외 송장 목록 초기화 (새 작업 세션)
        self._excluded_tracking_numbers.clear()
        self._update_exclude_tracking_list()
        self._add_log("[제외] 제외 송장 목록 초기화됨")
        
        # 2) SKU별 BIN 자동 배정
        bin_count = self.bin_manager.assign_bins_from_dataframe(self.excel_loader.df)
        if bin_count > 0:
            # 통계 정보 가져오기
            stats = self.bin_manager.get_statistics()
            shared_bins = stats.get("shared_bins", 0)
            dedicated_bins = stats.get("dedicated_bins", 0)
            
            self._add_log(f"<b style='color:#2196F3'>[BIN] SKU별 BIN 자동 배정 완료: {bin_count}개 BIN 생성 "
                         f"(전용: {dedicated_bins}, 공유: {shared_bins})</b>", html=True)
            
            # BIN 배정 상세 로그 (확장 정보 포함)
            sku_bins = self.bin_manager.get_all_sku_bins()
            for item in sku_bins[:10]:  # 처음 10개만 로그
                barcode, bin_id, bin_num, sku_qty, is_shared = item
                shared_tag = " [공유]" if is_shared else ""
                self._add_log(f"  → {bin_id}{shared_tag}: {barcode} (수량: {sku_qty})")
            if len(sku_bins) > 10:
                self._add_log(f"  ... 외 {len(sku_bins) - 10}개")
        else:
            self._add_log("[BIN] SKU가 없어서 BIN 배정 건너뜀")
        
        # 3) 송장별 BIN 매핑 구축
        self.bin_manager.build_order_bin_map(self.excel_loader.df)
        order_bin_count = len(self.bin_manager.get_order_bin_map())
        self._add_log(f"[BIN] 송장별 BIN 매핑 완료: {order_bin_count}개 송장")
        
        # PDF 폴더 설정
        pdf_path = self.pdf_path_edit.text().strip()
        if pdf_path:
            self.pdf_printer.set_labels_directory(pdf_path)
        
        # PDF 파일이 설정되어 있으면 자동으로 다시 스캔 (이미지 PDF 매핑을 위해)
        pdf_file_path = self.pdf_path_edit.text().strip()
        if pdf_file_path and os.path.exists(pdf_file_path):
            self.pdf_printer.set_pdf_file(pdf_file_path)
            self._add_log("엑셀 로드 후 PDF 재스캔 중...")
            
            # 엑셀에서 송장번호 목록 가져오기 (순서 보장)
            excel_tracking_numbers = None
            if self.excel_loader.df is not None and 'tracking_no' in self.excel_loader.df.columns:
                # 순서를 보장하기 위해 drop_duplicates 사용 (첫 번째 출현 순서 유지)
                excel_tracking_numbers = self.excel_loader.df['tracking_no'].drop_duplicates().tolist()
                self._add_log(f"엑셀 송장번호 순서: {', '.join(map(str, excel_tracking_numbers[:5]))}..." if len(excel_tracking_numbers) > 5 else f"엑셀 송장번호: {', '.join(map(str, excel_tracking_numbers))}")
            
            count = self.pdf_printer.build_tracking_index(excel_tracking_numbers)
            
            if count > 0:
                self._add_log(f"<b style='color:#4CAF50'>✓ PDF 재스캔 완료: {count}개 송장번호 발견</b>", html=True)
            else:
                self._add_log("[경고] PDF 재스캔 실패: 송장번호를 찾지 못했습니다.")
        
        # 구성 요약 출력
        self._show_load_summary()
        
        # ====== 작업 세션 저장 ======
        order_count = self.excel_loader.get_filtered_order_count()
        sku_count = len(self.excel_loader.df['barcode'].unique()) if self.excel_loader.df is not None and 'barcode' in self.excel_loader.df.columns else 0
        bin_count = self.bin_manager.get_bin_count()
        
        # 현재 선택된 업체 목록
        suppliers = self.excel_loader.get_current_suppliers() or []
        supplier_display = self._work_session_supplier
        
        # SKU → BIN 매핑 스냅샷
        sku_bin_map = self.bin_manager.get_sku_bin_map()
        
        # 세션 생성 및 저장
        session = self.session_manager.create_session(
            suppliers=suppliers,
            supplier_display=supplier_display,
            order_count=order_count,
            sku_count=sku_count,
            bin_count=bin_count,
            mode="reverse_matching",
            sku_bin_map=sku_bin_map
        )
        
        self._add_log(f"<b style='color:#4CAF50'>[세션 저장] {session.session_id}차 작업 저장됨 ({supplier_display})</b>", html=True)
        
        # UI 업데이트
        self._update_session_display()
        self._update_session_combo()
        self._update_fp_session_info()
    
    @Slot()
    def _on_change_supplier(self):
        """업체(공급처) 변경 - 다중 선택 지원"""
        # 원본 데이터가 없으면 경고
        if self.excel_loader._df_original is None:
            QMessageBox.warning(self, "경고", "먼저 엑셀 파일을 불러오세요.")
            return
        
        # 공급처 컬럼이 없으면 경고
        if not self.excel_loader.has_supplier_column():
            QMessageBox.information(self, "알림", "엑셀 파일에 공급처(업체) 컬럼이 없습니다.")
            return
        
        # 업체 목록 가져오기
        supplier_summary = self.excel_loader.get_supplier_summary()
        
        if not supplier_summary:
            QMessageBox.information(self, "알림", "공급처 데이터가 없습니다.")
            return
        
        if len(supplier_summary) <= 1:
            QMessageBox.information(self, "알림", "변경할 수 있는 다른 업체가 없습니다.")
            return
        
        # 현재 선택된 업체 리스트 가져오기
        current_suppliers = self.excel_loader.get_current_suppliers() or []
        
        # 업체 선택 다이얼로그 표시 (현재 선택 상태 전달)
        dialog = SupplierSelectDialog(supplier_summary, self, current_suppliers)
        if dialog.exec() == QDialog.Accepted:
            selected_suppliers = dialog.get_selected_suppliers()
            
            # 선택 비교 (리스트 비교)
            if set(selected_suppliers) == set(current_suppliers):
                self._add_log("[업체] 동일한 업체 선택됨 - 변경 없음")
                return
            
            # ===== BIN 완전 리셋 안내 =====
            self._add_log(f"<b style='color:#FF5722'>━━━ 업체 변경: BIN 완전 리셋 ━━━</b>", html=True)
            self._add_log(f"[BIN] 이전 업체의 모든 BIN 배정이 초기화됩니다.")
            
            # 업체 변경 적용
            if len(selected_suppliers) == len(supplier_summary):
                # 전체 선택
                self.excel_loader.filter_by_supplier(None)
                self._add_log(f"<b style='color:#FF9800'>[업체 변경] 전체 {len(selected_suppliers)}개 업체 선택 - {self.excel_loader.get_total_order_count()}건</b>", html=True)
            elif len(selected_suppliers) > 1:
                # 다중 업체 선택
                self.excel_loader.filter_by_supplier(selected_suppliers)
                self._add_log(f"<b style='color:#FF9800'>[업체 변경] {len(selected_suppliers)}개 업체 선택: {', '.join(selected_suppliers)} - {self.excel_loader.get_filtered_order_count()}건</b>", html=True)
            else:
                # 단일 업체 선택
                self.excel_loader.filter_by_supplier(selected_suppliers[0])
                self._add_log(f"<b style='color:#FF9800'>[업체 변경] '{selected_suppliers[0]}' 선택됨 - {self.excel_loader.get_filtered_order_count()}건</b>", html=True)
            
            # 상태바 업데이트
            file_path = self.excel_path_edit.text().strip()
            current_supplier = self.excel_loader.get_current_supplier()
            if current_supplier:
                self.status_file.setText(f"파일: {Path(file_path).name} | 업체: {current_supplier}")
            else:
                self.status_file.setText(f"파일: {Path(file_path).name}")
            
            # BIN 완전 리셋 후 재배정 (새 업체의 SKU에 맞게 BIN-01부터 다시 시작)
            self._process_after_supplier_selection(file_path)
            
            # 전체피킹 탭 정보도 업데이트
            self._update_fp_session_info()
            
            QMessageBox.information(
                self,
                "업체 변경 완료",
                f"업체가 변경되었습니다.\n\n"
                f"작업 차수: {self._work_session}차\n"
                f"선택 업체: {', '.join(selected_suppliers) if len(selected_suppliers) <= 3 else f'{len(selected_suppliers)}개 업체'}\n"
                f"주문 건수: {self.excel_loader.get_filtered_order_count()}건\n\n"
                f"⚠️ BIN이 완전히 초기화되어 새로 배정되었습니다."
            )
    
    @Slot()
    def _on_save_excel(self):
        """엑셀 파일 저장 (파일명_역매칭.xlsx로 저장)"""
        if self.excel_loader.df is None:
            QMessageBox.warning(self, "경고", "먼저 엑셀 파일을 불러오세요.")
            return
        
        # 저장 경로 확인
        save_path = self.save_path_edit.text().strip()
        
        if save_path:
            # 지정된 경로로 저장
            success, saved_path = self.excel_loader.save_excel(save_path)
            if success:
                self._add_log(f"엑셀 파일 저장 완료: {saved_path}")
                QMessageBox.information(self, "성공", f"엑셀 파일이 저장되었습니다.\n{saved_path}")
            else:
                QMessageBox.warning(self, "오류", "엑셀 파일 저장에 실패했습니다.")
        else:
            # 원본 위치에 _역매칭 붙여서 저장
            success, saved_path = self.excel_loader.save_excel()
            if success:
                self._add_log(f"엑셀 파일 저장 완료: {saved_path}")
                QMessageBox.information(self, "성공", f"엑셀 파일이 저장되었습니다.\n{saved_path}")
            else:
                QMessageBox.warning(self, "오류", "엑셀 파일 저장에 실패했습니다.")
    
    @Slot()
    def _on_save_product_pdf(self):
        """제품별 요약을 PDF로 저장"""
        if self.excel_loader.df is None:
            QMessageBox.warning(self, "경고", "먼저 엑셀 파일을 불러오세요.")
            return
        
        from datetime import datetime
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # 작업 차수 및 업체명 (파일명에 포함)
        session_num = self._work_session if self._work_session > 0 else 1
        supplier_name = self._work_session_supplier or self.excel_loader.get_current_supplier() or "전체"
        # 파일명에 사용할 수 없는 문자 제거
        safe_supplier = supplier_name.replace("/", "_").replace("\\", "_").replace(":", "_").replace(" ", "")
        
        # 저장 경로가 지정되어 있으면 해당 폴더에 자동 저장
        save_path = self.save_path_edit.text().strip()
        if save_path:
            # 지정된 경로의 폴더에 피킹리스트 PDF 저장
            save_dir = Path(save_path).parent
            file_path = str(save_dir / f"피킹리스트_{session_num}차_{safe_supplier}_{timestamp}.pdf")
        else:
            # 파일 저장 경로 선택 (기본 파일명에 타임스탬프 포함)
            default_name = f"피킹리스트_{session_num}차_{safe_supplier}_{timestamp}.pdf"
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "제품별 요약 PDF 저장",
                default_name,
                "PDF Files (*.pdf);;All Files (*)"
            )
            
            if not file_path:
                return
        
        if not file_path.lower().endswith('.pdf'):
            file_path += '.pdf'
        
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import mm
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            
            # 한글 폰트 등록 (맑은 고딕)
            try:
                pdfmetrics.registerFont(TTFont('MalgunGothic', 'C:/Windows/Fonts/malgun.ttf'))
                font_name = 'MalgunGothic'
            except:
                font_name = 'Helvetica'
            
            # 데이터 준비
            df = self.excel_loader.df
            pending = df[df['used'] == 0]
            
            if pending.empty:
                QMessageBox.information(self, "알림", "처리할 제품이 없습니다.")
                return
            
            # 로케이션 컬럼 확인
            has_location = 'location' in pending.columns
            
            # BIN 시스템 초기화 여부 확인
            has_bin = self.bin_manager.is_initialized
            
            # 제품별 집계 (UI와 동일하게 product_name + option_name으로 그룹화)
            product_data = []
            product_summary = {}
            
            for _, row in pending.iterrows():
                product_name = str(row['product_name']) if pd.notna(row['product_name']) else ''
                option_name = str(row['option_name']) if pd.notna(row['option_name']) else ''
                barcode = str(row['barcode']) if pd.notna(row['barcode']) else ''
                qty = int(row['qty']) if pd.notna(row['qty']) else 1
                scanned = int(row['scanned_qty']) if pd.notna(row['scanned_qty']) else 0
                remaining = qty - scanned
                
                location = ''
                if has_location and 'location' in row and pd.notna(row['location']):
                    location = str(row['location'])
                
                # BIN 주소 조회 (공유 BIN인 경우 ★ 표시)
                bin_id = self.bin_manager.get_sku_bin(barcode) if has_bin else "BIN 미지정"
                is_shared = self.bin_manager.is_shared_bin(bin_id) if has_bin else False
                bin_display = f"{bin_id}★" if is_shared else bin_id
                
                key = f"{product_name}|{option_name}"
                if key not in product_summary:
                    product_summary[key] = {
                        'product_name': product_name,
                        'option_name': option_name,
                        'remaining': 0,
                        'location': location,
                        'barcode': barcode,
                        'bin_id': bin_display
                    }
                product_summary[key]['remaining'] += remaining
            
            # 남은 수량이 있는 것만 추가
            for item in product_summary.values():
                if item['remaining'] > 0:
                    product_data.append(item)
            
            # BIN 번호 오름차순 정렬 (BIN 배정 기준과 동일하게 수량 내림차순)
            def get_bin_sort_key(item):
                bin_id = item.get('bin_id', 'BIN 미지정')
                if bin_id == 'BIN 미지정':
                    return (999, -item['remaining'])
                try:
                    bin_num = int(bin_id.split('-')[1])
                except:
                    bin_num = 999
                return (bin_num, -item['remaining'])
            
            product_data.sort(key=get_bin_sort_key)
            
            # PDF 생성을 위한 요소 준비
            elements = []
            
            # 스타일
            styles = getSampleStyleSheet()
            title_style = ParagraphStyle(
                'Title',
                parent=styles['Heading1'],
                fontName=font_name,
                fontSize=18,
                alignment=1  # 중앙 정렬
            )
            subtitle_style = ParagraphStyle(
                'Subtitle',
                parent=styles['Normal'],
                fontName=font_name,
                fontSize=12,
                alignment=1,  # 중앙 정렬
                textColor=colors.HexColor('#555555')
            )
            info_style = ParagraphStyle(
                'Info',
                parent=styles['Normal'],
                fontName=font_name,
                fontSize=10,
                alignment=1,  # 중앙 정렬
                textColor=colors.HexColor('#666666')
            )
            
            # 제목 - 작업 차수 포함
            from datetime import datetime
            title = Paragraph(f"<b>{session_num}차 피킹 리스트</b>", title_style)
            elements.append(title)
            
            # 부제목 - 업체명 및 날짜
            subtitle = Paragraph(f"업체: {supplier_name} | {datetime.now().strftime('%Y-%m-%d %H:%M')}", subtitle_style)
            elements.append(subtitle)
            elements.append(Spacer(1, 3*mm))
            
            # BIN 통계 정보
            if has_bin:
                stats = self.bin_manager.get_statistics()
                total_bins = stats.get("total_bins", 0)
                shared_bins = stats.get("shared_bins", 0)
                dedicated_bins = stats.get("dedicated_bins", 0)
                bin_info = Paragraph(
                    f"BIN 배정: 총 {total_bins}개 (전용: {dedicated_bins}, 공유: {shared_bins}) | ★ = 공유 BIN",
                    info_style
                )
                elements.append(bin_info)
            
            elements.append(Spacer(1, 5*mm))
            
            # 테이블 헤더 (BIN 컬럼 추가 - 첫 번째 컬럼)
            if has_location:
                headers = ['BIN', 'No', '수량', '로케이션', '제품명', '옵션명', '바코드']
                col_widths = [18*mm, 10*mm, 15*mm, 22*mm, 50*mm, 35*mm, 30*mm]
            else:
                headers = ['BIN', 'No', '수량', '제품명', '옵션명', '바코드']
                col_widths = [18*mm, 10*mm, 15*mm, 60*mm, 45*mm, 32*mm]
            
            # 테이블 데이터
            table_data = [headers]
            for i, item in enumerate(product_data, 1):
                bin_id = item.get('bin_id', 'BIN 미지정')
                if has_location:
                    row = [
                        bin_id,
                        str(i),
                        str(item['remaining']),
                        item['location'],
                        item['product_name'][:28],
                        item['option_name'][:18] if item['option_name'] != 'nan' else '',
                        item['barcode']
                    ]
                else:
                    row = [
                        bin_id,
                        str(i),
                        str(item['remaining']),
                        item['product_name'][:35],
                        item['option_name'][:22] if item['option_name'] != 'nan' else '',
                        item['barcode']
                    ]
                table_data.append(row)
            
            # 테이블 생성
            table = Table(table_data, colWidths=col_widths, repeatRows=1)
            table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), font_name),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2196F3')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('ALIGN', (0, 1), (2, -1), 'CENTER'),  # BIN, No, 수량 중앙
                ('ALIGN', (3, 1), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F5F5')]),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                # BIN 컬럼 강조
                ('FONTNAME', (0, 1), (0, -1), font_name),
                ('FONTSIZE', (0, 1), (0, -1), 10),
                ('BACKGROUND', (0, 1), (0, -1), colors.HexColor('#E3F2FD')),
            ]))
            
            elements.append(table)
            
            # 합계
            total_remaining = sum(item['remaining'] for item in product_data)
            summary_style = ParagraphStyle(
                'Summary',
                parent=styles['Normal'],
                fontName=font_name,
                fontSize=12,
                alignment=2  # 오른쪽 정렬
            )
            elements.append(Spacer(1, 5*mm))
            elements.append(Paragraph(f"총 {len(product_data)}개 품목 / {total_remaining}개 수량", summary_style))
            
            # PDF 저장 (Permission 오류 시 다른 이름으로 재시도)
            from utils import get_unique_filepath
            actual_path = file_path
            max_attempts = 10
            last_error = None
            
            for attempt in range(max_attempts):
                try:
                    if attempt > 0:
                        # 재시도 시 새 파일 경로 생성
                        stem = Path(file_path).stem
                        suffix = Path(file_path).suffix
                        parent = Path(file_path).parent
                        actual_path = str(parent / f"{stem}_{attempt}{suffix}")
                    
                    doc = SimpleDocTemplate(actual_path, pagesize=A4, 
                                           leftMargin=15*mm, rightMargin=15*mm,
                                           topMargin=15*mm, bottomMargin=15*mm)
                    doc.build(elements)
                    break
                except PermissionError as e:
                    last_error = str(e)
                    continue
                except Exception as e:
                    if "Permission denied" in str(e) or "Errno 13" in str(e):
                        last_error = str(e)
                        continue
                    raise
            else:
                raise Exception(f"모든 저장 시도 실패. 마지막 오류: {last_error}")
            
            self._add_log(f"제품별 PDF 저장 완료: {actual_path}")
            
            # 마지막 PDF 경로 저장 및 열기 버튼 활성화
            self._last_pdf_path = actual_path
            self.open_pdf_btn.setEnabled(True)
            
            # 파일명이 변경되었으면 알림
            if actual_path != file_path:
                QMessageBox.information(self, "성공", f"PDF가 저장되었습니다.\n{actual_path}\n\n※ 원본 파일이 사용 중이어서 다른 이름으로 저장되었습니다.")
            else:
                QMessageBox.information(self, "성공", f"PDF가 저장되었습니다.\n{actual_path}")
            
        except ImportError:
            QMessageBox.warning(self, "오류", "reportlab 패키지가 필요합니다.\npip install reportlab")
        except Exception as e:
            self._add_log(f"[오류] PDF 저장 실패: {str(e)}")
            QMessageBox.warning(self, "오류", f"PDF 저장 실패: {str(e)}")
    
    @Slot()
    def _on_open_picking_pdf(self):
        """마지막 저장된 피킹리스트 PDF 열기"""
        if self._last_pdf_path and Path(self._last_pdf_path).exists():
            import os
            os.startfile(self._last_pdf_path)
            self._add_log(f"피킹리스트 열기: {self._last_pdf_path}")
        else:
            QMessageBox.warning(self, "경고", "열 수 있는 PDF 파일이 없습니다.\n먼저 피킹리스트 PDF를 저장하세요.")
    
    @Slot()
    def _on_browse_save_path(self):
        """저장 경로 선택 (폴더 선택)"""
        folder_path = QFileDialog.getExistingDirectory(
            self,
            "엑셀 저장 폴더 선택",
            self.save_path_edit.text() or ""
        )
        
        if folder_path:
            self.save_path_edit.setText(folder_path)
            self._add_log(f"저장 폴더 설정: {folder_path}")
    
    @Slot()
    def _on_browse_label_folder(self):
        """송장 검색 폴더 선택"""
        folder_path = QFileDialog.getExistingDirectory(
            self,
            "송장 검색 폴더 선택",
            self.reprint_label_folder_edit.text() or "labels"
        )
        if folder_path:
            self.reprint_label_folder_edit.setText(folder_path)
            self._add_log(f"[REPRINT] 송장 검색 폴더 설정: {folder_path}")
    
    @Slot()
    def _on_browse_order_folder(self):
        """주문서 검색 폴더 선택"""
        folder_path = QFileDialog.getExistingDirectory(
            self,
            "주문서 검색 폴더 선택",
            self.reprint_order_folder_edit.text() or "orders"
        )
        if folder_path:
            self.reprint_order_folder_edit.setText(folder_path)
            self._add_log(f"[REPRINT] 주문서 검색 폴더 설정: {folder_path}")
    
    @Slot()
    def _on_toggle_scanner(self):
        """스캐너 시작/중지 (현재 사용 안 함 - 자동 시작으로 변경됨)"""
        # 스캐너는 프로그램 시작 시 자동으로 시작됨
        # 필요시 이 함수를 다시 활성화할 수 있음
        pass
    
    @Slot(bool)
    def _on_toggle_ezauto(self, checked: bool):
        """EzAuto 활성화/비활성화"""
        self.ezauto.enabled = checked
        self._add_log(f"EzAuto 입력: {'활성' if checked else '비활성'}")
    
    @Slot(str)
    def _on_ezauto_title_changed(self, title: str):
        """EzAuto 창 제목 변경"""
        self.ezauto.set_window_title(title)
    
    @Slot(bool)
    def _on_toggle_pdf(self, checked: bool):
        """PDF 출력 활성화/비활성화"""
        self.pdf_printer.enabled = checked
        self._add_log(f"PDF 출력: {'활성' if checked else '비활성'}")
    
    @Slot(bool)
    def _on_toggle_pdf_keep_temp(self, checked: bool):
        """PDF 임시 파일 보관 옵션 (송장/주문서 모두 적용)"""
        self.pdf_printer.keep_temp_files = checked
        self._add_log(f"PDF 임시 파일: {'보관' if checked else '출력 후 삭제'} (송장/주문서 모두 적용)")
    
    @Slot(bool)
    def _on_toggle_order_sheet(self, checked: bool):
        """주문서 출력 활성화/비활성화"""
        self.pdf_printer.order_sheet_enabled = checked
        
        # UI 요소 활성화/비활성화
        self.pdf_path_2_edit.setEnabled(checked)
        self.pdf_browse_2_btn.setEnabled(checked)
        
        if checked:
            # 활성화 시 두 번째 PDF 파일 설정
            pdf_path_2 = self.pdf_path_2_edit.text().strip()
            
            if pdf_path_2:
                self.pdf_printer.set_pdf_file_2(pdf_path_2)
                # 두 번째 PDF 인덱싱
                if self.excel_loader.df is not None:
                    tracking_numbers = self.excel_loader.get_all_tracking_numbers()
                    self.pdf_printer.build_tracking_index(tracking_numbers)
            
            # A4 프린터 설정 사용 (printer_2_combo 제거됨)
            a4_printer = self.a4_printer_combo.currentText()
            if a4_printer and a4_printer != "프린터 없음":
                self.pdf_printer.set_printer_2(a4_printer)
            
            self._add_log("주문서 출력 활성화됨 (A4 프린터 설정 사용)")
        else:
            # 비활성화 시 설정 초기화
            self.pdf_printer.set_pdf_file_2("")
            self.pdf_printer.set_printer_2("")
            self._add_log("주문서 출력 비활성화됨")
    
    @Slot()
    def _on_browse_pdf_file_2(self):
        """두 번째 PDF 파일 찾아보기 (주문서)"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "주문서 PDF 파일 선택",
            "",
            "PDF Files (*.pdf);;All Files (*)"
        )
        if file_path:
            self.pdf_path_2_edit.setText(file_path)
            self.pdf_printer.set_pdf_file_2(file_path)
            
            # 두 번째 PDF 인덱싱
            if self.excel_loader.df is not None:
                tracking_numbers = self.excel_loader.get_all_tracking_numbers()
                self.pdf_printer.build_tracking_index(tracking_numbers)
            
            # A4 프린터 설정 사용
            a4_printer = self.a4_printer_combo.currentText()
            if a4_printer and a4_printer != "프린터 없음":
                self.pdf_printer.set_printer_2(a4_printer)
            
            self._add_log(f"주문서 PDF 파일 설정: {file_path} (A4 프린터 설정 사용)")
    
    def _load_printer_list(self):
        """시스템 프린터 목록 로드"""
        printers = get_printers()
        
        # 라벨 프린터 목록 로드
        if hasattr(self, 'label_printer_combo'):
            self.label_printer_combo.clear()
            if printers:
                self.label_printer_combo.addItems(printers)
            else:
                self.label_printer_combo.addItem("프린터 없음")
            # 프린터 선택 시 이벤트 연결
            self.label_printer_combo.currentTextChanged.connect(self._on_label_printer_changed)
        
        # A4 프린터 목록 로드
        if hasattr(self, 'a4_printer_combo'):
            self.a4_printer_combo.clear()
            if printers:
                self.a4_printer_combo.addItems(printers)
            else:
                self.a4_printer_combo.addItem("프린터 없음")
            # 프린터 선택 시 이벤트 연결
            self.a4_printer_combo.currentTextChanged.connect(self._on_a4_printer_changed)
        
        # 기존 호환성 유지 (printer_1_combo)
        if hasattr(self, 'printer_1_combo'):
            self.printer_1_combo.clear()
            if printers:
                self.printer_1_combo.addItems(printers)
            else:
                self.printer_1_combo.addItem("프린터 없음")
            self.printer_1_combo.currentTextChanged.connect(self._on_printer_1_changed)
        
    
    def _load_printer_settings_to_ui(self):
        """settings.json에서 프린터 설정 로드하여 UI에 반영"""
        settings = load_printer_settings()
        label_printer = settings.get("label_printer")
        a4_printer = settings.get("a4_printer")
        
        # 프린터 목록 로드
        self._load_printer_list()
        
        # 저장된 프린터가 있으면 선택
        if label_printer and hasattr(self, 'label_printer_combo'):
            index = self.label_printer_combo.findText(label_printer)
            if index >= 0:
                self.label_printer_combo.setCurrentIndex(index)
            else:
                # 프린터가 목록에 없으면 경고
                self._add_log(f"[경고] 저장된 라벨 프린터를 찾을 수 없습니다: {label_printer}")
        
        if a4_printer and hasattr(self, 'a4_printer_combo'):
            index = self.a4_printer_combo.findText(a4_printer)
            if index >= 0:
                self.a4_printer_combo.setCurrentIndex(index)
            else:
                # 프린터가 목록에 없으면 경고
                self._add_log(f"[경고] 저장된 A4 프린터를 찾을 수 없습니다: {a4_printer}")
    
    @Slot(str)
    def _on_label_printer_changed(self, printer_name: str):
        """라벨 프린터 선택 변경"""
        if printer_name and printer_name != "프린터 없음":
            # settings.json에 저장
            save_printer_settings(label_printer=printer_name)
            # 기존 호환성 유지
            if hasattr(self.pdf_printer, 'set_printer_1'):
                self.pdf_printer.set_printer_1(printer_name)
            self._add_log(f"라벨 프린터 설정: {printer_name}")
    
    @Slot(str)
    def _on_a4_printer_changed(self, printer_name: str):
        """A4 프린터 선택 변경"""
        if printer_name and printer_name != "프린터 없음":
            # settings.json에 저장
            save_printer_settings(a4_printer=printer_name)
            # 주문서 출력이 활성화되어 있으면 프린터 설정 업데이트
            if hasattr(self, 'order_sheet_check') and self.order_sheet_check.isChecked():
                if hasattr(self.pdf_printer, 'set_printer_2'):
                    self.pdf_printer.set_printer_2(printer_name)
            self._add_log(f"A4 프린터 설정: {printer_name}")
    
    @Slot()
    def _on_test_label_printer(self, printer_name: str = None):
        """라벨 프린터 테스트 출력 (회전 설정 포함)"""
        # 프린터 이름이 전달되지 않으면 출고 탭 콤보박스에서 가져오기
        if not printer_name:
            printer_name = self.label_printer_combo.currentText()
        if not printer_name or printer_name == "프린터 없음":
            QMessageBox.warning(self, "경고", "라벨 프린터를 먼저 선택해주세요.")
            return
        
        # 현재 회전 설정 로드
        from printer_manager import load_label_rotation
        rotation = load_label_rotation()
        
        # 테스트 PDF 파일 경로 (회전별로 다른 파일)
        test_pdf_path = Path(__file__).parent / "labels" / f"test_label_{rotation}.pdf"
        test_pdf_path.parent.mkdir(exist_ok=True)
        
        # 테스트 PDF 생성 (항상 새로 생성 - 회전 설정이 바뀔 수 있으므로)
        try:
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import landscape
            from reportlab.lib.units import mm
            from datetime import datetime
            import json
            
            # 라벨 크기 (settings.json에서 로드, 기본값: 110x168mm)
            try:
                settings_path = Path(__file__).parent / "settings.json"
                with open(settings_path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                paper_size = settings.get("label_paper_size", {})
                label_width = paper_size.get("width_mm", 110) * mm
                label_height = paper_size.get("height_mm", 168) * mm
            except:
                label_width = 110 * mm
                label_height = 168 * mm
            
            c = canvas.Canvas(str(test_pdf_path), pagesize=(label_width, label_height))
            
            # 폰트 설정
            try:
                from reportlab.pdfbase import pdfmetrics
                from reportlab.pdfbase.ttfonts import TTFont
                # 시스템 폰트 사용 시도
                import os
                font_path = os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts', 'malgun.ttf')
                if os.path.exists(font_path):
                    pdfmetrics.registerFont(TTFont('Malgun', font_path))
                    c.setFont('Malgun', 12)
                else:
                    c.setFont('Helvetica', 12)
            except Exception:
                c.setFont('Helvetica', 12)
            
            # 테두리 그리기
            c.rect(5, 5, label_width - 10, label_height - 10)
            
            # 상단 표시 (이 부분이 위로 나와야 정상)
            c.setFontSize(14)
            c.drawCentredString(label_width / 2, label_height - 18, "▲ 위 ▲")
            
            # 좌측 표시
            c.saveState()
            c.translate(18, label_height / 2)
            c.rotate(90)
            c.drawCentredString(0, 0, "◀ 좌")
            c.restoreState()
            
            # 우측 표시
            c.saveState()
            c.translate(label_width - 18, label_height / 2)
            c.rotate(-90)
            c.drawCentredString(0, 0, "우 ▶")
            c.restoreState()
            
            # 중앙 - 회전 테스트 제목
            c.setFontSize(16)
            c.drawCentredString(label_width / 2, label_height / 2 + 15, "회전 테스트")
            
            # 회전 정보
            c.setFontSize(12)
            c.drawCentredString(label_width / 2, label_height / 2 - 5, f"설정: {rotation}°")
            
            # 프린터 정보
            c.setFontSize(9)
            short_printer = printer_name[:25] + "..." if len(printer_name) > 25 else printer_name
            c.drawCentredString(label_width / 2, label_height / 2 - 22, short_printer)
            c.drawCentredString(label_width / 2, label_height / 2 - 35, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            
            # 하단 표시
            c.setFontSize(14)
            c.drawCentredString(label_width / 2, 12, "▼ 아래 ▼")
            
            c.save()
            
        except ImportError as e:
            QMessageBox.warning(self, "경고", f"테스트 PDF 생성 실패: {str(e)}")
            return
        
        # PDF 생성 후 회전 적용하여 출력 (실제 송장 출력과 동일한 PIL 방식)
        try:
            import fitz
            from PIL import Image
            import io
            
            # 원본 PDF 열기
            doc = fitz.open(str(test_pdf_path))
            page = doc[0]
            
            # 용지 크기 (mm)
            paper_width_mm = label_width / mm
            paper_height_mm = label_height / mm
            
            # 고해상도 렌더링 (원본, 회전 없이)
            dpi = 300
            zoom = dpi / 72
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            
            # PIL Image로 변환 (원본)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            
            # ★ 1단계: 용지 크기의 흰색 캔버스 생성 (회전 전 기준)
            if rotation in [90, 270]:
                canvas_width = int(paper_height_mm * dpi / 25.4)
                canvas_height = int(paper_width_mm * dpi / 25.4)
            else:
                canvas_width = int(paper_width_mm * dpi / 25.4)
                canvas_height = int(paper_height_mm * dpi / 25.4)
            
            canvas = Image.new('RGB', (canvas_width, canvas_height), (255, 255, 255))
            
            # ★ 2단계: 캔버스에 이미지 배치 (비율 유지, 위쪽 정렬)
            scale = min(canvas_width / img.width, canvas_height / img.height)
            new_img_width = int(img.width * scale)
            new_img_height = int(img.height * scale)
            
            img_resized = img.resize((new_img_width, new_img_height), Image.LANCZOS)
            
            x_pos = 0  # 왼쪽 정렬
            y_pos = 0  # 위쪽 정렬
            canvas.paste(img_resized, (x_pos, y_pos))
            
            # ★ 3단계: 캔버스 전체를 회전 (이미지 + 여백 함께)
            if rotation == 90:
                canvas_rotated = canvas.rotate(-90, expand=True)
            elif rotation == 180:
                canvas_rotated = canvas.rotate(180, expand=True)
            elif rotation == 270:
                canvas_rotated = canvas.rotate(-270, expand=True)
            else:
                canvas_rotated = canvas
            
            # ★ 4단계: 회전된 캔버스를 PDF로 저장
            paper_width_pt = paper_width_mm * 2.8346
            paper_height_pt = paper_height_mm * 2.8346
            
            rotated_doc = fitz.open()
            new_page = rotated_doc.new_page(width=paper_width_pt, height=paper_height_pt)
            
            img_bytes = io.BytesIO()
            canvas_rotated.save(img_bytes, format='PNG')
            img_bytes.seek(0)
            
            target_rect = fitz.Rect(0, 0, paper_width_pt, paper_height_pt)
            new_page.insert_image(target_rect, stream=img_bytes.getvalue(), keep_proportion=True, overlay=True)
            
            # 회전된 PDF 저장
            rotated_pdf_path = test_pdf_path.parent / f"test_label_{rotation}_rotated.pdf"
            rotated_doc.save(str(rotated_pdf_path))
            rotated_doc.close()
            doc.close()
            
            # 출력
            if print_pdf_with_printer(str(rotated_pdf_path), printer_name):
                self._add_log(f"라벨 테스트 출력 완료 (회전: {rotation}°)")
                self._add_log(f"→ '▲ 위 ▲'가 위쪽이면 정상, 아니면 회전 설정 변경")
            else:
                QMessageBox.warning(self, "오류", f"라벨 프린터 테스트 출력 실패: {printer_name}")
                
        except ImportError:
            # PyMuPDF 없으면 원본 그대로 출력
            if print_pdf_with_printer(str(test_pdf_path), printer_name):
                self._add_log(f"라벨 테스트 출력 완료 (회전 미적용)")
            else:
                QMessageBox.warning(self, "오류", f"라벨 프린터 테스트 출력 실패: {printer_name}")
    
    @Slot()
    def _on_test_a4_printer(self, printer_name: str = None):
        """A4 프린터 테스트 출력"""
        # 프린터 이름이 전달되지 않으면 출고 탭 콤보박스에서 가져오기
        if not printer_name:
            printer_name = self.a4_printer_combo.currentText()
        if not printer_name or printer_name == "프린터 없음":
            QMessageBox.warning(self, "경고", "A4 프린터를 먼저 선택해주세요.")
            return
        
        # 테스트 PDF 파일 경로
        test_pdf_path = Path(__file__).parent / "orders" / "test_order.pdf"
        
        # 테스트 파일이 없으면 임시 파일 생성
        if not test_pdf_path.exists():
            test_pdf_path.parent.mkdir(exist_ok=True)
            try:
                from reportlab.pdfgen import canvas
                from reportlab.lib.pagesizes import A4
                c = canvas.Canvas(str(test_pdf_path), pagesize=A4)
                c.drawString(100, 750, "A4 프린터 테스트")
                c.drawString(100, 730, f"프린터: {printer_name}")
                c.save()
            except ImportError:
                QMessageBox.warning(self, "경고", "테스트 PDF 생성에 필요한 라이브러리가 없습니다.")
                return
        
        # 출력
        if print_pdf_with_printer(str(test_pdf_path), printer_name):
            self._add_log(f"A4 프린터 테스트 출력 완료: {printer_name}")
        else:
            QMessageBox.warning(self, "오류", f"A4 프린터 테스트 출력 실패: {printer_name}")
    
    @Slot()
    def _on_rotation_change(self):
        """송장 회전 설정 변경 (콤보박스 선택)"""
        from printer_manager import save_label_rotation
        
        if not hasattr(self, 'rotation_combo'):
            return
        
        # 콤보박스에서 선택된 값 가져오기 (0°, 90°, 180°, 270°)
        rotation_text = self.rotation_combo.currentText()
        rotation_values = {"0°": 0, "90°": 90, "180°": 180, "270°": 270}
        new_rotation = rotation_values.get(rotation_text, 270)
        
        # 저장
        if save_label_rotation(new_rotation):
            self._add_log(f"송장 회전 설정 변경: {new_rotation}°")
        else:
            QMessageBox.warning(self, "오류", "회전 설정 저장에 실패했습니다.")
    
    def _update_rotation_combo(self):
        """회전 콤보박스 선택값 업데이트"""
        from printer_manager import load_label_rotation
        
        if hasattr(self, 'rotation_combo'):
            rotation = load_label_rotation()
            rotation_map = {0: 0, 90: 1, 180: 2, 270: 3}
            index = rotation_map.get(rotation, 3)  # 기본값 270° (index 3)
            self.rotation_combo.blockSignals(True)  # 시그널 일시 차단
            self.rotation_combo.setCurrentIndex(index)
            self.rotation_combo.blockSignals(False)
    
    def _on_bin_settings(self):
        """BIN 설정 다이얼로그 열기"""
        dialog = BinSettingsDialog(self.bin_manager, self)
        if dialog.exec() == QDialog.Accepted:
            # 설정이 적용됨 - 엑셀이 로드되어 있으면 BIN 재배정
            if self.excel_loader.df is not None:
                self._add_log("[BIN] 설정 변경됨 - BIN 재배정 중...")
                
                # 새 설정으로 BIN 재배정
                bin_count = self.bin_manager.assign_bins_from_dataframe(self.excel_loader.df)
                if bin_count > 0:
                    stats = self.bin_manager.get_statistics()
                    shared_bins = stats.get("shared_bins", 0)
                    dedicated_bins = stats.get("dedicated_bins", 0)
                    config = stats.get("config", {})
                    
                    self._add_log(f"<b style='color:#2196F3'>[BIN] 재배정 완료: {bin_count}개 BIN "
                                 f"(전용: {dedicated_bins}, 공유: {shared_bins})</b>", html=True)
                    self._add_log(f"[BIN] 설정: 최대수량={config.get('max_qty_per_bin', 100)}, "
                                 f"소량기준={config.get('min_qty_threshold', 10)}이하, "
                                 f"공유BIN 최대SKU={config.get('max_sku_per_shared_bin', 5)}")
                    
                    # 송장별 BIN 매핑 재구축
                    self.bin_manager.build_order_bin_map(self.excel_loader.df)
                    
                    # UI 갱신
                    self._update_summary_tables()
                    self._update_current_tracking()
                
                QMessageBox.information(self, "완료", 
                    f"BIN 설정이 적용되었습니다.\n"
                    f"총 {bin_count}개 BIN이 생성되었습니다.")
            else:
                self._add_log("[BIN] 설정 저장됨 (엑셀 로드 시 적용됨)")
                QMessageBox.information(self, "완료", 
                    "BIN 설정이 저장되었습니다.\n엑셀 파일을 로드하면 적용됩니다.")
    
    @Slot(str)
    def _on_printer_1_changed(self, printer_name: str):
        """첫 번째 프린터 선택 변경 (기존 호환성 유지)"""
        if printer_name and printer_name != "프린터 없음":
            if hasattr(self.pdf_printer, 'set_printer_1'):
                self.pdf_printer.set_printer_1(printer_name)
            self._add_log(f"송장 프린터 설정: {printer_name}")
    
    
    @Slot()
    def _on_priority_changed(self):
        """우선순위 설정 변경 (라디오 버튼 자동 상호 배타적)"""
        self._apply_priority_rules()
    
    def _apply_preset(self, preset_name: str):
        """
        프리셋 적용
        
        Args:
            preset_name: 프리셋 이름 ("default", "backlog", "bulk")
        """
        from priority_engine import get_preset_rules
        
        # 프리셋 규칙 가져오기
        rules = get_preset_rules(preset_name)
        
        # 라디오 버튼 UI 상태 업데이트 (시그널 차단하여 무한 루프 방지)
        if hasattr(self, 'priority_single_radio'):
            self.priority_single_radio.blockSignals(True)
            self.priority_combo_radio.blockSignals(True)
            self.priority_no_type_radio.blockSignals(True)
            self.priority_small_qty_radio.blockSignals(True)
            self.priority_large_qty_radio.blockSignals(True)
            self.priority_no_qty_radio.blockSignals(True)
            self.priority_old_order_radio.blockSignals(True)
            self.priority_new_order_radio.blockSignals(True)
            self.priority_no_time_radio.blockSignals(True)
            
            self.priority_single_radio.setChecked(rules["single_first"])
            self.priority_combo_radio.setChecked(rules["combo_first"])
            # 유형 무관: 둘 다 False일 때
            if not rules["single_first"] and not rules["combo_first"]:
                self.priority_no_type_radio.setChecked(True)
            self.priority_small_qty_radio.setChecked(rules["small_qty_first"])
            self.priority_large_qty_radio.setChecked(rules["large_qty_first"])
            # 수량 무관: 둘 다 False일 때
            if not rules["small_qty_first"] and not rules["large_qty_first"]:
                self.priority_no_qty_radio.setChecked(True)
            self.priority_old_order_radio.setChecked(rules["old_order_first"])
            self.priority_new_order_radio.setChecked(rules["new_order_first"])
            # 시간 무관: 둘 다 False일 때
            if not rules["old_order_first"] and not rules["new_order_first"]:
                self.priority_no_time_radio.setChecked(True)
            
            self.priority_single_radio.blockSignals(False)
            self.priority_combo_radio.blockSignals(False)
            self.priority_no_type_radio.blockSignals(False)
            self.priority_small_qty_radio.blockSignals(False)
            self.priority_large_qty_radio.blockSignals(False)
            self.priority_no_qty_radio.blockSignals(False)
            self.priority_old_order_radio.blockSignals(False)
            self.priority_new_order_radio.blockSignals(False)
            self.priority_no_time_radio.blockSignals(False)
        
        # 규칙 적용
        self._apply_priority_rules()
        
        # 프리셋 이름 매핑
        preset_names = {
            "default": "기본(단품 우선)",
            "backlog": "밀린 주문 정리",
            "bulk": "대량 소화"
        }
        self._add_log(f"프리셋 적용: {preset_names.get(preset_name, preset_name)}")
    
    def _apply_priority_rules(self):
        """현재 UI 설정을 기반으로 우선순위 규칙 적용"""
        # 라디오 버튼에서 값 읽기
        if hasattr(self, 'priority_single_radio'):
            rules = {
                "single_first": self.priority_single_radio.isChecked(),
                "combo_first": self.priority_combo_radio.isChecked(),
                "small_qty_first": self.priority_small_qty_radio.isChecked(),
                "large_qty_first": self.priority_large_qty_radio.isChecked(),
                "old_order_first": self.priority_old_order_radio.isChecked(),
                "new_order_first": self.priority_new_order_radio.isChecked(),
                "manual_priority": True  # ⭐ 고정 기능 항상 활성화
            }
        else:
            # 초기화 중일 때는 기본값 사용
            rules = {
                "single_first": True,
                "combo_first": False,
                "small_qty_first": False,
                "large_qty_first": False,
                "old_order_first": False,
                "new_order_first": False,
                "manual_priority": True
            }
        
        # processor에 규칙 전달
        self.processor.set_priority_rules(rules)
        
        # 로그 출력 (변경사항만, manual_priority 제외)
        # log_text가 초기화되지 않았을 수 있으므로 안전하게 처리
        if hasattr(self, 'log_text'):
            active_rules = [k for k, v in rules.items() if v and k != "manual_priority"]
            if active_rules:
                self._add_log(f"우선순위 규칙 적용: {', '.join(active_rules)}")
    
    def _on_toggle_tracking_priority(self, tracking_no: str, is_priority: bool):
        """
        송장 ⭐ 고정 상태 토글 (방식 A: 카드의 ⭐ 버튼)
        
        Args:
            tracking_no: 송장번호
            is_priority: True면 ⭐ 고정, False면 해제
        """
        self._set_tracking_priority(tracking_no, is_priority)
        
        # UI 업데이트 (⭐ 버튼 상태 및 목록 반영)
        self._update_summary_table()
        self._update_priority_tracking_list()
        
        # 로그 출력
        status = "⭐ 고정" if is_priority else "⭐ 해제"
        self._add_log(f"송장 {tracking_no} {status}")
    
    def _set_tracking_priority(self, tracking_no: str, is_priority: bool):
        """
        송장 ⭐ 고정 상태 설정 (공통 함수)
        
        Args:
            tracking_no: 송장번호
            is_priority: True면 ⭐ 고정, False면 해제
        """
        self.excel_loader.set_tracking_priority(tracking_no, is_priority)
        
        # 메타데이터 캐시 갱신 (다음 매칭부터 적용)
        if self.excel_loader._metadata_cache:
            # 해당 송장의 메타데이터만 갱신
            if tracking_no in self.excel_loader._metadata_cache:
                meta = self.excel_loader._metadata_cache[tracking_no]
                meta["is_priority"] = is_priority
    
    def _on_add_priority_tracking(self):
        """우선 송장 추가 (방식 B: 직접 입력)"""
        input_text = self.priority_tracking_input.text().strip()
        if not input_text:
            return
        
        # 여러 개 입력 지원: 줄바꿈 또는 쉼표로 구분
        tracking_nos = []
        for line in input_text.replace(',', '\n').split('\n'):
            tn = line.strip()
            if tn:
                tracking_nos.append(tn)
        
        if not tracking_nos:
            return
        
        # 각 송장번호 추가
        added_count = 0
        not_found = []
        
        for tracking_no in tracking_nos:
            # 송장번호 존재 확인
            if self.excel_loader.df is None:
                QMessageBox.warning(self, "경고", "먼저 엑셀 파일을 불러오세요.")
                return
            
            # used=0인 송장만 확인 (처리되지 않은 송장)
            pending = self.excel_loader.df[self.excel_loader.df['used'] == 0]
            if tracking_no not in pending['tracking_no'].values:
                not_found.append(tracking_no)
                continue
            
            # 이미 우선 송장인지 확인
            if not self.excel_loader.get_tracking_priority(tracking_no):
                self._set_tracking_priority(tracking_no, True)
                added_count += 1
        
        # 입력창 초기화
        self.priority_tracking_input.clear()
        
        # 결과 메시지
        if added_count > 0:
            self._add_log(f"⭐ 우선 송장 {added_count}개 추가됨")
            self._update_priority_tracking_list()
            self._update_summary_table()
        
        if not_found:
            not_found_str = ', '.join(not_found[:5])
            if len(not_found) > 5:
                not_found_str += f" 외 {len(not_found) - 5}개"
            QMessageBox.warning(
                self, "경고",
                f"다음 송장번호를 찾을 수 없거나 이미 처리되었습니다:\n{not_found_str}"
            )
    
    def _on_remove_priority_tracking(self):
        """우선 송장 해제 (방식 B: 목록에서 선택 후 해제)"""
        selected_items = self.priority_tracking_list.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "알림", "해제할 송장을 선택하세요.")
            return
        
        removed_count = 0
        for item in selected_items:
            tracking_no = item.text()
            if self.excel_loader.get_tracking_priority(tracking_no):
                self._set_tracking_priority(tracking_no, False)
                removed_count += 1
        
        if removed_count > 0:
            self._add_log(f"⭐ 우선 송장 {removed_count}개 해제됨")
            self._update_priority_tracking_list()
            self._update_summary_table()
    
    def _update_priority_tracking_list(self):
        """우선 송장 목록 업데이트"""
        if not hasattr(self, 'priority_tracking_list'):
            return
        
        self.priority_tracking_list.clear()
        
        if self.excel_loader.df is None:
            return
        
        # 모든 우선 송장 조회
        all_tracking_nos = self.excel_loader.get_all_tracking_numbers()
        priority_tracking_nos = [
            tn for tn in all_tracking_nos
            if self.excel_loader.get_tracking_priority(tn)
        ]
        
        # 목록에 추가 (정렬)
        for tracking_no in sorted(priority_tracking_nos):
            item = QListWidgetItem(f"⭐ {tracking_no}")
            item.setData(Qt.UserRole, tracking_no)  # tracking_no 저장
            self.priority_tracking_list.addItem(item)
    
    # ===== 제외 송장 관리 =====
    
    def _on_add_exclude_tracking(self):
        """제외 송장 추가"""
        input_text = self.exclude_tracking_input.text().strip()
        if not input_text:
            return
        
        # 여러 개 입력 지원: 줄바꿈 또는 쉼표로 구분
        tracking_nos = []
        for line in input_text.replace(',', '\n').split('\n'):
            tn = line.strip()
            if tn:
                tracking_nos.append(tn)
        
        if not tracking_nos:
            return
        
        # 각 송장번호 추가
        added_count = 0
        
        for tracking_no in tracking_nos:
            # 이미 제외 목록에 있는지 확인
            if tracking_no not in self._excluded_tracking_numbers:
                self._excluded_tracking_numbers.add(tracking_no)
                added_count += 1
        
        # 입력창 초기화
        self.exclude_tracking_input.clear()
        
        # 목록 업데이트
        self._update_exclude_tracking_list()
        
        if added_count > 0:
            self._add_log(f"🚫 제외 송장 {added_count}개 추가됨")
    
    def _on_remove_exclude_tracking(self):
        """제외 송장 해제"""
        selected_items = self.exclude_tracking_list.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "알림", "해제할 송장을 선택하세요.")
            return
        
        removed_count = 0
        for item in selected_items:
            tracking_no = item.data(Qt.UserRole)
            if tracking_no in self._excluded_tracking_numbers:
                self._excluded_tracking_numbers.remove(tracking_no)
                removed_count += 1
        
        if removed_count > 0:
            self._add_log(f"🚫 제외 송장 {removed_count}개 해제됨")
            self._update_exclude_tracking_list()
    
    def _update_exclude_tracking_list(self):
        """제외 송장 목록 UI 업데이트"""
        if not hasattr(self, 'exclude_tracking_list'):
            return
        
        self.exclude_tracking_list.clear()
        
        # 목록에 추가 (정렬)
        for tracking_no in sorted(self._excluded_tracking_numbers):
            item = QListWidgetItem(f"🚫 {tracking_no}")
            item.setData(Qt.UserRole, tracking_no)
            self.exclude_tracking_list.addItem(item)
    
    def is_tracking_excluded(self, tracking_no: str) -> bool:
        """송장번호가 제외 목록에 있는지 확인"""
        return tracking_no in self._excluded_tracking_numbers
    
    @Slot()
    def _on_manual_scan(self):
        """수동 바코드 스캔"""
        barcode = self.manual_barcode_edit.text().strip()
        if barcode:
            # 스캐너 버퍼 클리어 (이중 처리 방지)
            self.scanner.clear_buffer()
            self._on_barcode_scanned(barcode)
            self.manual_barcode_edit.clear()
    
    @Slot(str)
    def _on_barcode_scanned(self, barcode: str):
        """바코드 스캔 이벤트"""
        import time as time_module
        
        # UI 레벨 중복 방지 (1초 내 동일 바코드 무시)
        if not hasattr(self, '_ui_last_barcode'):
            self._ui_last_barcode = ""
            self._ui_last_scan_time = 0
        
        current_time = time_module.time()
        if barcode == self._ui_last_barcode and (current_time - self._ui_last_scan_time) < 1.0:
            return  # 중복 무시 (로그 없이)
        
        self._ui_last_barcode = barcode
        self._ui_last_scan_time = current_time
        
        # ★ 차수 선택 여부 확인 (필수!)
        if not hasattr(self, '_shipment_session_id') or self._shipment_session_id <= 0:
            self._add_log("⚠️ [경고] 먼저 차수를 선택해주세요! (설정 탭 > 차수 관리)")
            return
        
        if self.excel_loader.df is None:
            self._add_log("[경고] 엑셀 파일을 먼저 로드하세요")
            return
        
        # 현재 작업 중인 송장이 제외 목록에 있는지 확인
        current_tracking = self.processor.current_tracking_no
        if current_tracking and self.is_tracking_excluded(current_tracking):
            self._add_log(f"🚫 [제외] 송장 {current_tracking}은(는) 제외 목록에 있어 처리되지 않습니다")
            return
        
        # 바코드로 찾을 수 있는 송장들 중 제외 목록 체크
        candidates = self.excel_loader.find_by_barcode(barcode)
        if not candidates.empty:
            # 모든 후보 송장이 제외 목록에 있는지 확인
            all_excluded = True
            excluded_tracking = None
            for _, row in candidates.iterrows():
                tracking_no = str(row['tracking_no'])
                if not self.is_tracking_excluded(tracking_no):
                    all_excluded = False
                    break
                excluded_tracking = tracking_no
            
            if all_excluded and excluded_tracking:
                self._add_log(f"🚫 [제외] 바코드 {barcode}의 송장({excluded_tracking})이 제외 목록에 있습니다")
                return
        
        # ★ 스캔 전 송장 정보 미리 표시 (즉시 UI 반영)
        if not candidates.empty:
            first_candidate = candidates.iloc[0]
            tracking_no = str(first_candidate['tracking_no'])
            # 현재 작업 송장이 없으면 즉시 표시
            if not self.processor.current_tracking_no:
                self._preview_tracking_info(tracking_no, barcode)
        
        self.processor.process_scan(barcode)
    
    def _preview_tracking_info(self, tracking_no: str, barcode: str):
        """스캔 전 송장 정보 미리보기 (즉시 UI 반영)"""
        try:
            # 현재 작업 송장 UI에 즉시 표시
            if hasattr(self, 'current_tracking_label'):
                self.current_tracking_label.setText(f"📦 {tracking_no}")
            
            # 송장 그룹 정보 가져오기
            group = self.excel_loader.get_tracking_group(tracking_no)
            if not group.empty:
                total_qty = int(group['qty'].sum())
                scanned_qty = int(group['scanned_qty'].sum())
                remaining = total_qty - scanned_qty
                
                # 남은 수량 표시
                if hasattr(self, 'remaining_label'):
                    self.remaining_label.setText(str(remaining))
                
                # BIN 주소 표시
                bin_ids = []
                for _, item in group.iterrows():
                    item_barcode = str(item['barcode']).strip()
                    bin_id = self.bin_manager.get_sku_bin(item_barcode)
                    bin_ids.append(bin_id)
                self._update_bin_display(bin_ids)
                
                # 상세 테이블 미리 채우기
                self.detail_table.setRowCount(len(group))
                for row, (_, item) in enumerate(group.iterrows()):
                    item_remaining = max(0, int(item['qty']) - int(item['scanned_qty']))
                    item_barcode = str(item['barcode']).strip()
                    bin_id = self.bin_manager.get_sku_bin(item_barcode)
                    is_shared = self.bin_manager.is_shared_bin(bin_id)
                    bin_display = f"{bin_id}★" if is_shared else bin_id
                    
                    self.detail_table.setItem(row, 0, QTableWidgetItem(str(item['product_name'])))
                    self.detail_table.setItem(row, 1, QTableWidgetItem(str(item['option_name'])))
                    self.detail_table.setItem(row, 2, QTableWidgetItem(str(item['barcode'])))
                    self.detail_table.setItem(row, 3, QTableWidgetItem(str(int(item['qty']))))
                    self.detail_table.setItem(row, 4, QTableWidgetItem(str(int(item['scanned_qty']))))
                    self.detail_table.setItem(row, 5, QTableWidgetItem(str(item_remaining)))
                    
                    # BIN 컬럼
                    bin_item = QTableWidgetItem(bin_display)
                    bin_item.setTextAlignment(Qt.AlignCenter)
                    bg_color, _ = self._get_bin_color(bin_id)
                    bin_item.setBackground(QColor(bg_color))
                    bin_item.setForeground(QColor("#FFFFFF"))
                    self.detail_table.setItem(row, 6, bin_item)
            
            # UI 즉시 갱신
            QApplication.processEvents()
        except Exception as e:
            pass  # 미리보기 실패 시 무시
    
    @Slot(object)
    def _on_scan_processed(self, event: ScanEvent):
        """스캔 처리 완료"""
        # 결과에 따른 색상
        if event.result == ScanResult.SUCCESS:
            color = "#4CAF50"  # 녹색
            # 스캔 성공 시 카드 반짝임 효과
            QTimer.singleShot(100, lambda: self._highlight_scanned_cards(event.barcode))
        elif event.result == ScanResult.ALREADY_USED:
            color = "#FF9800"  # 주황색
        else:
            color = "#F44336"  # 빨간색
        
        self._add_log(f"<span style='color:{color}'>{event.message}</span>", html=True)
    
    @Slot(str)
    def _on_tracking_completed(self, tracking_no: str):
        """송장 완료"""
        self._add_log(f"<b style='color:#4CAF50'>✓ 송장 {tracking_no} 완료!</b>", html=True)
        self._update_status_count()
        
        # 출력된 송장으로 표시
        self._mark_as_printed(tracking_no)
    
    @Slot(str)
    def _on_priority_cleared(self, tracking_no: str):
        """완료된 우선 송장 자동 해제 (시그널 핸들러)"""
        self._add_log(f"완료된 우선 송장 자동 해제: {tracking_no}")
        # UI 업데이트 (우선 송장 목록 및 카드 ⭐ 상태)
        self._update_priority_tracking_list()
        self._update_summary_table()
    
    @Slot()
    def _on_data_loaded(self):
        """데이터 로드 완료"""
        self._update_tables()
        self._update_status_count()
        # 우선 송장 목록 업데이트
        self._update_priority_tracking_list()
        # 설정 탭 업체 콤보박스 업데이트
        if hasattr(self, 'settings_supplier_combo'):
            self._update_settings_supplier_combo()
            self._update_settings_session_list()
    
    @Slot()
    def _on_data_updated(self):
        """데이터 업데이트"""
        self._update_tables()
    
    @Slot(str)
    def _on_error(self, message: str):
        """오류 발생"""
        self._add_log(f"<span style='color:#F44336'>[오류] {message}</span>", html=True)
    
    def _on_cancel_current_tracking(self):
        """현재 송장 취소"""
        tracking_no = self.processor.current_tracking_no
        if not tracking_no:
            return
        
        # 확인 없이 바로 취소 (빠른 작업을 위해)
        self._add_log(f"[취소] 송장 {tracking_no} 작업 취소")
        
        # 스캔한 수량 초기화
        if self.excel_loader.df is not None:
            mask = self.excel_loader.df['tracking_no'] == tracking_no
            if mask.any():
                self.excel_loader.df.loc[mask, 'scanned_qty'] = 0
        
        # ESP32 LCD 끄기
        self.processor._clear_all_bin_displays()
        
        # 현재 송장 초기화
        self.processor.reset_current_tracking()
        
        # UI 업데이트
        self._update_tables()
        self._add_log(f"[취소] 송장 {tracking_no} 초기화 완료 - 다시 스캔하세요")
    
    # === UI 업데이트 ===
    
    def _update_tables(self):
        """테이블 업데이트"""
        self._update_detail_table()
        self._update_summary_table()
    
    def _update_detail_table(self):
        """현재 송장 상세 테이블 업데이트"""
        tracking_no = self.processor.current_tracking_no
        
        if not tracking_no:
            self.current_tracking_label.setText("-")
            self.remaining_label.setText("0")
            self._update_bin_display(["BIN 미지정"])
            self.detail_table.setRowCount(0)
            self.cancel_current_tracking_btn.setEnabled(False)
            return
        
        self.current_tracking_label.setText(tracking_no)
        self.cancel_current_tracking_btn.setEnabled(True)
        
        # 현재 송장의 모든 SKU에 대한 BIN 주소 수집
        items = self.processor.get_current_tracking_items()
        if not items.empty:
            bin_ids = []
            for _, item in items.iterrows():
                barcode = str(item['barcode']).strip()
                bin_id = self.bin_manager.get_sku_bin(barcode)
                bin_ids.append(bin_id)
            self._update_bin_display(bin_ids)
        else:
            self._update_bin_display(["BIN 미지정"])
        
        items = self.processor.get_current_tracking_items()
        if items.empty:
            self.detail_table.setRowCount(0)
            return
        
        # 남은 수량 계산
        remaining = self.excel_loader.get_group_remaining(tracking_no)
        self.remaining_label.setText(str(remaining))
        
        # 테이블 업데이트
        self.detail_table.setRowCount(len(items))
        
        for row, (_, item) in enumerate(items.iterrows()):
            item_remaining = max(0, item['qty'] - item['scanned_qty'])
            barcode = str(item['barcode']).strip()
            bin_id = self.bin_manager.get_sku_bin(barcode)
            is_shared = self.bin_manager.is_shared_bin(bin_id)
            bin_display = f"{bin_id}★" if is_shared else bin_id
            
            self.detail_table.setItem(row, 0, QTableWidgetItem(str(item['product_name'])))
            self.detail_table.setItem(row, 1, QTableWidgetItem(str(item['option_name'])))
            self.detail_table.setItem(row, 2, QTableWidgetItem(str(item['barcode'])))
            self.detail_table.setItem(row, 3, QTableWidgetItem(str(item['qty'])))
            self.detail_table.setItem(row, 4, QTableWidgetItem(str(item['scanned_qty'])))
            self.detail_table.setItem(row, 5, QTableWidgetItem(str(item_remaining)))
            
            # BIN 컬럼 추가 (공유 BIN은 ★ 표시)
            bin_item = QTableWidgetItem(bin_display)
            bin_item.setTextAlignment(Qt.AlignCenter)
            # BIN 번호에 따른 배경색
            bg_color, _ = self._get_bin_color(bin_id)
            bin_item.setBackground(QColor(bg_color))
            bin_item.setForeground(QColor("#FFFFFF"))
            self.detail_table.setItem(row, 6, bin_item)
            
            # 완료된 항목은 녹색으로 표시
            if item_remaining == 0:
                for col in range(6):  # BIN 컬럼 제외
                    self.detail_table.item(row, col).setBackground(QColor("#E8F5E9"))
    
    def _update_summary_table(self):
        """요약 카드 업데이트 (구성별 + 제품별)"""
        if self.excel_loader.df is None:
            return
        
        df = self.excel_loader.df
        pending = df[df['used'] == 0]
        
        # === 구성별 카드 업데이트 ===
        while self.summary_grid.count():
            item = self.summary_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        if pending.empty:
            empty_label = QLabel("✅ 모든 송장 처리 완료!")
            empty_label.setAlignment(Qt.AlignCenter)
            empty_label.setStyleSheet("font-size: 16px; color: #4CAF50; padding: 20px;")
            self.summary_grid.addWidget(empty_label)
        else:
            # 각 송장별로 별도 카드 생성 (⭐ 기능을 위해)
            tracking_groups = pending.groupby('tracking_no')
            combo_cards = []
            
            for tracking_no, group in tracking_groups:
                # 각 송장에 대한 카드 정보 생성
                combo_info = self._create_combo_info_for_tracking(tracking_no, group)
                combo_cards.append(combo_info)
            
            # ⭐ 고정 송장을 먼저 정렬 (우선순위 반영)
            combo_cards.sort(key=lambda x: (
                not self.excel_loader.get_tracking_priority(x['tracking_nos'][0]),  # ⭐ 고정이 먼저
                -x['count']  # 그 다음 개수 내림차순
            ))
            
            for combo_info in combo_cards:
                card = self._create_summary_card(combo_info)
                self.summary_grid.addWidget(card)
            self.summary_grid.addStretch()
        
        # === 제품별 요약 업데이트 ===
        while self.product_grid.count():
            item = self.product_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        if pending.empty:
            empty_label2 = QLabel("✅ 모든 제품 처리 완료!")
            empty_label2.setAlignment(Qt.AlignCenter)
            empty_label2.setStyleSheet("font-size: 16px; color: #4CAF50; padding: 20px;")
            self.product_grid.addWidget(empty_label2)
        else:
            product_data = self._get_product_summary(pending)
            for prod_info in product_data:
                prod_card = self._create_product_card(prod_info)
                self.product_grid.addWidget(prod_card)
            self.product_grid.addStretch()
    
    def _get_product_summary(self, pending):
        """제품별 남은 수량 계산"""
        product_summary = {}
        
        for _, row in pending.iterrows():
            product_name = str(row['product_name']) if pd.notna(row['product_name']) else ''
            option_name = str(row['option_name']) if pd.notna(row['option_name']) else ''
            barcode = str(row['barcode']) if pd.notna(row['barcode']) else ''
            qty = int(row['qty']) if pd.notna(row['qty']) else 1
            scanned = int(row['scanned_qty']) if pd.notna(row['scanned_qty']) else 0
            remaining = qty - scanned
            
            key = f"{product_name}|{option_name}"
            if key not in product_summary:
                product_summary[key] = {
                    'product_name': product_name,
                    'option_name': option_name,
                    'barcode': barcode,
                    'total_qty': 0,
                    'remaining': 0
                }
            product_summary[key]['total_qty'] += qty
            product_summary[key]['remaining'] += remaining
        
        # 남은 수량 내림차순 정렬
        return sorted(product_summary.values(), key=lambda x: -x['remaining'])
    
    def _create_product_card(self, prod_info):
        """제품별 카드 생성"""
        card = QFrame()
        card.setFrameShape(QFrame.StyledPanel)
        
        # 바코드 정보 저장 (반짝임 효과용)
        card._barcode = prod_info.get('barcode', '')
        
        remaining = prod_info['remaining']
        if remaining >= 20:
            bg_color = "#FFEBEE"
            text_color = "#D32F2F"
        elif remaining >= 10:
            bg_color = "#FFF3E0"
            text_color = "#E65100"
        elif remaining >= 5:
            bg_color = "#E3F2FD"
            text_color = "#1565C0"
        else:
            bg_color = "#F5F5F5"
            text_color = "#616161"
        
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_color};
                border: 1px solid #ddd;
                border-radius: 5px;
                padding: 5px 8px;
                margin: 1px;
            }}
        """)
        
        layout = QHBoxLayout(card)
        layout.setContentsMargins(5, 3, 5, 3)
        layout.setSpacing(8)
        
        # 남은 수량 (4자리까지 표시)
        count_label = QLabel(f"<b style='color:{text_color}; font-size:14px;'>{remaining}</b>")
        count_label.setFixedWidth(50)
        count_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(count_label)
        
        # 제품명 + 옵션
        product_text = prod_info['product_name']
        if prod_info['option_name'] and prod_info['option_name'] != 'nan':
            product_text += f" ({prod_info['option_name']})"
        
        prod_label = QLabel(product_text)
        prod_label.setWordWrap(True)
        prod_label.setStyleSheet("font-size: 11px; color: #333;")
        layout.addWidget(prod_label, 1)
        
        return card
    
    def _create_combo_info_for_tracking(self, tracking_no: str, group: pd.DataFrame) -> dict:
        """
        특정 송장에 대한 카드 정보 생성
        
        Args:
            tracking_no: 송장번호
            group: 해당 송장의 DataFrame 그룹
        
        Returns:
            카드 정보 딕셔너리
        """
        barcodes = sorted(group['barcode'].unique())
        products = []
        
        for _, row in group.iterrows():
            product_name = str(row['product_name']) if pd.notna(row['product_name']) else ''
            option_name = str(row['option_name']) if pd.notna(row['option_name']) else ''
            qty = int(row['qty']) if pd.notna(row['qty']) else 1
            
            product_info = product_name
            if option_name and option_name != 'nan':
                product_info += f" ({option_name})"
            
            # 수량 뒤에 표시: 1개, 2개, 3개...
            product_info += f" {qty}개"
            
            if product_info and product_info not in products:
                products.append(product_info)
        
        return {
            'count': 1,  # 송장당 1개
            'products': products,
            'barcodes': barcodes,
            'tracking_nos': [tracking_no]  # 단일 송장
        }
    
    def _get_summary_combo_data(self, pending):
        """구성별 데이터 추출 (수량 포함) - 기존 함수 유지 (다른 곳에서 사용 가능)"""
        tracking_groups = pending.groupby('tracking_no')
        combo_counts = {}
        
        for tracking_no, group in tracking_groups:
            barcodes = tuple(sorted(group['barcode'].unique()))
            
            if barcodes not in combo_counts:
                combo_counts[barcodes] = {
                    'count': 0,
                    'products': [],
                    'barcodes': list(barcodes),
                    'tracking_nos': []  # 같은 구성의 송장번호 리스트
                }
                for _, row in group.iterrows():
                    product_name = str(row['product_name']) if pd.notna(row['product_name']) else ''
                    option_name = str(row['option_name']) if pd.notna(row['option_name']) else ''
                    qty = int(row['qty']) if pd.notna(row['qty']) else 1
                    
                    product_info = product_name
                    if option_name and option_name != 'nan':
                        product_info += f" ({option_name})"
                    
                    # 수량 뒤에 표시: 1개, 2개, 3개...
                    product_info += f" {qty}개"
                    
                    if product_info and product_info not in combo_counts[barcodes]['products']:
                        combo_counts[barcodes]['products'].append(product_info)
            
            combo_counts[barcodes]['count'] += 1
            if tracking_no not in combo_counts[barcodes]['tracking_nos']:
                combo_counts[barcodes]['tracking_nos'].append(tracking_no)
        
        return sorted(combo_counts.values(), key=lambda x: -x['count'])
    
    def _create_summary_card(self, combo_info):
        """요약 카드 생성 (가로 나열, 전체 품목 표시) + ⭐ 토글 버튼"""
        card = QFrame()
        card.setFrameShape(QFrame.StyledPanel)
        
        # 바코드 정보 저장 (반짝임 효과용)
        card._barcodes = combo_info.get('barcodes', [])
        # tracking_no 리스트 저장 (⭐ 토글용)
        card._tracking_nos = combo_info.get('tracking_nos', [])
        
        count = combo_info['count']
        if count >= 10:
            bg_color = "#FFEBEE"
            border_color = "#EF5350"
            count_color = "#D32F2F"
        elif count >= 5:
            bg_color = "#FFF3E0"
            border_color = "#FF9800"
            count_color = "#E65100"
        elif count >= 3:
            bg_color = "#E3F2FD"
            border_color = "#2196F3"
            count_color = "#1565C0"
        else:
            bg_color = "#F5F5F5"
            border_color = "#9E9E9E"
            count_color = "#616161"
        
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_color};
                border: 2px solid {border_color};
                border-radius: 8px;
                padding: 6px 10px;
                margin: 2px;
            }}
        """)
        
        layout = QHBoxLayout(card)
        layout.setSpacing(10)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # 개수 배지 (3자리 지원)
        count_label = QLabel(f"<b style='font-size:16px; color:{count_color};'>{count}</b>")
        count_label.setFixedWidth(50)
        count_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(count_label)
        
        # 상품 목록 (◆ 구분자로 명확히 구분)
        products = combo_info['products']
        products_text = "  ◆  ".join(products)
        
        prod_label = QLabel(products_text)
        prod_label.setWordWrap(True)
        prod_label.setStyleSheet("font-size: 11px; color: #333; line-height: 1.4;")
        layout.addWidget(prod_label, 1)
        
        # ⭐ 토글 버튼 (여러 송장이 있으면 첫 번째 송장 기준)
        # 실제로는 각 송장별로 별도 카드가 생성되므로 첫 번째 송장만 사용
        if card._tracking_nos:
            tracking_no = card._tracking_nos[0]
            is_priority = self.excel_loader.get_tracking_priority(tracking_no)
            
            star_btn = QPushButton("⭐" if is_priority else "☆")
            star_btn.setCheckable(True)
            star_btn.setChecked(is_priority)
            star_btn.setMaximumWidth(30)
            star_btn.setMaximumHeight(30)
            star_btn.setStyleSheet("""
                QPushButton {
                    border: none;
                    background-color: transparent;
                    font-size: 16px;
                }
                QPushButton:checked {
                    color: #FFD700;
                }
            """)
            star_btn.clicked.connect(lambda checked, tn=tracking_no: self._on_toggle_tracking_priority(tn, checked))
            layout.addWidget(star_btn)
        
        return card
    
    def _flash_card(self, card: QFrame, flash_color: str = "#FFEB3B"):
        """카드 반짝임 효과"""
        if not card:
            return
        
        # 원래 스타일 저장
        original_style = card.styleSheet()
        
        # 반짝임 색상으로 변경
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {flash_color};
                border: 3px solid #FFC107;
                border-radius: 8px;
                padding: 6px 10px;
                margin: 2px;
            }}
        """)
        
        # 0.3초 후 원래 스타일로 복원
        QTimer.singleShot(300, lambda: card.setStyleSheet(original_style))
    
    def _highlight_scanned_cards(self, barcode: str):
        """스캔된 바코드에 해당하는 카드들 반짝임"""
        # 구성별 카드에서 찾기
        for i in range(self.summary_grid.count()):
            item = self.summary_grid.itemAt(i)
            if item and item.widget():
                card = item.widget()
                if hasattr(card, '_barcodes') and barcode in card._barcodes:
                    self._flash_card(card)
        
        # 제품별 카드에서 찾기
        for i in range(self.product_grid.count()):
            item = self.product_grid.itemAt(i)
            if item and item.widget():
                card = item.widget()
                if hasattr(card, '_barcode') and card._barcode == barcode:
                    self._flash_card(card, "#4CAF50")  # 녹색 반짝임
    
    def _update_status_count(self):
        """상태바 카운트 업데이트"""
        if self.excel_loader.df is None:
            self.status_count.setText("처리: 0건")
            return
        
        total = len(self.excel_loader.df['tracking_no'].unique())
        completed = len(self.excel_loader.df[self.excel_loader.df['used'] == 1]['tracking_no'].unique())
        self.status_count.setText(f"처리: {completed}/{total}건")
    
    def _show_load_summary(self):
        """엑셀 로드 후 구성 요약 로그 표시 (다이얼로그 없음)"""
        if self.excel_loader.df is None:
            return
        
        df = self.excel_loader.df
        pending = df[df['used'] == 0]
        
        # 전체 통계
        total_tracking = len(df['tracking_no'].unique())
        pending_tracking = len(pending['tracking_no'].unique())
        
        self._add_log(f"총 송장: {total_tracking}건, 미처리: {pending_tracking}건")
    
    def _add_log(self, message: str, html: bool = False):
        """로그 추가"""
        # log_text가 초기화되지 않았으면 무시
        if not hasattr(self, 'log_text') or self.log_text is None:
            return
        
        timestamp = get_timestamp()
        if html:
            self.log_text.append(f"[{timestamp}] {message}")
        else:
            self.log_text.append(f"[{timestamp}] {message}")
        
        # 스크롤 아래로
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )
    
    def _update_bin_display(self, bin_ids: list = None):
        """
        BIN 주소 표시 업데이트 (여러 BIN 지원)
        
        Args:
            bin_ids: BIN ID 리스트 또는 단일 문자열
        """
        if not hasattr(self, 'bin_layout') or self.bin_layout is None:
            return
        
        # 기존 BIN 레이블 모두 제거
        while self.bin_layout.count():
            item = self.bin_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # bin_ids가 문자열이면 리스트로 변환
        if bin_ids is None:
            bin_ids = ["BIN 미지정"]
        elif isinstance(bin_ids, str):
            bin_ids = [bin_ids]
        
        # 중복 제거 및 정렬
        unique_bins = []
        seen = set()
        for bin_id in bin_ids:
            if bin_id not in seen:
                seen.add(bin_id)
                unique_bins.append(bin_id)
        
        # BIN 번호 기준 정렬
        def get_bin_num(bin_id):
            if bin_id == "BIN 미지정":
                return 999
            try:
                return int(bin_id.split('-')[1])
            except:
                return 999
        
        unique_bins.sort(key=get_bin_num)
        
        # 각 BIN에 대한 레이블 생성
        for bin_id in unique_bins:
            label = QLabel(bin_id)
            label.setFont(QFont("Consolas", 16, QFont.Bold))
            label.setAlignment(Qt.AlignCenter)
            
            # BIN 번호에 따른 색상 지정
            bg_color, text_color = self._get_bin_color(bin_id)
            
            label.setStyleSheet(f"""
                QLabel {{
                    color: {text_color};
                    background-color: {bg_color};
                    padding: 6px 12px;
                    border-radius: 6px;
                }}
            """)
            
            self.bin_layout.addWidget(label)
    
    def _get_bin_color(self, bin_id: str):
        """BIN ID에 따른 색상 반환"""
        if bin_id == "BIN 미지정":
            return "#9E9E9E", "#FFFFFF"
        
        try:
            bin_num = int(bin_id.split('-')[1])
        except:
            return "#9E9E9E", "#FFFFFF"
        
        # BIN 번호에 따른 색상 (1~5: 파랑, 6~10: 초록, 11~15: 주황, 16~: 빨강)
        if bin_num <= 5:
            return "#2196F3", "#FFFFFF"  # 파랑 (가장 많은 SKU)
        elif bin_num <= 10:
            return "#4CAF50", "#FFFFFF"  # 초록
        elif bin_num <= 15:
            return "#FF9800", "#FFFFFF"  # 주황
        else:
            return "#F44336", "#FFFFFF"  # 빨강
    
    def closeEvent(self, event):
        """프로그램 종료 시"""
        # 스캐너 중지
        self.scanner.stop()
        
        # 데이터 저장 확인
        if self.excel_loader.df is not None:
            reply = QMessageBox.question(
                self, "저장 확인",
                "변경사항을 저장하시겠습니까?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
            )
            
            if reply == QMessageBox.Yes:
                success, saved_path = self.excel_loader.save_excel()
                if success:
                    self._add_log(f"종료 시 저장 완료: {saved_path}")
                event.accept()
            elif reply == QMessageBox.No:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


def run_app():
    """애플리케이션 실행"""
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    # 설정 파일 확인 및 생성 (최초 실행 시)
    ensure_settings_file()
    
    # 프린터 설정 유효성 검사 및 경고
    validation = validate_printer_settings()
    
    # 프린터가 없으면 경고 메시지
    if not validation["has_any_printer"]:
        QMessageBox.warning(
            None,
            "프린터 경고",
            "⚠️ 시스템에 프린터가 설치되어 있지 않습니다.\n\n"
            "송장 출력 기능을 사용하려면 프린터를 설치하세요."
        )
    else:
        # 설정된 프린터가 없으면 자동 선택
        label_exists = validation["label_printer"]["exists"]
        label_name = validation["label_printer"]["name"]
        
        if not label_name:
            # 프린터가 설정되지 않았으면 자동 선택
            auto_select_default_printer()
            QMessageBox.information(
                None,
                "프린터 설정",
                "프린터가 설정되지 않아 기본 프린터로 자동 설정되었습니다.\n\n"
                "설정 탭에서 프린터를 변경할 수 있습니다."
            )
        elif not label_exists:
            # 설정된 프린터가 존재하지 않으면 경고
            QMessageBox.warning(
                None,
                "프린터 경고",
                f"⚠️ 설정된 라벨 프린터 '{label_name}'를 찾을 수 없습니다.\n\n"
                f"사용 가능한 프린터: {', '.join(validation['available_printers'][:5])}\n\n"
                f"설정 탭에서 프린터를 다시 선택하세요."
            )
    
    window = MainWindow()
    window.show()
    
    return app.exec()

