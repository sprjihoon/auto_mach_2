"""
주문 처리 로직
qty/scanned_qty 처리, 우선순위 정렬 로직
"""
from typing import Optional, Tuple, Dict, Set
from PySide6.QtCore import QObject, Signal
import pandas as pd
import threading

from models import ScanResult, ScanEvent
from excel_loader import ExcelLoader
from ezauto_input import EzAutoInput
from pdf_printer import PDFPrinter
from utils import get_timestamp, sanitize_barcode, sanitize_tracking_no

# ESP32 연동 (선택적)
try:
    from device_registry import DeviceRegistry
    from esp32_transport import Esp32Transport, DisplayCommand
    ESP32_AVAILABLE = True
except ImportError:
    ESP32_AVAILABLE = False
    DeviceRegistry = None
    Esp32Transport = None
    DisplayCommand = None

# winsound는 Windows 전용
try:
    import winsound
    HAS_WINSOUND = True
except ImportError:
    HAS_WINSOUND = False
    print("[order_processor] winsound를 사용할 수 없습니다 (Windows 전용)")


def play_scan_sound():
    """스캔 성공 신호음 (짧은 비프)"""
    if not HAS_WINSOUND:
        return
    def _play():
        try:
            winsound.Beep(1000, 100)  # 1000Hz, 100ms
        except Exception:
            pass
    threading.Thread(target=_play, daemon=True).start()


def play_complete_sound():
    """송장 완료 신호음 (멜로디)"""
    if not HAS_WINSOUND:
        return
    def _play():
        try:
            winsound.Beep(800, 150)   # 낮은 음
            winsound.Beep(1000, 150)  # 중간 음
            winsound.Beep(1200, 200)  # 높은 음
        except Exception:
            pass
    threading.Thread(target=_play, daemon=True).start()


def play_error_sound():
    """오류 신호음"""
    if not HAS_WINSOUND:
        return
    def _play():
        try:
            winsound.Beep(300, 300)  # 낮은 음, 긴 소리
        except Exception:
            pass
    threading.Thread(target=_play, daemon=True).start()


