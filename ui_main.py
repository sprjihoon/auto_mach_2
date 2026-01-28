"""
PySide6 UI 화면
"""
import sys
import os
import re
from pathlib import Path
from typing import Optional
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


class SummaryDialog(QDialog):
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
    save_bin_settings, load_bin_settings
)
from pdf_search import find_pdf_by_tracking_or_order
from reprint_pdf_extractor import extract_pages_from_pdf, extract_reprint_page_to_temp
from bin_manager import BinManager


class SupplierSelectDialog(QDialog):
    """업체(공급처) 선택 다이얼로그"""
    
    def __init__(self, supplier_summary: list, parent=None):
        """
        Args:
            supplier_summary: [{"supplier": "업체A", "order_count": 10, "item_count": 50}, ...]
        """
        super().__init__(parent)
        self.supplier_summary = supplier_summary
        self.selected_supplier = None
        self.setWindowTitle("🏢 업체 선택")
        self.setMinimumSize(500, 400)
        self._init_ui()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # 헤더
        header = QLabel("<h2>🏢 업체를 선택하세요</h2>")
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)
        
        # 설명
        desc = QLabel(
            "엑셀 파일에 여러 업체(공급처)의 데이터가 포함되어 있습니다.\n"
            "작업할 업체를 선택해주세요."
        )
        desc.setStyleSheet("color: #666; padding: 10px; background: #f5f5f5; border-radius: 5px;")
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignCenter)
        layout.addWidget(desc)
        
        # 업체 목록 (라디오 버튼)
        list_group = QGroupBox("업체 목록")
        list_layout = QVBoxLayout(list_group)
        
        # 스크롤 영역
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(8)
        
        self.supplier_group = QButtonGroup(self)
        
        # 전체 옵션 추가
        total_orders = sum(s["order_count"] for s in self.supplier_summary)
        total_items = sum(s["item_count"] for s in self.supplier_summary)
        
        all_radio = QRadioButton(f"전체 ({len(self.supplier_summary)}개 업체, {total_orders}건, {total_items}개)")
        all_radio.setStyleSheet("font-weight: bold; font-size: 13px; padding: 8px;")
        all_radio.setProperty("supplier", "전체")
        self.supplier_group.addButton(all_radio)
        scroll_layout.addWidget(all_radio)
        
        # 구분선
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background-color: #ddd;")
        scroll_layout.addWidget(line)
        
        # 각 업체별 라디오 버튼
        for idx, item in enumerate(self.supplier_summary):
            supplier = item["supplier"]
            order_count = item["order_count"]
            item_count = item["item_count"]
            
            radio = QRadioButton(f"{supplier}  ({order_count}건, {item_count}개)")
            radio.setStyleSheet("font-size: 12px; padding: 6px;")
            radio.setProperty("supplier", supplier)
            self.supplier_group.addButton(radio)
            scroll_layout.addWidget(radio)
        
        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        list_layout.addWidget(scroll)
        
        layout.addWidget(list_group, 1)
        
        # 버튼 영역
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        cancel_btn = QPushButton("취소")
        cancel_btn.setMinimumWidth(100)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        select_btn = QPushButton("선택")
        select_btn.setMinimumWidth(100)
        select_btn.setStyleSheet("background: #4CAF50; color: white; font-weight: bold;")
        select_btn.clicked.connect(self._on_select)
        btn_layout.addWidget(select_btn)
        
        layout.addLayout(btn_layout)
    
    def _on_select(self):
        """업체 선택 확정"""
        checked_btn = self.supplier_group.checkedButton()
        if checked_btn:
            self.selected_supplier = checked_btn.property("supplier")
            self.accept()
        else:
            QMessageBox.warning(self, "경고", "업체를 선택해주세요.")
    
    def get_selected_supplier(self) -> str:
        """선택된 업체 반환"""
        return self.selected_supplier


