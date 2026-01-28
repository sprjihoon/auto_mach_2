"""
모드 관리 모듈
역매칭(REVERSE_MATCHING) / 전체피킹(FULL_PICK) 모드 관리

기존 역매칭 모드는 수정하지 않고, 전체피킹 모드를 별도로 관리
"""
from enum import Enum
from typing import Optional, Callable, List
from PySide6.QtCore import QObject, Signal


class WorkMode(Enum):
    """작업 모드"""
    REVERSE_MATCHING = "reverse_matching"  # 역매칭 (기존)
    FULL_PICK = "full_pick"                # 전체피킹 (신규)


class FullPickState(Enum):
    """전체피킹 상태"""
    IDLE = "idle"                    # 대기 상태
    WAIT_SKU_SCAN = "wait_sku_scan"  # SKU 스캔 대기
    BIN_ACTIVE = "bin_active"        # BIN 활성화 (피킹 진행중)
    BIN_DONE = "bin_done"            # 개별 BIN 완료
    SKU_DONE = "sku_done"            # SKU 피킹 완료


class ModeManager(QObject):
    """
    작업 모드 관리자
    
    역매칭/전체피킹 모드를 전환하고 상태를 관리
    """
    
    # 시그널
    mode_changed = Signal(object)        # WorkMode
    state_changed = Signal(object)       # FullPickState (전체피킹 모드용)
    
    def __init__(self):
        super().__init__()
        
        # 현재 모드 (기본값: 역매칭)
        self._current_mode: WorkMode = WorkMode.REVERSE_MATCHING
        
        # 전체피킹 상태
        self._full_pick_state: FullPickState = FullPickState.IDLE
        
        # 모드 변경 콜백
        self._on_mode_change_callbacks: List[Callable] = []
    
    @property
    def current_mode(self) -> WorkMode:
        """현재 작업 모드"""
        return self._current_mode
    
    @property
    def is_reverse_matching(self) -> bool:
        """역매칭 모드인지 확인"""
        return self._current_mode == WorkMode.REVERSE_MATCHING
    
    @property
    def is_full_pick(self) -> bool:
        """전체피킹 모드인지 확인"""
        return self._current_mode == WorkMode.FULL_PICK
    
    @property
    def full_pick_state(self) -> FullPickState:
        """전체피킹 상태"""
        return self._full_pick_state
    
    def set_mode(self, mode: WorkMode) -> bool:
        """
        작업 모드 변경
        
        Args:
            mode: 새 작업 모드
        
        Returns:
            성공 여부
        """
        if mode == self._current_mode:
            return True
        
        old_mode = self._current_mode
        self._current_mode = mode
        
        # 전체피킹 모드로 전환 시 상태 초기화
        if mode == WorkMode.FULL_PICK:
            self._full_pick_state = FullPickState.WAIT_SKU_SCAN
            self.state_changed.emit(self._full_pick_state)
        else:
            self._full_pick_state = FullPickState.IDLE
        
        # 시그널 발생
        self.mode_changed.emit(mode)
        
        # 콜백 호출
        for callback in self._on_mode_change_callbacks:
            try:
                callback(old_mode, mode)
            except Exception as e:
                print(f"[ModeManager] 콜백 오류: {e}")
        
        return True
    
    def switch_to_reverse_matching(self):
        """역매칭 모드로 전환"""
        self.set_mode(WorkMode.REVERSE_MATCHING)
    
    def switch_to_full_pick(self):
        """전체피킹 모드로 전환"""
        self.set_mode(WorkMode.FULL_PICK)
    
    def set_full_pick_state(self, state: FullPickState):
        """
        전체피킹 상태 변경
        
        Args:
            state: 새 상태
        """
        if self._current_mode != WorkMode.FULL_PICK:
            return
        
        if state == self._full_pick_state:
            return
        
        self._full_pick_state = state
        self.state_changed.emit(state)
    
    def reset_full_pick(self):
        """전체피킹 상태 초기화"""
        if self._current_mode == WorkMode.FULL_PICK:
            self._full_pick_state = FullPickState.WAIT_SKU_SCAN
            self.state_changed.emit(self._full_pick_state)
    
    def on_mode_change(self, callback: Callable):
        """
        모드 변경 콜백 등록
        
        Args:
            callback: (old_mode, new_mode) -> None
        """
        if callback not in self._on_mode_change_callbacks:
            self._on_mode_change_callbacks.append(callback)
    
    def get_mode_display_name(self) -> str:
        """현재 모드 표시명"""
        if self._current_mode == WorkMode.REVERSE_MATCHING:
            return "역매칭"
        elif self._current_mode == WorkMode.FULL_PICK:
            return "전체피킹"
        return "알 수 없음"
    
    def get_state_display_name(self) -> str:
        """현재 상태 표시명 (전체피킹 모드용)"""
        state_names = {
            FullPickState.IDLE: "대기",
            FullPickState.WAIT_SKU_SCAN: "SKU 스캔 대기",
            FullPickState.BIN_ACTIVE: "피킹 진행중",
            FullPickState.BIN_DONE: "BIN 완료",
            FullPickState.SKU_DONE: "SKU 완료"
        }
        return state_names.get(self._full_pick_state, "알 수 없음")
