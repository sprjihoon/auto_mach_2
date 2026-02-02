"""
미리피킹(PRE_PICK) 엔진
주문(송장번호/주문번호) 기준 미리 피킹하여 각 주문 박스에 상품을 담아두는 작업 모드

동작:
1. 송장번호(또는 주문번호) 스캔
2. 주문 조회 → 빈 슬롯에 배정 (최대 3개)
3. BIN별 수량 그룹핑하여 화면 표시
4. ESP32 LCD에 슬롯별 색상으로 BIN 수량 표시
5. 작업자가 슬롯 완료 버튼 클릭 (PC 또는 ESP32)
6. 슬롯 비우고 중복 방지 목록에 추가
"""
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
from PySide6.QtCore import QObject, Signal
import pandas as pd
import winsound
import threading


# 슬롯별 색상 정의 (ESP32 LED/LCD용)
SLOT_COLORS = {
    1: "green",   # 슬롯 1: 녹색
    2: "blue",    # 슬롯 2: 파란색
    3: "yellow",  # 슬롯 3: 노란색
}


# ============================================================
# 상태 정의
# ============================================================

class SlotState(Enum):
    """슬롯 상태"""
    EMPTY = "empty"          # 비어있음
    ACTIVE = "active"        # 활성화 (작업중)
    WAITING = "waiting"      # 대기중 (BIN 충돌로 대기)
    DONE = "done"            # 완료


class OrderPrePickState(Enum):
    """주문 미리피킹 상태"""
    WAITING = "waiting"              # 대기
    PRE_PICKING = "pre_picking"      # 피킹중
    PRE_PICK_DONE = "pre_pick_done"  # 피킹 완료


# ============================================================
# 데이터 클래스
# ============================================================

@dataclass
class BinTask:
    """BIN별 피킹 작업"""
    bin_id: str
    qty: int                              # 필요 수량
    order_indices: List[int] = field(default_factory=list)  # DataFrame 인덱스
    barcodes: Set[str] = field(default_factory=set)         # 바코드 목록
    done: bool = False                    # 완료 여부


@dataclass
class SlotOrder:
    """슬롯에 배정된 주문"""
    slot_id: int                          # 슬롯 번호 (1, 2, 3)
    tracking_no: str                      # 송장번호
    state: SlotState = SlotState.EMPTY    # 슬롯 상태
    order_state: OrderPrePickState = OrderPrePickState.WAITING  # 주문 상태
    bins: Dict[str, BinTask] = field(default_factory=dict)      # bin_id → BinTask
    
    @property
    def total_qty(self) -> int:
        """총 피킹 수량"""
        return sum(b.qty for b in self.bins.values())
    
    @property
    def total_bins(self) -> int:
        """BIN 개수"""
        return len(self.bins)
    
    @property
    def bin_list(self) -> List[Tuple[str, str, int, bool]]:
        """BIN 목록 (바코드, BIN, 수량, 완료여부) - 정렬됨"""
        result = []
        for bin_id, task in sorted(self.bins.items()):
            # 바코드가 여러 개면 쉼표로 구분
            barcodes_str = ", ".join(sorted(task.barcodes)) if task.barcodes else "-"
            result.append((barcodes_str, bin_id, task.qty, task.done))
        return result
    
    @property
    def all_bins_done(self) -> bool:
        """모든 BIN 완료 여부"""
        return all(task.done for task in self.bins.values()) if self.bins else False
    
    @property
    def done_bins_count(self) -> int:
        """완료된 BIN 개수"""
        return sum(1 for task in self.bins.values() if task.done)


# ============================================================
# 사운드 함수
# ============================================================

def play_slot_assign_sound():
    """슬롯 배정 신호음"""
    def _play():
        winsound.Beep(800, 100)
        winsound.Beep(1000, 100)
    threading.Thread(target=_play, daemon=True).start()


def play_slot_complete_sound():
    """슬롯 완료 신호음"""
    def _play():
        winsound.Beep(1000, 150)
        winsound.Beep(1200, 150)
        winsound.Beep(1400, 200)
    threading.Thread(target=_play, daemon=True).start()


def play_error_sound():
    """오류 신호음"""
    def _play():
        winsound.Beep(300, 300)
    threading.Thread(target=_play, daemon=True).start()


# ============================================================
# BinQueueController - BIN 큐 관리
# ============================================================

