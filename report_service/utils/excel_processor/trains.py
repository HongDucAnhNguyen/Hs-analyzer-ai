"""TRAINS utilities

Handles conversion between flow values for TRAINS lookup.
"""

import logging

logger = logging.getLogger(__name__)


def convert_flow_to_vietnamese(flow_value: str) -> str:
    """Convert flow value to Vietnamese display
    
    Args:
        flow_value: Flow value (Import/Export/Nhập/Xuất)
        
    Returns:
        Vietnamese flow value (Nhập/Xuất)
    """
    if not flow_value:
        return ""
    
    flow_lower = flow_value.lower()
    if flow_lower == "import" or flow_lower == "nhập":
        return "Nhập"
    elif flow_lower == "export" or flow_lower == "xuất":
        return "Xuất"
    return flow_value


def convert_flow_to_lookup_key(flow_value: str) -> str:
    """Convert flow value to English lookup key for train_links
    
    Args:
        flow_value: Flow value (Import/Export/Nhập/Xuất)
        
    Returns:
        English lookup key (import/export)
    """
    if not flow_value:
        return "import"
    
    flow_lower = flow_value.lower()
    if flow_lower == "nhập" or flow_lower == "import":
        return "import"
    elif flow_lower == "xuất" or flow_lower == "export":
        return "export"
    return "import"
