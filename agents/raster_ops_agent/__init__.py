# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
RasterOps Agent - Handles raster data processing and analysis.

Supports:
- PostGIS raster queries (stored disaster data)
- External COG processing (STAC, MPC, user uploads)
- Raster-vector overlay operations
- Raster algebra and classification
"""

from agents.raster_ops_agent.assistant import create_raster_ops_agent

__all__ = ["create_raster_ops_agent"]
