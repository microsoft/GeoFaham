# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Static file routes - serving HTML pages, colormaps, and mosaic JSON files.
"""
import json
import logging
import os
import aiofiles
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from backend.crud.templates import crud_page

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/")
async def root():
    """Serve the chat interface HTML file."""
    return FileResponse("frontend/index.html")


@router.get("/crud")
async def crud_index():
    """Serve the CRUD admin page."""
    return crud_page()


@router.get("/titiler_colormaps.json")
async def serve_colormaps():
    """Serve the TiTiler colormaps list for frontend colormap picker."""
    try:
        async with aiofiles.open("titiler_colormaps.json", 'r') as f:
            colormaps = json.loads(await f.read())
        return JSONResponse(content=colormaps)
    except Exception as e:
        logger.error(f"Error serving colormaps: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error reading colormaps file: {str(e)}")


@router.get("/api/mosaic/{filename}")
async def serve_mosaic_json(filename: str):
    """
    Serve MosaicJSON files for TiTiler mosaic endpoint.
    Files are stored in dump/query_jsons/ directory or /tmp/stac_exports/ for test files.
    """
    # Try dump/query_jsons first
    mosaic_path = os.path.join("dump", "query_jsons", filename)
    
    # If not found, try /tmp/stac_exports (for test files)
    if not os.path.exists(mosaic_path):
        mosaic_path = os.path.join("/tmp", "stac_exports", filename)
    
    if not os.path.exists(mosaic_path):
        raise HTTPException(status_code=404, detail=f"Mosaic file not found: {filename}")
    
    if not filename.endswith('.json'):
        raise HTTPException(status_code=400, detail="Invalid file type, must be .json")
    
    try:
        async with aiofiles.open(mosaic_path, 'r') as f:
            mosaic_data = json.loads(await f.read())
        return JSONResponse(content=mosaic_data)
    except Exception as e:
        logger.error(f"Error serving mosaic JSON {filename}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error reading mosaic file: {str(e)}")
