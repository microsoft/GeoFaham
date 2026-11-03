# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Reject cross-site browser requests that could drive the agents or change state.

Browsers send an Origin header on WebSocket handshakes and cross-origin POSTs.
Requests are accepted when the Origin matches the Host the browser connected to,
or is listed in GEOFAHAM_ALLOWED_ORIGINS. Requests without an Origin header
(curl, scripts, server-to-server) are not browser cross-site requests and pass.
"""
import os
from urllib.parse import urlsplit

from starlette.responses import PlainTextResponse

_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def allowed_origins() -> list[str]:
    """Extra origins (e.g. a separately hosted frontend) from GEOFAHAM_ALLOWED_ORIGINS."""
    raw = os.getenv("GEOFAHAM_ALLOWED_ORIGINS", "")
    return [origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip()]


def is_origin_allowed(origin: str | None, host: str | None, allowed: set[str]) -> bool:
    if origin is None:
        return True
    origin = origin.rstrip("/")
    if origin in allowed:
        return True
    parts = urlsplit(origin)
    return parts.scheme in ("http", "https") and bool(host) and parts.netloc.lower() == host.lower()


class OriginCheckMiddleware:
    """ASGI middleware covering WebSocket handshakes and state-changing HTTP requests."""

    def __init__(self, app, allowed: list[str] | None = None):
        self.app = app
        self.allowed = set(allowed_origins() if allowed is None else allowed)

    async def __call__(self, scope, receive, send):
        checked = scope["type"] == "websocket" or (
            scope["type"] == "http" and scope["method"] in _UNSAFE_METHODS
        )
        if checked:
            headers = dict(scope.get("headers") or [])
            origin = headers.get(b"origin")
            host = headers.get(b"host")
            if not is_origin_allowed(
                origin.decode("latin-1") if origin is not None else None,
                host.decode("latin-1") if host is not None else None,
                self.allowed,
            ):
                if scope["type"] == "websocket":
                    await send({"type": "websocket.close", "code": 1008})
                else:
                    await PlainTextResponse("Cross-origin request blocked", status_code=403)(scope, receive, send)
                return
        await self.app(scope, receive, send)
