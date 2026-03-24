# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

from fastapi.responses import HTMLResponse
from pathlib import Path

TEMPLATE_PATH = Path(__file__).parent / "templates" / "crud.html"
# ./templates/crud.html
def crud_page():
    try:
        html = TEMPLATE_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        html = "<html><body><h1>crud.html not found</h1></body></html>"
    return HTMLResponse(content=html)
