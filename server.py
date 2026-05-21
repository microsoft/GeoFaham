# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
GeoFaham Server - FastAPI application entry point.

This is a slim entry point that imports and mounts all route modules.
Route handlers are organized in the routes/ folder by domain.
"""
import logging
from pathlib import Path

# Load .env file before any other imports
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Initialize GeoFaham logging early to suppress noisy Azure loggers
from agents.core.logging import setup_logging
setup_logging()

from backend.crud.routes import router as crud_router
from backend.routes import (
    static_router,
    history_router,
    geojson_router,
    raster_router,
    benchmark_router,
    websocket_router,
    polling_router,
    frontend_config_router
)
from backend.services.raster_service import titiler_app

# Configure app-level logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="GeoFaham",
    description="Geospatial AI Agent Platform",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount TiTiler app for raster tile serving
app.mount("/tiles", titiler_app)

# Serve static files
app.mount("/frontend", StaticFiles(directory="./frontend"), name="frontend")

# Include routers BEFORE static file mounts
app.include_router(websocket_router)        # /ws/chat - must be before static mounts
app.include_router(static_router)           # /, /crud, colormaps, mosaic
app.include_router(history_router)          # /history
app.include_router(geojson_router)          # /api/upload-geojson, /api/user-artifacts
app.include_router(raster_router)           # /api/raster/*, /api/upload-raster
app.include_router(benchmark_router)        # /api/reset, /api/save-benchmark-gt
app.include_router(polling_router)           # /api/polling/* - HTTP fallback
app.include_router(frontend_config_router)   # /api/config - per-deployment frontend settings
app.include_router(crud_router, prefix="/api")  # /api/disasters, /api/building_damage, etc.


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8010)
