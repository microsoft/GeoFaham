# Python and HTTP APIs

## Python

Run this script from the repository root after configuring `.env` and restoring
the database. The full team loads the Vector Agent's schema and disaster catalog
at startup.

```python
import asyncio

from dotenv import load_dotenv
from autogen_agentchat.ui import Console


async def main():
    load_dotenv()
    from agents import get_team

    async def user_input(prompt, cancellation_token=None):
        return await asyncio.to_thread(input, prompt)

    team = await get_team(user_input)
    await Console(team.run_stream(task="Find bridges in St. Louis, Missouri."))


if __name__ == "__main__":
    asyncio.run(main())
```

The entry-point guard is required when Raster tools spawn a worker process.
For a single agent, use `create_single_agent("postgis")`, `"map_search"`,
`"stac"`, or `"raster_ops"` from the `agents` package. Each agent uses its
configured model client. See [agent tools](AGENTS_DOCUMENTATION.md) and
[configuration](CONFIGURATION.md).

## HTTP and WebSocket

Run `python server.py`; FastAPI's `/docs` page lists HTTP request and response
schemas. The frontend uses these routes:

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/config` | GET | Runtime frontend configuration, including the Azure Maps key |
| `/ws/chat` | WebSocket | Chat, streamed events, and clarification replies |
| `/api/polling/init` | POST | Create a polling session with a selected `mode` |
| `/api/polling/send` | POST | Submit content with a `session_id` |
| `/api/polling/poll` | GET | Drain queued messages for a `session_id` |
| `/api/upload-geojson` | POST | Upload GeoJSON and register its artifact |
| `/api/upload-raster` | POST | Upload a GeoTIFF and register its artifact |
| `/api/user-artifacts` | GET | List uploaded artifacts |
| `/api/raster/info` | GET | Read raster metadata |
| `/api/reset` | POST | Stop active runs and clear conversation, team state, and response registry |
| `/history` | GET | Read conversation history |
| `/api/disasters` | GET | List database disaster records |
| `/tiles/cog/*` | GET | Serve COG tiles through TiTiler |

Modes are `multi-agent`, `postgis`, `map_search`, `stac`, and `raster_ops`.
Polling supports completed requests but its user-input callback does not support
mid-run clarification. Use WebSocket or the Python callback for that interaction.
Reset clears application state across sessions in the running process; it does
not delete uploaded or generated artifact files.

Route implementations are under [backend/routes](../backend/routes/) and database
CRUD routes under [backend/crud](../backend/crud/). Tool payloads are described
in [tool responses](TOOL_RESPONSE_SCHEMAS.md).
