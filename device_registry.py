"""
ESP32 장치 레지스트리
device_id (MAC 기반) <-> bin_id 자동 바인딩 관리

기능:
- ESP32 장치 등록 (hello 메시지)
- device_id → bin_id 바인딩
- 중복 바인딩 방지 (1 BIN = 1 device)
- 바인딩 해제
- 장치 상태 관리
"""
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from PySide6.QtCore import QObject, Signal
import json


@dataclass
class DeviceInfo:
    """ESP32 장치 정보"""
    device_id: str              # 고유 ID (MAC 기반)
    bin_id: Optional[str] = None  # 바인딩된 BIN ID
    connected: bool = False     # 연결 상태
    last_seen: Optional[datetime] = None  # 마지막 통신 시간
    websocket: object = None    # WebSocket 연결 객체
    wifi_ssid: Optional[str] = None  # 현재 연결된 WiFi SSID (hello 수신 시 갱신)

    def to_dict(self) -> dict:
        return {
            "device_id": self.device_id,
            "bin_id": self.bin_id,
            "connected": self.connected,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "wifi_ssid": self.wifi_ssid
        }


class DeviceRegistry(QObject):
    """
    ESP32 장치 레지스트리
    
    device_id <-> bin_id 매핑 관리
    """
    
    # 시그널
    device_connected = Signal(str)      # device_id
    device_disconnected = Signal(str)   # device_id
    device_bound = Signal(str, str)     # device_id, bin_id
    device_unbound = Signal(str)        # device_id
    
    def __init__(self):
        super().__init__()
        
        # device_id → DeviceInfo
        self._devices: Dict[str, DeviceInfo] = {}
        
        # bin_id → device_id (역방향 조회용)
        self._bin_device_map: Dict[str, str] = {}
        
        # 자동 바인딩 모드 (순차적으로 BIN 할당)
        self._auto_bind_enabled: bool = True
        self._next_auto_bin_number: int = 1
    
    @property
    def connected_count(self) -> int:
        """연결된 장치 수"""
        return sum(1 for d in self._devices.values() if d.connected)
    
    @property
    def bound_count(self) -> int:
        """바인딩된 장치 수"""
        return sum(1 for d in self._devices.values() if d.bin_id is not None)
    
    def register_device(self, device_id: str, websocket: object = None, wifi_ssid: Optional[str] = None) -> DeviceInfo:
        """
        장치 등록 (hello 메시지 수신 시)

        Args:
            device_id: ESP32 고유 ID
            websocket: WebSocket 연결 객체
            wifi_ssid: 현재 연결된 WiFi SSID (hello에 포함된 값)

        Returns:
            DeviceInfo 객체
        """
        if device_id in self._devices:
            # 기존 장치 재연결
            device = self._devices[device_id]
            device.connected = True
            device.last_seen = datetime.now()
            device.websocket = websocket
            if wifi_ssid is not None:
                device.wifi_ssid = wifi_ssid or None
        else:
            # 새 장치 등록
            device = DeviceInfo(
                device_id=device_id,
                connected=True,
                last_seen=datetime.now(),
                websocket=websocket,
                wifi_ssid=wifi_ssid or None
            )
            self._devices[device_id] = device

        self.device_connected.emit(device_id)
        return device
    
    def unregister_device(self, device_id: str):
        """
        장치 연결 해제 (고장/끊김 시 BIN도 해제 → 정상 보드에만 BIN 배정 가능)
        
        Args:
            device_id: ESP32 고유 ID
        """
        if device_id in self._devices:
            device = self._devices[device_id]
            # 연결 끊긴 보드는 BIN 해제 → 해당 BIN 번호가 비어서 다른(정상) 보드에 재배정 가능
            self.unbind_device(device_id)
            device.connected = False
            device.websocket = None

            self.device_disconnected.emit(device_id)
    
    def bind_device(self, device_id: str, bin_id: str) -> bool:
        """
        장치를 BIN에 바인딩
        
        Args:
            device_id: ESP32 고유 ID
            bin_id: BIN ID (예: "BIN-01")
        
        Returns:
            성공 여부
        """
        # 장치 존재 확인
        if device_id not in self._devices:
            print(f"[DeviceRegistry] 장치 없음: {device_id}")
            return False
        
        # 중복 바인딩 확인 (이미 다른 장치가 해당 BIN에 바인딩됨)
        if bin_id in self._bin_device_map:
            existing_device = self._bin_device_map[bin_id]
            if existing_device != device_id:
                print(f"[DeviceRegistry] BIN 중복: {bin_id} -> {existing_device}")
                return False
        
        device = self._devices[device_id]
        
        # 기존 바인딩 해제
        if device.bin_id and device.bin_id != bin_id:
            if device.bin_id in self._bin_device_map:
                del self._bin_device_map[device.bin_id]
        
        # 새 바인딩
        device.bin_id = bin_id
        self._bin_device_map[bin_id] = device_id
        
        self.device_bound.emit(device_id, bin_id)
        return True
    
    def unbind_device(self, device_id: str):
        """
        장치 바인딩 해제
        
        Args:
            device_id: ESP32 고유 ID
        """
        if device_id not in self._devices:
            return
        
        device = self._devices[device_id]
        
        if device.bin_id:
            if device.bin_id in self._bin_device_map:
                del self._bin_device_map[device.bin_id]
            device.bin_id = None
            
            self.device_unbound.emit(device_id)
    
    def auto_bind_device(self, device_id: str) -> Optional[str]:
        """
        장치 자동 바인딩 (비어 있는 가장 작은 BIN 번호 할당 → 고장 보드 끊김 시 번호가 비어 정상 보드에 맞게 배정)
        
        Args:
            device_id: ESP32 고유 ID
        
        Returns:
            할당된 bin_id 또는 None
        """
        if not self._auto_bind_enabled:
            return None
        
        # 이미 바인딩된 경우 건너뛰기 (재연결 시 기존 BIN 유지)
        if device_id in self._devices and self._devices[device_id].bin_id:
            return self._devices[device_id].bin_id
        
        # 비어 있는 가장 작은 BIN 번호 할당 (끊긴 보드의 BIN이 비었으면 그 번호 재사용)
        for n in range(1, 100):
            bin_id = f"BIN-{n:02d}"
            if bin_id not in self._bin_device_map:
                if self.bind_device(device_id, bin_id):
                    return bin_id
                break
        
        return None
    
    def get_device(self, device_id: str) -> Optional[DeviceInfo]:
        """장치 정보 조회"""
        return self._devices.get(device_id)
    
    def get_device_by_bin(self, bin_id: str) -> Optional[DeviceInfo]:
        """BIN ID로 장치 조회"""
        device_id = self._bin_device_map.get(bin_id)
        if device_id:
            return self._devices.get(device_id)
        return None
    
    def get_bin_id(self, device_id: str) -> Optional[str]:
        """장치의 BIN ID 조회"""
        device = self._devices.get(device_id)
        return device.bin_id if device else None
    
    def get_device_id_by_bin(self, bin_id: str) -> Optional[str]:
        """BIN ID로 device_id 조회"""
        return self._bin_device_map.get(bin_id)
    
    def is_bin_bound(self, bin_id: str) -> bool:
        """BIN에 장치가 바인딩되어 있는지 확인"""
        return bin_id in self._bin_device_map
    
    def get_websocket(self, device_id: str) -> Optional[object]:
        """장치의 WebSocket 객체 조회"""
        device = self._devices.get(device_id)
        return device.websocket if device else None
    
    def get_websocket_by_bin(self, bin_id: str) -> Optional[object]:
        """BIN ID로 WebSocket 객체 조회"""
        device = self.get_device_by_bin(bin_id)
        return device.websocket if device else None
    
    def get_all_devices(self) -> List[DeviceInfo]:
        """모든 장치 목록"""
        return list(self._devices.values())
    
    def get_connected_devices(self) -> List[DeviceInfo]:
        """연결된 장치 목록"""
        return [d for d in self._devices.values() if d.connected]
    
    def get_bound_devices(self) -> List[DeviceInfo]:
        """바인딩된 장치 목록"""
        return [d for d in self._devices.values() if d.bin_id is not None]
    
    def get_bindings(self) -> Dict[str, str]:
        """bin_id → device_id 매핑 반환"""
        return self._bin_device_map.copy()
    
    def set_auto_bind(self, enabled: bool):
        """자동 바인딩 모드 설정"""
        self._auto_bind_enabled = enabled
    
    def reset_auto_bind_counter(self):
        """자동 바인딩 카운터 리셋"""
        self._next_auto_bin_number = 1
    
    def clear_all_bindings(self):
        """모든 바인딩 해제"""
        for device in self._devices.values():
            device.bin_id = None
        self._bin_device_map.clear()
        self._next_auto_bin_number = 1
    
    def get_summary(self) -> dict:
        """레지스트리 요약 정보"""
        return {
            "total_devices": len(self._devices),
            "connected": self.connected_count,
            "bound": self.bound_count,
            "auto_bind_enabled": self._auto_bind_enabled,
            "bindings": self.get_bindings()
        }
    
    def to_json(self) -> str:
        """JSON 직렬화"""
        data = {
            "devices": [d.to_dict() for d in self._devices.values()],
            "bindings": self._bin_device_map,
            "auto_bind_enabled": self._auto_bind_enabled
        }
        return json.dumps(data, indent=2, ensure_ascii=False)
