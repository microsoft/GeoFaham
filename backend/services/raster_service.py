# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Raster/COG tile service using TiTiler for converting GeoTIFF/COG files to XYZ tiles.
Supports both local files and remote COG URLs, and MosaicJSON for multi-image rendering.
"""

import os
from typing import Optional, Dict, Any, Tuple
from enum import Enum
import logging
from fastapi import FastAPI, Request
from fastapi.responses import Response
from titiler.core.factory import TilerFactory, ColorMapFactory
from titiler.mosaic.factory import MosaicTilerFactory
from titiler.core.errors import DEFAULT_STATUS_CODES, add_exception_handlers
from rio_tiler.io import Reader as RioReader
import rasterio
from cogeo_mosaic.errors import NoAssetFoundError
from cogeo_mosaic.backends import MosaicBackend
from io import BytesIO
from PIL import Image

# Import caching modules
try:
    from backend.services.cache import cached, setup_cache
    CACHE_AVAILABLE = True
except ImportError as e:
    CACHE_AVAILABLE = False
    print(f"Warning: Cache modules not available. Running without cache. ({e})")

# Import planetary computer for MPC URL signing
try:
    import planetary_computer
    MPC_AVAILABLE = True
except ImportError:
    MPC_AVAILABLE = False
    print("Warning: planetary_computer not available. MPC URLs will not be signed.")

logger = logging.getLogger(__name__)


# Custom reader function to sign Microsoft Planetary Computer URLs
def mpc_reader(url: str, **kwargs):
    """
    Custom reader that signs Microsoft Planetary Computer URLs before reading.
    
    This allows unsigned URLs in MosaicJSON files to work indefinitely,
    with signing happening at render time rather than at mosaic creation time.
    """
    if MPC_AVAILABLE and "blob.core.windows.net" in url:
        # Sign the URL using planetary_computer
        signed_url = planetary_computer.sign(url)
        return RioReader(signed_url, **kwargs)
    else:
        # For non-MPC URLs, use standard reader
        return RioReader(url, **kwargs)


# Create cached version of MosaicTilerFactory if cache is available
if CACHE_AVAILABLE:
    class CachedMosaicTilerFactory(MosaicTilerFactory):
        """MosaicTilerFactory with built-in caching for tile endpoints."""
        
        def register_routes(self):
            """Register routes with caching on tile endpoints."""
            super().register_routes()
            
            # Wrap tile routes with cache decorator
            for route in self.router.routes:
                if hasattr(route, 'path') and '/tiles/' in route.path and hasattr(route, 'endpoint'):
                    original_endpoint = route.endpoint
                    # Wrap with cached decorator
                    route.endpoint = cached(alias="default")(original_endpoint)
                    logger.debug(f"Added cache to route: {route.path}")


class ColorMap(str, Enum):
    """Available colormaps for raster visualization."""
    VIRIDIS = "viridis"
    PLASMA = "plasma"
    INFERNO = "inferno"
    MAGMA = "magma"
    CIVIDIS = "cividis"
    GREENS = "greens"
    BLUES = "blues"
    REDS = "reds"
    GREYS = "greys"
    RAINBOW = "rainbow"
    TERRAIN = "terrain"
    RDYLGN = "rdylgn"  # Red-Yellow-Green (good for damage/vegetation)
    SPECTRAL = "spectral"


def create_titiler_app() -> FastAPI:
    """
    Create a TiTiler FastAPI application for serving raster tiles.
    
    Returns:
        FastAPI application with TiTiler endpoints
    """
    app = FastAPI(
        title="QE Raster Tile Server",
        description="Tile server for GeoTIFF, COG files, and MosaicJSON",
        version="1.0.0"
    )
    
    # Setup cache on startup
    if CACHE_AVAILABLE:
        @app.on_event("startup")
        async def startup_cache():
            setup_cache()
            logger.info("Cache initialized for tile endpoints")
    
    # Add custom exception handler for NoAssetFoundError to return transparent tiles
    @app.exception_handler(NoAssetFoundError)
    async def handle_no_asset_found(request: Request, exc: NoAssetFoundError):
        """Return a transparent 256x256 PNG tile when no assets are found."""
        # Create a transparent 256x256 PNG
        img = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
        buf = BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        
        return Response(
            content=buf.getvalue(),
            media_type="image/png",
            status_code=200,
            headers={
                "Cache-Control": "public, max-age=3600",
                "X-Cache": "MISS-NO-ASSET"
            }
        )
    
    # Create TilerFactory which provides standard endpoints:
    # - /cog/tiles/{z}/{x}/{y} - Get tile
    # - /cog/info - Get raster info
    # - /cog/statistics - Get statistics
    # - /cog/preview - Get preview image
    # - /cog/point - Get point value
    cog = TilerFactory(router_prefix="/cog")
    app.include_router(cog.router, prefix="/cog", tags=["Cloud Optimized GeoTIFF"])
    colormap = ColorMapFactory(router_prefix="/colormap")
    app.include_router(colormap.router, prefix="/colormap", tags=["Colormaps"])
    # Create MosaicTilerFactory for MosaicJSON support:
    # - /mosaicjson/tiles/{z}/{x}/{y} - Get mosaic tile (with caching)
    # - /mosaicjson/info - Get mosaic info
    # - /mosaicjson/{z}/{x}/{y}/assets - Get assets for tile
    # - /mosaicjson/point - Get point value from mosaic
    if CACHE_AVAILABLE:
        mosaic = CachedMosaicTilerFactory(router_prefix="/mosaicjson", backend=MosaicBackend)
        logger.info("Using CachedMosaicTilerFactory with tile caching enabled")
    else:
        mosaic = MosaicTilerFactory(router_prefix="/mosaicjson", backend=MosaicBackend)
        logger.info("Using standard MosaicTilerFactory (no caching)")
    
    app.include_router(mosaic.router, prefix="/mosaicjson", tags=["MosaicJSON"])
    
    # Add exception handlers
    add_exception_handlers(app, DEFAULT_STATUS_CODES)
    
    logger.info("TiTiler app created with /cog and /mosaicjson endpoints")
    
    return app


class RasterService:
    """Service for managing raster files and metadata."""
    
    def __init__(self):
        pass
    
    def validate_raster(self, file_path: str) -> Tuple[bool, Optional[str]]:
        """
        Validate if a file is a valid raster.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            with rasterio.open(file_path) as src:
                # Check if it has at least one band
                if src.count < 1:
                    return False, "Raster has no bands"
                
                # Check if it has a CRS
                if src.crs is None:
                    return False, "Raster has no coordinate reference system (CRS)"
                
                return True, None
        except Exception as e:
            return False, str(e)
    
    def get_raster_info(self, url: str) -> Dict[str, Any]:
        """
        Get metadata about a raster file.
        
        Args:
            url: Path to local GeoTIFF or URL to COG
            
        Returns:
            Dictionary with raster metadata
        """
        try:
            if not url.startswith(('http://', 'https://')):
                url = os.path.abspath(url)
            
            with RioReader(url) as src:
                info = src.info()
                
                # Calculate zoom levels based on resolution
                # Web Mercator tile size is 256 pixels
                # Use the dataset's width/height to estimate appropriate zoom
                import math
                from morecantile import tms
                from rasterio.warp import transform_bounds
                from rasterio.crs import CRS
                
                # Get Web Mercator TMS
                web_mercator = tms.get("WebMercatorQuad")
                
                # Calculate minzoom and maxzoom based on bounds and resolution
                minzoom = src.minzoom
                maxzoom = src.maxzoom
                
                # Transform bounds to WGS84 (EPSG:4326) for Azure Maps
                bounds_wgs84 = list(info.bounds)
                if info.crs:
                    # Parse CRS from string if needed
                    src_crs = CRS.from_string(str(info.crs)) if isinstance(info.crs, str) else info.crs
                    
                    # Check if transformation is needed
                    if src_crs.to_epsg() != 4326:
                        # Transform from native CRS to WGS84
                        bounds_wgs84 = transform_bounds(
                            src_crs,
                            'EPSG:4326',
                            *info.bounds
                        )
            
            return {
                "bounds": list(bounds_wgs84),
                "minzoom": minzoom,
                "maxzoom": maxzoom,
                "band_count": len(info.band_descriptions),
                "band_descriptions": [desc[0] for desc in info.band_descriptions],
                "dtype": str(info.dtype),
                "nodata_value": str(info.nodata_type),
                "width": info.width,
                "height": info.height,
                "crs": str(info.crs) if info.crs else None,
                "driver": info.driver,
                "colorinterp": info.colorinterp if hasattr(info, 'colorinterp') else None
            }
        except Exception as e:
            logger.error(f"Error getting raster info: {str(e)}")
            raise


# Global instances
titiler_app = create_titiler_app()
raster_service = RasterService()
