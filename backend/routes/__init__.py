# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Routes module - FastAPI route handlers organized by domain.
"""
from backend.routes.static import router as static_router
from backend.routes.history import router as history_router
from backend.routes.geojson import router as geojson_router
from backend.routes.raster import router as raster_router
from backend.routes.benchmark import router as benchmark_router
from backend.routes.websocket import router as websocket_router
from backend.routes.polling import router as polling_router

__all__ = [
    'static_router',
    'history_router', 
    'geojson_router',
    'raster_router',
    'benchmark_router',
    'websocket_router',
    'polling_router'
]
