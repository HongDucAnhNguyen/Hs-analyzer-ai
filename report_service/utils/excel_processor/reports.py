"""Report generation functions

Generates HS Consistency, Value Variance, and NTM reports from parsed Excel data.
"""

import logging
from typing import Dict, List

import pandas as pd

from report_service.core.models import (
    ExcelRowData,
    FlowType,
    HSConsistencyItem,
    HSConsistencyReport,
    NTMItem,
    NTMReport,
    ValueVarianceItem,
    ValueVarianceReport,
    get_flow_from_ma_loai_hinh,
)

from .helpers import is_valid_npl_sp
from .tariff import get_duty_rate, get_tax_str, load_tariff_rates, parse_tax_value

logger = logging.getLogger(__name__)


def generate_hs_consistency_reports(rows: List[ExcelRowData]) -> HSConsistencyReport:
    """Generate HS Inconsistency report - optimized with vectorized pandas
    
    Args:
        rows: List of parsed Excel row data
        
    Returns:
        HSConsistencyReport with inconsistent NPL/SP items
    """
    tariff_rates = load_tariff_rates()
    
    if not rows:
        return HSConsistencyReport(items=[], total_items=0)
    
    # Build DataFrame directly from list comprehension (faster than append)
    data = [
        {
            'row_idx': idx,
            'flow': row.flow or get_flow_from_ma_loai_hinh(row.ma_loai_hinh).value,
            'ma_loai_hinh': row.ma_loai_hinh or '',
            'ma_npl_sp': row.ma_npl_sp or '',
            'ma_hs': row.ma_hs or '',
            'ten_hang': row.ten_hang or '',
            'tong_tri_gia': row.tong_tri_gia or 0.0,
        }
        for idx, row in enumerate(rows)
    ]
    
    df = pd.DataFrame(data)
    
    # Vectorized: find inconsistent NPL/SP
    hs_count = df.groupby('ma_npl_sp')['ma_hs'].nunique()
    inconsistent_npl = set(hs_count[hs_count >= 2].index)
    
    # Filter using vectorized isin
    mask = df['ma_npl_sp'].isin(inconsistent_npl)
    filtered_df = df.loc[mask].copy()
    
    if filtered_df.empty:
        return HSConsistencyReport(items=[], total_items=0)
    
    # Vectorized tax lookup
    filtered_df['tax'] = filtered_df['ma_hs'].apply(get_tax_str)
    
    # Vectorized tax parsing
    def get_tax_numeric(tax_str) -> float:
        if pd.isna(tax_str) or not tax_str:
            return None
        numeric_val, _ = parse_tax_value(str(tax_str))
        return numeric_val
    
    def is_tax_text(tax_str) -> bool:
        if pd.isna(tax_str) or not tax_str:
            return False
        _, is_text = parse_tax_value(str(tax_str))
        return is_text
    
    filtered_df['tax_numeric'] = filtered_df['tax'].apply(get_tax_numeric)
    filtered_df['tax_is_text'] = filtered_df['tax'].apply(is_tax_text)
    
    # Vectorized max tax per group
    max_tax_map = filtered_df.groupby('ma_npl_sp')['tax_numeric'].transform('max')
    filtered_df['max_tax'] = max_tax_map
    
    # Vectorized impact calculation
    def calc_impact_vectorized(row):
        if row['tax_is_text']:
            return row['tong_tri_gia']
        if pd.isna(row['tax_numeric']) or pd.isna(row['max_tax']):
            return 0.0
        tax_diff = row['max_tax'] - row['tax_numeric']
        return row['tong_tri_gia'] * tax_diff / 100 if tax_diff > 0 else 0.0
    
    filtered_df['impact_amount'] = filtered_df.apply(calc_impact_vectorized, axis=1)
    
    # ============================================================================
    # MERGE ROWS: Group by (ma_npl_sp, ma_hs, ten_hang), sum total values
    # ============================================================================
    
    agg_dict = {
        'row_idx': 'first',
        'flow': 'first',
        'ma_loai_hinh': 'first',
        'tong_tri_gia': 'sum',
        'tax': 'first',
        'tax_numeric': 'first',
        'tax_is_text': 'first',
        'max_tax': 'first',
        'impact_amount': 'sum',
    }
    
    filtered_df = filtered_df.groupby(
        ['ma_npl_sp', 'ma_hs', 'ten_hang'], 
        as_index=False,
        sort=False
    ).agg(agg_dict)
    
    logger.info(f"After merge: {len(filtered_df)} rows (merged by HS code & Tên hàng)")
    
    # Top 10 selection (exclude G type, empty NPL/SP, and special-chars-only NPL/SP)
    eligible_mask = (
        ~filtered_df['ma_loai_hinh'].str.startswith('G', na=False) & 
        filtered_df['ma_npl_sp'].apply(is_valid_npl_sp)
    )
    
    eligible_df = filtered_df.loc[eligible_mask, ['ma_npl_sp', 'impact_amount']].drop_duplicates('ma_npl_sp')
    eligible_df = eligible_df.groupby('ma_npl_sp')['impact_amount'].sum()
    eligible_df = eligible_df[eligible_df > 0].nlargest(10)
    
    top_10 = set(eligible_df.index)
    ip_ranking = {npl: f"IP{i+1}" for i, npl in enumerate(eligible_df.index)}
    
    # Sort and convert to items
    filtered_df.sort_values(['ma_npl_sp', 'ma_hs', 'row_idx'], inplace=True)
    
    items = []
    for row in filtered_df.itertuples(index=False):
        ma_npl_sp = row.ma_npl_sp
        is_g_type = row.ma_loai_hinh.startswith('G') if row.ma_loai_hinh else False
        is_valid = is_valid_npl_sp(ma_npl_sp)
        is_top_10 = ma_npl_sp in top_10 and not is_g_type and is_valid
        
        items.append(HSConsistencyItem(
            flow=row.flow,
            ma_loai_hinh=row.ma_loai_hinh or None,
            ma_npl_sp=ma_npl_sp or None,
            ma_hs=row.ma_hs or None,
            ten_hang=row.ten_hang or None,
            total=float(row.tong_tri_gia),
            tax=row.tax if pd.notna(row.tax) else None,
            impact_amount=row.impact_amount,
            to_pic="x" if is_top_10 else None,
            impact_refer=ip_ranking.get(ma_npl_sp) if is_top_10 else None,
        ))
    
    return HSConsistencyReport(items=items, total_items=len(items))