class OrderProcessor(QObject):
    """주문 처리 핵심 로직"""
    
    # 시그널
    scan_processed = Signal(object)  # ScanEvent
    tracking_completed = Signal(str)  # tracking_no
    ui_update_required = Signal()
    log_message = Signal(str)  # 로그 메시지
    scanner_pause = Signal()  # 스캐너 일시 중지
    scanner_resume = Signal()  # 스캐너 재개
    
    def __init__(
        self,
        excel_loader: ExcelLoader,
        ezauto_input: EzAutoInput,
        pdf_printer: PDFPrinter
    ):
        super().__init__()
        self.excel = excel_loader
        self.ezauto = ezauto_input
        self.pdf = pdf_printer
        
        # 현재 작업 중인 tracking_no
        self._current_tracking_no: Optional[str] = None
        
        # 처리 중 플래그 (재스캔 방지)
        self._is_processing: bool = False
        self._last_barcode: str = ""
        self._last_scan_time: float = 0
        
        # 우선순위 규칙 (기본값은 excel_loader에서 관리)
        self._priority_rules: Optional[dict] = None
        
        # ★ 세션 내 출력 완료된 송장 추적 (중복 출력 방지)
        self._printed_tracking_nos: set = set()
        self._printing_tracking: set = set()  # 출력 진행 중인 송장
        
        # ★ ESP32 연동 (출고 시 합포장 빈 표시)
        self._device_registry = None
        self._esp32_transport = None
        self._bin_manager = None
        self._esp32_enabled: bool = False
        self._active_bins: Set[str] = set()  # 현재 표시 중인 빈 목록
        
        # 출고 모드 전용 색상
        self.SHIPMENT_COLOR = "red"
    
    @property
    def current_tracking_no(self) -> Optional[str]:
        return self._current_tracking_no
    
    def process_scan(self, barcode: str) -> Optional[ScanEvent]:
        """
        바코드 스캔 처리 메인 로직
        
        1) 바코드 스캔 감지
        2) (barcode == 입력값) AND (used == 0) 조건으로 후보 행 조회
        3) ORDER BY qty ASC, tracking_no ASC 정렬
        4) candidates.iloc[0] 선택
        5) scanned_qty += 1
        6) remaining == 0 이면 PDF 출력, used = 1
        """
        import time as time_module
        
        barcode = sanitize_barcode(barcode)
        timestamp = get_timestamp()
        current_time = time_module.time()
        
        # 같은 바코드 1초 내 재스캔 방지 (스캐너 더블 스캔 방지용)
        if barcode == self._last_barcode and (current_time - self._last_scan_time) < 1.0:
            self.log_message.emit(f"[무시] 더블 스캔 방지: {barcode}")
            # None 대신 일관된 ScanEvent 반환
            return ScanEvent(
                timestamp=timestamp,
                barcode=barcode,
                tracking_no=None,
                result=ScanResult.ERROR,
                message=f"더블 스캔 무시: {barcode}"
            )
        
        self._last_barcode = barcode
        self._last_scan_time = current_time
        
        # 송장번호 형식 감지 (13자리 또는 12자리 숫자) → 무시
        # 송장번호는 보통 12-13자리 숫자이므로, 바코드 스캔과 구분하기 위해 무시
        if barcode.isdigit() and (len(barcode) == 13 or len(barcode) == 12):
            # 엑셀에 해당 송장번호가 실제로 있는지 확인
            # 있으면 정상 처리, 없으면 송장번호 스캔으로 간주하여 무시
            if self.excel.df is not None:
                pending = self.excel.df[self.excel.df['used'] == 0]
                if barcode not in pending['tracking_no'].values:
                    # 엑셀에 없는 13자리 숫자는 송장번호 스캔으로 간주하여 무시
                    event = ScanEvent(
                        timestamp=timestamp,
                        barcode=barcode,
                        tracking_no=None,
                        result=ScanResult.NOT_FOUND,
                        message=f"송장번호 스캔 무시: {barcode}"
                    )
                    self.log_message.emit(f"[정보] 송장번호 스캔 무시: {barcode}")
                    return event
            else:
                # 엑셀 미로드 시 13자리 숫자는 무시
                event = ScanEvent(
                    timestamp=timestamp,
                    barcode=barcode,
                    tracking_no=None,
                    result=ScanResult.NOT_FOUND,
                    message=f"송장번호 스캔 무시: {barcode}"
                )
                self.log_message.emit(f"[정보] 송장번호 스캔 무시: {barcode}")
                return event
        
        self.log_message.emit(f"바코드 스캔: {barcode}")
        
        # 1. 현재 작업 중인 송장이 있으면 그 송장에서만 찾기
        if self._current_tracking_no:
            current_group = self.excel.get_tracking_group(self._current_tracking_no)
            # 대소문자 무시하여 비교
            current_match = current_group[
                (current_group['barcode'].astype(str).str.strip().str.upper() == barcode.upper()) & 
                (current_group['scanned_qty'] < current_group['qty'])
            ]
            
            if not current_match.empty:
                # 현재 송장에서 해당 바코드 처리
                candidates = current_match.reset_index(drop=False)
                self.log_message.emit(f"[디버그] 현재 송장 {self._current_tracking_no}에서 처리")
            else:
                # 현재 송장에 해당 바코드 없음 → 경고음 + 무시
                play_error_sound()  # 경고음 🚨
                
                event = ScanEvent(
                    timestamp=timestamp,
                    barcode=barcode,
                    tracking_no=self._current_tracking_no,
                    result=ScanResult.NOT_FOUND,
                    message=f"⚠️ 현재 송장({self._current_tracking_no})에 '{barcode}' 없음!"
                )
                self.scan_processed.emit(event)
                self.log_message.emit(f"[경고] {event.message}")
                return event
        else:
            # 새 송장 검색 (우선순위 엔진 사용)
            try:
                # 우선순위 규칙 전달 (없으면 excel_loader의 기본 규칙 사용)
                candidates = self.excel.find_candidates(barcode, self._priority_rules)
                self.log_message.emit(f"[디버그] 후보 {len(candidates)}건 찾음")
            except Exception as e:
                self.log_message.emit(f"[오류] 후보 검색 실패: {str(e)}")
                candidates = None
        
        if candidates is None or candidates.empty:
            # 바코드 없음 → 경고음
            play_error_sound()  # 경고음 🚨
            
            event = ScanEvent(
                timestamp=timestamp,
                barcode=barcode,
                tracking_no=None,
                result=ScanResult.NOT_FOUND,
                message=f"⚠️ 바코드 '{barcode}'를 찾을 수 없습니다"
            )
            self.scan_processed.emit(event)
            self.log_message.emit(f"[경고] {event.message}")
            return event
        
        # 2. 첫 번째 후보 선택 (qty 가장 작고, tracking_no 오름차순)
        selected = candidates.iloc[0]
        tracking_no = sanitize_tracking_no(selected['tracking_no'])  # ★ 소숫점 제거
        original_index = selected['index']  # 원본 DataFrame 인덱스
        
        # 3. 이미 사용된 송장인지 확인
        if self.excel.is_tracking_used(tracking_no):
            event = ScanEvent(
                timestamp=timestamp,
                barcode=barcode,
                tracking_no=tracking_no,
                result=ScanResult.ALREADY_USED,
                message=f"이미 처리된 송장입니다: {tracking_no}"
            )
            self.scan_processed.emit(event)
            self.log_message.emit(f"[경고] {event.message}")
            return event
        
        # 4. scanned_qty 증가
        if not self.excel.increment_scanned(original_index):
            event = ScanEvent(
                timestamp=timestamp,
                barcode=barcode,
                tracking_no=tracking_no,
                result=ScanResult.ERROR,
                message=f"스캔 수량 업데이트 실패"
            )
            self.scan_processed.emit(event)
            self.log_message.emit(f"[오류] {event.message}")
            return event
        
        # 5. EzAuto 입력 전송 (같은 송장이면 바코드만)
        is_new_tracking = (self._current_tracking_no != tracking_no)
        
        # 처리 시작
        self._is_processing = True
        
        # 스캐너 일시 중지 (EzAuto 입력 중 키 입력 방지)
        self.scanner_pause.emit()
        
        if is_new_tracking:
            # 새 송장: 송장번호 + 바코드 입력
            self._current_tracking_no = tracking_no
            self.ezauto.send_input(tracking_no, barcode)
            self.log_message.emit(f"[EzAuto] 송장번호 + 바코드 입력: {tracking_no} / {barcode}")
            
            # ★ ESP32: 새 송장 로드 시 남은 제품들의 빈 표시
            self._send_remaining_bins_display(tracking_no, exclude_barcode=barcode)
        else:
            # 같은 송장: 바코드만 입력
            self.ezauto.send_barcode_only(barcode)
            self.log_message.emit(f"[EzAuto] 바코드만 입력: {barcode}")
            
            # ★ ESP32: 스캔 후 빈 표시 업데이트
            self._update_bin_display_after_scan(tracking_no, barcode)
        
        # ★ 스캐너 재개 전 대기 (EzAuto 입력 완료 + 포커스 복귀 안정화)
        import time as time_mod
        time_mod.sleep(0.8)  # 0.5 → 0.8초로 늘림
        
        # 스캐너 재개
        self.log_message.emit("[디버그] 스캐너 재개 준비...")
        self.scanner_resume.emit()
        self.log_message.emit("[디버그] 스캐너 재개 완료 (0.3초 쿨다운 시작)")
        
        # 7. 남은 수량 계산
        remaining = self.excel.get_group_remaining(tracking_no)
        
        # 8. UI 업데이트 요청
        self.ui_update_required.emit()
        
        # 9. 완료 확인
        if remaining == 0:
            # 송장 완료! 스캔 완료 후 PDF 출력
            self.log_message.emit(f"[완료] 송장 {tracking_no} 구성 완료!")
            
            # ★ 중복 출력 방지 (3단계 체크)
            # 1단계: 이미 출력 완료된 송장인지 확인 (세션 내 추적)
            if tracking_no in self._printed_tracking_nos:
                self.log_message.emit(f"⚠️ [중복 방지] 송장 {tracking_no}은(는) 이 세션에서 이미 출력됨 → 출력 건너뛰기")
            # 2단계: 엑셀에서 used=1인지 확인
            elif self.excel.is_tracking_used(tracking_no):
                self.log_message.emit(f"⚠️ [중복 방지] 송장 {tracking_no}은(는) 이미 처리 완료됨 → 출력 건너뛰기")
            # 3단계: 현재 출력 진행 중인지 확인
            elif tracking_no in self._printing_tracking:
                self.log_message.emit(f"⚠️ [중복 방지] 송장 {tracking_no} 출력 진행 중 → 건너뛰기")
            else:
                # 출력 시작 전 플래그 설정
                self._printing_tracking.add(tracking_no)
                
                # PDF 출력 전 상태 체크
                pdf_index_count = len(self.pdf._tracking_index) if hasattr(self.pdf, '_tracking_index') else 0
                if pdf_index_count == 0:
                    self.log_message.emit(f"⚠️ [경고] PDF 인덱스가 비어있습니다! PDF 파일을 먼저 로드하세요.")
                    self.log_message.emit(f"   → '데이터 업로드'에서 송장 라벨 PDF 파일을 선택하세요.")
                
                # PDF 출력 (스캔 완료 후)
                self.log_message.emit(f"[출력] 송장 {tracking_no} PDF 출력 시작 (인덱스: {pdf_index_count}개)")
                if self.pdf.print_pdf(tracking_no):
                    self.log_message.emit(f"[성공] PDF 출력 완료: {tracking_no}")
                    # ★ 출력 완료 후 영구 추적 목록에 추가
                    self._printed_tracking_nos.add(tracking_no)
                else:
                    self.log_message.emit(f"[오류] PDF 출력 실패: {tracking_no}")
                    self.log_message.emit(f"   → PDF 파일이 설정되어 있는지 확인하세요.")
                    self.log_message.emit(f"   → 라벨 프린터가 설정되어 있는지 확인하세요.")
                
                # 출력 완료 후 진행 중 플래그 제거
                self._printing_tracking.discard(tracking_no)
            
            # ★ ESP32: 송장 완료 시 모든 빈 표시 끄기
            self._clear_all_bin_displays()
            
            # 완료 신호음 🎵
            play_complete_sound()
            
            # used = 1 설정
            self.excel.mark_used(tracking_no)
            self.log_message.emit(f"[완료] 송장 {tracking_no} 처리 완료 (used=1)")
            
            # 스캐너 일시 중지 (다음 송장 자동 시작 방지)
            self.scanner_pause.emit()
            
            # 완료 시그널
            self.tracking_completed.emit(tracking_no)
            self._current_tracking_no = None
            
            # ★ 1.2초 대기 후 스캐너 재개 (송장 완료 후 충분한 대기)
            import time as time_mod
            time_mod.sleep(1.2)
            self.log_message.emit("[디버그] 송장 완료 후 스캐너 재개 준비...")
            self.scanner_resume.emit()
            self.log_message.emit("[정보] 다음 송장 스캔 준비 완료 (0.3초 쿨다운 시작)")
            
            event = ScanEvent(
                timestamp=timestamp,
                barcode=barcode,
                tracking_no=tracking_no,
                result=ScanResult.SUCCESS,
                message=f"송장 {tracking_no} 구성 완료!"
            )
        else:
            # 스캔 성공 신호음 🔔
            play_scan_sound()
            
            event = ScanEvent(
                timestamp=timestamp,
                barcode=barcode,
                tracking_no=tracking_no,
                result=ScanResult.SUCCESS,
                message=f"스캔 성공 (남은 수량: {remaining})"
            )
        
        # 처리 완료
        self._is_processing = False
        
        self.scan_processed.emit(event)
        self.log_message.emit(f"[정보] {event.message}")
        return event
    
    def get_current_tracking_items(self) -> pd.DataFrame:
        """현재 작업 중인 tracking_no의 항목들 반환"""
        if not self._current_tracking_no:
            return pd.DataFrame()
        return self.excel.get_tracking_group(self._current_tracking_no)
    
    def get_pending_summary(self) -> pd.DataFrame:
        """미처리 항목 요약"""
        return self.excel.get_summary_by_barcode()
    
    def reset_current_tracking(self):
        """현재 tracking_no 초기화"""
        # ★ ESP32: 빈 표시 끄기
        self._clear_all_bin_displays()
        
        self._current_tracking_no = None
        self.ui_update_required.emit()
    
    def set_priority_rules(self, rules: dict):
        """
        우선순위 규칙 설정
        
        Args:
            rules: 우선순위 규칙 딕셔너리
        """
        self._priority_rules = rules
        # excel_loader에도 전달
        self.excel.set_priority_rules(rules)
    
    def get_printed_tracking_nos(self) -> set:
        """
        이 세션에서 출력된 송장번호 목록 반환
        
        Returns:
            출력된 송장번호 set
        """
        return self._printed_tracking_nos.copy()
    
    def set_printed_tracking_nos(self, tracking_nos: set):
        """
        출력된 송장번호 목록 설정 (세션 복원 시 사용)
        
        Args:
            tracking_nos: 출력된 송장번호 set
        """
        self._printed_tracking_nos = set(tracking_nos) if tracking_nos else set()
    
    def add_printed_tracking_no(self, tracking_no: str):
        """
        출력된 송장번호 추가 (외부에서 출력 시 사용)
        
        Args:
            tracking_no: 출력된 송장번호
        """
        self._printed_tracking_nos.add(tracking_no)
    
    def is_already_printed(self, tracking_no: str) -> bool:
        """
        해당 송장이 이미 출력되었는지 확인
        
        Args:
            tracking_no: 확인할 송장번호
        
        Returns:
            이미 출력되었으면 True
        """
        return tracking_no in self._printed_tracking_nos
    
    def clear_printed_tracking_nos(self):
        """
        출력된 송장번호 목록 초기화 (새 세션 시작 시)
        """
        self._printed_tracking_nos.clear()
        self._printing_tracking.clear()
    
    # ===== ESP32 연동 메서드 (출고 시 합포장 빈 표시) =====
    
    def set_esp32(self, device_registry=None, esp32_transport=None, bin_manager=None):
        """
        ESP32 연동 설정 (출고 시 합포장 빈 위치 + 수량 표시)
        
        Args:
            device_registry: DeviceRegistry 객체
            esp32_transport: Esp32Transport 객체
            bin_manager: BinManager 객체
        """
        self._device_registry = device_registry
        self._esp32_transport = esp32_transport
        self._bin_manager = bin_manager
        
        # ESP32 연동 활성화 여부 체크
        self._esp32_enabled = (
            ESP32_AVAILABLE and 
            device_registry is not None and 
            esp32_transport is not None and 
            bin_manager is not None
        )
        
        if self._esp32_enabled:
            self.log_message.emit("[ESP32] 출고 모드 ESP32 연동 활성화됨")
        else:
            self.log_message.emit("[ESP32] 출고 모드 ESP32 연동 비활성화")
    
    def _send_remaining_bins_display(self, tracking_no: str, exclude_barcode: str = None):
        """
        현재 송장의 아직 스캔하지 않은 제품들의 빈에 수량 표시
        
        Args:
            tracking_no: 송장번호
            exclude_barcode: 방금 스캔한 바코드 (표시 제외)
        """
        if not self._esp32_enabled:
            return
        
        if not self._esp32_transport.is_running:
            return
        
        # 현재 표시 중인 빈 초기화
        self._clear_all_bin_displays()
        
        # 해당 송장의 모든 항목 조회
        items = self.excel.get_tracking_group(tracking_no)
        if items.empty:
            return
        
        # 빈별 남은 수량 집계
        bin_qty_map: Dict[str, int] = {}
        
        for _, row in items.iterrows():
            barcode = str(row['barcode']).strip()
            qty = int(row['qty'])
            scanned_qty = int(row.get('scanned_qty', 0))
            remaining = qty - scanned_qty
            
            # 방금 스캔한 바코드는 제외 (이미 처리됨)
            if exclude_barcode and barcode.upper() == exclude_barcode.upper():
                # 스캔 후 남은 수량 계산 (scanned_qty가 아직 업데이트 안됐을 수 있음)
                remaining = remaining - 1
            
            if remaining <= 0:
                continue
            
            # 빈 조회
            bin_id = self._bin_manager.get_sku_bin(barcode)
            if bin_id == "BIN 미지정":
                continue
            
            # 빈별 수량 합산
            if bin_id not in bin_qty_map:
                bin_qty_map[bin_id] = 0
            bin_qty_map[bin_id] += remaining
        
        # 각 빈에 표시 전송
        for bin_id, qty in bin_qty_map.items():
            if qty <= 0:
                continue
            
            device_id = self._device_registry.get_device_id_by_bin(bin_id)
            if not device_id:
                self.log_message.emit(f"[ESP32] BIN {bin_id}에 연결된 장치 없음")
                continue
            
            # 디스플레이 명령 전송
            cmd = DisplayCommand(
                mode="shipment",
                bin_id=bin_id,
                color=self.SHIPMENT_COLOR,
                qty=qty,
                blink=False
            )
            
            if self._esp32_transport.send_display(device_id, cmd):
                self._active_bins.add(bin_id)
                self.log_message.emit(f"[ESP32] {bin_id} 표시: {qty}개 (빨간색)")
            else:
                self.log_message.emit(f"[ESP32] {bin_id} 전송 실패")
    
    def _update_bin_display_after_scan(self, tracking_no: str, scanned_barcode: str):
        """
        스캔 후 빈 표시 업데이트 (해당 제품의 빈만 업데이트)
        
        Args:
            tracking_no: 송장번호
            scanned_barcode: 스캔된 바코드
        """
        if not self._esp32_enabled:
            return
        
        if not self._esp32_transport.is_running:
            return
        
        # 스캔된 바코드의 빈 조회
        bin_id = self._bin_manager.get_sku_bin(scanned_barcode)
        if bin_id == "BIN 미지정":
            return
        
        # 해당 송장에서 이 빈에 속한 제품들의 남은 수량 계산
        items = self.excel.get_tracking_group(tracking_no)
        if items.empty:
            return
        
        remaining_qty = 0
        for _, row in items.iterrows():
            barcode = str(row['barcode']).strip()
            item_bin = self._bin_manager.get_sku_bin(barcode)
            
            if item_bin != bin_id:
                continue
            
            qty = int(row['qty'])
            scanned_qty = int(row.get('scanned_qty', 0))
            remaining = qty - scanned_qty
            
            if remaining > 0:
                remaining_qty += remaining
        
        # 남은 수량이 있으면 업데이트, 없으면 끄기
        device_id = self._device_registry.get_device_id_by_bin(bin_id)
        if not device_id:
            return
        
        if remaining_qty > 0:
            # 수량 업데이트
            cmd = DisplayCommand(
                mode="shipment",
                bin_id=bin_id,
                color=self.SHIPMENT_COLOR,
                qty=remaining_qty,
                blink=False
            )
            self._esp32_transport.send_display(device_id, cmd)
            self.log_message.emit(f"[ESP32] {bin_id} 업데이트: {remaining_qty}개")
        else:
            # 해당 빈 끄기
            self._clear_bin_display(bin_id)
    
    def _clear_bin_display(self, bin_id: str):
        """
        특정 빈의 표시 끄기
        
        Args:
            bin_id: 빈 ID
        """
        if not self._esp32_enabled:
            return
        
        if bin_id not in self._active_bins:
            return
        
        device_id = self._device_registry.get_device_id_by_bin(bin_id)
        if device_id:
            self._esp32_transport.send_off(device_id, bin_id)
            self.log_message.emit(f"[ESP32] {bin_id} OFF")
        
        self._active_bins.discard(bin_id)
    
    def _clear_all_bin_displays(self):
        """
        모든 활성 빈의 표시 끄기
        """
        if not self._esp32_enabled:
            return
        
        for bin_id in list(self._active_bins):
            device_id = self._device_registry.get_device_id_by_bin(bin_id)
            if device_id:
                self._esp32_transport.send_off(device_id, bin_id)
        
        if self._active_bins:
            self.log_message.emit(f"[ESP32] 모든 빈 표시 OFF ({len(self._active_bins)}개)")
        
        self._active_bins.clear()

