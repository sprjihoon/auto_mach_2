"""
PDF 자동출력 모듈
Windows os.startfile 방식으로 클릭 없이 기본 프린터로 인쇄
PDF 내용에서 송장번호를 찾아서 해당 페이지만 출력 지원
"""
import os
import re
import tempfile
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from PySide6.QtCore import QObject, Signal

from utils import get_pdf_path, pdf_exists
from printer_manager import print_pdf_with_printer, load_printer_settings, load_label_rotation

# PDF 처리 라이브러리 (고정밀 인식을 위해 여러 라이브러리 사용)
PDF_SUPPORT = False
HAS_PDFPLUMBER = False
HAS_FITZ = False

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    print("[pdf_printer] pdfplumber 패키지가 설치되지 않았습니다. pip install pdfplumber")

try:
    import fitz  # PyMuPDF
    HAS_FITZ = True
except ImportError:
    print("[pdf_printer] PyMuPDF 패키지가 설치되지 않았습니다. pip install PyMuPDF")

# 둘 다 있어야 PDF_SUPPORT = True
if HAS_PDFPLUMBER and HAS_FITZ:
    PDF_SUPPORT = True
elif HAS_FITZ:
    # PyMuPDF만 있어도 기본 기능은 동작
    PDF_SUPPORT = True
    print("[pdf_printer] pdfplumber 없이 PyMuPDF만 사용합니다 (일부 기능 제한)")