def generate_hs_consistency_report(rows: List[ExcelRowData]) -> HSConsistencyReport:
    """Backward compatibility wrapper"""
    return generate_hs_consistency_reports(rows)


def generate_value_variance_report(rows: List[ExcelRowData]) -> ValueVarianceReport:
    """Generate Value Variance report - optimized with new columns
    
    Args:
        rows: List of parsed Excel row data
        
    Returns:
        ValueVarianceReport with price variance analysis
    """
    tariff_rates = load_tariff_rates()
    
    if not rows:
        return ValueVarianceReport(items=[], total_items=0)
    
    # Collect data including ma_hs and tong_so_luong for new calculations
    data = [
        {
            'flow': row.flow or get_flow_from_ma_loai_hinh(row.ma_loai_hinh).value,
            'dieu_kien_gia_hoa_don': row.dieu_kien_gia_hoa_don or '',
            'ma_npl_sp': row.ma_npl_sp or '',
            'ten_doi_tac': row.ten_doi_tac or '',
            'ma_hs': row.ma_hs or '',
            'don_gia_tinh_thue': row.don_gia_tinh_thue,
            'tong_so_luong': row.tong_so_luong or 0.0,
        }
        for row in rows
        if row.don_gia_tinh_thue is not None
    ]
    
    if not data:
        return ValueVarianceReport(items=[], total_items=0)
    
    df = pd.DataFrame(data)
    
    # Get duty rate for each HS code
    df['duty_rate'] = df['ma_hs'].apply(get_duty_rate)
    
    # Group by flow, dieu_kien_gia_hoa_don, ma_npl_sp, ten_doi_tac (4 columns)
    # Each unique combination gets its own row
    group_cols = ['ma_npl_sp', 'ten_doi_tac', 'flow', 'dieu_kien_gia_hoa_don']
    
    # Custom aggregation function
    def aggregate_group(group_df):
        min_price = group_df['don_gia_tinh_thue'].min()
        max_price = group_df['don_gia_tinh_thue'].max()
        # Sum and count for true average calculation
        sum_price = group_df['don_gia_tinh_thue'].sum()
        count_price = len(group_df)
        
        # Sum of ALL tong_so_luong values in the group
        sum_tong_so_luong = group_df['tong_so_luong'].sum()
        
        # Find row with min price to get its tong_so_luong (for Impact calculation)
        min_price_rows = group_df[group_df['don_gia_tinh_thue'] == min_price]
        tong_so_luong_min = min_price_rows['tong_so_luong'].sum()
        
        # Find HS code with maximum duty rate
        valid_duty = group_df[group_df['duty_rate'].notna()]
        if not valid_duty.empty:
            max_duty_idx = valid_duty['duty_rate'].idxmax()
            hs_code_max_duty = valid_duty.loc[max_duty_idx, 'ma_hs']
            import_duty_rate_max = valid_duty.loc[max_duty_idx, 'duty_rate']
        else:
            hs_codes_in_group = group_df[group_df['ma_hs'].notna() & (group_df['ma_hs'] != '')]
            if not hs_codes_in_group.empty:
                hs_code_max_duty = hs_codes_in_group['ma_hs'].iloc[0]
            else:
                hs_code_max_duty = None
            import_duty_rate_max = None
        
        # Calculate impact: (max - min) × duty_rate × quantity
        impact_amount = 0.0
        if import_duty_rate_max is not None and import_duty_rate_max > 0:
            price_diff = max_price - min_price
            if price_diff > 0 and tong_so_luong_min > 0:
                impact_amount = price_diff * (import_duty_rate_max / 100) * tong_so_luong_min
        
        return pd.Series({
            'min_don_gia_tinh_thue': min_price,
            'max_don_gia_tinh_thue': max_price,
            'sum_don_gia_tinh_thue': sum_price,
            'count_don_gia_tinh_thue': count_price,
            'hs_code_max_duty': hs_code_max_duty,
            'import_duty_rate_max': import_duty_rate_max,
            'tong_so_luong_min': tong_so_luong_min,
            'sum_tong_so_luong': sum_tong_so_luong,
            'impact_amount': impact_amount,
        })
    
    grouped = df.groupby(group_cols, as_index=False).apply(aggregate_group, include_groups=False)
    grouped = grouped.reset_index(drop=True)
    
    # Flatten the result if nested
    if isinstance(grouped.columns, pd.MultiIndex):
        grouped.columns = ['_'.join(col).strip('_') for col in grouped.columns]
    
    # Sort by impact_amount descending to select top 10
    grouped_sorted = grouped.sort_values('impact_amount', ascending=False)
    
    # Select top 10 with positive impact (exclude empty/invalid NPL/SP)
    eligible_mask = (
        grouped_sorted['ma_npl_sp'].apply(is_valid_npl_sp) &
        (grouped_sorted['impact_amount'] > 0)
    )
    eligible_df = grouped_sorted.loc[eligible_mask].copy()
    
    # Create compound key for each eligible row (4 columns)
    eligible_df['compound_key'] = (
        eligible_df['flow'].fillna('') + '|' + 
        eligible_df['dieu_kien_gia_hoa_don'].fillna('') + '|' + 
        eligible_df['ma_npl_sp'].fillna('') + '|' +
        eligible_df['ten_doi_tac'].fillna('')
    )
    
    top_10_keys = set(eligible_df.head(10)['compound_key'].tolist())
    ip_ranking = {}
    for i, key in enumerate(eligible_df.head(10)['compound_key'].tolist()):
        ip_ranking[key] = f"IP{i+1}"
    
    # Sort by original order for output (4 columns)
    grouped.sort_values(['flow', 'dieu_kien_gia_hoa_don', 'ma_npl_sp', 'ten_doi_tac'], inplace=True)
    
    items = []
    for row in grouped.itertuples(index=False):
        flow = row.flow if hasattr(row, 'flow') else ''
        dieu_kien = row.dieu_kien_gia_hoa_don if hasattr(row, 'dieu_kien_gia_hoa_don') else ''
        ma_npl_sp = row.ma_npl_sp if hasattr(row, 'ma_npl_sp') else ''
        ten_doi_tac = row.ten_doi_tac if hasattr(row, 'ten_doi_tac') else ''
        impact = row.impact_amount if hasattr(row, 'impact_amount') else 0
        
        compound_key = f"{flow or ''}|{dieu_kien or ''}|{ma_npl_sp or ''}|{ten_doi_tac or ''}"
        is_top_10 = compound_key in top_10_keys and pd.notna(impact) and impact > 0
        
        items.append(ValueVarianceItem(
            flow=flow,
            dieu_kien_gia_hoa_don=dieu_kien or None,
            ma_npl_sp=ma_npl_sp or None,
            ten_doi_tac=ten_doi_tac or None,
            hs_code_max_duty=row.hs_code_max_duty if pd.notna(row.hs_code_max_duty) else None,
            import_duty_rate_max=float(row.import_duty_rate_max) if pd.notna(row.import_duty_rate_max) else None,
            tong_so_luong_min=float(row.tong_so_luong_min) if pd.notna(row.tong_so_luong_min) else None,
            sum_tong_so_luong=float(row.sum_tong_so_luong) if pd.notna(row.sum_tong_so_luong) else None,
            min_don_gia_tinh_thue=float(row.min_don_gia_tinh_thue) if pd.notna(row.min_don_gia_tinh_thue) else None,
            max_don_gia_tinh_thue=float(row.max_don_gia_tinh_thue) if pd.notna(row.max_don_gia_tinh_thue) else None,
            sum_don_gia_tinh_thue=float(row.sum_don_gia_tinh_thue) if pd.notna(row.sum_don_gia_tinh_thue) else None,
            count_don_gia_tinh_thue=int(row.count_don_gia_tinh_thue) if pd.notna(row.count_don_gia_tinh_thue) else None,
            impact_amount=float(impact) if pd.notna(impact) and impact > 0 else None,
            to_pic="x" if is_top_10 else None,
            impact_refer=ip_ranking.get(compound_key) if is_top_10 else None,
        ))
    
    return ValueVarianceReport(items=items, total_items=len(items))


