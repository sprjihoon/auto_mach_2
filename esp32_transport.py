"""
ESP32 WebSocket 통신 모듈
PC가 WebSocket 서버 역할

통신 프로토콜:
ESP32 → PC:
  { type:"hello", device_id:"esp32_123" }
  { type:"done", bin_id:"A03", device_id:"esp32_123" }

PC → ESP32:
  { type:"bind", bin_id:"A03" }
  { type:"display", mode:"full_pick", bin:"A03", color:"purple", qty:3 }
  { type:"off", bin:"A03" }
"""
import asyncio
import json
import threading
from typing import Optional, Callable, Dict, Set
from dataclasses import dataclass
from PySide6.QtCore import QObject, Signal

try:
    import websockets
    from websockets.server import serve
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    print("[ESP32Transport] websockets 패키지 없음. pip install websockets")


@dataclass
class DisplayCommand:
    """LCD 표시 명령"""
    mode: str           # "full_pick", "reverse_match" 등
    bin_id: str         # BIN ID
    color: str          # 색상 (purple, green, red 등)
    qty: int            # 수량
    blink: bool = False # 깜빡임 여부


class Esp32Transport(QObject):
    """
    ESP32 WebSocket 서버
    
    PC가 서버 역할, ESP32가 클라이언트로 연결
    """
    
    # 시그널
    device_hello = Signal(str)          # device_id (장치 연결)
    device_done = Signal(str, str)      # bin_id, device_id (BIN 완료)
    device_disconnected = Signal(str)   # device_id
    server_started = Signal(int)        # port
    server_stopped = Signal()
    message_received = Signal(str, dict)  # device_id, message
    error_occurred = Signal(str)        # error message
    
    # 기본 설정
    DEFAULT_HOST = "0.0.0.0"
    DEFAULT_PORT = 8765
    
    def __init__(self, host: str = None, port: int = None):
        super().__init__()
        
        self._host = host or self.DEFAULT_HOST
        self._port = port or self.DEFAULT_PORT
        
        # WebSocket 연결 관리
        self._connections: Dict[str, object] = {}  # device_id → websocket
        self._websocket_to_device: Dict[object, str] = {}  # websocket → device_id
        
        # 서버 상태
        self._server = None
        self._server_task = None
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None
        self._running = False
        
        # 메시지 핸들러
        self._message_handlers: Dict[str, Callable] = {}
        
        # 콜백
        self._on_hello_callback: Optional[Callable] = None
        self._on_done_callback: Optional[Callable] = None
    
    @property
    def is_running(self) -> bool:
        """서버 실행 중 여부"""
        return self._running
    
    @property
    def connected_count(self) -> int:
        """연결된 장치 수"""
        return len(self._connections)
    
    def set_on_hello(self, callback: Callable):
        """hello 메시지 콜백 설정"""
        self._on_hello_callback = callback
    
    def set_on_done(self, callback: Callable):
        """done 메시지 콜백 설정"""
        self._on_done_callback = callback
    
    def start(self) -> bool:
        """
        WebSocket 서버 시작
        
        Returns:
            성공 여부
        """
        if not WEBSOCKETS_AVAILABLE:
            self.error_occurred.emit("websockets 패키지가 설치되지 않았습니다.")
            return False
        
        if self._running:
            return True
        
        try:
            # 별도 스레드에서 asyncio 이벤트 루프 실행
            self._server_thread = threading.Thread(target=self._run_server, daemon=True)
            self._server_thread.start()
            return True
        except Exception as e:
            self.error_occurred.emit(f"서버 시작 실패: {str(e)}")
            return False
    
    def _run_server(self):
        """서버 실행 (별도 스레드)"""
        try:
            # 새 이벤트 루프 생성
            self._event_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._event_loop)
            
            # 서버 시작
            self._event_loop.run_until_complete(self._start_server())
            self._running = True
            self.server_started.emit(self._port)
            
            # 이벤트 루프 실행
            self._event_loop.run_forever()
        except Exception as e:
            self.error_occurred.emit(f"서버 오류: {str(e)}")
        finally:
            self._running = False
    
    async def _start_server(self):
        """비동기 서버 시작"""
        self._server = await serve(
            self._handle_connection,
            self._host,
            self._port,
            ping_interval=30,
            ping_timeout=10
        )
        print(f"[ESP32Transport] WebSocket 서버 시작: ws://{self._host}:{self._port}")
    
    async def _handle_connection(self, websocket, path=None):
        """클라이언트 연결 처리"""
        device_id = None
        
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    msg_type = data.get("type", "")
                    
                    if msg_type == "hello":
                        # 장치 연결 (hello)
                        device_id = data.get("device_id", "unknown")
                        self._connections[device_id] = websocket
                        self._websocket_to_device[websocket] = device_id
                        
                        print(f"[ESP32Transport] 장치 연결: {device_id}")
                        self.device_hello.emit(device_id)
                        
                        if self._on_hello_callback:
                            self._on_hello_callback(device_id, websocket)
                    
                    elif msg_type == "done":
                        # BIN 완료 (done)
                        bin_id = data.get("bin_id", "")
                        dev_id = data.get("device_id", device_id or "unknown")
                        
                        print(f"[ESP32Transport] BIN 완료: {bin_id} (장치: {dev_id})")
                        self.device_done.emit(bin_id, dev_id)
                        
                        if self._on_done_callback:
                            self._on_done_callback(bin_id, dev_id)
                    
                    # 일반 메시지 시그널
                    self.message_received.emit(device_id or "unknown", data)
                    
                except json.JSONDecodeError:
                    print(f"[ESP32Transport] JSON 파싱 오류: {message}")
                except Exception as e:
                    print(f"[ESP32Transport] 메시지 처리 오류: {e}")
        
        except Exception as e:
            print(f"[ESP32Transport] 연결 오류: {e}")
        
        finally:
            # 연결 해제
            if device_id:
                if device_id in self._connections:
                    del self._connections[device_id]
                if websocket in self._websocket_to_device:
                    del self._websocket_to_device[websocket]
                
                print(f"[ESP32Transport] 장치 연결 해제: {device_id}")
                self.device_disconnected.emit(device_id)
    
    def stop(self):
        """서버 중지"""
        if not self._running:
            return
        
        try:
            if self._server:
                self._server.close()
            
            if self._event_loop:
                self._event_loop.call_soon_threadsafe(self._event_loop.stop)
            
            self._running = False
            self._connections.clear()
            self._websocket_to_device.clear()
            
            self.server_stopped.emit()
            print("[ESP32Transport] 서버 중지됨")
        except Exception as e:
            print(f"[ESP32Transport] 서버 중지 오류: {e}")
    
    def send_to_device(self, device_id: str, message: dict) -> bool:
        """
        특정 장치에 메시지 전송
        
        Args:
            device_id: 장치 ID
            message: 전송할 메시지 (dict)
        
        Returns:
            성공 여부
        """
        if device_id not in self._connections:
            print(f"[ESP32Transport] 장치 없음: {device_id}")
            return False
        
        websocket = self._connections[device_id]
        return self._send_async(websocket, message)
    
    def send_to_bin(self, bin_id: str, message: dict, device_registry=None) -> bool:
        """
        BIN에 연결된 장치에 메시지 전송
        
        Args:
            bin_id: BIN ID
            message: 전송할 메시지
            device_registry: DeviceRegistry 객체 (bin_id → device_id 조회용)
        
        Returns:
            성공 여부
        """
        if device_registry:
            device_id = device_registry.get_device_id_by_bin(bin_id)
            if device_id:
                return self.send_to_device(device_id, message)
        
        # device_registry 없이 직접 찾기 (비효율적)
        # 보통은 device_registry를 사용해야 함
        return False
    
    def _send_async(self, websocket, message: dict) -> bool:
        """비동기 전송"""
        if not self._event_loop or not self._running:
            return False
        
        try:
            json_msg = json.dumps(message)
            asyncio.run_coroutine_threadsafe(
                websocket.send(json_msg),
                self._event_loop
            )
            return True
        except Exception as e:
            print(f"[ESP32Transport] 전송 오류: {e}")
            return False
    
    def broadcast(self, message: dict) -> int:
        """
        모든 연결된 장치에 브로드캐스트
        
        Args:
            message: 전송할 메시지
        
        Returns:
            전송 성공한 장치 수
        """
        success_count = 0
        for device_id in list(self._connections.keys()):
            if self.send_to_device(device_id, message):
                success_count += 1
        return success_count
    
    # ===== 편의 메서드 =====
    
    def send_bind(self, device_id: str, bin_id: str) -> bool:
        """
        바인딩 명령 전송
        
        { type:"bind", bin_id:"A03" }
        """
        return self.send_to_device(device_id, {
            "type": "bind",
            "bin_id": bin_id
        })
    
    def send_display(self, device_id: str, cmd: DisplayCommand) -> bool:
        """
        디스플레이 명령 전송
        
        { type:"display", mode:"full_pick", bin:"A03", color:"purple", qty:3 }
        """
        return self.send_to_device(device_id, {
            "type": "display",
            "mode": cmd.mode,
            "bin": cmd.bin_id,
            "color": cmd.color,
            "qty": cmd.qty,
            "blink": cmd.blink
        })
    
    def send_off(self, device_id: str, bin_id: str) -> bool:
        """
        LCD OFF 명령 전송
        
        { type:"off", bin:"A03" }
        """
        return self.send_to_device(device_id, {
            "type": "off",
            "bin": bin_id
        })
    
    def send_display_to_bin(self, bin_id: str, mode: str, color: str, qty: int, 
                            device_registry=None) -> bool:
        """
        BIN에 디스플레이 명령 전송 (편의 메서드)
        """
        if not device_registry:
            return False
        
        device_id = device_registry.get_device_id_by_bin(bin_id)
        if not device_id:
            return False
        
        cmd = DisplayCommand(mode=mode, bin_id=bin_id, color=color, qty=qty)
        return self.send_display(device_id, cmd)
    
    def send_off_to_bin(self, bin_id: str, device_registry=None) -> bool:
        """
        BIN에 OFF 명령 전송 (편의 메서드)
        """
        if not device_registry:
            return False
        
        device_id = device_registry.get_device_id_by_bin(bin_id)
        if not device_id:
            return False
        
        return self.send_off(device_id, bin_id)
    
    def get_connected_devices(self) -> list:
        """연결된 장치 ID 목록"""
        return list(self._connections.keys())
    
    def is_device_connected(self, device_id: str) -> bool:
        """장치 연결 상태 확인"""
        return device_id in self._connections