class PDFPrinter(QObject):
    """PDF 자동 출력 클래스"""
    
    # 시그널
    print_success = Signal(str)  # 성공 메시지
    print_error = Signal(str)    # 오류 메시지
    index_updated = Signal(int)  # 인덱싱 완료 (페이지 수)
    
    def __init__(self):
        super().__init__()
        self._enabled = True
        self._labels_dir: Optional[Path] = None
        self._pdf_file: Optional[Path] = None  # 단일 PDF 파일
        self._tracking_index: Dict[str, Tuple[Path, int]] = {}  # {tracking_no: (pdf_path, page_num)}
        self._temp_dir = Path(tempfile.gettempdir()) / "auto_mach_labels"
        self._temp_dir.mkdir(exist_ok=True)
        self._keep_temp_files = False  # 출력 후 임시 파일 삭제 (기본값: False)
        
        # 주문서 출력 기능 (두 번째 PDF 및 프린터)
        self._order_sheet_enabled = False  # 주문서 출력 활성화 여부
        self._pdf_file_2: Optional[Path] = None  # 두 번째 PDF 파일 (주문서)
        self._printer_name_2: Optional[str] = None  # 두 번째 프린터 이름
        self._tracking_index_2: Dict[str, Tuple[Path, int]] = {}  # 두 번째 PDF 인덱스
        
        # 송장 출력 프린터 (첫 번째 PDF)
        self._printer_name_1: Optional[str] = None  # 첫 번째 프린터 이름 (송장)
    
    @property
    def enabled(self) -> bool:
        return self._enabled
    
    @enabled.setter
    def enabled(self, value: bool):
        self._enabled = value
    
    @property
    def keep_temp_files(self) -> bool:
        """임시 파일 보관 여부"""
        return self._keep_temp_files
    
    @keep_temp_files.setter
    def keep_temp_files(self, value: bool):
        """임시 파일 보관 여부 설정 (True: 출력 후에도 임시 파일 유지, False: 출력 후 삭제)"""
        self._keep_temp_files = value
    
    @property
    def order_sheet_enabled(self) -> bool:
        """주문서 출력 활성화 여부"""
        return self._order_sheet_enabled
    
    @order_sheet_enabled.setter
    def order_sheet_enabled(self, value: bool):
        """주문서 출력 활성화 여부 설정"""
        self._order_sheet_enabled = value
    
    def set_pdf_file_2(self, path: str):
        """두 번째 PDF 파일 설정 (주문서)"""
        if path:
            self._pdf_file_2 = Path(path)
        else:
            self._pdf_file_2 = None
            self._tracking_index_2.clear()
    
    def set_printer_1(self, printer_name: str):
        """첫 번째 프린터 이름 설정 (송장 출력용)"""
        self._printer_name_1 = printer_name if printer_name else None
    
    def set_printer_2(self, printer_name: str):
        """두 번째 프린터 이름 설정"""
        self._printer_name_2 = printer_name if printer_name else None
    
    def set_labels_directory(self, path: str):
        """라벨 PDF 폴더 경로 설정 (하위 호환)"""
        self._labels_dir = Path(path)
    
    def set_pdf_file(self, path: str):
        """단일 PDF 파일 설정"""
        self._pdf_file = Path(path)
        self._labels_dir = self._pdf_file.parent
    
    def build_tracking_index(self, excel_tracking_numbers: List[str] = None) -> int:
        """
        PDF 파일에서 송장번호 인덱스 생성
        
        Args:
            excel_tracking_numbers: 엑셀에서 가져온 송장번호 목록 (이미지 PDF의 경우 순서대로 매핑)
        """
        if not PDF_SUPPORT:
            self.print_error.emit("PDF 라이브러리가 설치되지 않았습니다 (pdfplumber, PyMuPDF)")
            return 0
        
        self._tracking_index.clear()
        total_pages = 0
        
        # 단일 파일 모드
        if self._pdf_file and self._pdf_file.exists():
            pdf_files = [self._pdf_file]
        elif self._labels_dir and self._labels_dir.exists():
            pdf_files = list(self._labels_dir.glob("*.pdf"))
        else:
            return 0
        
        for pdf_path in pdf_files:
            try:
                # 송장번호 패턴 매칭 (다양한 형식 지원)
                # 하이픈, 공백, 다양한 변형 모두 지원
                patterns = [
                    # 등기번호: 패턴 (최우선 - 명시적 표시)
                    r'등기번호[:\s\-]*([0-9]{5}[-–—\s]{0,2}\d{4}[-–—\s]{0,2}\d{4})',  # "등기번호:" 패턴
                    r'송장번호[:\s\-]*([0-9]{5}[-–—\s]{0,2}\d{4}[-–—\s]{0,2}\d{4})',  # "송장번호:" 패턴
                    
                    # 5-4-4 형식 (하이픈 포함) - 일반적인 형식
                    r'(\d{5}[-–—\s]+\d{4}[-–—\s]+\d{4})',     # 모든 하이픈 변형
                    r'(\d{5}\s*[-–—]\s*\d{4}\s*[-–—]\s*\d{4})',  # 공백 포함
                    
                    # 13자리 연속 숫자 (일반적인 송장번호 길이)
                    r'\b(\d{13})\b',                           # 단어 경계 포함
                    r'(?<!\d)(\d{13})(?!\d)',                  # 앞뒤 숫자 제외
                    
                    # 12자리 연속 숫자
                    r'\b(\d{12})\b',
                    r'(?<!\d)(\d{12})(?!\d)',
                    
                    # 11자리 연속 숫자
                    r'\b(\d{11})\b',
                    r'(?<!\d)(\d{11})(?!\d)',
                ]
                
                # 디버깅: 사용할 패턴 로그
                self.print_success.emit(f"송장번호 패턴 {len(patterns)}개 사용하여 스캔 시작")
                
                # 방법 1: pdfplumber로 고정밀 텍스트 추출
                text_extracted = False
                try:
                    with pdfplumber.open(pdf_path) as pdf:
                        for page_num, page in enumerate(pdf.pages):
                            # 표준 텍스트 추출
                            text = page.extract_text() or ""
                            
                            # 고정밀 텍스트 추출 옵션 여러 방법 시도
                            if not text or len(text.strip()) < 10:
                                extraction_methods = [
                                    # 방법 1: 고정밀 옵션
                                    {"x_tolerance": 1, "y_tolerance": 1, "layout": True},
                                    {"x_tolerance": 3, "y_tolerance": 3, "layout": True},
                                    {"x_tolerance": 5, "y_tolerance": 5, "layout": False},
                                    # 방법 2: 다른 설정들
                                    {"x_tolerance": 2, "y_tolerance": 2, "layout": True, "x_density": 10, "y_density": 10},
                                    {"use_text_flow": True, "layout": True},
                                ]
                                
                                for method in extraction_methods:
                                    try:
                                        text = page.extract_text(**method) or ""
                                        if text and len(text.strip()) >= 10:
                                            break
                                    except:
                                        continue
                            
                            if text and len(text.strip()) > 0:
                                text_extracted = True
                                found_matches = set()
                                
                                # 원본 텍스트 보존
                                original_text = text
                                
                                # 디버깅: 추출된 텍스트에서 송장번호 패턴 찾기
                                text_sample = text.replace('\n', ' ').replace('\r', ' ')[:500]
                                
                                # 13자리 숫자 패턴 찾기 (디버깅용)
                                tracking_candidates = re.findall(r'\b\d{13}\b', original_text)
                                if tracking_candidates:
                                    self.print_success.emit(f"[페이지 {page_num + 1}] 13자리 숫자 발견: {', '.join(tracking_candidates[:5])}")
                                
                                # 하이픈/공백 포함 송장번호 패턴 (5-4-4 형식)
                                hyphen_patterns = re.findall(r'\d{5}[-–—\s]+\d{4}[-–—\s]+\d{4}', original_text)
                                if hyphen_patterns:
                                    self.print_success.emit(f"[페이지 {page_num + 1}] ✓ 송장번호 하이픈 패턴: {', '.join(hyphen_patterns[:3])}")
                                
                                # "등기번호" 주변 패턴 처리
                                special_patterns = re.findall(r'등기번호[:\s\-]*([0-9]{5}[-–—\s]{0,2}\d{4}[-–—\s]{0,2}\d{4})', original_text)
                                for sp in special_patterns:
                                    clean = re.sub(r'[-–—\s]', '', sp)
                                    if clean.isdigit():
                                        text = text + f" {sp} "  # 패턴 탐색을 위해 텍스트에 추가
                                
                                # 전체 텍스트 샘플 (송장번호 위치 확인)
                                if '등기번호' in text_sample or '송장번호' in text_sample or re.search(r'\d{5}[-–—\s]+\d{4}[-–—\s]+\d{4}', text_sample) or re.search(r'\b\d{13}\b', text_sample):
                                    self.print_success.emit(f"[페이지 {page_num + 1}] 텍스트: {text_sample}...")
                                
                                # 원본 텍스트에서 직접 패턴 매칭 (정규화 전)
                                for pattern in patterns:
                                    matches = re.findall(pattern, original_text)
                                    if matches:
                                        self.print_success.emit(f"[페이지 {page_num + 1}] 패턴 매칭 성공: {matches}")
                                    
                                    for match in matches:
                                        # 모든 하이픈 변형과 공백 제거
                                        clean_match = re.sub(r'[-–—\s]', '', match)
                                        
                                        # 숫자만 남았는지 확인 (최소 10자리)
                                        if clean_match.isdigit() and len(clean_match) >= 10:
                                            # 이미 처리한 매치는 건너뛰기
                                            if clean_match in found_matches:
                                                continue
                                            found_matches.add(clean_match)
                                            
                                            # 디버깅: 송장번호 매칭 성공
                                            self.print_success.emit(f"✓ 송장번호 발견: {match} → {clean_match} (페이지 {page_num + 1})")
                                            
                                            # 하이픈 제거한 버전 저장 (주요 인덱스)
                                            if clean_match not in self._tracking_index:
                                                self._tracking_index[clean_match] = (pdf_path, page_num)
                                                total_pages += 1
                                            
                                            # 원본 형식도 저장 (하이픈 포함)
                                            if match != clean_match and match not in self._tracking_index:
                                                self._tracking_index[match] = (pdf_path, page_num)
                                
                                # 추가로 정규화된 텍스트에서도 시도 (원본에서 못 찾은 경우)
                                if not found_matches:
                                    text = re.sub(r'[^\w\s\-–—]', ' ', original_text)  # 특수문자 제거
                                    text = re.sub(r'\s+', ' ', text)         # 다중 공백 제거
                                    
                                    self.print_success.emit(f"[페이지 {page_num + 1}] 정규화된 텍스트에서 재시도...")
                                    
                                    for pattern in patterns:
                                        matches = re.findall(pattern, text)
                                        for match in matches:
                                            # 모든 하이픈 변형과 공백 제거
                                            clean_match = re.sub(r'[-–—\s]', '', match)
                                            
                                            # 숫자만 남았는지 확인 (최소 10자리)
                                            if clean_match.isdigit() and len(clean_match) >= 10:
                                                # 이미 처리한 매치는 건너뛰기
                                                if clean_match in found_matches:
                                                    continue
                                                found_matches.add(clean_match)
                                                
                                                # 디버깅: 송장번호 매칭 성공
                                                self.print_success.emit(f"✓ 송장번호 발견 (정규화 후): {match} → {clean_match} (페이지 {page_num + 1})")
                                                
                                                # 하이픈 제거한 버전 저장 (주요 인덱스)
                                                if clean_match not in self._tracking_index:
                                                    self._tracking_index[clean_match] = (pdf_path, page_num)
                                                    total_pages += 1
                                                
                                                # 원본 형식도 저장 (하이픈 포함)
                                                if match != clean_match and match not in self._tracking_index:
                                                    self._tracking_index[match] = (pdf_path, page_num)
                except Exception as e:
                    # pdfplumber 실패 시 다음 방법으로
                    pass
                
                # 방법 2: PyMuPDF로 고정밀 텍스트 추출
                if not text_extracted:
                    try:
                        doc = fitz.open(pdf_path)
                        pymupdf_extracted = False
                        for page_num in range(len(doc)):
                            page = doc[page_num]
                            
                            # 다양한 텍스트 추출 방법 시도
                            texts_to_try = []
                            
                            # 1) 기본 텍스트 추출
                            text1 = page.get_text() or ""
                            if text1.strip():
                                texts_to_try.append(text1)
                            
                            # 2) 고정밀 텍스트 추출
                            try:
                                text2 = page.get_text("text", clip=None) or ""
                                if text2.strip() and text2 not in texts_to_try:
                                    texts_to_try.append(text2)
                            except:
                                pass
                            
                            # 3) 블록 단위 텍스트 추출
                            try:
                                blocks = page.get_text("blocks") or []
                                block_text = ""
                                for block in blocks:
                                    if len(block) >= 5 and isinstance(block[4], str):
                                        block_text += block[4] + " "
                                if block_text.strip() and block_text not in texts_to_try:
                                    texts_to_try.append(block_text)
                            except:
                                pass
                            
                            # 각 텍스트에서 송장번호 추출
                            for text in texts_to_try:
                                if text and len(text.strip()) > 0:
                                    pymupdf_extracted = True
                                    found_matches = set()
                                    
                                    # 텍스트 정규화
                                    text = re.sub(r'[^\w\s\-–—]', ' ', text)
                                    text = re.sub(r'\s+', ' ', text)
                                    
                                    for pattern in patterns:
                                        matches = re.findall(pattern, text)
                                        for match in matches:
                                            # 모든 하이픈 변형과 공백 제거
                                            clean_match = re.sub(r'[-–—\s]', '', match)
                                            
                                            # 숫자만 남았는지 확인 (최소 10자리)
                                            if clean_match.isdigit() and len(clean_match) >= 10:
                                                # 이미 처리한 매치는 건너뛰기
                                                if clean_match in found_matches:
                                                    continue
                                                found_matches.add(clean_match)
                                                
                                                # 하이픈 제거한 버전 저장 (주요 인덱스)
                                                if clean_match not in self._tracking_index:
                                                    self._tracking_index[clean_match] = (pdf_path, page_num)
                                                    total_pages += 1
                                                
                                                # 원본 형식도 저장 (하이픈 포함)
                                                if match != clean_match and match not in self._tracking_index:
                                                    self._tracking_index[match] = (pdf_path, page_num)
                        
                        # 텍스트 추출 실패 시 엑셀 기반 매핑 시도 (최후 수단)
                        # 텍스트 추출 실패 시 더 강력한 방법들 시도
                        if not pymupdf_extracted:
                            self.print_error.emit(f"⚠️ 기본 텍스트 추출 실패, 고급 방법 시도 중...")
                            
                            # 방법 3: 더 강력한 텍스트 추출 시도
                            try:
                                advanced_extracted = False
                                for page_num in range(len(doc)):
                                    page = doc[page_num]
                                    
                                    # 여러 추출 방법 시도
                                    extraction_methods = [
                                        # 방법 1: 딕셔너리 형태로 추출
                                        lambda p: p.get_text("dict"),
                                        # 방법 2: 단어 단위로 추출  
                                        lambda p: p.get_text("words"),
                                        # 방법 3: JSON 형태로 추출
                                        lambda p: p.get_text("json"),
                                        # 방법 4: 원시 텍스트
                                        lambda p: p.get_text("rawdict"),
                                    ]
                                    
                                    page_text = ""
                                    for method in extraction_methods:
                                        try:
                                            result = method(page)
                                            if isinstance(result, dict):
                                                # 딕셔너리에서 텍스트 추출
                                                if 'blocks' in result:
                                                    for block in result['blocks']:
                                                        if 'lines' in block:
                                                            for line in block['lines']:
                                                                if 'spans' in line:
                                                                    for span in line['spans']:
                                                                        if 'text' in span:
                                                                            page_text += span['text'] + " "
                                            elif isinstance(result, list):
                                                # 단어 리스트에서 텍스트 추출
                                                for item in result:
                                                    if isinstance(item, tuple) and len(item) >= 5:
                                                        page_text += str(item[4]) + " "
                                                    elif isinstance(item, str):
                                                        page_text += item + " "
                                            elif isinstance(result, str):
                                                page_text = result
                                                
                                            if page_text and len(page_text.strip()) > 10:
                                                break
                                        except:
                                            continue
                                    
                                    if page_text and len(page_text.strip()) > 0:
                                        advanced_extracted = True
                                        self.print_success.emit(f"[페이지 {page_num + 1}] 고급 텍스트 추출 성공: {page_text[:100]}...")
                                        
                                        # 송장번호 패턴 찾기
                                        found_matches = set()
                                        for pattern in patterns:
                                            matches = re.findall(pattern, page_text)
                                            for match in matches:
                                                clean_match = re.sub(r'[-–—\s]', '', match)
                                                if clean_match.isdigit() and len(clean_match) >= 10:
                                                    if clean_match not in found_matches:
                                                        found_matches.add(clean_match)
                                                        self.print_success.emit(f"✓ 고급 추출로 송장번호 발견: {match} → {clean_match} (페이지 {page_num + 1})")
                                                        
                                                        if clean_match not in self._tracking_index:
                                                            self._tracking_index[clean_match] = (pdf_path, page_num)
                                                            total_pages += 1
                                                        
                                                        if match != clean_match and match not in self._tracking_index:
                                                            self._tracking_index[match] = (pdf_path, page_num)
                                
                                if not advanced_extracted:
                                    self.print_error.emit(f"❌ 모든 텍스트 추출 방법 실패 ({pdf_path.name})")
                                    self.print_error.emit(f"💡 이 PDF는 이미지로만 구성되어 있습니다")
                                    self.print_error.emit(f"해결방법: Chrome에서 PDF 열어서 '인쇄 → PDF로 저장'으로 텍스트 PDF 변환")
                                    
                            except Exception as e:
                                self.print_error.emit(f"고급 텍스트 추출 실패: {str(e)}")
                        
                        doc.close()
                    except Exception as e:
                        # 예외 발생 시 명확한 오류 메시지
                        self.print_error.emit(f"❌ PDF 처리 예외 발생 ({pdf_path.name}): {str(e)}")
                        self.print_error.emit(f"💡 해결 방법: PDF를 텍스트 선택 가능한 형태로 다시 저장하세요")
                        
            except Exception as e:
                self.print_error.emit(f"PDF 스캔 오류 ({pdf_path.name}): {str(e)}")
                continue
        
        self.index_updated.emit(total_pages)
        
        # 두 번째 PDF 파일 인덱싱 (주문서 출력 활성화 시)
        if self._order_sheet_enabled and self._pdf_file_2 and self._pdf_file_2.exists():
            self._build_tracking_index_2(excel_tracking_numbers)
        
        return total_pages
    
    def _build_tracking_index_2(self, excel_tracking_numbers: List[str] = None) -> int:
        """
        두 번째 PDF 파일에서 송장번호 인덱스 생성 (주문서)
        
        Args:
            excel_tracking_numbers: 엑셀에서 가져온 송장번호 목록
        """
        if not PDF_SUPPORT or not self._pdf_file_2 or not self._pdf_file_2.exists():
            return 0
        
        self._tracking_index_2.clear()
        total_pages = 0
        
        try:
            # 첫 번째 PDF와 동일한 패턴 사용
            patterns = [
                r'등기번호[:\s\-]*([0-9]{5}[-–—\s]{0,2}\d{4}[-–—\s]{0,2}\d{4})',
                r'송장번호[:\s\-]*([0-9]{5}[-–—\s]{0,2}\d{4}[-–—\s]{0,2}\d{4})',
                r'(\d{5}[-–—\s]+\d{4}[-–—\s]+\d{4})',
                r'(\d{5}\s*[-–—]\s*\d{4}\s*[-–—]\s*\d{4})',
                r'\b(\d{13})\b',
                r'(?<!\d)(\d{13})(?!\d)',
                r'\b(\d{12})\b',
                r'(?<!\d)(\d{12})(?!\d)',
                r'\b(\d{11})\b',
                r'(?<!\d)(\d{11})(?!\d)',
            ]
            
            # PyMuPDF로 PDF 열기
            doc = fitz.open(str(self._pdf_file_2))
            total_pages = len(doc)
            found_matches = set()
            
            for page_num in range(total_pages):
                page = doc[page_num]
                original_text = page.get_text() or ""
                
                # 패턴 매칭
                for pattern in patterns:
                    matches = re.findall(pattern, original_text)
                    for match in matches:
                        clean_match = re.sub(r'[-–—\s]', '', match)
                        if clean_match.isdigit() and len(clean_match) >= 10:
                            if clean_match in found_matches:
                                continue
                            found_matches.add(clean_match)
                            
                            if clean_match not in self._tracking_index_2:
                                self._tracking_index_2[clean_match] = (self._pdf_file_2, page_num)
                                # 원본 형식도 저장
                                if match != clean_match and match not in self._tracking_index_2:
                                    self._tracking_index_2[match] = (self._pdf_file_2, page_num)
            
            doc.close()
            self.print_success.emit(f"두 번째 PDF 인덱싱 완료: {len(self._tracking_index_2)}개 송장번호, {total_pages}페이지")
            
        except Exception as e:
            self.print_error.emit(f"두 번째 PDF 인덱싱 오류: {str(e)}")
        
        return total_pages
    
    def get_indexed_tracking_numbers(self) -> List[str]:
        """인덱싱된 송장번호 목록 반환"""
        return list(self._tracking_index.keys())
    
    def _detect_content_rect(self, page):
        """페이지에서 내용이 있는 영역(Rect) 추정"""
        rect = page.rect
        try:
            blocks = page.get_text("blocks") or []
            xs0, ys0, xs1, ys1 = [], [], [], []
            for block in blocks:
                if len(block) >= 5:
                    x0, y0, x1, y1, text = block[:5]
                    if isinstance(text, str) and text.strip():
                        xs0.append(x0)
                        ys0.append(y0)
                        xs1.append(x1)
                        ys1.append(y1)
            if xs0 and ys0 and xs1 and ys1:
                margin = 10
                clip = fitz.Rect(
                    max(rect.x0, min(xs0) - margin),
                    max(rect.y0, min(ys0) - margin),
                    min(rect.x1, max(xs1) + margin),
                    min(rect.y1, max(ys1) + margin),
                )
                return clip
        except Exception:
            pass
        return rect
    
    def extract_page_to_temp(self, tracking_no: str) -> Optional[Path]:
        """
        송장번호에 해당하는 페이지를 임시 PDF로 추출
        다음 페이지에 수령자 이름만 있고 송장번호가 없으면 함께 추출 (2장 송장 처리)
        """
        if tracking_no not in self._tracking_index:
            self.print_error.emit(f"인덱스에 없는 송장번호: {tracking_no}")
            return None
        
        pdf_path, page_num = self._tracking_index[tracking_no]
        self.print_success.emit(f"⚠️ 페이지 추출 시작: {tracking_no} → {pdf_path.name} 페이지 {page_num + 1}")
        self.print_success.emit(f"⚠️ 요청된 송장번호: {tracking_no}, 매핑된 페이지: {page_num + 1}")
        
        try:
            # 파일명에 사용할 수 있도록 하이픈 제거
            clean_tracking_no = re.sub(r'[-–—\s]', '', tracking_no)
            
            # PyMuPDF로 PDF 열기
            doc = fitz.open(pdf_path)
            total_pages = len(doc)
            
            # 페이지 번호 검증 (0-based)
            if page_num < 0 or page_num >= total_pages:
                self.print_error.emit(f"페이지 번호 오류: {page_num} (총 {total_pages}페이지)")
                doc.close()
                return None
            
            # 현재 페이지에서 수령자 이름 추출 시도
            recipient_name = None
            try:
                current_page = doc[page_num]
                current_text = current_page.get_text() or ""
                
                # 수령자 이름 패턴 찾기 (한글 이름, 영문 이름 등)
                # 일반적인 패턴: "수령자", "받는분", "수신인" 등의 키워드 다음에 이름
                name_patterns = [
                    r'수령자[:\s]*([가-힣]{2,4})',
                    r'받는분[:\s]*([가-힣]{2,4})',
                    r'수신인[:\s]*([가-힣]{2,4})',
                    r'받는\s*사람[:\s]*([가-힣]{2,4})',
                    r'수령인[:\s]*([가-힣]{2,4})',
                ]
                
                for pattern in name_patterns:
                    match = re.search(pattern, current_text)
                    if match:
                        recipient_name = match.group(1).strip()
                        break
            except Exception:
                pass
            
            # 2장 송장 처리: 다음 페이지 확인
            start_page = page_num
            end_page = page_num
            
            # 다음 페이지가 있고, 현재 페이지에서 수령자 이름을 찾았거나 제품 정보가 많은 경우
            if page_num + 1 < total_pages:
                next_page = doc[page_num + 1]
                next_text = next_page.get_text() or ""
                
                # 다음 페이지에 다른 송장번호가 있는지 확인
                # 송장번호 패턴: 5-4-4 형식 또는 11-13자리 연속 숫자
                next_tracking_patterns = [
                    r'\d{5}[-–—\s]+\d{4}[-–—\s]+\d{4}',  # 5-4-4 형식
                    r'\b\d{13}\b',  # 13자리
                    r'\b\d{12}\b',  # 12자리
                    r'\b\d{11}\b',  # 11자리
                ]
                
                next_has_tracking = False
                for pattern in next_tracking_patterns:
                    matches = re.findall(pattern, next_text)
                    for match in matches:
                        clean_match = re.sub(r'[-–—\s]', '', match)
                        if clean_match.isdigit() and len(clean_match) >= 10:
                            # 다른 송장번호가 있으면 중단
                            if clean_match != clean_tracking_no:
                                next_has_tracking = True
                                break
                    if next_has_tracking:
                        break
                
                # 다음 페이지에 송장번호가 없고, 고객 정보나 제품 정보가 있으면 포함
                if not next_has_tracking:
                    # 다음 페이지에 고객 이름, 제품명, 수량 등의 키워드가 있는지 확인
                    has_customer_info = any(keyword in next_text for keyword in [
                        '수령자', '받는분', '수신인', '고객', '주문자',
                        '상품명', '제품명', '품목', '수량', '개'
                    ])
                    
                    # 또는 현재 페이지에서 수령자 이름을 찾았고, 다음 페이지에 내용이 있으면 포함
                    if has_customer_info or (recipient_name and len(next_text.strip()) > 20):
                        end_page = page_num + 1
                        self.print_success.emit(f"✓ 2장 송장 감지: 다음 페이지({page_num + 2})도 함께 출력")
            
            # 2장 송장 시 페이지 크기 비교 - 크기가 많이 다르면 첫 페이지만 출력
            if end_page > start_page:
                first_page = doc[start_page]
                second_page = doc[end_page]
                first_rect = self._detect_content_rect(first_page)
                second_rect = self._detect_content_rect(second_page)
                
                # 두 번째 페이지가 첫 번째 페이지의 60% 미만이면 건너뛰기
                first_area = first_rect.width * first_rect.height
                second_area = second_rect.width * second_rect.height
                
                if second_area < first_area * 0.6:
                    self.print_success.emit(f"⚠️ 두 번째 페이지 크기가 첫 번째의 {second_area/first_area*100:.0f}%로 너무 작음 → 첫 페이지만 출력")
                    end_page = start_page
            
            # 추출할 페이지 범위 확정
            if start_page == end_page:
                self.print_success.emit(f"📄 단일 페이지 추출: {tracking_no} (페이지 {start_page + 1}만 인쇄)")
            else:
                self.print_success.emit(f"📄 2장 송장 추출: {tracking_no} (페이지 {start_page + 1}~{end_page + 1})")
            
            # 추출된 페이지 수 확인
            extracted_pages = end_page - start_page + 1
            self.print_success.emit(f"PDF 페이지 추출: {tracking_no} (페이지 {start_page + 1}부터 {end_page + 1}까지, 총 {extracted_pages}장)")
            
            optimized_doc = fitz.open()
            
            # 회전 설정 로드
            label_rotation = load_label_rotation()
            self.print_success.emit(f"회전 설정: {label_rotation}도")
            
            # 첫 페이지 크기 기준 (모든 페이지를 이 크기로 통일)
            first_page_for_size = doc[start_page]
            first_clip_rect = self._detect_content_rect(first_page_for_size)
            base_width = first_clip_rect.width
            base_height = first_clip_rect.height
            
            # 회전 설정에 따른 기준 크기 계산
            if label_rotation in [90, 270]:
                base_rotated_width = base_height
                base_rotated_height = base_width
            else:
                base_rotated_width = base_width
                base_rotated_height = base_height
            
            # PIL import (회전을 위해)
            from PIL import Image
            import io
            
            # 모든 페이지를 순회하며 추출
            for page_idx in range(start_page, end_page + 1):
                page = doc[page_idx]
                
                # 내용 영역 추출 (텍스트 블록 기준)
                clip_rect = self._detect_content_rect(page)
                if page_idx == start_page:
                    self.print_success.emit(f"클립 영역 (페이지 {page_idx + 1}): {clip_rect}")
                
                # 송장 영역 크기 (포인트 단위)
                clip_width = clip_rect.width
                clip_height = clip_rect.height
                
                self.print_success.emit(f"📐 송장 원본 크기: {clip_width:.1f}x{clip_height:.1f}pt")
                
                # ★ 용지 크기 로드 (settings.json)
                import json
                try:
                    settings_path = Path(__file__).parent / "settings.json"
                    with open(settings_path, 'r', encoding='utf-8') as f:
                        settings = json.load(f)
                    paper_size = settings.get("label_paper_size", {})
                    paper_width_mm = paper_size.get("width_mm", 110)
                    paper_height_mm = paper_size.get("height_mm", 168)
                except:
                    paper_width_mm = 110
                    paper_height_mm = 168
                
                # 고해상도 렌더링 (원본 영역만, 회전 없이)
                dpi = 300
                zoom = dpi / 72
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat, clip=clip_rect, alpha=False)
                
                # PIL Image로 변환 (원본, 회전 없음)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                
                # ★ 1단계: 용지 크기의 흰색 캔버스 생성 (회전 전 기준)
                # 회전 전 용지 크기 (픽셀)
                if label_rotation in [90, 270]:
                    # 90도/270도 회전 시 가로세로가 바뀌므로, 회전 전에는 반대로
                    canvas_width = int(paper_height_mm * dpi / 25.4)
                    canvas_height = int(paper_width_mm * dpi / 25.4)
                else:
                    canvas_width = int(paper_width_mm * dpi / 25.4)
                    canvas_height = int(paper_height_mm * dpi / 25.4)
                
                # 흰색 캔버스 생성
                canvas = Image.new('RGB', (canvas_width, canvas_height), (255, 255, 255))
                
                # ★ 2단계: 캔버스에 이미지 배치 (비율 유지, 위쪽 정렬)
                # 이미지를 캔버스 크기에 맞게 스케일링
                scale = min(canvas_width / img.width, canvas_height / img.height)
                new_img_width = int(img.width * scale)
                new_img_height = int(img.height * scale)
                
                img_resized = img.resize((new_img_width, new_img_height), Image.LANCZOS)
                
                # 이미지를 왼쪽 위에 배치 (여백은 오른쪽/아래쪽)
                x_pos = 0  # 왼쪽 정렬
                y_pos = 0  # 위쪽 정렬
                
                canvas.paste(img_resized, (x_pos, y_pos))
                
                empty_space_px = canvas_height - new_img_height
                empty_space_mm = empty_space_px / dpi * 25.4
                self.print_success.emit(f"[캔버스] {canvas_width}x{canvas_height}px, 이미지: {new_img_width}x{new_img_height}px, 여백: {empty_space_mm:.1f}mm")
                
                # ★ 3단계: 캔버스 전체를 회전 (이미지 + 여백 함께)
                if label_rotation == 90:
                    canvas_rotated = canvas.rotate(-90, expand=True)
                elif label_rotation == 180:
                    canvas_rotated = canvas.rotate(180, expand=True)
                elif label_rotation == 270:
                    canvas_rotated = canvas.rotate(-270, expand=True)
                else:
                    canvas_rotated = canvas
                
                self.print_success.emit(f"[회전] {label_rotation}도, 최종: {canvas_rotated.width}x{canvas_rotated.height}px")
                
                # ★ 4단계: 회전된 캔버스를 PDF로 저장
                # mm → pt 변환 (1mm = 2.8346pt)
                paper_width_pt = paper_width_mm * 2.8346
                paper_height_pt = paper_height_mm * 2.8346
                
                new_page = optimized_doc.new_page(width=paper_width_pt, height=paper_height_pt)
                
                # 회전된 캔버스를 PNG 바이트로 변환
                img_bytes = io.BytesIO()
                canvas_rotated.save(img_bytes, format='PNG')
                img_bytes.seek(0)
                
                # 용지 전체에 배치
                target_rect = fitz.Rect(0, 0, paper_width_pt, paper_height_pt)
                
                # 이미지 삽입
                new_page.insert_image(target_rect, stream=img_bytes.getvalue(), keep_proportion=True, overlay=True)
            
            temp_path = self._temp_dir / f"{clean_tracking_no}.pdf"
            if temp_path.exists():
                temp_path.unlink()
            optimized_doc.save(str(temp_path))
            
            optimized_doc.close()
            doc.close()
            
            pages_info = f"{extracted_pages}장" if extracted_pages > 1 else "1장"
            self.print_success.emit(f"✅ 라벨 PDF 생성 완료: {temp_path.name} ({pages_info}, 원본 방향 유지)")
            return temp_path
            
        except Exception as e:
            self.print_error.emit(f"페이지 추출 오류: {str(e)}")
            return None
    
    def _extract_page_to_temp_2(self, tracking_no: str, pdf_path: Path, page_num: int) -> Optional[Path]:
        """
        두 번째 PDF에서 송장번호에 해당하는 페이지를 임시 PDF로 추출 (주문서)
        extract_page_to_temp와 동일한 로직이지만 두 번째 PDF 인덱스 사용
        """
        self.print_success.emit(f"[주문서] 페이지 추출 시작: {tracking_no} → {pdf_path.name} 페이지 {page_num + 1}")
        
        try:
            clean_tracking_no = re.sub(r'[-–—\s]', '', tracking_no)
            
            doc = fitz.open(str(pdf_path))
            total_pages = len(doc)
            
            if page_num >= total_pages:
                doc.close()
                self.print_error.emit(f"[주문서] 페이지 번호 오류: {page_num + 1} (총 {total_pages}페이지)")
                return None
            
            # 시작/끝 페이지 결정 (2장 송장 처리)
            start_page = page_num
            end_page = page_num
            
            # 다음 페이지 확인 (2장 송장 처리)
            if page_num + 1 < total_pages:
                next_page = doc[page_num + 1]
                next_text = next_page.get_text() or ""
                
                # 다음 페이지에 다른 송장번호가 있는지 확인
                next_tracking_patterns = [
                    r'등기번호[:\s\-]*([0-9]{5}[-–—\s]{0,2}\d{4}[-–—\s]{0,2}\d{4})',
                    r'송장번호[:\s\-]*([0-9]{5}[-–—\s]{0,2}\d{4}[-–—\s]{0,2}\d{4})',
                    r'(\d{5}[-–—\s]+\d{4}[-–—\s]+\d{4})',
                    r'\b\d{13}\b',
                    r'\b\d{12}\b',
                    r'\b\d{11}\b',
                ]
                
                next_has_tracking = False
                for pattern in next_tracking_patterns:
                    matches = re.findall(pattern, next_text)
                    for match in matches:
                        clean_match = re.sub(r'[-–—\s]', '', match)
                        if clean_match.isdigit() and len(clean_match) >= 10:
                            if clean_match != clean_tracking_no:
                                next_has_tracking = True
                                break
                    if next_has_tracking:
                        break
                
                # 다음 페이지에 송장번호가 없고, 고객 정보나 제품 정보가 있으면 포함
                if not next_has_tracking:
                    has_customer_info = any(keyword in next_text for keyword in [
                        '수령자', '받는분', '수신인', '고객', '주문자',
                        '상품명', '제품명', '품목', '수량', '개'
                    ])
                    
                    if has_customer_info or len(next_text.strip()) > 20:
                        end_page = page_num + 1
                        self.print_success.emit(f"[주문서] ✓ 2장 송장 감지: 다음 페이지({page_num + 2})도 함께 출력")
            
            # 페이지 추출 (주문서는 크롭 없이 원본 전체 사용)
            optimized_doc = fitz.open()
            for page_idx in range(start_page, end_page + 1):
                page = doc[page_idx]
                original_rect = page.rect
                original_rotation = page.rotation
                
                # 주문서는 크롭 없이 전체 페이지 사용
                dpi = 300
                zoom = dpi / 72
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat, alpha=False)  # clip 파라미터 제거 (전체 페이지)
                
                if original_rotation in [90, 270]:
                    new_page = optimized_doc.new_page(width=original_rect.height, height=original_rect.width)
                else:
                    new_page = optimized_doc.new_page(width=original_rect.width, height=original_rect.height)
                
                target_rect = fitz.Rect(0, 0, new_page.rect.width, new_page.rect.height)
                new_page.insert_image(target_rect, pixmap=pix, rotate=0, keep_proportion=True, overlay=True)
            
            temp_path = self._temp_dir / f"order_{clean_tracking_no}.pdf"
            if temp_path.exists():
                temp_path.unlink()
            optimized_doc.save(str(temp_path))
            
            optimized_doc.close()
            doc.close()
            
            extracted_pages = end_page - start_page + 1
            pages_info = f"{extracted_pages}장" if extracted_pages > 1 else "1장"
            self.print_success.emit(f"[주문서] ✅ PDF 생성 완료: {temp_path.name} ({pages_info})")
            return temp_path
            
        except Exception as e:
            self.print_error.emit(f"[주문서] 페이지 추출 오류: {str(e)}")
            return None
    
    def get_pdf_path(self, tracking_no: str) -> Path:
        """tracking_no로 PDF 경로 반환"""
        if self._labels_dir:
            return self._labels_dir / f"{tracking_no}.pdf"
        return get_pdf_path(tracking_no)
    
    def print_pdf(self, tracking_no: str) -> bool:
        """
        PDF 자동 출력
        1. 인덱스에서 송장번호 찾기 → 해당 페이지만 추출하여 출력
        2. 없으면 {tracking_no}.pdf 파일 직접 출력
        3. 주문서 출력 활성화 시 두 번째 PDF도 동시 출력
        """
        if not self._enabled:
            self.print_error.emit("PDF 출력이 비활성화되어 있습니다")
            return False
        
        # 출력 전 상태 체크
        if not self._pdf_file and not self._labels_dir:
            self.print_error.emit("⚠️ PDF 파일이 설정되지 않았습니다. '데이터 업로드'에서 PDF 파일을 선택하세요.")
            return False
        
        if len(self._tracking_index) == 0:
            self.print_error.emit(f"⚠️ PDF 인덱스가 비어있습니다. PDF 파일을 다시 로드하거나 '📑 PDF 재스캔' 버튼을 클릭하세요.")
            return False
        
        # 프린터 설정 체크
        settings = load_printer_settings()
        label_printer = settings.get("label_printer")
        if not label_printer:
            self.print_error.emit("⚠️ 라벨 프린터가 설정되지 않았습니다. '설정' 탭에서 라벨 프린터를 선택하세요.")
            return False
        
        # 첫 번째 PDF 출력 (기존 로직)
        result1 = self._print_pdf_single(tracking_no, is_second=False)
        
        # 두 번째 PDF 출력 (주문서 출력 활성화 시)
        if self._order_sheet_enabled and self._pdf_file_2 and self._printer_name_2:
            import threading
            thread = threading.Thread(
                target=self._print_pdf_single,
                args=(tracking_no, True),
                daemon=True
            )
            thread.start()
            # 첫 번째 출력 결과 반환 (두 번째는 백그라운드에서 실행)
            return result1
        else:
            return result1
    
    def _print_pdf_single(self, tracking_no: str, is_second: bool = False) -> bool:
        """
        단일 PDF 출력 (내부 메서드)
        
        Args:
            tracking_no: 송장번호
            is_second: True면 두 번째 PDF 출력, False면 첫 번째 PDF 출력
        """
        # 하이픈 제거한 버전으로 정규화
        clean_tracking_no = re.sub(r'[-–—\s]', '', tracking_no)
        
        pdf_path = None
        
        # 1. 인덱스에서 송장번호 찾기 (원본 PDF 파일과 페이지 번호 확인)
        original_pdf_path = None
        page_num = None
        
        # 두 번째 PDF인지에 따라 인덱스 선택
        if is_second:
            tracking_index = self._tracking_index_2
            pdf_file = self._pdf_file_2
            printer_name = self._printer_name_2
            prefix = "[주문서] "
        else:
            tracking_index = self._tracking_index
            pdf_file = self._pdf_file
            printer_name = None  # 기본 프린터 사용
            prefix = "[라벨] "
        
        # 디버깅: 인덱스에 있는 송장번호 목록 확인
        indexed_tracking_nos = list(tracking_index.keys())[:10]  # 처음 10개만
        self.print_success.emit(f"{prefix}인덱스 확인: 검색 대상 {tracking_no} (정규화: {clean_tracking_no}), 인덱스에 {len(tracking_index)}개 송장번호 존재")
        if indexed_tracking_nos:
            self.print_success.emit(f"{prefix}인덱스 샘플: {', '.join(map(str, indexed_tracking_nos))}")
        
        # 디버깅: 전체 인덱스 매핑 상태 확인 (송장번호 → 페이지)
        mapping_info = []
        for key, (pdf_file_path, p_num) in tracking_index.items():
            if len(key) >= 10:  # 송장번호만 (너무 짧은 키 제외)
                mapping_info.append(f"{key}→페이지{p_num + 1}")
        
        if mapping_info:
            sample_mappings = mapping_info[:8]  # 처음 8개만
            self.print_success.emit(f"{prefix}송장→페이지 매핑: {', '.join(sample_mappings)}" + ("..." if len(mapping_info) > 8 else ""))
        
        search_keys = [clean_tracking_no, tracking_no]
        matched_key = None
        for key in search_keys:
            if key in tracking_index:
                original_pdf_path, page_num = tracking_index[key]
                matched_key = key
                self.print_success.emit(f"{prefix}✓ 송장번호 매칭 성공: '{tracking_no}' → 인덱스 키 '{matched_key}' (원본: {original_pdf_path.name}, 페이지: {page_num + 1})")
                break
        
        if not matched_key:
            if is_second:
                # 두 번째 PDF는 없어도 경고만 (첫 번째는 계속 진행)
                self.print_error.emit(f"{prefix}✗ 송장번호 매칭 실패: '{tracking_no}' (정규화: '{clean_tracking_no}')를 인덱스에서 찾을 수 없습니다")
                return False
            else:
                self.print_error.emit(f"{prefix}✗ 송장번호 매칭 실패: '{tracking_no}' (정규화: '{clean_tracking_no}')를 인덱스에서 찾을 수 없습니다")
        
        # 2. 해당 페이지를 임시 파일로 추출하여 실물 프린터로 인쇄
        if original_pdf_path and page_num is not None:
            # 두 번째 PDF인 경우 별도 추출 메서드 사용
            if is_second:
                pdf_path = self._extract_page_to_temp_2(matched_key, original_pdf_path, page_num)
            else:
                pdf_path = self.extract_page_to_temp(matched_key)
            if not pdf_path:
                self.print_error.emit(f"{prefix}페이지 추출 실패: {tracking_no} (매칭 키: {matched_key})")
                return False
        else:
            # 인덱스에 없으면 직접 파일 찾기 (하이픈 제거 버전으로 검색)
            if is_second:
                self.print_error.emit(f"{prefix}PDF 파일 없음: {clean_tracking_no}")
                return False
            pdf_path = self.get_pdf_path(clean_tracking_no)
            if not pdf_path.exists():
                # 원본 형식으로도 시도
                pdf_path = self.get_pdf_path(tracking_no)
                if not pdf_path.exists():
                    self.print_error.emit(f"{prefix}PDF 파일 없음: {clean_tracking_no}")
                    return False
        
        try:
            # 프린터 이름 결정 (printer_manager 설정 우선 사용)
            if is_second:
                # 주문서: settings.json의 a4_printer 또는 UI에서 선택한 프린터
                settings = load_printer_settings()
                target_printer_name = settings.get("a4_printer") or self._printer_name_2
            else:
                # 송장: settings.json의 label_printer 또는 UI에서 선택한 프린터
                settings = load_printer_settings()
                target_printer_name = settings.get("label_printer") or self._printer_name_1
            
            # printer_manager를 사용하여 출력
            pdf_path_str = str(pdf_path)
            success = print_pdf_with_printer(pdf_path_str, target_printer_name)
            
            if success:
                printer_display = target_printer_name if target_printer_name else "기본 프린터"
                output_type = "주문서" if is_second else "송장"
                self.print_success.emit(f"{prefix}PDF 출력 요청 완료: {tracking_no} → {printer_display}")
                
                # 출력 후 임시 파일 삭제 여부 확인 (송장/주문서 모두 동일하게 적용)
                # keep_temp_files 설정이 True이면 임시 파일 보관, False이면 삭제
                if not self._keep_temp_files and pdf_path and pdf_path.exists():
                    import time
                    time.sleep(2)  # 2초 대기 (인쇄 시작 시간 확보)
                    try:
                        pdf_path.unlink()
                        self.print_success.emit(f"{prefix}임시 파일 삭제: {pdf_path.name} ({output_type})")
                    except Exception as e:
                        self.print_success.emit(f"{prefix}임시 파일 삭제 실패 (무시): {str(e)} ({output_type})")
                elif self._keep_temp_files:
                    self.print_success.emit(f"{prefix}임시 파일 보관: {pdf_path.name} ({output_type})")
                
                return True
            else:
                self.print_error.emit(f"{prefix}PDF 출력 실패: {tracking_no}")
                return False
            
            # 기존 Adobe Reader 방식 (백업, 필요시 사용)
            # import subprocess
            # pdf_path_str = str(pdf_path)
            # 
            # # win32api, win32print는 선택적 (pywin32 설치 시에만 사용)
            # try:
            #     import win32api
            #     import win32print
            #     HAS_WIN32API = True
            # except ImportError:
            #     HAS_WIN32API = False
            # 
            # # 실물 프린터로 직접 인쇄 (기본 프린터 사용)
            # 
            # # 방법 1: Adobe Reader로 실물 프린터 인쇄 (가장 확실한 방법)
            # # /t 옵션: 기본 프린터로 인쇄 후 자동 종료 (사용자 클릭 불필요)
            # adobe_readers = [
            #     r"C:\Program Files\Adobe\Acrobat Reader DC\Reader\AcroRd32.exe",
            #     r"C:\Program Files (x86)\Adobe\Acrobat Reader DC\Reader\AcroRd32.exe",
            #     r"C:\Program Files\Adobe\Acrobat DC\Acrobat\Acrobat.exe",
            #     r"C:\Program Files (x86)\Adobe\Acrobat DC\Acrobat\Acrobat.exe",
            # ]
            # 
            # for reader_path in adobe_readers:
            #     if os.path.exists(reader_path):
            #         try:
            #             # Adobe Reader/Acrobat로 기본 프린터에 직접 인쇄
            #             # /t "파일" "프린터명": 지정된 프린터로 인쇄 후 종료
            #             # /p "파일": 기본 프린터로 인쇄 (인쇄 대화상자 없이)
            #             
            #             # 프린터 이름 결정 (선택된 프린터 우선 사용)
            #             if is_second:
            #                 target_printer_name = self._printer_name_2
            #             else:
            #                 target_printer_name = self._printer_name_1  # 첫 번째 프린터 (송장)
            #             
            #             if not target_printer_name and HAS_WIN32API:
            #                 try:
            #                     target_printer_name = win32print.GetDefaultPrinter()
            #                 except:
            #                     pass
            #             
            #             # 프린터 이름이 있으면 /t 옵션 사용, 없으면 /p 사용
            #             if target_printer_name:
            #                 # /t "파일" "프린터명" - 지정된 프린터로 인쇄 후 종료
            #                 cmd = [reader_path, "/t", pdf_path_str, target_printer_name]
            #                 self.print_success.emit(f"{prefix}인쇄 명령: {reader_path} /t → {target_printer_name}")
            #             else:
            #                 # /p "파일" - 기본 프린터로 인쇄
            #                 cmd = [reader_path, "/p", pdf_path_str]
            #                 self.print_success.emit(f"{prefix}인쇄 명령: {reader_path} /p")
            #             
            #             # 프린터로 인쇄 명령 전송
            #             subprocess.Popen(
            #                 cmd,
            #                 shell=False,
            #                 stdout=subprocess.DEVNULL,
            #                 stderr=subprocess.DEVNULL,
            #                 creationflags=subprocess.CREATE_NO_WINDOW
            #             )
            #             
            #             # 인쇄 명령 전송 완료
            #             result_returncode = 0  # Popen은 즉시 반환
            #             
            #             # 실행 결과 확인
            #             if result_returncode == 0:
            #                 self.print_success.emit(f"{prefix}Adobe Reader 인쇄 명령 전송 성공: {tracking_no}")
            #                 
            #                 # 출력 후 임시 파일 삭제 (기본값: 삭제)
            #                 if not self._keep_temp_files and pdf_path and pdf_path.exists():
            #                     # 인쇄 명령 전송 후 잠시 대기 후 삭제 (인쇄가 시작될 시간 확보)
            #                     import time
            #                     time.sleep(2)  # 2초 대기
            #                     try:
            #                         pdf_path.unlink()
            #                         self.print_success.emit(f"{prefix}임시 파일 삭제: {pdf_path.name}")
            #                     except Exception as e:
            #                         # 삭제 실패해도 인쇄는 정상 진행됨
            #                         self.print_success.emit(f"{prefix}임시 파일 삭제 실패 (무시): {str(e)}")
            #             else:
            #                 self.print_error.emit(f"{prefix}Adobe Reader 인쇄 실패")
        except Exception as e:
            self.print_error.emit(f"{prefix}PDF 출력 오류: {str(e)}")
            return False
    
    def check_pdf_exists(self, tracking_no: str) -> bool:
        """PDF 파일 존재 여부 확인"""
        pdf_path = self.get_pdf_path(tracking_no)
        return pdf_path.exists()


