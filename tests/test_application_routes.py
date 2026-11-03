# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Application routes retained when integrating agent workflows."""

import unittest
from unittest.mock import patch

from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.routes import reset
from backend.services.origin_policy import OriginCheckMiddleware
import server


class ApplicationRouteTests(unittest.TestCase):
    def test_frontend_configuration_keeps_the_deployment_maps_key(self):
        with patch.dict("os.environ", {"AZURE_MAPS_KEY": "test-maps-key"}):
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