class BinQueueController:
    """
    BIN 큐 컨트롤러
    
    - 하나의 BIN이 여러 슬롯에서 동시에 필요할 수 있음
    - BIN은 동시에 하나의 슬롯만 active 상태
    - 나머지는 queue에 대기
    - active 슬롯이 완료되면 다음 슬롯을 자동 활성화
    """
    
    def __init__(self):
        # bin_id → [slot_id, ...] (대기 큐)
        self._bin_queue: Dict[str, List[int]] = defaultdict(list)
        
        # bin_id → active slot_id (현재 활성 슬롯)
        self._bin_active: Dict[str, Optional[int]] = {}
    
    def register_bin(self, bin_id: str, slot_id: int) -> bool:
        """
        BIN 등록
        
        Args:
            bin_id: BIN ID
            slot_id: 슬롯 번호
        
        Returns:
            True면 즉시 활성화, False면 대기
        """
        if bin_id not in self._bin_active or self._bin_active[bin_id] is None:
            # 해당 BIN이 비어있으면 즉시 활성화
            self._bin_active[bin_id] = slot_id
            return True
        else:
            # 이미 다른 슬롯이 사용중이면 대기열에 추가
            if slot_id not in self._bin_queue[bin_id]:
                self._bin_queue[bin_id].append(slot_id)
            return False
    
    def release_bin(self, bin_id: str, slot_id: int) -> Optional[int]:
        """
        BIN 해제 (슬롯 완료 시)
        
        Args:
            bin_id: BIN ID
            slot_id: 완료된 슬롯 번호
        
        Returns:
            다음 활성화될 슬롯 번호 (없으면 None)
        """
        # 현재 활성 슬롯 확인
        if self._bin_active.get(bin_id) == slot_id:
            # 대기열에서 다음 슬롯 가져오기
            if self._bin_queue[bin_id]:
                next_slot = self._bin_queue[bin_id].pop(0)
                self._bin_active[bin_id] = next_slot
                return next_slot
            else:
                self._bin_active[bin_id] = None
                return None
        else:
            # 대기열에서 제거
            if slot_id in self._bin_queue[bin_id]:
                self._bin_queue[bin_id].remove(slot_id)
        
        return None
    
    def release_all_bins_for_slot(self, slot_id: int) -> List[Tuple[str, Optional[int]]]:
        """
        슬롯의 모든 BIN 해제
        
        Args:
            slot_id: 슬롯 번호
        
        Returns:
            [(bin_id, next_slot_id), ...] 다음 활성화될 슬롯 목록
        """
        result = []
        
        # 활성 상태에서 해제
        for bin_id, active_slot in list(self._bin_active.items()):
            if active_slot == slot_id:
                next_slot = self.release_bin(bin_id, slot_id)
                result.append((bin_id, next_slot))
        
        # 대기열에서도 제거
        for bin_id in list(self._bin_queue.keys()):
            if slot_id in self._bin_queue[bin_id]:
                self._bin_queue[bin_id].remove(slot_id)
        
        return result
    
    def is_bin_active_for_slot(self, bin_id: str, slot_id: int) -> bool:
        """해당 BIN이 해당 슬롯에서 활성 상태인지 확인"""
        return self._bin_active.get(bin_id) == slot_id
    
    def get_active_slot_for_bin(self, bin_id: str) -> Optional[int]:
        """BIN의 현재 활성 슬롯 반환"""
        return self._bin_active.get(bin_id)
    
    def get_waiting_slots_for_bin(self, bin_id: str) -> List[int]:
        """BIN의 대기 슬롯 목록 반환"""
        return list(self._bin_queue.get(bin_id, []))
    
    def clear(self):
        """모든 큐 초기화"""
        self._bin_queue.clear()
        self._bin_active.clear()


# ============================================================
# SlotManager - 슬롯 관리
# ============================================================

