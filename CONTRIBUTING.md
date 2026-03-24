# Contributing

This project welcomes contributions and suggestions. Most contributions require you to
agree to a Contributor License Agreement (CLA) declaring that you have the right to,
and actually do, grant us the rights to use your contribution. For details, visit
https://cla.microsoft.com.

When you submit a pull request, a CLA-bot will automatically determine whether you need
to provide a CLA and decorate the PR appropriately (e.g., label, comment). Simply follow the
instructions provided by the bot. You will only need to do this once across all repositories using our CLA.

This project has adopted the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/).
For more information see the [Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/)
or contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with any additional questions or comments.

## Getting Started

### Prerequisites

- Python 3.11+
- PostgreSQL with PostGIS extension
- Azure OpenAI API access

### Setup

```bash
# Clone the repository
git clone https://github.com/microsoft/GeoFaham.git
cd GeoFaham

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
# Edit .env with your credentials
```

### Running Tests

```bash
python -m pytest tests/
```

## Development Guidelines

- Follow existing patterns in `agents/core/` and `agents/base/`
- All tools return `GeoFahamToolResponse` as JSON string
- Use `get_config()` for all configuration access
- Log using `get_logger("module.name")`

## Adding a New Agent

1. Create folder: `agents/new_agent/`
2. Add files: `assistant.py`, `tools.py`, `_prompts.py`, `__init__.py`
3. Register in `agents/team.py`
4. Update `agents/orchestrator_agent/_agent_capabilities.py`
5. Add constants to `agents/core/constants.py`
