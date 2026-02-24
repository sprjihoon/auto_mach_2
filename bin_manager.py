"""
BIN 관리 모듈
SKU별 BIN 자동 배정 및 송장별 BIN 매핑

기능:
- BIN당 최대수량 설정 (초과 시 다음 BIN으로 분산)
- 최소수량 이하 SKU 중복 BIN 배정 (소량 SKU들을 하나의 BIN에 묶기)
- 중복 BIN 최대 SKU 개수 설정
"""
from typing import Dict, List, Optional, Tuple
from PySide6.QtCore import QObject, Signal
import pandas as pd


class BinManager(QObject):
    """BIN 주소 관리 클래스"""
    
    # 시그널
    bin_updated = Signal()  # BIN 정보 갱신됨
    bin_reset = Signal()    # BIN 전체 리셋됨
    
    # 기본 설정값
    DEFAULT_MAX_QTY_PER_BIN = 100       # BIN당 최대 수량
    DEFAULT_MIN_QTY_THRESHOLD = 10      # 최소 수량 임계값 (이하면 공유 BIN)
    DEFAULT_MAX_SKU_PER_SHARED_BIN = 5  # 공유 BIN당 최대 SKU 개수
    DEFAULT_DEDICATED_QTY_THRESHOLD = 0 # 전용 BIN 수량 임계값 (이상이면 중복금지, 0=비활성)
    # 단일품목 1개 공유빈: 상품수량 1개이고 다른 조합 주문에 안 나오는 SKU 전용 (하드코딩 1번)
    SINGLE_ITEM_SHARED_BIN_ID = "BIN-01"
    
    def __init__(self):
        super().__init__()
        # SKU(바코드) → BIN 매핑 (단일 BIN 또는 리스트)
        # 대량 SKU: {"barcode": ["BIN-01", "BIN-02"]} (여러 BIN에 분산)
        # 소량 SKU: {"barcode": "BIN-05"} (공유 BIN)
        self._sku_bin_map: Dict[str, str] = {}  # 대표 BIN (첫 번째)
        self._sku_bin_list: Dict[str, List[str]] = {}  # 전체 BIN 리스트 (분산 시)
        
        # 송장번호 → BIN 매핑
        self._order_bin_map: Dict[str, str] = {}
        
        # BIN → SKU 리스트 (공유 BIN용)
        self._bin_sku_map: Dict[str, List[str]] = {}
        
        # BIN별 수량 추적
        self._bin_qty_map: Dict[str, int] = {}
        
        # BIN 카운터
        self._bin_counter: int = 0
        
        # 초기화 여부
        self._initialized: bool = False
        
        # 설정값
        self._max_qty_per_bin: int = self.DEFAULT_MAX_QTY_PER_BIN
        self._min_qty_threshold: int = self.DEFAULT_MIN_QTY_THRESHOLD
        self._max_sku_per_shared_bin: int = self.DEFAULT_MAX_SKU_PER_SHARED_BIN
        self._dedicated_qty_threshold: int = self.DEFAULT_DEDICATED_QTY_THRESHOLD
        
        # SKU별 수량 정보 (조회용)
        self._sku_qty_map: Dict[str, int] = {}
    
    @property
    def is_initialized(self) -> bool:
        """BIN 시스템 초기화 여부"""
        return self._initialized
    
    @property
    def max_qty_per_bin(self) -> int:
        """BIN당 최대 수량"""
        return self._max_qty_per_bin
    
    @max_qty_per_bin.setter
    def max_qty_per_bin(self, value: int):
        """BIN당 최대 수량 설정"""
        self._max_qty_per_bin = max(1, value)
    
    @property
    def min_qty_threshold(self) -> int:
        """최소 수량 임계값 (이하면 공유 BIN)"""
        return self._min_qty_threshold
    
    @min_qty_threshold.setter
    def min_qty_threshold(self, value: int):
        """최소 수량 임계값 설정"""
        self._min_qty_threshold = max(0, value)
    
    @property
    def max_sku_per_shared_bin(self) -> int:
        """공유 BIN당 최대 SKU 개수"""
        return self._max_sku_per_shared_bin
    
    @max_sku_per_shared_bin.setter
    def max_sku_per_shared_bin(self, value: int):
        """공유 BIN당 최대 SKU 개수 설정"""
        self._max_sku_per_shared_bin = max(1, value)
    
    @property
    def dedicated_qty_threshold(self) -> int:
        """전용 BIN 수량 임계값 (이상이면 중복금지, 0=비활성)"""
        return self._dedicated_qty_threshold
    
    @dedicated_qty_threshold.setter
    def dedicated_qty_threshold(self, value: int):
        """전용 BIN 수량 임계값 설정"""
        self._dedicated_qty_threshold = max(0, value)
    
    def set_config(self, max_qty_per_bin: int = None, min_qty_threshold: int = None, 
                   max_sku_per_shared_bin: int = None, dedicated_qty_threshold: int = None):
        """
        BIN 설정 일괄 변경
        
        Args:
            max_qty_per_bin: BIN당 최대 수량 (None이면 유지)
            min_qty_threshold: 최소 수량 임계값 (None이면 유지)
            max_sku_per_shared_bin: 공유 BIN당 최대 SKU 개수 (None이면 유지)
            dedicated_qty_threshold: 전용 BIN 수량 임계값 (None이면 유지, 0=비활성)
        """
        if max_qty_per_bin is not None:
            self._max_qty_per_bin = max(1, max_qty_per_bin)
        if min_qty_threshold is not None:
            self._min_qty_threshold = max(0, min_qty_threshold)
        if max_sku_per_shared_bin is not None:
            self._max_sku_per_shared_bin = max(1, max_sku_per_shared_bin)
        if dedicated_qty_threshold is not None:
            self._dedicated_qty_threshold = max(0, dedicated_qty_threshold)
    
    def get_config(self) -> Dict[str, int]:
        """
        현재 BIN 설정 반환
        
        Returns:
            설정 딕셔너리
        """
        return {
            "max_qty_per_bin": self._max_qty_per_bin,
            "min_qty_threshold": self._min_qty_threshold,
            "max_sku_per_shared_bin": self._max_sku_per_shared_bin,
            "dedicated_qty_threshold": self._dedicated_qty_threshold
        }
    
    def reset(self):
        """
        BIN 전체 리셋
        - 엑셀 로드 시 반드시 호출
        - 모든 BIN 정보 초기화
        """
        self._sku_bin_map.clear()
        self._sku_bin_list.clear()
        self._order_bin_map.clear()
        self._bin_sku_map.clear()
        self._bin_qty_map.clear()
        self._sku_qty_map.clear()
        self._bin_counter = 0
        self._initialized = False
        self.bin_reset.emit()
    
    def _create_new_bin(self) -> str:
        """새 BIN 생성"""
        self._bin_counter += 1
        bin_id = f"BIN-{self._bin_counter:02d}"
        self._bin_sku_map[bin_id] = []
        self._bin_qty_map[bin_id] = 0
        return bin_id
    
    def assign_bins_from_dataframe(self, df: pd.DataFrame) -> int:
        """
        DataFrame에서 SKU별 BIN 자동 배정 (개선된 알고리즘)
        
        0) 단일품목 1개 공유빈: 해당 SKU가 나오는 모든 주문이 "한 건 한 줄 수량 1"인 SKU만
           → BIN-01에 고정 배정 (초과 시 BIN-02, BIN-03...)
        1) 전용 BIN (dedicated_qty_threshold 이상) → 각각 독립 BIN
        2) 대량 SKU (수량 > min_qty_threshold) → 각각 독립 BIN, 필요시 분산
        3) 소량 SKU (수량 <= min_qty_threshold) → 공유 BIN에 묶음
        
        Args:
            df: 엑셀 DataFrame (tracking_no, barcode, qty 컬럼 필수)
        
        Returns:
            배정된 BIN 개수
        """
        # 리셋
        self.reset()
        
        if df is None or df.empty:
            return 0
        
        # used=0인 미처리 항목만 대상
        pending = df[df['used'] == 0] if 'used' in df.columns else df
        
        if pending.empty:
            return 0
        
        # SKU(바코드)별 총 수량 집계
        sku_qty = pending.groupby('barcode')['qty'].sum().reset_index()
        sku_qty.columns = ['barcode', 'total_qty']
        
        # 총 수량 내림차순 정렬
        sku_qty = sku_qty.sort_values('total_qty', ascending=False).reset_index(drop=True)
        
        # 단일품목 1개 공유빈 대상: 해당 SKU가 나오는 모든 주문이 "한 건에 한 줄, 수량 1"인 경우만
        # (다른 조합/다수량 주문에 한 번이라도 나오면 제외)
        pending_barcode_str = pending['barcode'].astype(str).str.strip()
        order_is_single_item_1 = {}
        for tn, grp in pending.groupby('tracking_no'):
            order_is_single_item_1[tn] = (len(grp) == 1 and int(grp.iloc[0]['qty']) == 1)
        single_item_barcodes = set()
        for barcode in sku_qty['barcode'].astype(str).str.strip():
            if not barcode or barcode == 'nan':
                continue
            orders_with_b = pending.loc[pending_barcode_str == barcode, 'tracking_no'].unique()
            if len(orders_with_b) > 0 and all(order_is_single_item_1.get(tn, False) for tn in orders_with_b):
                single_item_barcodes.add(barcode)
        
        # SKU 분류: 단일품목1 vs 대량 vs 소량 vs 전용(중복금지)
        single_item_skus = []  # (barcode, qty) - BIN-01 공유빈 전용
        large_skus = []
        small_skus = []
        dedicated_skus = []
        
        for _, row in sku_qty.iterrows():
            barcode = str(row['barcode']).strip()
            qty = int(row['total_qty'])
            
            if not barcode or barcode == 'nan':
                continue
            
            self._sku_qty_map[barcode] = qty
            
            if barcode in single_item_barcodes:
                single_item_skus.append((barcode, qty))
                continue
            if self._dedicated_qty_threshold > 0 and qty >= self._dedicated_qty_threshold:
                dedicated_skus.append((barcode, qty))
            elif qty > self._min_qty_threshold:
                large_skus.append((barcode, qty))
            else:
                small_skus.append((barcode, qty))
        # 0. 단일품목 1개 공유빈: BIN-01 고정, 초과 시 BIN-02, BIN-03...
        if single_item_skus:
            self._bin_counter = 1
            self._bin_sku_map[self.SINGLE_ITEM_SHARED_BIN_ID] = []
            self._bin_qty_map[self.SINGLE_ITEM_SHARED_BIN_ID] = 0
            current_bin_id = self.SINGLE_ITEM_SHARED_BIN_ID
            current_bin_qty = 0
            for barcode, qty in single_item_skus:
                if current_bin_qty + qty > self._max_qty_per_bin and current_bin_qty > 0:
                    current_bin_id = self._create_new_bin()
                    current_bin_qty = 0
                self._bin_sku_map[current_bin_id].append(barcode)
                self._bin_qty_map[current_bin_id] += qty
                current_bin_qty += qty
                self._sku_bin_map[barcode] = current_bin_id
                self._sku_bin_list[barcode] = [current_bin_id]
        # 1. 전용 BIN 강제 SKU 처리 (중복금지 룰 - 수량 기준)
        for barcode, qty in dedicated_skus:
            bins_for_sku = []
            remaining_qty = qty
            
            while remaining_qty > 0:
                bin_id = self._create_new_bin()
                assign_qty = min(remaining_qty, self._max_qty_per_bin)
                
                self._bin_sku_map[bin_id].append(barcode)
                self._bin_qty_map[bin_id] = assign_qty
                bins_for_sku.append(bin_id)
                
                remaining_qty -= assign_qty
            
            # 대표 BIN (첫 번째)
            self._sku_bin_map[barcode] = bins_for_sku[0]
            # 전체 BIN 리스트
            self._sku_bin_list[barcode] = bins_for_sku
        
        # 2. 대량 SKU 처리 (각각 독립 BIN, 필요시 분산)
        for barcode, qty in large_skus:
            bins_for_sku = []
            remaining_qty = qty
            
            while remaining_qty > 0:
                bin_id = self._create_new_bin()
                assign_qty = min(remaining_qty, self._max_qty_per_bin)
                
                self._bin_sku_map[bin_id].append(barcode)
                self._bin_qty_map[bin_id] = assign_qty
                bins_for_sku.append(bin_id)
                
                remaining_qty -= assign_qty
            
            # 대표 BIN (첫 번째)
            self._sku_bin_map[barcode] = bins_for_sku[0]
            # 전체 BIN 리스트
            self._sku_bin_list[barcode] = bins_for_sku
        
        # 3. 소량 SKU 처리 (공유 BIN에 묶기)
        if small_skus:
            current_shared_bin = None
            current_shared_qty = 0
            current_shared_sku_count = 0
            
            for barcode, qty in small_skus:
                # 새 공유 BIN이 필요한지 확인
                need_new_bin = (
                    current_shared_bin is None or
                    current_shared_sku_count >= self._max_sku_per_shared_bin or
                    current_shared_qty + qty > self._max_qty_per_bin
                )
                
                if need_new_bin:
                    # 새 공유 BIN 생성
                    current_shared_bin = self._create_new_bin()
                    current_shared_qty = 0
                    current_shared_sku_count = 0
                
                # SKU를 공유 BIN에 추가
                self._bin_sku_map[current_shared_bin].append(barcode)
                self._bin_qty_map[current_shared_bin] += qty
                current_shared_qty += qty
                current_shared_sku_count += 1
                
                # 대표 BIN
                self._sku_bin_map[barcode] = current_shared_bin
                self._sku_bin_list[barcode] = [current_shared_bin]
        
        self._initialized = True
        self.bin_updated.emit()
        return self._bin_counter
    
    def get_sku_bin(self, barcode: str) -> str:
        """
        SKU(바코드)의 대표 BIN 주소 조회
        
        Args:
            barcode: 바코드
        
        Returns:
            BIN 주소 (예: "BIN-01") 또는 "BIN 미지정"
        """
        if not self._initialized:
            return "BIN 미지정"
        
        barcode = str(barcode).strip()
        return self._sku_bin_map.get(barcode, "BIN 미지정")
    
    def get_sku_all_bins(self, barcode: str) -> List[str]:
        """
        SKU(바코드)의 모든 BIN 주소 조회 (분산 시 여러 개)
        
        Args:
            barcode: 바코드
        
        Returns:
            BIN 주소 리스트 (예: ["BIN-01", "BIN-02"])
        """
        if not self._initialized:
            return []
        
        barcode = str(barcode).strip()
        return self._sku_bin_list.get(barcode, [])
    
    def get_bin_skus(self, bin_id: str) -> List[str]:
        """
        BIN에 포함된 SKU 목록 조회 (공유 BIN 확인용)
        
        Args:
            bin_id: BIN ID (예: "BIN-01")
        
        Returns:
            바코드 리스트
        """
        return self._bin_sku_map.get(bin_id, [])
    
    def get_bin_qty(self, bin_id: str) -> int:
        """
        BIN의 총 수량 조회
        
        Args:
            bin_id: BIN ID
        
        Returns:
            총 수량
        """
        return self._bin_qty_map.get(bin_id, 0)
    
    def get_sku_qty(self, barcode: str) -> int:
        """
        SKU의 총 수량 조회
        
        Args:
            barcode: 바코드
        
        Returns:
            총 수량
        """
        return self._sku_qty_map.get(str(barcode).strip(), 0)
    
    def is_shared_bin(self, bin_id: str) -> bool:
        """
        공유 BIN인지 확인 (SKU가 2개 이상)
        
        Args:
            bin_id: BIN ID
        
        Returns:
            공유 BIN 여부
        """
        skus = self._bin_sku_map.get(bin_id, [])
        return len(skus) > 1
    
    def build_order_bin_map(self, df: pd.DataFrame):
        """
        송장별 BIN 매핑 구축
        - 각 송장의 대표 SKU 결정 (첫 번째 바코드)
        - sku_bin_map을 사용하여 order_bin_map 생성
        
        Args:
            df: 엑셀 DataFrame
        """
        self._order_bin_map.clear()
        
        if df is None or df.empty or not self._initialized:
            return
        
        # used=0인 미처리 항목만 대상
        pending = df[df['used'] == 0] if 'used' in df.columns else df
        
        if pending.empty:
            return
        
        # 송장별 첫 번째 바코드를 대표 SKU로 사용
        for tracking_no, group in pending.groupby('tracking_no'):
            tracking_no_str = str(tracking_no).strip()
            
            # 첫 번째 바코드 (대표 SKU)
            first_barcode = str(group.iloc[0]['barcode']).strip()
            
            # BIN 조회
            bin_id = self._sku_bin_map.get(first_barcode, "BIN 미지정")
            self._order_bin_map[tracking_no_str] = bin_id
        
        self.bin_updated.emit()
    
    def get_order_bin(self, tracking_no: str) -> str:
        """
        송장번호의 BIN 주소 조회
        
        Args:
            tracking_no: 송장번호
        
        Returns:
            BIN 주소 (예: "BIN-01") 또는 "BIN 미지정"
        """
        if not self._initialized:
            return "BIN 미지정"
        
        tracking_no = str(tracking_no).strip()
        return self._order_bin_map.get(tracking_no, "BIN 미지정")
    
    def get_all_sku_bins(self) -> List[Tuple[str, str, int, int, bool]]:
        """
        모든 SKU-BIN 매핑 목록 반환 (정렬용, 확장 정보 포함)
        
        Returns:
            [(barcode, bin_id, bin_number, sku_qty, is_shared), ...] 리스트
        """
        result = []
        for barcode, bin_id in self._sku_bin_map.items():
            # BIN-01 → 1
            try:
                bin_num = int(bin_id.split('-')[1])
            except:
                bin_num = 999
            
            sku_qty = self._sku_qty_map.get(barcode, 0)
            is_shared = self.is_shared_bin(bin_id)
            
            result.append((barcode, bin_id, bin_num, sku_qty, is_shared))
        
        # BIN 번호 오름차순 정렬
        result.sort(key=lambda x: x[2])
        return result
    
    def get_all_bins_info(self) -> List[Dict]:
        """
        모든 BIN 정보 반환
        
        Returns:
            [{"bin_id": "BIN-01", "skus": [...], "qty": 100, "is_shared": False}, ...]
        """
        result = []
        for bin_id in sorted(self._bin_sku_map.keys(), key=lambda x: int(x.split('-')[1])):
            skus = self._bin_sku_map[bin_id]
            qty = self._bin_qty_map.get(bin_id, 0)
            is_shared = len(skus) > 1
            
            result.append({
                "bin_id": bin_id,
                "skus": skus,
                "sku_count": len(skus),
                "qty": qty,
                "is_shared": is_shared
            })
        
        return result
    
    def get_sku_bin_map(self) -> Dict[str, str]:
        """SKU-BIN 매핑 딕셔너리 반환 (대표 BIN)"""
        return self._sku_bin_map.copy()
    
    def get_order_bin_map(self) -> Dict[str, str]:
        """송장-BIN 매핑 딕셔너리 반환"""
        return self._order_bin_map.copy()
    
    def get_bin_count(self) -> int:
        """배정된 BIN 개수"""
        return self._bin_counter
    
    def get_shared_bin_count(self) -> int:
        """공유 BIN 개수"""
        return sum(1 for bin_id in self._bin_sku_map if len(self._bin_sku_map[bin_id]) > 1)
    
    def get_statistics(self) -> Dict:
        """
        BIN 통계 정보 반환
        
        Returns:
            통계 딕셔너리
        """
        total_bins = self._bin_counter
        shared_bins = self.get_shared_bin_count()
        total_skus = len(self._sku_bin_map)
        
        # 분산된 SKU 개수 (여러 BIN에 걸쳐 있는 SKU)
        distributed_skus = sum(1 for bins in self._sku_bin_list.values() if len(bins) > 1)
        
        return {
            "total_bins": total_bins,
            "shared_bins": shared_bins,
            "dedicated_bins": total_bins - shared_bins,
            "total_skus": total_skus,
            "distributed_skus": distributed_skus,
            "config": self.get_config()
        }