class SlotManager(QObject):
    """
    슬롯 관리자
    
    - 최대 3개 슬롯 관리
    - 슬롯 배정/해제
    - 슬롯 상태 관리
    """
    
    MAX_SLOTS = 3
    
    # 시그널
    slot_assigned = Signal(int, str)        # slot_id, tracking_no
    slot_state_changed = Signal(int, object)  # slot_id, SlotState
    slot_completed = Signal(int, str)       # slot_id, tracking_no
    slot_cleared = Signal(int)              # slot_id
    
    def __init__(self, bin_queue_controller: BinQueueController):
        super().__init__()
        
        self._bin_queue = bin_queue_controller
        
        # 활성 슬롯 개수 (1~3)
        self._active_slot_count: int = 3
        
        # 슬롯 데이터: slot_id → SlotOrder
        self._slots: Dict[int, Optional[SlotOrder]] = {
            1: None,
            2: None,
            3: None
        }
    
    @property
    def active_slot_count(self) -> int:
        """현재 활성화된 슬롯 개수"""
        return self._active_slot_count
    
    def set_active_slot_count(self, count: int):
        """활성 슬롯 개수 설정 (1~3)"""
        self._active_slot_count = max(1, min(3, count))
    
    @property
    def slots(self) -> Dict[int, Optional[SlotOrder]]:
        """슬롯 데이터"""
        return self._slots
    
    def get_slot(self, slot_id: int) -> Optional[SlotOrder]:
        """슬롯 조회"""
        return self._slots.get(slot_id)
    
    def get_empty_slot(self) -> Optional[int]:
        """비어있는 슬롯 번호 반환 (활성 슬롯 범위 내)"""
        for slot_id in range(1, self._active_slot_count + 1):
            if self._slots[slot_id] is None:
                return slot_id
        return None
    
    def get_active_slots(self) -> List[int]:
        """활성화된 슬롯 번호 목록"""
        return [
            slot_id for slot_id, slot in self._slots.items()
            if slot is not None and slot.state == SlotState.ACTIVE
        ]
    
    def get_waiting_slots(self) -> List[int]:
        """대기중인 슬롯 번호 목록"""
        return [
            slot_id for slot_id, slot in self._slots.items()
            if slot is not None and slot.state == SlotState.WAITING
        ]
    
    def is_order_in_slots(self, tracking_no: str) -> Optional[int]:
        """주문이 이미 슬롯에 있는지 확인"""
        for slot_id, slot in self._slots.items():
            if slot is not None and slot.tracking_no == tracking_no:
                return slot_id
        return None
    
    def assign_order(self, tracking_no: str, bins: Dict[str, BinTask]) -> Tuple[bool, int, str]:
        """
        주문을 슬롯에 배정
        
        Args:
            tracking_no: 송장번호
            bins: BIN별 작업 정보
        
        Returns:
            (성공여부, slot_id, 메시지)
        """
        # 이미 배정된 주문인지 확인
        existing_slot = self.is_order_in_slots(tracking_no)
        if existing_slot:
            return False, existing_slot, f"Already in slot {existing_slot}"
        
        # 빈 슬롯 찾기
        slot_id = self.get_empty_slot()
        if slot_id is None:
            return False, 0, "All slots are busy"
        
        # 슬롯 생성
        slot_order = SlotOrder(
            slot_id=slot_id,
            tracking_no=tracking_no,
            state=SlotState.ACTIVE,
            order_state=OrderPrePickState.PRE_PICKING,
            bins=bins
        )
        
        # BIN 등록 및 상태 결정
        has_waiting_bin = False
        for bin_id in bins.keys():
            is_active = self._bin_queue.register_bin(bin_id, slot_id)
            if not is_active:
                has_waiting_bin = True
        
        # 대기 BIN이 있으면 WAITING 상태로
        if has_waiting_bin:
            slot_order.state = SlotState.WAITING
        
        self._slots[slot_id] = slot_order
        
        # 시그널 발생
        self.slot_assigned.emit(slot_id, tracking_no)
        self.slot_state_changed.emit(slot_id, slot_order.state)
        
        return True, slot_id, f"Assigned to slot {slot_id}"
    
    def complete_slot(self, slot_id: int) -> Tuple[bool, str]:
        """
        슬롯 완료 처리
        
        Args:
            slot_id: 슬롯 번호
        
        Returns:
            (성공여부, 메시지)
        """
        slot = self._slots.get(slot_id)
        if slot is None:
            return False, "Slot is empty"
        
        if slot.state == SlotState.DONE:
            return False, "Slot already completed"
        
        # BIN 해제 및 다음 슬롯 활성화
        next_activations = self._bin_queue.release_all_bins_for_slot(slot_id)
        
        # 상태 변경
        slot.state = SlotState.DONE
        slot.order_state = OrderPrePickState.PRE_PICK_DONE
        
        tracking_no = slot.tracking_no
        
        # 시그널 발생
        self.slot_state_changed.emit(slot_id, SlotState.DONE)
        self.slot_completed.emit(slot_id, tracking_no)
        
        # 다음 슬롯 활성화 처리
        for bin_id, next_slot_id in next_activations:
            if next_slot_id is not None:
                self._try_activate_slot(next_slot_id)
        
        return True, f"Slot {slot_id} completed"
    
    def _try_activate_slot(self, slot_id: int):
        """슬롯 활성화 시도"""
        slot = self._slots.get(slot_id)
        if slot is None or slot.state != SlotState.WAITING:
            return
        
        # 모든 BIN이 활성화 가능한지 확인
        all_active = True
        for bin_id in slot.bins.keys():
            if not self._bin_queue.is_bin_active_for_slot(bin_id, slot_id):
                all_active = False
                break
        
        if all_active:
            slot.state = SlotState.ACTIVE
            self.slot_state_changed.emit(slot_id, SlotState.ACTIVE)
    
    def clear_slot(self, slot_id: int) -> bool:
        """슬롯 비우기"""
        slot = self._slots.get(slot_id)
        if slot is None:
            return False
        
        # BIN 해제
        self._bin_queue.release_all_bins_for_slot(slot_id)
        
        self._slots[slot_id] = None
        self.slot_cleared.emit(slot_id)
        
        return True
    
    def clear_completed_slots(self):
        """완료된 슬롯 모두 비우기"""
        for slot_id in [1, 2, 3]:
            slot = self._slots.get(slot_id)
            if slot is not None and slot.state == SlotState.DONE:
                self.clear_slot(slot_id)
    
    def clear_all(self):
        """모든 슬롯 비우기"""
        for slot_id in [1, 2, 3]:
            if self._slots[slot_id] is not None:
                self.clear_slot(slot_id)
    
    def get_all_active_bins(self) -> Set[str]:
        """현재 활성화된 모든 BIN 목록"""
        active_bins = set()
        for slot in self._slots.values():
            if slot is not None and slot.state == SlotState.ACTIVE:
                active_bins.update(slot.bins.keys())
        return active_bins
    
    def get_slot_summary(self) -> List[dict]:
        """슬롯 요약 정보"""
        result = []
        for slot_id in [1, 2, 3]:
            slot = self._slots.get(slot_id)
            if slot is None:
                result.append({
                    "slot_id": slot_id,
                    "state": SlotState.EMPTY,
                    "tracking_no": None,
                    "bins": [],
                    "total_qty": 0
                })
            else:
                result.append({
                    "slot_id": slot_id,
                    "state": slot.state,
                    "tracking_no": slot.tracking_no,
                    "bins": slot.bin_list,
                    "total_qty": slot.total_qty
                })
        return result


