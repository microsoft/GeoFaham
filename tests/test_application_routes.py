# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Application routes retained when integrating agent workflows."""

import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import numpy as np
import rasterio
from rasterio.transform import from_origin

from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.routes import reset
from backend.services import raster_service
from backend.services.origin_policy import OriginCheckMiddleware
import server


class ApplicationRouteTests(unittest.TestCase):
    def test_frontend_configuration_keeps_the_deployment_maps_key(self):
        with patch.dict("os.environ", {"AZURE_MAPS_KEY": "test-maps-key"}), \
                patch.object(server, "check_startup", new_callable=AsyncMock):
            with TestClient(server.app) as client:
                response = client.get("/api/config")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {"azureMapsKey": "test-maps-key"})
                self.assertEqual(client.get("/").status_code, 200)
                self.assertEqual(client.get("/frontend/js/app.js").status_code, 200)

    def test_server_mounts_reset_without_the_old_debug_routes(self):
        self.assertEqual(server.app.url_path_for("reset_application"), "/api/reset")
        paths = server.app.openapi()["paths"]
        self.assertIn("post", paths["/api/reset"])
        self.assertNotIn("/api/save-benchmark-gt", paths)
        self.assertNotIn("/api/test-raster", paths)

    def test_cross_site_browser_requests_are_rejected_before_reaching_handlers(self):
        client = TestClient(server.app)  # no lifespan: the guard must reject before any app startup work
        with patch.object(reset, "stop_chat_tasks") as stop:
            response = client.post("/api/reset", headers={"Origin": "https://evil.example"})
            self.assertEqual(response.status_code, 403)
            with self.assertRaises(WebSocketDisconnect) as closed:
                with client.websocket_connect("/ws/chat", headers={"Origin": "https://evil.example"}):
                    pass
            self.assertEqual(closed.exception.code, 1008)
        stop.assert_not_called()


class OriginPolicyTests(unittest.TestCase):
    def test_same_origin_allowlisted_and_non_browser_requests_pass(self):
        app = FastAPI()
        app.add_middleware(OriginCheckMiddleware, allowed=["https://maps.example"])

        @app.post("/change")
        async def change():
            return {"ok": True}

        @app.websocket("/ws")
        async def ws(websocket: WebSocket):
            await websocket.accept()
            await websocket.send_text("hi")
            await websocket.close()

        client = TestClient(app)
        for origin in (None, "http://testserver", "https://maps.example"):
            headers = {"Origin": origin} if origin else {}
            self.assertEqual(client.post("/change", headers=headers).status_code, 200, origin)
            with client.websocket_connect("/ws", headers=headers) as websocket:
                self.assertEqual(websocket.receive_text(), "hi")
        for origin in ("https://evil.example", "null", "http://testserver.evil.example"):
            self.assertEqual(client.post("/change", headers={"Origin": origin}).status_code, 403, origin)
        self.assertEqual(client.get("/change", headers={"Origin": "https://evil.example"}).status_code, 405)


class RasterSourceTests(unittest.TestCase):
    def test_raster_routes_only_open_data_folder_files_and_imagery_hosts(self):
        client = TestClient(server.app)
        with tempfile.TemporaryDirectory() as base:
            path = os.path.join(base, "r.tif")
            with rasterio.open(path, "w", driver="GTiff", width=4, height=4, count=1, dtype="uint8",
                               crs="EPSG:4326", transform=from_origin(0, 4, 1, 1)) as dst:
                dst.write(np.ones((1, 4, 4), dtype="uint8"))
            paths = SimpleNamespace(paths=SimpleNamespace(base_dir=base, data_dir=base))
            with patch.object(raster_service, "get_config", return_value=paths):
                self.assertEqual(client.get("/tiles/cog/info", params={"url": path}).status_code, 200)
                self.assertEqual(client.get("/api/raster/info", params={"url": path}).status_code, 200)
                for url in ("/etc/hosts", os.path.join(base, "..", "x.tif"),
                            "/vsicurl/http://169.254.169.254/latest/meta-data",
                            "http://169.254.169.254/x.tif", "https://169.254.169.254/x.tif",
                            "https://planetarycomputer.microsoft.com@169.254.169.254/x.tif"):
                    self.assertEqual(client.get("/tiles/cog/info", params={"url": url}).status_code, 403, url)
                    self.assertEqual(client.get("/api/raster/info", params={"url": url}).status_code, 403, url)
        blob = "https://sentinel2l2a01.blob.core.windows.net/x/B04.tif"
        self.assertEqual(raster_service.checked_raster_source(blob), blob)
