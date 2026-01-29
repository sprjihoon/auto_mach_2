"""
UI 대화상자 모듈
SummaryDialog, SetupWizardDialog, SupplierSelectDialog, BinSettingsDialog
"""
import pandas as pd
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QGridLayout, QFrame, QPushButton, QTabWidget, QWidget,
    QTextEdit, QGroupBox, QComboBox, QLineEdit, QSpinBox,
    QCheckBox, QListWidget, QMessageBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from printer_manager import (
    get_printers, save_printer_settings, load_printer_settings,
    save_bin_settings, load_bin_settings,
    get_diagnosis_report, load_esp32_settings, save_esp32_settings,
    load_ezauto_settings, save_ezauto_settings,
    set_first_run_complete
)
from utils import is_admin


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


class SetupWizardDialog(QDialog):
    """첫 실행 설정 마법사 다이얼로그"""
    
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


class SupplierSelectDialog(QDialog):
    """업체(공급처) 선택 다이얼로그 - 다중 선택 지원"""
    
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
