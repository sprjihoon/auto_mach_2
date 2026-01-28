"""
전체피킹(FULL_PICK) 엔진
SKU 기준 여러 주문 수량 합산 → BIN별 분배 피킹 모드

동작:
1. SKU 바코드 스캔
2. 해당 SKU 포함 주문들 조회
3. BIN별 수량 합산
4. PC 화면 + ESP32 LCD에 표시
5. 작업자가 각 BIN에 투입 후 터치
6. 모든 BIN 완료 시 SKU 피킹 완료
"""
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from PySide6.QtCore import QObject, Signal
import pandas as pd
import winsound
import threading

from mode_manager import FullPickState
from device_registry import DeviceRegistry
from esp32_transport import Esp32Transport, DisplayCommand


def play_fullpick_start_sound():
    """전체피킹 시작 신호음"""
    def _play():
        winsound.Beep(800, 100)
        winsound.Beep(1000, 100)
    threading.Thread(target=_play, daemon=True).start()


def play_bin_done_sound():
    """BIN 완료 신호음"""
    def _play():
        winsound.Beep(1200, 80)
    threading.Thread(target=_play, daemon=True).start()


def play_sku_complete_sound():
    """SKU 피킹 완료 신호음"""
    def _play():
        winsound.Beep(800, 150)
        winsound.Beep(1000, 150)
        winsound.Beep(1200, 200)
    threading.Thread(target=_play, daemon=True).start()


def play_error_sound():
    """오류 신호음"""
    def _play():
        winsound.Beep(300, 300)
    threading.Thread(target=_play, daemon=True).start()


@dataclass
class BinPickTask:
    """BIN별 피킹 작업"""
    bin_id: str
    qty: int                    # 피킹 수량
    done: bool = False          # 완료 여부
    order_indices: List[int] = field(default_factory=list)  # 관련 주문 인덱스


@dataclass
class SkuPickSession:
    """SKU 피킹 세션"""
    barcode: str                         # SKU 바코드
    total_qty: int                       # 총 피킹 수량
    bins: Dict[str, BinPickTask] = field(default_factory=dict)  # bin_id → BinPickTask
    
    @property
    def completed_qty(self) -> int:
        """완료된 수량"""
        return sum(b.qty for b in self.bins.values() if b.done)
    
    @property
    def remaining_qty(self) -> int:
        """남은 수량"""
        return self.total_qty - self.completed_qty
    
    @property
    def completed_bins(self) -> int:
        """완료된 BIN 수"""
        return sum(1 for b in self.bins.values() if b.done)
    
    @property
    def total_bins(self) -> int:
        """전체 BIN 수"""
        return len(self.bins)
    
    @property
    def is_complete(self) -> bool:
        """전체 완료 여부"""
        return all(b.done for b in self.bins.values()) if self.bins else False


