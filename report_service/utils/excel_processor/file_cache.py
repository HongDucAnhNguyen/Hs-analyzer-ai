"""Excel file caching utilities

Memory-efficient caching for Excel file data to avoid multiple reads.
Supports both xlsx and xlsb formats.
"""

import gc
import logging
from dataclasses import dataclass, field
from io import BytesIO
from typing import Optional

import pandas as pd
from openpyxl import load_workbook

logger = logging.getLogger(__name__)


@dataclass
class ExcelFileCache:
    """Cache Excel file data to avoid multiple reads
    
    Reads the file ONCE and caches:
    - DataFrame (main data)
    - Sheet name
    - Header row index
    - Raw bytes for output generation
    """
    file_content: bytes
    _df: Optional[pd.DataFrame] = field(default=None, repr=False)
    _sheet_name: Optional[str] = None
    _header_row: Optional[int] = None
    _max_row: Optional[int] = None
    _max_col: Optional[int] = None
    _is_xlsb: bool = False
    _loaded: bool = False
    
    def __post_init__(self):
        """Detect file type on initialization"""
        self._is_xlsb = self._detect_xlsb()
    
    def _detect_xlsb(self) -> bool:
        """Detect if file is xlsb format"""
        try:
            from pyxlsb import open_workbook as open_xlsb
            with open_xlsb(BytesIO(self.file_content)) as wb:
                return len(wb.sheets) > 0
        except Exception:
            return False
    
    def _find_header_row_fast(self, max_scan: int = 20) -> int:
        """Find header row efficiently using streaming read"""
        header_keywords = {"STT", "Số TK", "Mã loại hình", "Mã HS", "Tên hàng"}
        
        try:
            if self._is_xlsb:
                from pyxlsb import open_workbook as open_xlsb
                with open_xlsb(BytesIO(self.file_content)) as wb:
                    with wb.get_sheet(wb.sheets[0]) as sheet:
                        row_idx = 0
                        for row in sheet.rows():
                            if row_idx >= max_scan:
                                break
                            row_values = [str(cell.v).strip() if cell.v else "" for cell in row]
                            row_str = ' '.join(row_values)
                            
                            # Check first cell for STT
                            if row_values and row_values[0] == "STT":
                                return row_idx
                            
                            # Count keyword matches
                            matches = sum(1 for kw in header_keywords if kw in row_str)
                            if matches >= 3:
                                return row_idx
                            row_idx += 1
            else:
                # Use read_only mode for xlsx - much faster
                wb = load_workbook(BytesIO(self.file_content), read_only=True, data_only=True)
                ws = wb.active
                
                for row_idx, row in enumerate(ws.iter_rows(max_row=max_scan, values_only=True)):
                    row_values = [str(v).strip() if v else "" for v in row]
                    row_str = ' '.join(row_values)
                    
                    if row_values and row_values[0] == "STT":
                        wb.close()
                        return row_idx
                    
                    matches = sum(1 for kw in header_keywords if kw in row_str)
                    if matches >= 3:
                        wb.close()
                        return row_idx
                
                wb.close()
        except Exception as e:
            logger.warning(f"Error finding header row: {e}")
        
        return 0
    
    def load(self, force: bool = False) -> None:
        """Load file data into cache (lazy loading)"""
        if self._loaded and not force:
            return
        
        self._header_row = self._find_header_row_fast()
        logger.info(f"Detected header row: {self._header_row}")
        
        # Get sheet name efficiently
        try:
            if self._is_xlsb:
                from pyxlsb import open_workbook as open_xlsb
                with open_xlsb(BytesIO(self.file_content)) as wb:
                    self._sheet_name = wb.sheets[0] if wb.sheets else "Sheet1"
            else:
                wb = load_workbook(BytesIO(self.file_content), read_only=True)
                self._sheet_name = wb.active.title
                wb.close()
        except Exception:
            self._sheet_name = "Input Data"
        
        # Load DataFrame with optimizations
        self._load_dataframe()
        self._loaded = True
    
    def _load_dataframe(self) -> None:
        """Load DataFrame with memory optimizations"""
        engine = 'pyxlsb' if self._is_xlsb else 'openpyxl'
        
        try:
            # Try calamine engine first (much faster for xlsx)
            if not self._is_xlsb:
                try:
                    self._df = pd.read_excel(
                        BytesIO(self.file_content),
                        engine='calamine',
                        header=self._header_row,
                        sheet_name=0
                    )
                    logger.info("Loaded with calamine engine (fastest)")
                    return
                except Exception:
                    pass  # Fall back to openpyxl
            
            # Standard loading with specified engine
            self._df = pd.read_excel(
                BytesIO(self.file_content),
                engine=engine,
                header=self._header_row,
                sheet_name=0
            )
            
            # Optimize dtypes to reduce memory
            self._optimize_dtypes()
            
            logger.info(f"Loaded DataFrame: {len(self._df)} rows, {len(self._df.columns)} cols")
            
        except Exception as e:
            logger.error(f"Failed to load DataFrame: {e}")
            self._df = pd.DataFrame()
    
    def _optimize_dtypes(self) -> None:
        """Optimize DataFrame dtypes to reduce memory usage"""
        if self._df is None or self._df.empty:
            return
        
        for col in self._df.columns:
            col_type = self._df[col].dtype
            
            # Convert object columns with low cardinality to category
            if col_type == 'object':
                nunique = self._df[col].nunique()
                if nunique / len(self._df) < 0.5:  # Less than 50% unique
                    self._df[col] = self._df[col].astype('category')
            
            # Downcast numeric types
            elif col_type in ['int64', 'int32']:
                self._df[col] = pd.to_numeric(self._df[col], downcast='integer')
            elif col_type in ['float64', 'float32']:
                self._df[col] = pd.to_numeric(self._df[col], downcast='float')
    
    @property
    def df(self) -> pd.DataFrame:
        """Get cached DataFrame"""
        if not self._loaded:
            self.load()
        return self._df
    
    @property
    def sheet_name(self) -> str:
        """Get cached sheet name"""
        if not self._loaded:
            self.load()
        return self._sheet_name or "Input Data"
    
    @property
    def header_row(self) -> int:
        """Get cached header row index"""
        if not self._loaded:
            self.load()
        return self._header_row or 0
    
    @property
    def is_xlsb(self) -> bool:
        """Check if file is xlsb format"""
        return self._is_xlsb
    
    def clear(self) -> None:
        """Clear cache to free memory"""
        self._df = None
        self._loaded = False
        gc.collect()