def generate_ntm_report(rows: List[ExcelRowData], train_links: Dict[str, str] = None) -> NTMReport:
    """Generate NTM report - optimized
    
    Args:
        rows: List of parsed Excel row data
        train_links: Optional dictionary mapping HS codes to TRAINS links
        
    Returns:
        NTMReport with non-tariff measures data
    """
    train_links = train_links or {}
    
    if not rows:
        return NTMReport(items=[], total_items=0)
    
    data = []
    for row in rows:
        flow = row.flow or get_flow_from_ma_loai_hinh(row.ma_loai_hinh).value
        is_import = flow == FlowType.NHAP.value
        # Display value in Vietnamese
        flow_display = "Nhập" if is_import else "Xuất"
        # Lookup key for train_links (English, lowercase)
        flow_lookup = "import" if is_import else "export"
        
        hs_code = row.ma_hs or ''
        hs_code_6 = hs_code[:6] if hs_code else ''
        
        if hs_code_6:
            data.append({
                'flow_display': flow_display,
                'flow_lookup': flow_lookup,
                'hs_code_6': hs_code_6,
                'ma_npl_sp': row.ma_npl_sp or '',
                'ten_hang': row.ten_hang or '',
            })
    
    if not data:
        return NTMReport(items=[], total_items=0)
    
    df = pd.DataFrame(data)
    
    # Group by flow, hs_code_6, ma_npl_sp, and ten_hang to preserve all unique products
    # Previously only grouped by flow and hs_code_6, which lost products with same HS code
    grouped = df.groupby(['flow_display', 'flow_lookup', 'hs_code_6', 'ma_npl_sp', 'ten_hang'], as_index=False).first()
    grouped.sort_values(['flow_display', 'hs_code_6', 'ma_npl_sp'], inplace=True)
    
    items = [
        NTMItem(
            qd_1357=row.flow_display,  # Vietnamese: "Nhập" or "Xuất"
            hs_code=row.hs_code_6,
            ma_npl_sp=row.ma_npl_sp or None,
            ten_hang=row.ten_hang or None,
            train_link=train_links.get(f"{row.hs_code_6}:{row.flow_lookup}", ""),
        )
        for row in grouped.itertuples(index=False)
    ]
    
    return NTMReport(items=items, total_items=len(items))

