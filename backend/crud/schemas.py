# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, field_validator

class BuildingDamageIn(BaseModel):
    damaged: Optional[bool] = None
    damage_pct: Optional[float] = None
    disaster_id: Optional[int] = None
    geojson: Optional[dict] = None

    @field_validator('disaster_id', mode='before')
    @classmethod
    def empty_disaster_to_none(cls, v):
        if v == '' or v is None:
            return None
        return v

    @field_validator('damage_pct', mode='before')
    @classmethod
    def empty_damage_pct_to_none(cls, v):
        if v == '' or v is None:
            return None
        return v

class DisasterIn(BaseModel):
    disaster_type: str
    disaster_date: Optional[str] = None  # ISO date string
    description: Optional[str] = None
    area: Optional[str] = None
    city: Optional[str] = None
    county: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None

    @field_validator('disaster_date', mode='before')
    @classmethod
    def empty_disaster_date_to_none(cls, v):
        if v == '' or v is None:
            return None
        return v

class FloodMapIn(BaseModel):
    disaster_id: Optional[int] = None
    source: Optional[str] = None
    metadata: Optional[dict] = None
    geojson: Optional[dict] = None

    @field_validator('disaster_id', mode='before')
    @classmethod
    def empty_disaster_to_none(cls, v):
        if v == '' or v is None:
            return None
        return v

class Pagination(BaseModel):
    total: int
    items: List[Dict[str, Any]]
    page: int
    page_size: int
