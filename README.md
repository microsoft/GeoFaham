<p align="center">
  <h1 align="center">🌍 GeoFaham</h1>
  <p align="center">
    <strong>AI-Powered Geospatial Analysis Platform for Disaster Assessment</strong>
  </p>
  <p align="center">
    Multi-agent system combining satellite imagery, OpenStreetMap data, and PostGIS databases
    <br />
    for comprehensive disaster damage analysis and geospatial intelligence.
  </p>
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#architecture">Architecture</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#usage">Usage</a> •
  <a href="#api">API</a> •
  <a href="#documentation">Docs</a>
</p>

---

## Overview

GeoFaham is an intelligent geospatial analysis platform that leverages multiple AI agents to automate disaster damage assessment workflows. It combines:

- **Satellite Imagery** from Microsoft Planetary Computer (Sentinel-2, Landsat, SAR)
- **OpenStreetMap** features (buildings, roads, infrastructure)
- **PostGIS Database** with disaster records and damage assessments
- **Raster Analysis** with automated Python code generation

The system uses [AutoGen](https://github.com/microsoft/autogen) for multi-agent orchestration, allowing natural language queries to be automatically decomposed into specialized agent tasks.

## Features

### 🤖 Multi-Agent System
- **Orchestrator Agent** - Plans and coordinates complex geospatial workflows
- **Vector Agent** - PostGIS spatial queries with GeoJSON integration
- **Maps Agent** - OpenStreetMap feature extraction (14 specialized tools)
- **STAC Agent** - Satellite imagery search from 100+ collections
- **Raster Ops Agent** - Python code generation for raster analysis

### 🗺️ Geospatial Capabilities
- Burn severity mapping and wildfire analysis
- Flood extent detection and damage assessment
- Building damage classification
- Vegetation health monitoring (NDVI, NBR)
- Population exposure analysis
- Infrastructure impact assessment

### 🖥️ Interactive Web Interface
- Real-time chat with AI agents
- Interactive map visualization (Leaflet.js)
- Layer management and styling
- Raster tile streaming (TiTiler)
- GeoJSON upload and management

## Architecture

```
GeoFaham/
├── agents/                    # Multi-agent system
│   ├── core/                  # Foundation (config, types, logging)
│   ├── shared/                # Shared utilities (serialization, geojson)
│   ├── base/                  # Agent factory, model client
│   ├── vector_agent/          # PostGIS queries
│   ├── maps_agent/            # OpenStreetMap extraction
│   ├── stac_agent/            # Satellite imagery (Planetary Computer)
│   ├── raster_ops_agent/      # Raster analysis code execution
│   ├── orchestrator_agent/    # Multi-agent coordination
│   └── team.py                # Team creation
│
├── backend/                   # FastAPI server
│   ├── routes/                # API endpoints
│   ├── services/              # Business logic (raster, tiles)
│   └── crud/                  # Database operations
│
├── frontend/                  # Web UI
│   ├── index.html             # Main page
│   ├── js/                    # JavaScript modules
│   └── css/                   # Styles
│
├── data/                      # Static reference data (version controlled)
│   ├── stac/                  # STAC band metadata
│   └── db/                    # Database schemas, SQL
│
├── runtime/                   # Generated at runtime (gitignored)
│   ├── artifacts/             # Generated GeoJSON, COG files
│   ├── state/                 # Team state, response store
│   └── history/               # Conversation logs
│
├── tests/                     # Test suite
│   ├── console_test.py        # Interactive agent testing
│   └── tool_test.py           # Tool-level testing
│
├── docs/                      # Documentation
├── server.py                  # FastAPI entry point
└── requirements.txt           # Python dependencies
```

### Agent Communication Flow

```
User Query
    │
    ▼
┌─────────────────┐
│   Orchestrator  │ ◄── Plans workflow, delegates tasks
└────────┬────────┘
         │
    ┌────┴────┬─────────┬─────────┐
    ▼         ▼         ▼         ▼
┌───────┐ ┌───────┐ ┌───────┐ ┌────────┐
│Vector │ │ Maps  │ │ STAC  │ │ Raster │
│Agent  │ │ Agent │ │ Agent │ │  Ops   │
└───┬───┘ └───┬───┘ └───┬───┘ └───┬────┘
    │         │         │         │
    ▼         ▼         ▼         ▼
 PostGIS   OSM APIs  Planetary  Python
Database   Nominatim  Computer  Executor
           Overpass   STAC API
```

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL with PostGIS extension
- Azure OpenAI API access
- (Optional) Local Nominatim/Overpass for OSM queries

### Installation

```bash
# Clone the repository
git clone https://github.com/your-org/GeoFaham.git
cd GeoFaham

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
# Edit .env with your credentials
```

### Configuration

Edit `.env` with your settings:

```bash
# Azure OpenAI (required)
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com

# PostgreSQL (required for vector_agent)
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=geofaham
POSTGRES_USER=your_user
POSTGRES_PASSWORD=your_password

# Model configuration
GEOFAHAM_DEFAULT_MODEL=gpt-4o
GEOFAHAM_REASONING_MODEL=gpt-5.1
```

### Running the Server

```bash
# Start the server
python server.py

# Or with uvicorn for development
uvicorn server:app --reload --host 0.0.0.0 --port 8005
```

Visit `http://localhost:8005` to access the web interface.

## Usage

### Web Interface

1. Open `http://localhost:8005` in your browser
2. Type your query in the chat input, e.g.:
   - "Show me damaged buildings in the Lahaina fire area"
   - "Calculate burn severity for the 2023 Maui wildfire"
   - "Find hospitals within 5km of the flood zone"
3. Watch the agents collaborate to answer your query
4. View results on the interactive map

### Command Line Testing

```bash
# Interactive agent console
python -m tests.console_test

# Test specific agent
python -m tests.console_test --agent vector
python -m tests.console_test --agent maps
python -m tests.console_test --agent stac
python -m tests.console_test --agent raster
python -m tests.console_test --agent team

# Single query mode
python -m tests.console_test --agent maps --query "Get boundary for Lahaina, Hawaii"

# Test individual tools
python -m tests.tool_test --agent maps --list
python -m tests.tool_test --agent maps --tool get_address_coordinates
```

### Python API

```python
from agents import get_team
from agents.core.config import get_config
from agents.base.client import init_model_client

# Create a single agent
from agents.vector_agent import create_vector_agent

config = get_config()
client = init_model_client(model=config.get_agent_model("VECTOR_AGENT"))
agent = create_vector_agent(client)

# Create the full team
async def main():
    async def user_input(prompt, token=None):
        return input(prompt)
    
    team = await get_team(user_input)
    
    # Run a query
    from autogen_agentchat.ui import Console
    stream = team.run_stream(task="Find all bridges in St. Louis, MO")
    await Console(stream)

import asyncio
asyncio.run(main())
```

## API Reference

### REST Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/ws/chat` | WebSocket | Real-time chat with agents |
| `/api/disasters` | GET | List disasters in database |
| `/api/upload-geojson` | POST | Upload GeoJSON file |
| `/api/user-artifacts` | GET | List user artifacts |
| `/api/raster/info` | GET | Get raster metadata |
| `/tiles/{z}/{x}/{y}` | GET | Raster tile endpoint (TiTiler) |
| `/history` | GET | Conversation history |

### Agent Tools

#### Vector Agent
- `execute_query` - Run PostGIS SELECT queries
- `execute_query_with_geojson` - Query with GeoJSON spatial joins
- `get_available_responses` - Access previous agent responses

#### Maps Agent
- `get_roads`, `get_buildings`, `get_waterways`, `get_bridges`
- `get_pois`, `get_landuse`, `get_natural_features`, `get_infrastructure`
- `get_admin_boundary`, `get_neighborhoods`
- `get_address_coordinates`, `get_place_bounding_box`
- `search_feature_by_name`, `get_features_by_tags`

#### STAC Agent
- `get_collection_details` - Get satellite collection metadata
- `execute_stac_search` - Search satellite imagery (fetch/show modes)

#### Raster Ops Agent
- `execute_custom_raster_code` - Execute Python raster analysis

## Documentation

| Document | Description |
|----------|-------------|
| [docs/TOOL_RESPONSE_SCHEMAS.md](docs/TOOL_RESPONSE_SCHEMAS.md) | JSON schemas for all tool responses |
| [docs/DATA_DIRECTORY_STRUCTURE.md](docs/DATA_DIRECTORY_STRUCTURE.md) | File organization best practices |
| [docs/agents.md](docs/agents.md) | Agent architecture overview |

## Configuration Reference

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AZURE_OPENAI_ENDPOINT` | ✅ | - | Azure OpenAI endpoint |
| `POSTGRES_HOST` | ✅ | localhost | PostgreSQL host |
| `POSTGRES_DB` | ✅ | geofaham | Database name |
| `POSTGRES_USER` | ✅ | - | Database user |
| `POSTGRES_PASSWORD` | ✅ | - | Database password |
| `GEOFAHAM_DEFAULT_MODEL` | ❌ | gpt-4o | Model for simple agents |
| `GEOFAHAM_REASONING_MODEL` | ❌ | gpt-5.1 | Model for complex agents |
| `GEOFAHAM_BASE_DIR` | ❌ | ./runtime | Runtime artifacts directory |
| `GEOFAHAM_DATA_DIR` | ❌ | ./data | Static data directory |

### Model Configuration

Per-agent model overrides via environment variables:

```bash
GEOFAHAM_VECTOR_AGENT_MODEL=gpt-5.1
GEOFAHAM_MAPS_AGENT_MODEL=gpt-4o
GEOFAHAM_STAC_AGENT_MODEL=gpt-4o
GEOFAHAM_RASTER_AGENT_MODEL=gpt-5.1
GEOFAHAM_ORCHESTRATOR_PLANNER_MODEL=gpt-5.1
GEOFAHAM_ORCHESTRATOR_PROGRESS_MODEL=gpt-4o
```

## Development

### Adding a New Agent

1. Create folder: `agents/new_agent/`
2. Add files:
   - `assistant.py` - Agent factory function
   - `tools.py` - Tool implementations
   - `_prompts.py` - System prompt
   - `__init__.py` - Package exports
3. Register in `agents/team.py`
4. Update `agents/orchestrator_agent/_agent_capabilities.py`
5. Add constants to `agents/core/constants.py`

### Code Style

- Follow existing patterns in `agents/core/` and `agents/base/`
- All tools return `GeoFahamToolResponse` as JSON string
- Use `get_config()` for all configuration access
- Log using `get_logger("module.name")`

### Testing

```bash
# Run unit tests
python -m pytest tests/

# Test specific agent
python -m tests.test_vector_agent
python -m tests.test_maps_agent

# Interactive testing
python -m tests.console_test --agent vector
```

## Tech Stack

| Component | Technology |
|-----------|------------|
| AI Agents | [AutoGen](https://github.com/microsoft/autogen) 0.7+ |
| LLM | Azure OpenAI (GPT-4o, GPT-5) |
| Backend | FastAPI, Uvicorn |
| Database | PostgreSQL + PostGIS |
| Geospatial | GeoPandas, Rasterio, Shapely |
| Satellite Data | PySTAC, Planetary Computer, stackstac |
| Raster Tiles | TiTiler, rio-tiler |
| OSM | OSMnx, Nominatim, Overpass |
| Frontend | Vanilla JS, Leaflet.js |

## License

[MIT License](LICENSE.txt)

## Trademarks

This project may contain trademarks or logos for projects, products, or services. Authorized use of Microsoft trademarks or logos is subject to and must follow [Microsoft's Trademark & Brand Guidelines](https://www.microsoft.com/en-us/legal/intellectualproperty/trademarks/usage/general). Use of Microsoft trademarks or logos in modified versions of this project must not cause confusion or imply Microsoft sponsorship. Any use of third-party trademarks or logos are subject to those third-party's policies.

## Acknowledgments

- [Microsoft Planetary Computer](https://planetarycomputer.microsoft.com/) for satellite data access
- [AutoGen](https://github.com/microsoft/autogen) for multi-agent framework
- [OpenStreetMap](https://www.openstreetmap.org/) contributors for map data
- [TiTiler](https://developmentseed.org/titiler/) for raster tile serving