# ============================================================
# PrePickEngine - 미리피킹 메인 엔진
# ============================================================

class PrePickEngine(QObject):
    """
    미리피킹 엔진
    
    주문 스캔 → 슬롯 배정 → BIN별 수량 표시 → 완료 처리
    ESP32 연동: 슬롯별 색상 표시, 다중 SKU BIN은 깜빡임
    """
    
    # 시그널
    order_scanned = Signal(str)                    # tracking_no
    order_assigned = Signal(int, str, list)        # slot_id, tracking_no, [(bin_id, qty), ...]
    order_completed = Signal(int, str)             # slot_id, tracking_no
    order_not_found = Signal(str)                  # tracking_no
    already_picked = Signal(str)                   # tracking_no
    slots_full = Signal()                          # 슬롯이 가득 참
    slot_state_changed = Signal(int, object)       # slot_id, SlotState
    bin_completed = Signal(int, str)               # slot_id, bin_id (개별 BIN 완료)
    log_message = Signal(str)                      # 로그 메시지
    error_occurred = Signal(str)                   # 에러 메시지
    
    def __init__(self):
        super().__init__()
        
        # BIN 큐 컨트롤러
        self._bin_queue = BinQueueController()
        
        # 슬롯 관리자
        self._slot_manager = SlotManager(self._bin_queue)
        
        # 슬롯 매니저 시그널 연결
        self._slot_manager.slot_assigned.connect(self._on_slot_assigned)
        self._slot_manager.slot_state_changed.connect(self._on_slot_state_changed)
        self._slot_manager.slot_completed.connect(self._on_slot_completed)
        
        # 데이터 참조
        self._excel_df: Optional[pd.DataFrame] = None
        self._bin_manager = None
        
        # 완료된 주문 (메모리 기반)
        self._completed_orders: Set[str] = set()
        
        # ESP32 연동
        self._device_registry = None
        self._esp32_transport = None
        self._lcd_enabled: bool = False
        
        # BIN별 SKU 개수 (깜빡임 판단용)
        self._bin_sku_count: Dict[str, int] = {}
    
    @property
    def slot_manager(self) -> SlotManager:
        """슬롯 관리자"""
        return self._slot_manager
    
    @property
    def bin_queue(self) -> BinQueueController:
        """BIN 큐 컨트롤러"""
        return self._bin_queue
    
    def set_data_source(self, df: pd.DataFrame, bin_manager):
        """
        데이터 소스 설정
        
        Args:
            df: 엑셀 DataFrame
            bin_manager: BinManager 객체
        """
        self._excel_df = df
        self._bin_manager = bin_manager
        
        # BIN별 SKU 개수 계산 (깜빡임 판단용)
        self._calculate_bin_sku_counts()
    
    def _calculate_bin_sku_counts(self):
        """BIN별 SKU 개수 계산"""
        self._bin_sku_count.clear()
        
        if self._excel_df is None or self._bin_manager is None:
            return
        
        # BIN별 SKU 집합
        bin_skus: Dict[str, Set[str]] = defaultdict(set)
        
        for _, row in self._excel_df.iterrows():
            barcode = str(row.get('barcode', '')).strip()
            if not barcode:
                continue
            
            bin_id = self._bin_manager.get_sku_bin(barcode)
            if bin_id and bin_id != "BIN 미지정":
                bin_skus[bin_id].add(barcode)
        
        # SKU 개수 저장
        for bin_id, skus in bin_skus.items():
            self._bin_sku_count[bin_id] = len(skus)
    
    def set_esp32(self, device_registry, esp32_transport):
        """
        ESP32 연동 설정
        
        Args:
            device_registry: DeviceRegistry 객체
            esp32_transport: Esp32Transport 객체
        """
        self._device_registry = device_registry
        self._esp32_transport = esp32_transport
        self._lcd_enabled = True
        
        # ESP32 터치 완료 시그널 연결
        if esp32_transport:
            esp32_transport.device_done.connect(self._on_device_done)
        
        self.log_message.emit("[미리피킹] ESP32 연동 활성화")
    
    def _on_device_done(self, bin_id: str, device_id: str):
        """
        ESP32 터치 완료 이벤트 처리
        
        Args:
            bin_id: 완료된 BIN ID
            device_id: 장치 ID
        """
        # 해당 BIN이 어느 슬롯에 있는지 찾기
        for slot_id in [1, 2, 3]:
            slot = self._slot_manager.get_slot(slot_id)
            if slot and slot.state == SlotState.ACTIVE and bin_id in slot.bins:
                self._complete_bin(slot_id, bin_id)
                return
        
        self.log_message.emit(f"[미리피킹] BIN {bin_id} 터치 - 활성 슬롯에 없음")
    
    def _complete_bin(self, slot_id: int, bin_id: str) -> bool:
        """
        개별 BIN 완료 처리
        
        Args:
            slot_id: 슬롯 번호
            bin_id: BIN ID
        
        Returns:
            성공 여부
        """
        slot = self._slot_manager.get_slot(slot_id)
        if not slot or bin_id not in slot.bins:
            return False
        
        task = slot.bins[bin_id]
        if task.done:
            self.log_message.emit(f"[미리피킹] 이미 완료된 BIN: {bin_id}")
            return False
        
        # BIN 완료 처리
        task.done = True
        
        # LCD OFF
        if self._lcd_enabled and self._esp32_transport and self._device_registry:
            device_id = self._device_registry.get_device_id_by_bin(bin_id)
            if device_id:
                self._esp32_transport.send_off(device_id, bin_id)
        
        # 완료 신호음 (짧은 비프)
        import winsound
        import threading
        def _beep():
            winsound.Beep(1000, 100)
        threading.Thread(target=_beep, daemon=True).start()
        
        # 시그널
        self.bin_completed.emit(slot_id, bin_id)
        self.log_message.emit(f"[미리피킹] BIN 완료: {bin_id} (슬롯 {slot_id}, {slot.done_bins_count}/{slot.total_bins})")
        
        # 모든 BIN 완료 시 슬롯 자동 완료
        if slot.all_bins_done:
            self.log_message.emit(f"[미리피킹] 슬롯 {slot_id} 모든 BIN 완료 → 자동 완료 처리")
            self.complete_slot(slot_id)
        
        return True
    
    def enable_lcd(self, enabled: bool = True):
        """LCD 연동 활성화/비활성화"""
        self._lcd_enabled = enabled
    
    def is_multi_sku_bin(self, bin_id: str) -> bool:
        """BIN에 여러 SKU가 있는지 확인 (깜빡임 대상)"""
        return self._bin_sku_count.get(bin_id, 0) > 1
    
    def _send_lcd_display(self, slot_id: int, bin_id: str, qty: int):
        """ESP32 LCD에 표시 명령 전송"""
        if not self._lcd_enabled or not self._esp32_transport or not self._device_registry:
            return
        
        from esp32_transport import DisplayCommand
        
        # 슬롯별 색상
        color = SLOT_COLORS.get(slot_id, "white")
        
        # 다중 SKU BIN이면 깜빡임
        blink = self.is_multi_sku_bin(bin_id)
        
        # 장치 ID 조회
        device_id = self._device_registry.get_device_id_by_bin(bin_id)
        if not device_id:
            self.log_message.emit(f"[경고] BIN {bin_id}에 연결된 장치 없음")
            return
        
        # 표시 명령 전송
        cmd = DisplayCommand(
            mode="pre_pick",
            bin_id=bin_id,
            color=color,
            qty=qty,
            blink=blink
        )
        
        if self._esp32_transport.send_display(device_id, cmd):
            blink_str = " (깜빡임)" if blink else ""
            self.log_message.emit(f"[LCD] {bin_id} 표시: {qty}개, {color}{blink_str}")
        else:
            self.log_message.emit(f"[LCD] {bin_id} 전송 실패")
    
    def _send_lcd_off(self, bin_id: str):
        """ESP32 LCD OFF 명령 전송"""
        if not self._lcd_enabled or not self._esp32_transport or not self._device_registry:
            return
        
        device_id = self._device_registry.get_device_id_by_bin(bin_id)
        if device_id:
            self._esp32_transport.send_off(device_id, bin_id)
    
    def _update_all_lcd_displays(self):
        """모든 활성 슬롯의 BIN에 LCD 표시 업데이트"""
        if not self._lcd_enabled:
            return
        
        for slot_id in range(1, self._slot_manager.active_slot_count + 1):
            slot = self._slot_manager.get_slot(slot_id)
            if slot and slot.state == SlotState.ACTIVE:
                for bin_id, task in slot.bins.items():
                    # 해당 BIN이 이 슬롯에서 활성 상태인지 확인
                    if self._bin_queue.is_bin_active_for_slot(bin_id, slot_id):
                        self._send_lcd_display(slot_id, bin_id, task.qty)
    
    def process_scan(self, tracking_no: str) -> Tuple[bool, str]:
        """
        주문 스캔 처리
        
        Args:
            tracking_no: 송장번호 또는 주문번호
        
        Returns:
            (성공여부, 메시지)
        """
        tracking_no = str(tracking_no).strip()
        
        if not tracking_no:
            return False, "Empty tracking number"
        
        self.order_scanned.emit(tracking_no)
        self.log_message.emit(f"[미리피킹] 스캔: {tracking_no}")
        
        # 데이터 확인
        if self._excel_df is None or self._excel_df.empty:
            self.error_occurred.emit("엑셀 데이터가 로드되지 않았습니다.")
            play_error_sound()
            return False, "No data loaded"
        
        # 이미 완료된 주문인지 확인
        if tracking_no in self._completed_orders:
            self.already_picked.emit(tracking_no)
            self.log_message.emit(f"[미리피킹] 이미 완료된 주문: {tracking_no}")
            play_error_sound()
            return False, "Already picked"
        
        # 이미 슬롯에 있는지 확인
        existing_slot = self._slot_manager.is_order_in_slots(tracking_no)
        if existing_slot:
            self.log_message.emit(f"[미리피킹] 이미 슬롯 {existing_slot}에 배정됨: {tracking_no}")
            return False, f"Already in slot {existing_slot}"
        
        # 주문 조회
        order_items = self._excel_df[
            self._excel_df['tracking_no'].astype(str).str.strip() == tracking_no
        ]
        
        if order_items.empty:
            self.order_not_found.emit(tracking_no)
            self.log_message.emit(f"[미리피킹] 주문 없음: {tracking_no}")
            play_error_sound()
            return False, "Order not found"
        
        # BIN별 수량 집계
        bins = self._aggregate_bins(order_items)
        
        if not bins:
            self.error_occurred.emit(f"피킹할 항목이 없습니다: {tracking_no}")
            play_error_sound()
            return False, "No items to pick"
        
        # 슬롯에 배정
        success, slot_id, message = self._slot_manager.assign_order(tracking_no, bins)
        
        if success:
            play_slot_assign_sound()
            bin_list = [(bin_id, task.qty) for bin_id, task in sorted(bins.items())]
            self.order_assigned.emit(slot_id, tracking_no, bin_list)
            self.log_message.emit(f"[미리피킹] 슬롯 {slot_id} 배정: {tracking_no} ({len(bins)}개 BIN)")
            
            # ESP32 LCD 표시 업데이트
            self._update_all_lcd_displays()
        else:
            if "All slots are busy" in message:
                self.slots_full.emit()
            play_error_sound()
            self.log_message.emit(f"[미리피킹] 배정 실패: {message}")
        
        return success, message
    
    def _aggregate_bins(self, order_items: pd.DataFrame) -> Dict[str, BinTask]:
        """BIN별 수량 집계 (바코드 포함)"""
        bins: Dict[str, BinTask] = {}
        
        for idx, row in order_items.iterrows():
            barcode = str(row.get('barcode', '')).strip()
            qty = int(row.get('qty', 1))
            scanned_qty = int(row.get('scanned_qty', 0))
            remaining = qty - scanned_qty
            
            if remaining <= 0:
                continue
            
            # BIN 조회
            bin_id = "BIN 미지정"
            if self._bin_manager:
                bin_id = self._bin_manager.get_sku_bin(barcode)
                if bin_id == "BIN 미지정":
                    # 송장 기준으로도 조회
                    tracking_no = str(row.get('tracking_no', ''))
                    bin_id = self._bin_manager.get_order_bin(tracking_no)
            
            if bin_id not in bins:
                bins[bin_id] = BinTask(bin_id=bin_id, qty=0)
            
            bins[bin_id].qty += remaining
            bins[bin_id].order_indices.append(idx)
            bins[bin_id].barcodes.add(barcode)  # 바코드 추가
        
        return bins
    
    def complete_slot(self, slot_id: int) -> Tuple[bool, str]:
        """
        슬롯 완료 처리
        
        Args:
            slot_id: 슬롯 번호
        
        Returns:
            (성공여부, 메시지)
        """
        slot = self._slot_manager.get_slot(slot_id)
        if slot is None:
            return False, "Slot is empty"
        
        tracking_no = slot.tracking_no
        
        success, message = self._slot_manager.complete_slot(slot_id)
        
        if success:
            play_slot_complete_sound()
            self._completed_orders.add(tracking_no)
            self.order_completed.emit(slot_id, tracking_no)
            self.log_message.emit(f"[미리피킹] 슬롯 {slot_id} 완료: {tracking_no}")
            
            # 완료된 슬롯 자동 비우기 (옵션)
            # self._slot_manager.clear_slot(slot_id)
        
        return success, message
    
    def clear_slot(self, slot_id: int) -> bool:
        """슬롯 비우기"""
        # 먼저 해당 슬롯의 BIN들 LCD 끄기
        slot = self._slot_manager.get_slot(slot_id)
        if slot and self._lcd_enabled and self._esp32_transport and self._device_registry:
            for bin_id in slot.bins.keys():
                device_id = self._device_registry.get_device_id_by_bin(bin_id)
                if device_id:
                    self._esp32_transport.send_off(device_id, bin_id)
        
        success = self._slot_manager.clear_slot(slot_id)
        if success:
            self.log_message.emit(f"[미리피킹] 슬롯 {slot_id} 비움")
        return success
    
    def clear_completed_slots(self):
        """완료된 슬롯 비우기"""
        self._slot_manager.clear_completed_slots()
        self.log_message.emit("[미리피킹] 완료된 슬롯 정리")
    
    def _on_slot_assigned(self, slot_id: int, tracking_no: str):
        """슬롯 배정 이벤트"""
        pass  # order_assigned 시그널로 처리
    
    def _on_slot_state_changed(self, slot_id: int, state: SlotState):
        """슬롯 상태 변경 이벤트"""
        self.slot_state_changed.emit(slot_id, state)
    
    def _on_slot_completed(self, slot_id: int, tracking_no: str):
        """슬롯 완료 이벤트"""
        pass  # order_completed 시그널로 처리
    
    def get_slots_summary(self) -> List[dict]:
        """슬롯 요약 정보"""
        return self._slot_manager.get_slot_summary()
    
    def get_active_bins(self) -> Set[str]:
        """현재 활성화된 BIN 목록"""
        return self._slot_manager.get_all_active_bins()
    
    def is_completed(self, tracking_no: str) -> bool:
        """주문 완료 여부"""
        return tracking_no in self._completed_orders
    
    def reset(self):
        """엔진 초기화"""
        # 모든 슬롯의 BIN LCD 끄기
        if self._lcd_enabled and self._esp32_transport and self._device_registry:
            for slot_id in [1, 2, 3]:
                slot = self._slot_manager.get_slot(slot_id)
                if slot:
                    for bin_id in slot.bins.keys():
                        device_id = self._device_registry.get_device_id_by_bin(bin_id)
                        if device_id:
                            self._esp32_transport.send_off(device_id, bin_id)
        
        self._slot_manager.clear_all()
        self._bin_queue.clear()
        self._completed_orders.clear()
        self.log_message.emit("[미리피킹] 엔진 초기화")


