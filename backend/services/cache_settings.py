# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Cache settings for TiTiler
"""

from pydantic_settings import BaseSettings
from typing import Optional


class CacheSettings(BaseSettings):
    """Cache settings for Redis/Memory cache"""

    endpoint: Optional[str] = None
    ttl: int = 3600  # 1 hour default TTL
    namespace: str = "qe_tiles"

    model_config = {
        "env_file": ".env",
        "env_prefix": "CACHE_",
        "extra": "ignore"  # Ignore extra fields from .env
    }


cache_settings = CacheSettings()
