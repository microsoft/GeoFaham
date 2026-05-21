# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Frontend configuration route - exposes per-deployment settings the browser
needs at boot time (e.g., the Azure Maps subscription key) without baking
them into the static frontend bundle.
"""
import logging
import os

from fastapi import APIRouter
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/config")
async def get_frontend_config():
    """
    Return runtime configuration values the frontend needs before
    initializing the Azure Maps SDK. Values are sourced from the
    server's environment so they can vary per deployment.
    """
    azure_maps_key = os.getenv("AZURE_MAPS_KEY", "")
    if not azure_maps_key:
        logger.warning(
            "AZURE_MAPS_KEY is not set; the frontend map will fail to "
            "initialize until it is configured in the server environment."
        )
    return JSONResponse(content={"azureMapsKey": azure_maps_key})
