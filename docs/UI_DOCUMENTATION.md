# Web interface

![Flood-analysis conversation and map layers](figures/geofaham-web-interface.png)

The frontend is a static application served by FastAPI. It uses Azure Maps for
map display and plain JavaScript modules for chat, layers, and session controls.
There is no frontend build step. See the [demo gallery](DEMO_GALLERY.md) for
recorded interactions.

## Layout and controls

The map occupies the left pane and chat the right. The header contains agent
mode, upload, reset, debug controls, and connection status.

| Control | Behavior |
|---------|----------|
| Agent mode | Selects the full team or an individual agent and reconnects |
| Map style | Switches road, satellite, hybrid, and dark basemaps |
| Drawing tools | Creates geometry that can accompany the next message |
| Layer controls | Toggles outputs and adjusts supported raster display settings |
| Upload | Saves a GeoJSON file and its metadata on the server |
| Visualize | Previews GeoJSON without uploading it through the upload workflow |
| Reset | Clears the interface and requests a backend session reset |
| Debug mode | Shows test controls and additional messages; persisted in localStorage |

Chat renders assistant Markdown and displays layer notices and errors. Enter
sends a message; Shift+Enter inserts a newline. The input is enabled when the
backend requests user input or finishes a turn.

## Connection

`core/websocket.js` connects to `/ws/chat` with the selected mode. On repeated
connection failure it can use the backend's HTTP polling routes. User messages
carry content, source, and optional drawn geometry in `user_raw_json`.

Changing mode reconnects the session. Model, database, and map-service errors are reported separately from connection
status.

## Response rendering

`chat/message-handler.js` handles incoming events and sends layers to
`core/response-router.js`. The router normalizes response metadata and selects
the rendering path.

| Output | Rendering |
|--------|-----------|
| GeoJSON | Vector layers, property popups, and fitted bounds |
| Building damage | Vector styling based on `damage_pct`, with a legend |
| COG raster | TiTiler tile layer with bounds, scaling, opacity, and colormap settings |
| Temporal raster or mosaic | Layer sequence with a timeline control |
| STAC imagery | Image tiles and supported temporal grouping |

Metadata may appear in the common response fields or in renderer-specific
payloads. Use [response schemas](TOOL_RESPONSE_SCHEMAS.md) when changing a
producer and check the matching renderer.

## Screenshot analysis toolbox

The frontend includes screenshot capture and buttons for map-view analysis.
These controls call `/api/analyze-raster`; that route is not implemented, so
screenshot analysis is unavailable.

## Source map

| File or directory | Responsibility |
|-------------------|----------------|
| [index.html](../frontend/index.html) | Page structure and modals |
| [config.js](../frontend/js/config.js) | Endpoints and UI settings |
| [frontend_config.py](../backend/routes/frontend_config.py) | Runtime Azure Maps configuration |
| [app.js](../frontend/js/app.js) | Application initialization and controls |
| [core/websocket.js](../frontend/js/core/websocket.js) | WebSocket and polling transport |
| [chat/](../frontend/js/chat/) | Input, history display, and incoming messages |
| [map/](../frontend/js/map/) | Map initialization, drawing, and layer controls |
| [layers/](../frontend/js/layers/) | Vector, raster, and temporal renderers |
| [modals/](../frontend/js/modals/) | Upload and preview |

Set `AZURE_MAPS_KEY` in `.env`. The frontend reads it through `/api/config`
before initializing the map.
The backend mounts TiTiler under `/tiles`.
