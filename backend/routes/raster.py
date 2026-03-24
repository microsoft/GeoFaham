# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Raster routes - upload, info, and test endpoints.
"""
import json
import logging
import os
import time
import uuid
import aiofiles
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse

from backend.routes.config import USER_DATA_PATH, USER_ARTIFACTS_JSON
from backend.services.raster_service import raster_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/test-raster")
async def test_raster_visualization():
    """
    Test endpoint to visualize the sample Saint Louis TIF file.
    Returns a raster message that can be rendered on the map.
    """
    try:
        # Hardcoded path to test TIF file
        file_path = "/path/to/test_data/sample_rgb.tif"
        
        # Get raster info
        info = raster_service.get_raster_info(file_path)
        
        # Create raster message
        raster_message = {
            "type": "raster",
            "data": {
                "url": file_path,
                "title": "Kenya May 1 Planetscope RGB",
                "bounds": info["bounds"],
                "minzoom": info["minzoom"],
                "maxzoom": info["maxzoom"]
            }
        }
        
        return JSONResponse(content=raster_message)
        
    except Exception as e:
        logger.error(f"Error in test raster endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/raster/info")
async def get_raster_info(url: str):
    """
    Get metadata about a raster file.
    
    Query params:
        url: Path to local GeoTIFF or URL to COG
    """
    try:
        info = raster_service.get_raster_info(url)
        return JSONResponse(content=info)
    except Exception as e:
        logger.error(f"Error getting raster info: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/upload-raster")
async def upload_raster(
    file: UploadFile = File(...),
    title: str = Form(...),
    description: str = Form(None),
    colormap: str = Form(None),
    rescale_min: float = Form(None),
    rescale_max: float = Form(None)
):
    """Upload a GeoTIFF/COG raster file."""
    try:
        # Validate file extension
        if not file.filename.lower().endswith(('.tif', '.tiff', '.geotiff')):
            raise HTTPException(status_code=400, detail="File must be a GeoTIFF (.tif, .tiff)")
        
        # Ensure user data directory exists
        os.makedirs(USER_DATA_PATH, exist_ok=True)
        
        # Generate unique filename
        file_id = uuid.uuid4().hex
        filename = f"{file_id}_{file.filename}"
        file_path = os.path.join(USER_DATA_PATH, filename)
        
        # Save file
        content = await file.read()
        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(content)
        
        # Validate raster
        is_valid, error_msg = raster_service.validate_raster(file_path)
        if not is_valid:
            os.remove(file_path)
            raise HTTPException(status_code=400, detail=f"Invalid raster file: {error_msg}")
        
        # Get raster info
        raster_info = raster_service.get_raster_info(file_path)
        
        # Register in user_artifacts.json
        artifact = {
            "id": file_id,
            "type": "raster",
            "title": title,
            "description": description or "",
            "filename": filename,
            "file_path": file_path,
            "bounds": raster_info["bounds"],
            "minzoom": raster_info["minzoom"],
            "maxzoom": raster_info["maxzoom"],
            "band_count": raster_info["band_count"],
            "colormap": colormap,
            "rescale_min": rescale_min,
            "rescale_max": rescale_max,
            "uploaded_at": time.time()
        }
        
        # Update user_artifacts.json
        artifacts = []
        if os.path.exists(USER_ARTIFACTS_JSON):
            async with aiofiles.open(USER_ARTIFACTS_JSON, 'r') as f:
                content = await f.read()
                artifacts = json.loads(content)
        
        artifacts.append(artifact)
        
        async with aiofiles.open(USER_ARTIFACTS_JSON, 'w') as f:
            await f.write(json.dumps(artifacts, indent=2))
        
        logger.info(f"Uploaded raster: {filename}")
        
        return JSONResponse(content={
            "success": True,
            "artifact": artifact,
            "message": f"Raster '{title}' uploaded successfully"
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading raster: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
