# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Backend module - contains all server-side logic.
"""
from backend.routes import (
    static_router,
    history_router,
    geojson_router,
    raster_router,
    benchmark_router,
    websocket_router
)
from backend.crud.routes import router as crud_router

__all__ = [
    'static_router',
    'history_router',
    'geojson_router', 
    'raster_router',
    'benchmark_router',
    'websocket_router',
    'crud_router'
]
