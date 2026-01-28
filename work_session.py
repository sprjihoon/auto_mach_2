"""
작업 세션 관리 모듈
업체 선택/변경 시 차수별 세션 정보 저장 및 관리

기능:
- 작업 차수별 세션 저장 (업체, BIN 매핑, 시간 등)
- 세션 목록 조회
- 세션 선택/로드
- 세션 파일 저장/불러오기
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
from PySide6.QtCore import QObject, Signal
import json
import os


@dataclass
class WorkSession:
    """작업 세션 정보"""
    session_id: int                      # 차수 (1, 2, 3...)
    suppliers: List[str]                 # 선택된 업체 목록
    supplier_display: str                # 표시용 업체명
    created_at: datetime                 # 생성 시간
    order_count: int = 0                 # 주문 건수
    sku_count: int = 0                   # SKU 개수
    bin_count: int = 0                   # BIN 개수
    mode: str = "reverse_matching"       # 작업 모드 (reverse_matching, full_pick)
    status: str = "active"               # 상태 (active, completed, cancelled)
    sku_bin_map: Dict[str, str] = field(default_factory=dict)  # SKU → BIN 매핑 스냅샷
    
    def to_dict(self) -> dict:
        """딕셔너리로 변환"""
        return {
            "session_id": self.session_id,
            "suppliers": self.suppliers,
            "supplier_display": self.supplier_display,
            "created_at": self.created_at.isoformat(),
            "order_count": self.order_count,
            "sku_count": self.sku_count,
            "bin_count": self.bin_count,
            "mode": self.mode,
            "status": self.status,
            "sku_bin_map": self.sku_bin_map
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'WorkSession':
        """딕셔너리에서 생성"""
        return cls(
            session_id=data.get("session_id", 0),
            suppliers=data.get("suppliers", []),
            supplier_display=data.get("supplier_display", ""),
            created_at=datetime.fromisoformat(data.get("created_at", datetime.now().isoformat())),
            order_count=data.get("order_count", 0),
            sku_count=data.get("sku_count", 0),
            bin_count=data.get("bin_count", 0),
            mode=data.get("mode", "reverse_matching"),
            status=data.get("status", "active"),
            sku_bin_map=data.get("sku_bin_map", {})
        )
    
    def get_display_name(self) -> str:
        """표시용 이름"""
        time_str = self.created_at.strftime("%H:%M")
        return f"{self.session_id}차 [{self.supplier_display}] ({self.order_count}건, {time_str})"


class WorkSessionManager(QObject):
    """
    작업 세션 관리자
    
    차수별 세션을 저장하고 관리
    """
    
    # 시그널
    session_created = Signal(object)      # WorkSession
    session_selected = Signal(object)     # WorkSession
    session_list_updated = Signal()
    
    def __init__(self, save_path: str = None):
        super().__init__()
        
        # 세션 목록 (session_id → WorkSession)
        self._sessions: Dict[int, WorkSession] = {}
        
        # 현재 활성 세션
        self._current_session: Optional[WorkSession] = None
        
        # 다음 세션 ID
        self._next_session_id: int = 1
        
        # 저장 경로
        self._save_path = save_path or "work_sessions.json"
        
        # 파일에서 로드
        self._load_from_file()
    
    @property
    def current_session(self) -> Optional[WorkSession]:
        """현재 활성 세션"""
        return self._current_session
    
    @property
    def current_session_id(self) -> int:
        """현재 차수"""
        return self._current_session.session_id if self._current_session else 0
    
    @property
    def session_count(self) -> int:
        """저장된 세션 수"""
        return len(self._sessions)
    
    def create_session(self, 
                      suppliers: List[str],
                      supplier_display: str,
                      order_count: int = 0,
                      sku_count: int = 0,
                      bin_count: int = 0,
                      mode: str = "reverse_matching",
                      sku_bin_map: Dict[str, str] = None) -> WorkSession:
        """
        새 작업 세션 생성
        
        Args:
            suppliers: 선택된 업체 목록
            supplier_display: 표시용 업체명
            order_count: 주문 건수
            sku_count: SKU 개수
            bin_count: BIN 개수
            mode: 작업 모드
            sku_bin_map: SKU → BIN 매핑
        
        Returns:
            생성된 WorkSession
        """
        session = WorkSession(
            session_id=self._next_session_id,
            suppliers=suppliers,
            supplier_display=supplier_display,
            created_at=datetime.now(),
            order_count=order_count,
            sku_count=sku_count,
            bin_count=bin_count,
            mode=mode,
            status="active",
            sku_bin_map=sku_bin_map or {}
        )
        
        # 저장
        self._sessions[session.session_id] = session
        self._current_session = session
        self._next_session_id += 1
        
        # 파일 저장
        self._save_to_file()
        
        # 시그널
        self.session_created.emit(session)
        self.session_list_updated.emit()
        
        return session
    
    def select_session(self, session_id: int) -> Optional[WorkSession]:
        """
        세션 선택
        
        Args:
            session_id: 선택할 세션 ID
        
        Returns:
            선택된 세션 또는 None
        """
        session = self._sessions.get(session_id)
        if session:
            self._current_session = session
            self.session_selected.emit(session)
            return session
        return None
    
    def get_session(self, session_id: int) -> Optional[WorkSession]:
        """세션 조회"""
        return self._sessions.get(session_id)
    
    def get_all_sessions(self) -> List[WorkSession]:
        """모든 세션 목록 (최신순)"""
        return sorted(
            self._sessions.values(),
            key=lambda s: s.created_at,
            reverse=True
        )
    
    def get_active_sessions(self) -> List[WorkSession]:
        """활성 세션 목록"""
        return [s for s in self._sessions.values() if s.status == "active"]
    
    def update_session(self, session_id: int, **kwargs) -> bool:
        """
        세션 정보 업데이트
        
        Args:
            session_id: 세션 ID
            **kwargs: 업데이트할 필드들
        
        Returns:
            성공 여부
        """
        session = self._sessions.get(session_id)
        if not session:
            return False
        
        for key, value in kwargs.items():
            if hasattr(session, key):
                setattr(session, key, value)
        
        self._save_to_file()
        self.session_list_updated.emit()
        return True
    
    def complete_session(self, session_id: int):
        """세션 완료 처리"""
        self.update_session(session_id, status="completed")
    
    def cancel_session(self, session_id: int):
        """세션 취소 처리"""
        self.update_session(session_id, status="cancelled")
    
    def delete_session(self, session_id: int) -> bool:
        """세션 삭제"""
        if session_id in self._sessions:
            del self._sessions[session_id]
            
            if self._current_session and self._current_session.session_id == session_id:
                self._current_session = None
            
            self._save_to_file()
            self.session_list_updated.emit()
            return True
        return False
    
    def clear_all_sessions(self):
        """모든 세션 삭제"""
        self._sessions.clear()
        self._current_session = None
        self._next_session_id = 1
        self._save_to_file()
        self.session_list_updated.emit()
    
    def _save_to_file(self):
        """파일에 저장"""
        try:
            data = {
                "next_session_id": self._next_session_id,
                "current_session_id": self._current_session.session_id if self._current_session else None,
                "sessions": [s.to_dict() for s in self._sessions.values()]
            }
            with open(self._save_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[WorkSessionManager] 저장 실패: {e}")
    
    def _load_from_file(self):
        """파일에서 로드"""
        if not os.path.exists(self._save_path):
            return
        
        try:
            with open(self._save_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self._next_session_id = data.get("next_session_id", 1)
            
            for session_data in data.get("sessions", []):
                session = WorkSession.from_dict(session_data)
                self._sessions[session.session_id] = session
            
            current_id = data.get("current_session_id")
            if current_id and current_id in self._sessions:
                self._current_session = self._sessions[current_id]
            
        except Exception as e:
            print(f"[WorkSessionManager] 로드 실패: {e}")
    
    def get_session_choices(self) -> List[tuple]:
        """
        세션 선택 옵션 목록 반환 (드롭다운용)
        
        Returns:
            [(session_id, display_name), ...]
        """
        sessions = self.get_all_sessions()
        return [(s.session_id, s.get_display_name()) for s in sessions]