# ============================================================
# 테스트용 예시 데이터
# ============================================================

def create_test_data() -> pd.DataFrame:
    """테스트용 예시 데이터 생성"""
    data = [
        # 주문 12345 (BIN: A03, B07)
        {"tracking_no": "12345", "barcode": "SKU001", "qty": 3, "scanned_qty": 0},
        {"tracking_no": "12345", "barcode": "SKU002", "qty": 1, "scanned_qty": 0},
        
        # 주문 12346 (BIN: C01)
        {"tracking_no": "12346", "barcode": "SKU003", "qty": 2, "scanned_qty": 0},
        
        # 주문 12347 (BIN: A03, D05) - A03이 12345와 충돌
        {"tracking_no": "12347", "barcode": "SKU001", "qty": 1, "scanned_qty": 0},
        {"tracking_no": "12347", "barcode": "SKU004", "qty": 2, "scanned_qty": 0},
        
        # 주문 12348 (BIN: E02)
        {"tracking_no": "12348", "barcode": "SKU005", "qty": 4, "scanned_qty": 0},
    ]
    
    return pd.DataFrame(data)


class TestBinManager:
    """테스트용 BinManager"""
    
    def __init__(self):
        self._sku_bin_map = {
            "SKU001": "A03",
            "SKU002": "B07",
            "SKU003": "C01",
            "SKU004": "D05",
            "SKU005": "E02",
        }
    
    def get_sku_bin(self, barcode: str) -> str:
        return self._sku_bin_map.get(barcode, "BIN 미지정")
    
    def get_order_bin(self, tracking_no: str) -> str:
        return "BIN 미지정"