class BinSettingsDialog(QDialog):
    """BIN 설정 다이얼로그"""
    
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
        
        # 우선순위 규칙 초기화 (기본값: 단품 우선)
        from priority_engine import get_default_rules
        self.processor.set_priority_rules(get_default_rules())
        
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
        
        # 재출력 탭
        self.reprint_tab = self._create_reprint_tab()
        self.tab_widget.addTab(self.reprint_tab, "재출력")
        
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
        """상단 섹션: 파일 로드 및 설정"""
        group = QGroupBox("설정")
        layout = QHBoxLayout(group)
        layout.setSpacing(5)  # 요소간 간격 줄임
        
        # 엑셀 파일 경로
        layout.addWidget(QLabel("엑셀:"))
        self.excel_path_edit = QLineEdit()
        self.excel_path_edit.setPlaceholderText("엑셀 파일 선택")
        self.excel_path_edit.setMaximumWidth(180)
        layout.addWidget(self.excel_path_edit)
        
        # 찾아보기 버튼
        self.browse_btn = QPushButton("찾아보기")
        self.browse_btn.clicked.connect(self._on_browse_excel)
        layout.addWidget(self.browse_btn)
        
        # 로드 버튼
        self.load_btn = QPushButton("불러오기")
        self.load_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        self.load_btn.clicked.connect(self._on_load_excel)
        layout.addWidget(self.load_btn)
        
        # 구성 요약 버튼
        self.summary_btn = QPushButton("📦 구성요약")
        self.summary_btn.clicked.connect(self._on_show_summary)
        layout.addWidget(self.summary_btn)
        
        # 업체 변경 버튼
        self.supplier_btn = QPushButton("🏢 업체변경")
        self.supplier_btn.clicked.connect(self._on_change_supplier)
        self.supplier_btn.setToolTip("다른 업체(공급처)로 변경")
        layout.addWidget(self.supplier_btn)
        
        layout.addSpacing(15)
        
        # PDF 파일 경로
        layout.addWidget(QLabel("PDF:"))
        self.pdf_path_edit = QLineEdit()
        self.pdf_path_edit.setPlaceholderText("PDF 선택")
        self.pdf_path_edit.setMaximumWidth(180)
        layout.addWidget(self.pdf_path_edit)
        
        # PDF 파일 찾아보기 버튼
        self.pdf_browse_btn = QPushButton("파일 선택")
        self.pdf_browse_btn.clicked.connect(self._on_browse_pdf_file)
        layout.addWidget(self.pdf_browse_btn)
        
        layout.addSpacing(15)
        
        # 스캐너 시작/중지 버튼 제거 (자동 시작으로 변경)
        # self.scanner_btn = QPushButton("스캐너 시작")
        # self.scanner_btn.setCheckable(True)
        # self.scanner_btn.clicked.connect(self._on_toggle_scanner)
        # self.scanner_btn.setMinimumWidth(100)
        # layout.addWidget(self.scanner_btn)
        
        # EzAuto 창 제목
        layout.addWidget(QLabel("창 제목:"))
        self.ezauto_title_edit = QLineEdit()
        self.ezauto_title_edit.setText("이지오토")
        self.ezauto_title_edit.setMaximumWidth(80)
        self.ezauto_title_edit.textChanged.connect(self._on_ezauto_title_changed)
        layout.addWidget(self.ezauto_title_edit)
        
        # EzAuto 활성화
        self.ezauto_check = QCheckBox("EzAuto 입력")
        self.ezauto_check.setChecked(True)
        self.ezauto_check.toggled.connect(self._on_toggle_ezauto)
        layout.addWidget(self.ezauto_check)
        
        # PDF 출력 활성화
        self.pdf_check = QCheckBox("PDF 출력")
        self.pdf_check.setChecked(True)
        self.pdf_check.toggled.connect(self._on_toggle_pdf)
        layout.addWidget(self.pdf_check)
        
        # PDF 임시 파일 보관 옵션
        self.pdf_keep_temp_check = QCheckBox("임시 파일 보관")
        self.pdf_keep_temp_check.setChecked(False)  # 기본값: 삭제
        self.pdf_keep_temp_check.setToolTip("체크 시 출력 후 임시 PDF 파일을 보관합니다 (기본: 출력 후 삭제)")
        self.pdf_keep_temp_check.toggled.connect(self._on_toggle_pdf_keep_temp)
        layout.addWidget(self.pdf_keep_temp_check)
        
        layout.addSpacing(15)
        
        # 주문서 출력 기능
        self.order_sheet_check = QCheckBox("주문서출력")
        self.order_sheet_check.setChecked(False)
        self.order_sheet_check.setToolTip("체크 시 두 번째 PDF 파일을 다른 프린터로 동시 출력합니다")
        self.order_sheet_check.toggled.connect(self._on_toggle_order_sheet)
        layout.addWidget(self.order_sheet_check)
        
        # 주문서 PDF 파일 경로 (체크박스 활성화 시에만 표시)
        self.pdf_path_2_edit = QLineEdit()
        self.pdf_path_2_edit.setPlaceholderText("주문서 PDF 선택")
        self.pdf_path_2_edit.setMaximumWidth(180)
        self.pdf_path_2_edit.setEnabled(False)
        layout.addWidget(self.pdf_path_2_edit)
        
        # 주문서 PDF 파일 찾아보기 버튼
        self.pdf_browse_2_btn = QPushButton("주문서 선택")
        self.pdf_browse_2_btn.setEnabled(False)
        self.pdf_browse_2_btn.clicked.connect(self._on_browse_pdf_file_2)
        layout.addWidget(self.pdf_browse_2_btn)
        
        # 오른쪽 여백 (창 최대화 시 벌어짐 방지)
        layout.addStretch()
        
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
        
        # 수동 바코드 입력
        manual_layout = QHBoxLayout()
        self.manual_barcode_edit = QLineEdit()
        self.manual_barcode_edit.setPlaceholderText("수동 바코드 입력")
        self.manual_barcode_edit.returnPressed.connect(self._on_manual_scan)
        manual_layout.addWidget(self.manual_barcode_edit)
        
        self.manual_scan_btn = QPushButton("스캔")
        self.manual_scan_btn.clicked.connect(self._on_manual_scan)
        manual_layout.addWidget(self.manual_scan_btn)
        
        right_layout.addLayout(manual_layout)
        
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
        """로그 섹션"""
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
        
        # 프린터 설정 그룹 (로그 지우기 옆에 배치)
        btn_layout.addSpacing(10)
        btn_layout.addWidget(QLabel("라벨 프린터:"))
        self.label_printer_combo = QComboBox()
        self.label_printer_combo.setMaximumWidth(150)
        self.label_printer_combo.setToolTip("송장(라벨)을 출력할 프린터를 선택하세요")
        btn_layout.addWidget(self.label_printer_combo)
        
        # 라벨 테스트 출력 버튼
        self.label_test_btn = QPushButton("테스트")
        self.label_test_btn.setMaximumWidth(60)
        self.label_test_btn.setToolTip("라벨 프린터 테스트 출력")
        self.label_test_btn.clicked.connect(self._on_test_label_printer)
        btn_layout.addWidget(self.label_test_btn)
        
        btn_layout.addSpacing(10)
        
        # A4 프린터 선택
        btn_layout.addWidget(QLabel("A4 프린터:"))
        self.a4_printer_combo = QComboBox()
        self.a4_printer_combo.setMaximumWidth(150)
        self.a4_printer_combo.setToolTip("주문서(A4)를 출력할 프린터를 선택하세요")
        btn_layout.addWidget(self.a4_printer_combo)
        
        # A4 테스트 출력 버튼
        self.a4_test_btn = QPushButton("테스트")
        self.a4_test_btn.setMaximumWidth(60)
        self.a4_test_btn.setToolTip("A4 프린터 테스트 출력")
        self.a4_test_btn.clicked.connect(self._on_test_a4_printer)
        btn_layout.addWidget(self.a4_test_btn)
        
        btn_layout.addSpacing(10)
        
        # BIN 설정 버튼
        self.bin_settings_btn = QPushButton("🗃️ BIN 설정")
        self.bin_settings_btn.setToolTip("BIN 배정 설정 (최대수량, 공유 BIN 등)")
        self.bin_settings_btn.clicked.connect(self._on_bin_settings)
        btn_layout.addWidget(self.bin_settings_btn)
        
        btn_layout.addStretch()
        
        # 저장 경로 설정
        btn_layout.addWidget(QLabel("저장 위치:"))
        self.save_path_edit = QLineEdit()
        self.save_path_edit.setPlaceholderText("저장 위치 선택")
        self.save_path_edit.setMaximumWidth(200)
        btn_layout.addWidget(self.save_path_edit)
        
        self.save_browse_btn = QPushButton("위치 선택")
        self.save_browse_btn.clicked.connect(self._on_browse_save_path)
        btn_layout.addWidget(self.save_browse_btn)
        
        # 저장 버튼
        save_btn = QPushButton("엑셀 저장")
        save_btn.clicked.connect(self._on_save_excel)
        btn_layout.addWidget(save_btn)
        
        # 제품별 PDF 저장 버튼
        pdf_save_btn = QPushButton("📄 피킹리스트 PDF")
        pdf_save_btn.clicked.connect(self._on_save_product_pdf)
        btn_layout.addWidget(pdf_save_btn)
        
        # 피킹리스트 열기 버튼
        self.open_pdf_btn = QPushButton("📂 피킹리스트 열기")
        self.open_pdf_btn.clicked.connect(self._on_open_picking_pdf)
        self.open_pdf_btn.setEnabled(False)  # 초기에는 비활성화
        btn_layout.addWidget(self.open_pdf_btn)
        
        # 마지막 저장된 PDF 경로
        self._last_pdf_path = None
        
        layout.addLayout(btn_layout)
        
        return group
    
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
    
    @Slot(int)
    def _on_pdf_indexed(self, count: int):
        """PDF 인덱싱 완료"""
        if count > 0:
            self._add_log(f"PDF 인덱스: {count}개 송장번호")
        
        # Processor 시그널
        self.processor.scan_processed.connect(self._on_scan_processed)
        self.processor.tracking_completed.connect(self._on_tracking_completed)
        self.processor.ui_update_required.connect(self._update_tables)
        self.processor.log_message.connect(self._add_log)
        self.processor.scanner_pause.connect(self.scanner.pause)
        self.processor.scanner_resume.connect(self.scanner.resume)
    
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
        """엑셀 파일 로드"""
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
                    # 여러 업체가 있으면 선택 다이얼로그 표시
                    self._add_log(f"[업체] {len(supplier_summary)}개 업체 발견: {', '.join([s['supplier'] for s in supplier_summary])}")
                    
                    dialog = SupplierSelectDialog(supplier_summary, self)
                    if dialog.exec() == QDialog.Accepted:
                        selected = dialog.get_selected_supplier()
                        if selected and selected != "전체":
                            # 선택한 업체로 필터링
                            self.excel_loader.filter_by_supplier(selected)
                            self._add_log(f"<b style='color:#2196F3'>[업체] '{selected}' 선택됨 - {self.excel_loader.get_filtered_order_count()}건</b>", html=True)
                        else:
                            self._add_log(f"[업체] 전체 업체 선택 - {self.excel_loader.get_total_order_count()}건")
                    else:
                        # 취소 시 로드 중단
                        self._add_log("[업체] 업체 선택 취소됨 - 로드 중단")
                        return
                elif len(supplier_summary) == 1:
                    # 업체가 하나뿐이면 자동 선택
                    supplier = supplier_summary[0]["supplier"]
                    self._add_log(f"[업체] 단일 업체: '{supplier}' 자동 선택")
                else:
                    self._add_log("[업체] 공급처 데이터 없음")
            
            # 현재 선택된 업체 표시
            current_supplier = self.excel_loader.get_current_supplier()
            if current_supplier:
                self.status_file.setText(f"파일: {Path(file_path).name} | 업체: {current_supplier}")
            else:
                self.status_file.setText(f"파일: {Path(file_path).name}")
            
            # 이후 로직 실행 (BIN 배정, PDF 스캔 등)
            self._process_after_supplier_selection(file_path)
    
    def _process_after_supplier_selection(self, file_path: str):
        """업체 선택 후 실행되는 로직 (BIN 배정, PDF 스캔 등)"""
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
        
        # 1) BIN 전체 리셋
        self.bin_manager.reset()
        self._add_log("[BIN] BIN 정보 리셋 완료")
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
    
    @Slot()
    def _on_change_supplier(self):
        """업체(공급처) 변경"""
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
        
        # 업체 선택 다이얼로그 표시
        dialog = SupplierSelectDialog(supplier_summary, self)
        if dialog.exec() == QDialog.Accepted:
            selected = dialog.get_selected_supplier()
            current = self.excel_loader.get_current_supplier()
            
            # 같은 업체 선택 시 무시
            if selected == current or (selected == "전체" and current is None):
                self._add_log("[업체] 동일한 업체 선택됨 - 변경 없음")
                return
            
            # 업체 변경 적용
            if selected and selected != "전체":
                self.excel_loader.filter_by_supplier(selected)
                self._add_log(f"<b style='color:#FF9800'>[업체 변경] '{selected}' 선택됨 - {self.excel_loader.get_filtered_order_count()}건</b>", html=True)
            else:
                self.excel_loader.filter_by_supplier(None)
                self._add_log(f"<b style='color:#FF9800'>[업체 변경] 전체 업체 선택 - {self.excel_loader.get_total_order_count()}건</b>", html=True)
            
            # 상태바 업데이트
            file_path = self.excel_path_edit.text().strip()
            current_supplier = self.excel_loader.get_current_supplier()
            if current_supplier:
                self.status_file.setText(f"파일: {Path(file_path).name} | 업체: {current_supplier}")
            else:
                self.status_file.setText(f"파일: {Path(file_path).name}")
            
            # BIN 및 PDF 재처리
            self._process_after_supplier_selection(file_path)
            
            QMessageBox.information(
                self,
                "업체 변경 완료",
                f"업체가 변경되었습니다.\n\n"
                f"선택 업체: {selected}\n"
                f"주문 건수: {self.excel_loader.get_filtered_order_count()}건"
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
        
        # 저장 경로가 지정되어 있으면 해당 폴더에 자동 저장
        save_path = self.save_path_edit.text().strip()
        if save_path:
            # 지정된 경로의 폴더에 피킹리스트 PDF 저장
            save_dir = Path(save_path).parent
            file_path = str(save_dir / f"피킹리스트_{timestamp}.pdf")
        else:
            # 파일 저장 경로 선택 (기본 파일명에 타임스탬프 포함)
            default_name = f"피킹리스트_{timestamp}.pdf"
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
            
            # PDF 생성
            doc = SimpleDocTemplate(file_path, pagesize=A4, 
                                   leftMargin=15*mm, rightMargin=15*mm,
                                   topMargin=15*mm, bottomMargin=15*mm)
            
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
            
            # 제목
            from datetime import datetime
            title = Paragraph(f"제품별 피킹 리스트 ({datetime.now().strftime('%Y-%m-%d %H:%M')})", title_style)
            elements.append(title)
            elements.append(Spacer(1, 10*mm))
            
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
            
            # PDF 저장
            doc.build(elements)
            
            self._add_log(f"제품별 PDF 저장 완료: {file_path}")
            
            # 마지막 PDF 경로 저장 및 열기 버튼 활성화
            self._last_pdf_path = file_path
            self.open_pdf_btn.setEnabled(True)
            
            QMessageBox.information(self, "성공", f"PDF가 저장되었습니다.\n{file_path}")
            
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
    def _on_test_label_printer(self):
        """라벨 프린터 테스트 출력"""
        printer_name = self.label_printer_combo.currentText()
        if not printer_name or printer_name == "프린터 없음":
            QMessageBox.warning(self, "경고", "라벨 프린터를 먼저 선택해주세요.")
            return
        
        # 테스트 PDF 파일 경로
        test_pdf_path = Path(__file__).parent / "labels" / "test_label.pdf"
        
        # 테스트 파일이 없으면 임시 파일 생성
        if not test_pdf_path.exists():
            test_pdf_path.parent.mkdir(exist_ok=True)
            try:
                from reportlab.pdfgen import canvas
                from reportlab.lib.pagesizes import letter
                c = canvas.Canvas(str(test_pdf_path), pagesize=letter)
                c.drawString(100, 750, "라벨 프린터 테스트")
                c.drawString(100, 730, f"프린터: {printer_name}")
                c.save()
            except ImportError:
                QMessageBox.warning(self, "경고", "테스트 PDF 생성에 필요한 라이브러리가 없습니다.")
                return
        
        # 출력
        if print_pdf_with_printer(str(test_pdf_path), printer_name):
            self._add_log(f"라벨 프린터 테스트 출력 완료: {printer_name}")
        else:
            QMessageBox.warning(self, "오류", f"라벨 프린터 테스트 출력 실패: {printer_name}")
    
    @Slot()
    def _on_test_a4_printer(self):
        """A4 프린터 테스트 출력"""
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
            self.priority_small_qty_radio.blockSignals(True)
            self.priority_large_qty_radio.blockSignals(True)
            self.priority_no_qty_radio.blockSignals(True)
            self.priority_old_order_radio.blockSignals(True)
            self.priority_new_order_radio.blockSignals(True)
            self.priority_no_time_radio.blockSignals(True)
            
            self.priority_single_radio.setChecked(rules["single_first"])
            self.priority_combo_radio.setChecked(rules["combo_first"])
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
        
        self.processor.process_scan(barcode)
    
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
    
    @Slot()
    def _on_data_updated(self):
        """데이터 업데이트"""
        self._update_tables()
    
    @Slot(str)
    def _on_error(self, message: str):
        """오류 발생"""
        self._add_log(f"<span style='color:#F44336'>[오류] {message}</span>", html=True)
    
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
            return
        
        self.current_tracking_label.setText(tracking_no)
        
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
    
    window = MainWindow()
    window.show()
    
    return app.exec()

