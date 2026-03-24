# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Serialization Utilities

Convert various data types to JSON-serializable formats.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict


def serialize_value(value: Any) -> Any:
    """
    Convert PostgreSQL-specific and other types to JSON-serializable types.
    
    Args:
        value: Any value that might need serialization
    
    Returns:
        JSON-serializable value
    """
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode('utf-8', errors='ignore')
    return value


def serialize_properties(props: Dict[str, Any]) -> None:
    """
    Serialize property values in-place for JSON compatibility.
    
    Converts datetime objects and other non-serializable types.
    
    Args:
        props: Dictionary of properties to serialize (modified in-place)
    """
    for key, value in props.items():
        if isinstance(value, (datetime, date)):
            props[key] = value.isoformat()
        elif isinstance(value, Decimal):
            props[key] = float(value)
        elif isinstance(value, bytes):
            props[key] = value.decode('utf-8', errors='ignore')