def get_available_printers() -> List[str]:
    """
    Windows 시스템에서 사용 가능한 프린터 목록 반환
    
    Returns:
        프린터 이름 리스트
    """
    printers = []
    try:
        import win32print
        printer_info = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)
        printers = [info[2] for info in printer_info]
    except ImportError:
        # pywin32가 없으면 빈 리스트 반환
        pass
    except Exception:
        pass
    
    return printers


def print_pdf_simple(tracking_no: str, labels_dir: str = "labels") -> bool:
    """
    간단한 PDF 출력 함수 (클래스 없이 사용)
    
    사용예:
        print_pdf_simple("6091486739755")
        print_pdf_simple("6091486739755", "C:/labels")
    """
    pdf_path = Path(labels_dir) / f"{tracking_no}.pdf"
    
    if not pdf_path.exists():
        print(f"[오류] PDF 파일 없음: {pdf_path}")
        return False
    
    try:
        os.startfile(str(pdf_path), "print")
        print(f"[성공] PDF 인쇄 요청: {tracking_no}.pdf")
        return True
    except Exception as e:
        print(f"[오류] PDF 인쇄 실패: {str(e)}")
        return False


def create_picking_list_pdf(df, output_path: str, sku_bin_map: dict = None) -> bool:
    """
    피킹리스트 PDF 생성
    
    Args:
        df: 주문 데이터 DataFrame
        output_path: 저장할 PDF 파일 경로
        sku_bin_map: SKU → BIN 매핑 딕셔너리
    
    Returns:
        성공 여부
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        
        # 한글 폰트 등록 (자동 탐색)
        from utils import find_korean_font
        try:
            font_path = find_korean_font()
            if font_path and os.path.exists(font_path):
                pdfmetrics.registerFont(TTFont('KoreanFont', font_path))
                font_name = 'KoreanFont'
                print(f"[피킹리스트] 한글 폰트 사용: {font_path}")
            else:
                font_name = 'Helvetica'
                print("[피킹리스트] 한글 폰트를 찾을 수 없어 영문 폰트 사용")
        except Exception as e:
            font_name = 'Helvetica'
            print(f"[피킹리스트] 폰트 로드 오류: {e}")
        
        # PDF 문서 생성
        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            rightMargin=15*mm,
            leftMargin=15*mm,
            topMargin=15*mm,
            bottomMargin=15*mm
        )
        
        elements = []
        
        # 스타일 설정
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'Title',
            parent=styles['Heading1'],
            fontName=font_name,
            fontSize=16,
            alignment=1,  # 중앙 정렬
            spaceAfter=10*mm
        )
        
        # 제목
        elements.append(Paragraph("제품별 피킹리스트", title_style))
        elements.append(Spacer(1, 5*mm))
        
        # SKU별 집계
        if df is None or df.empty:
            elements.append(Paragraph("데이터가 없습니다.", styles['Normal']))
        else:
            # BIN 정보 추가
            df_copy = df.copy()
            if sku_bin_map:
                df_copy['bin'] = df_copy['barcode'].map(lambda x: sku_bin_map.get(str(x), '-'))
            else:
                df_copy['bin'] = '-'
            
            # 로케이션 칼럼 존재 여부 확인
            has_location = 'location' in df_copy.columns
            
            # SKU별 집계 (로케이션 포함)
            agg_dict = {
                'qty': 'sum',
                'product_name': 'first'
            }
            if has_location:
                agg_dict['location'] = 'first'
            
            sku_summary = df_copy.groupby(['barcode', 'bin']).agg(agg_dict).reset_index()
            
            # BIN 순서로 정렬
            sku_summary = sku_summary.sort_values(['bin', 'barcode'])
            
            # 테이블 데이터 생성 (로케이션 포함 여부에 따라)
            if has_location:
                table_data = [['BIN', '로케이션', '바코드', '상품명', '수량']]
            else:
                table_data = [['BIN', '바코드', '상품명', '수량']]
            
            for _, row in sku_summary.iterrows():
                bin_val = str(row['bin']) if row['bin'] else '-'
                barcode = str(row['barcode'])
                # 상품명이 27자 초과하면 "..."으로 줄임
                raw_name = str(row['product_name']) if row['product_name'] else '-'
                product_name = raw_name[:27] + '...' if len(raw_name) > 27 else raw_name
                qty = int(row['qty'])
                
                if has_location:
                    location = str(row['location']) if pd.notna(row.get('location')) else '-'
                    table_data.append([bin_val, location, barcode, product_name, str(qty)])
                else:
                    table_data.append([bin_val, barcode, product_name, str(qty)])
            
            # 합계 행
            total_qty = int(sku_summary['qty'].sum())
            if has_location:
                table_data.append(['합계', '', '', f'{len(sku_summary)}종', str(total_qty)])
            else:
                table_data.append(['합계', '', f'{len(sku_summary)}종', str(total_qty)])
            
            # 테이블 생성 (로케이션 포함 여부에 따라 칼럼 너비 조정)
            if has_location:
                col_widths = [20*mm, 25*mm, 40*mm, 65*mm, 20*mm]
                product_name_col = 3  # 상품명 칼럼 인덱스
            else:
                col_widths = [25*mm, 45*mm, 80*mm, 25*mm]
                product_name_col = 2  # 상품명 칼럼 인덱스
            table = Table(table_data, colWidths=col_widths)
            
            # 테이블 스타일
            table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), font_name),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('ALIGN', (product_name_col, 1), (product_name_col, -1), 'LEFT'),  # 상품명은 왼쪽 정렬
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
                ('FONTSIZE', (0, -1), (-1, -1), 10),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            
            elements.append(table)
        
        # PDF 생성
        doc.build(elements)
        print(f"[피킹리스트] PDF 생성 완료: {output_path}")
        return True
        
    except ImportError as e:
        print(f"[피킹리스트] reportlab 패키지가 필요합니다: {e}")
        raise Exception(f"reportlab 패키지가 필요합니다: {e}")
    except Exception as e:
        import traceback
        print(f"[피킹리스트] PDF 생성 오류: {e}")
        traceback.print_exc()
        raise Exception(f"PDF 생성 오류: {e}")