if __name__ == "__main__":
    # 테스트 실행
    print("=== 미리피킹 엔진 테스트 ===\n")
    
    # 테스트 데이터 생성
    df = create_test_data()
    bin_manager = TestBinManager()
    
    # 엔진 생성
    engine = PrePickEngine()
    engine.set_data_source(df, bin_manager)
    
    # 로그 출력 연결
    engine.log_message.connect(print)
    
    # 테스트 1: 주문 12345 스캔
    print("\n--- 테스트 1: 주문 12345 스캔 ---")
    success, msg = engine.process_scan("12345")
    print(f"결과: {success}, {msg}")
    
    # 슬롯 상태 확인
    for slot in engine.get_slots_summary():
        if slot["tracking_no"]:
            print(f"  슬롯 {slot['slot_id']}: {slot['tracking_no']} - {slot['state'].value}")
            for bin_id, qty in slot["bins"]:
                print(f"    {bin_id}: {qty}")
    
    # 테스트 2: 주문 12346 스캔
    print("\n--- 테스트 2: 주문 12346 스캔 ---")
    success, msg = engine.process_scan("12346")
    print(f"결과: {success}, {msg}")
    
    # 테스트 3: 주문 12347 스캔 (A03 충돌)
    print("\n--- 테스트 3: 주문 12347 스캔 (A03 충돌) ---")
    success, msg = engine.process_scan("12347")
    print(f"결과: {success}, {msg}")
    
    # 슬롯 상태 확인
    print("\n--- 현재 슬롯 상태 ---")
    for slot in engine.get_slots_summary():
        if slot["tracking_no"]:
            print(f"  슬롯 {slot['slot_id']}: {slot['tracking_no']} - {slot['state'].value}")
    
    # 테스트 4: 슬롯 1 완료
    print("\n--- 테스트 4: 슬롯 1 완료 ---")
    success, msg = engine.complete_slot(1)
    print(f"결과: {success}, {msg}")
    
    # 슬롯 상태 확인 (슬롯 3이 ACTIVE로 변경되어야 함)
    print("\n--- 완료 후 슬롯 상태 ---")
    for slot in engine.get_slots_summary():
        if slot["tracking_no"]:
            print(f"  슬롯 {slot['slot_id']}: {slot['tracking_no']} - {slot['state'].value}")
    
    print("\n=== 테스트 완료 ===")