class FullPickEngine(QObject):
    """
    전체피킹 엔진
    
    SKU 스캔 → BIN별 수량 계산 → LCD 표시 → 터치 완료 처리
    """
    
    # 시그널
    session_started = Signal(str, int)     # barcode, total_qty
    bin_list_ready = Signal(list)          # [(bin_id, qty), ...]
    bin_completed = Signal(str, int)       # bin_id, qty
    session_completed = Signal(str, int)   # barcode, total_qty
    state_changed = Signal(object)         # FullPickState
    error_occurred = Signal(str)           # error message
    log_message = Signal(str)              # 로그 메시지
    
    # 전체피킹 전용 색상
    FULL_PICK_COLOR = "purple"
    
    def __init__(self, 
                 device_registry: DeviceRegistry = None,
                 esp32_transport: Esp32Transport = None):
        super().__init__()
        
        # 의존성
        self._device_registry = device_registry
        self._esp32_transport = esp32_transport
        
        # 현재 세션
        self._current_session: Optional[SkuPickSession] = None
        
        # 상태
        self._state: FullPickState = FullPickState.IDLE
        
        # 데이터 참조 (ui_main에서 설정)
        self._excel_df: Optional[pd.DataFrame] = None
        self._bin_manager = None  # BinManager 참조
        
        # ESP32 연동 활성화 여부
        self._lcd_enabled: bool = True
    
    @property
    def state(self) -> FullPickState:
        """현재 상태"""
        return self._state
    
    @property
    def current_session(self) -> Optional[SkuPickSession]:
        """현재 피킹 세션"""
        return self._current_session
    
    @property
    def is_active(self) -> bool:
        """피킹 진행 중 여부"""
        return self._current_session is not None
    
    def set_data_source(self, df: pd.DataFrame, bin_manager):
        """
        데이터 소스 설정
        
        Args:
            df: 엑셀 DataFrame
            bin_manager: BinManager 객체
        """
        self._excel_df = df
        self._bin_manager = bin_manager
    
    def set_device_registry(self, registry: DeviceRegistry):
        """DeviceRegistry 설정"""
        self._device_registry = registry
    
    def set_esp32_transport(self, transport: Esp32Transport):
        """Esp32Transport 설정"""
        self._esp32_transport = transport
        
        # done 이벤트 연결
        if transport:
            transport.device_done.connect(self._on_device_done)
    
    def enable_lcd(self, enabled: bool = True):
        """LCD 연동 활성화/비활성화"""
        self._lcd_enabled = enabled
    
    def _set_state(self, state: FullPickState):
        """상태 변경"""
        if state != self._state:
            self._state = state
            self.state_changed.emit(state)
    
    def process_scan(self, barcode: str) -> bool:
        """
        바코드 스캔 처리
        
        Args:
            barcode: 스캔된 SKU 바코드
        
        Returns:
            처리 성공 여부
        """
        barcode = str(barcode).strip()
        
        # 이미 세션 진행 중이면 무시 (같은 SKU 재스캔 방지)
        if self._current_session:
            if self._current_session.barcode == barcode:
                self.log_message.emit(f"[전체피킹] 이미 진행중인 SKU: {barcode}")
                return False
            else:
                # 다른 SKU 스캔 → 현재 세션 취소하고 새 세션 시작
                self.log_message.emit(f"[전체피킹] 새 SKU 스캔, 기존 세션 취소: {self._current_session.barcode}")
                self.cancel_session()
        
        # 데이터 확인
        if self._excel_df is None or self._excel_df.empty:
            self.error_occurred.emit("엑셀 데이터가 로드되지 않았습니다.")
            play_error_sound()
            return False
        
        if self._bin_manager is None:
            self.error_occurred.emit("BIN 관리자가 설정되지 않았습니다.")
            play_error_sound()
            return False
        
        # SKU에 해당하는 미처리 주문 조회
        pending = self._excel_df[self._excel_df['used'] == 0]
        sku_orders = pending[pending['barcode'].astype(str).str.strip() == barcode]
        
        if sku_orders.empty:
            self.error_occurred.emit(f"No Order for this SKU: {barcode}")
            self.log_message.emit(f"[전체피킹] SKU 없음: {barcode}")
            play_error_sound()
            return False
        
        # BIN별 수량 집계
        bin_qty_map: Dict[str, BinPickTask] = {}
        total_qty = 0
        
        for idx, row in sku_orders.iterrows():
            tracking_no = str(row['tracking_no'])
            qty = int(row['qty']) - int(row.get('scanned_qty', 0))  # 남은 수량
            
            if qty <= 0:
                continue
            
            # 송장의 BIN 조회
            bin_id = self._bin_manager.get_order_bin(tracking_no)
            if bin_id == "BIN 미지정":
                # SKU의 BIN 조회
                bin_id = self._bin_manager.get_sku_bin(barcode)
            
            if bin_id not in bin_qty_map:
                bin_qty_map[bin_id] = BinPickTask(bin_id=bin_id, qty=0)
            
            bin_qty_map[bin_id].qty += qty
            bin_qty_map[bin_id].order_indices.append(idx)
            total_qty += qty
        
        if total_qty == 0:
            self.error_occurred.emit(f"피킹할 수량이 없습니다: {barcode}")
            play_error_sound()
            return False
        
        # 세션 생성
        self._current_session = SkuPickSession(
            barcode=barcode,
            total_qty=total_qty,
            bins=bin_qty_map
        )
        
        # 상태 변경
        self._set_state(FullPickState.BIN_ACTIVE)
        
        # 시작 신호음
        play_fullpick_start_sound()
        
        # 시그널 발생
        self.session_started.emit(barcode, total_qty)
        
        # BIN 리스트 전달
        bin_list = [(bin_id, task.qty) for bin_id, task in sorted(bin_qty_map.items())]
        self.bin_list_ready.emit(bin_list)
        
        self.log_message.emit(f"[전체피킹] SKU: {barcode}, 총 {total_qty}개, {len(bin_list)}개 BIN")
        
        # LCD 표시
        self._send_display_to_all_bins()
        
        return True
    
    def _send_display_to_all_bins(self):
        """모든 활성 BIN에 LCD 표시 명령 전송"""
        if not self._lcd_enabled:
            return
        
        if not self._current_session:
            return
        
        if not self._esp32_transport or not self._device_registry:
            self.log_message.emit("[전체피킹] LCD 연동 비활성 (ESP32 미연결)")
            return
        
        for bin_id, task in self._current_session.bins.items():
            if task.done:
                continue
            
            # BIN에 연결된 장치 확인
            device_id = self._device_registry.get_device_id_by_bin(bin_id)
            if not device_id:
                self.log_message.emit(f"[경고] BIN {bin_id}에 연결된 장치 없음")
                continue
            
            # 디스플레이 명령 전송
            cmd = DisplayCommand(
                mode="full_pick",
                bin_id=bin_id,
                color=self.FULL_PICK_COLOR,
                qty=task.qty,
                blink=False
            )
            
            if self._esp32_transport.send_display(device_id, cmd):
                self.log_message.emit(f"[LCD] {bin_id} 표시: {task.qty}개")
            else:
                self.log_message.emit(f"[LCD] {bin_id} 전송 실패")
    
    def _on_device_done(self, bin_id: str, device_id: str):
        """
        ESP32 터치 완료 이벤트 처리
        
        Args:
            bin_id: 완료된 BIN ID
            device_id: 장치 ID
        """
        self.complete_bin(bin_id)
    
    def complete_bin(self, bin_id: str) -> bool:
        """
        BIN 완료 처리
        
        Args:
            bin_id: 완료할 BIN ID
        
        Returns:
            성공 여부
        """
        if not self._current_session:
            return False
        
        if bin_id not in self._current_session.bins:
            self.log_message.emit(f"[전체피킹] 알 수 없는 BIN: {bin_id}")
            return False
        
        task = self._current_session.bins[bin_id]
        
        if task.done:
            self.log_message.emit(f"[전체피킹] 이미 완료된 BIN: {bin_id}")
            return False
        
        # BIN 완료 처리
        task.done = True
        
        # LCD OFF 명령
        if self._lcd_enabled and self._esp32_transport and self._device_registry:
            device_id = self._device_registry.get_device_id_by_bin(bin_id)
            if device_id:
                self._esp32_transport.send_off(device_id, bin_id)
        
        # 신호음
        play_bin_done_sound()
        
        # 시그널
        self.bin_completed.emit(bin_id, task.qty)
        self.log_message.emit(f"[전체피킹] BIN 완료: {bin_id} ({task.qty}개)")
        
        # 상태 변경
        self._set_state(FullPickState.BIN_DONE)
        
        # 모든 BIN 완료 확인
        if self._current_session.is_complete:
            self._complete_session()
        else:
            # 아직 진행중
            self._set_state(FullPickState.BIN_ACTIVE)
        
        return True
    
    def _complete_session(self):
        """세션 완료 처리"""
        if not self._current_session:
            return
        
        barcode = self._current_session.barcode
        total_qty = self._current_session.total_qty
        
        # 데이터 업데이트 (scanned_qty 증가)
        self._update_excel_data()
        
        # 완료 신호음
        play_sku_complete_sound()
        
        # 상태 변경
        self._set_state(FullPickState.SKU_DONE)
        
        # 시그널
        self.session_completed.emit(barcode, total_qty)
        self.log_message.emit(f"[전체피킹] SKU 완료: {barcode} (총 {total_qty}개)")
        
        # 세션 초기화
        self._current_session = None
        
        # 다음 SKU 대기 상태로
        self._set_state(FullPickState.WAIT_SKU_SCAN)
    
    def _update_excel_data(self):
        """엑셀 데이터 업데이트 (scanned_qty 증가)"""
        if not self._current_session or self._excel_df is None:
            return
        
        for bin_id, task in self._current_session.bins.items():
            if not task.done:
                continue
            
            for idx in task.order_indices:
                if idx in self._excel_df.index:
                    # scanned_qty를 qty와 동일하게 설정 (완료 처리)
                    current_qty = self._excel_df.at[idx, 'qty']
                    self._excel_df.at[idx, 'scanned_qty'] = current_qty
    
    def cancel_session(self):
        """현재 세션 취소"""
        if not self._current_session:
            return
        
        # 모든 활성 BIN LCD OFF
        if self._lcd_enabled and self._esp32_transport and self._device_registry:
            for bin_id, task in self._current_session.bins.items():
                if not task.done:
                    device_id = self._device_registry.get_device_id_by_bin(bin_id)
                    if device_id:
                        self._esp32_transport.send_off(device_id, bin_id)
        
        barcode = self._current_session.barcode
        self._current_session = None
        self._set_state(FullPickState.WAIT_SKU_SCAN)
        
        self.log_message.emit(f"[전체피킹] 세션 취소: {barcode}")
    
    def reset(self):
        """엔진 리셋"""
        self.cancel_session()
        self._set_state(FullPickState.IDLE)
    
    def get_bin_status(self) -> List[Tuple[str, int, bool]]:
        """
        현재 BIN 상태 목록
        
        Returns:
            [(bin_id, qty, done), ...]
        """
        if not self._current_session:
            return []
        
        return [
            (bin_id, task.qty, task.done)
            for bin_id, task in sorted(self._current_session.bins.items())
        ]
    
    def get_session_summary(self) -> dict:
        """현재 세션 요약"""
        if not self._current_session:
            return {}
        
        return {
            "barcode": self._current_session.barcode,
            "total_qty": self._current_session.total_qty,
            "completed_qty": self._current_session.completed_qty,
            "remaining_qty": self._current_session.remaining_qty,
            "total_bins": self._current_session.total_bins,
            "completed_bins": self._current_session.completed_bins,
            "is_complete": self._current_session.is_complete
        }
