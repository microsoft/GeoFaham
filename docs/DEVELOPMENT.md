# Development

Use the [quick start](../README.md#quick-start) for installation, model settings,
and database setup. Run commands below from the repository root.

## Tests

These regression tests run without live model or imagery requests:

```bash
python -m unittest tests.test_workflow_contracts tests.test_clarification_flow tests.test_artifact_metadata
```

The test directory also contains agent scripts that use configured credentials,
the database, or external services. To try an agent or the full team interactively:

```bash
python -m tests.console_test --agent vector
python -m tests.console_test --agent team
```

Other console choices are `maps`, `stac`, and `raster`. Live checks can incur
model API charges. Use a separate `GEOFAHAM_BASE_DIR` for test outputs and state.

## Conventions

Use `get_config()` for configuration and `get_logger("module.name")` for logging.
Build tool results with the [shared response builders](../agents/shared/responses.py);
`get_available_responses` returns the registry's own discovery envelope.
Keep artifact payloads in files and pass their response IDs between steps.

When changing a tool, check its callers, agent prompt, response builder, and
frontend renderer. For prompt changes, test a valid request, missing required
information, and a failed tool call. Verify generated outputs against the input
data as well as the final answer.

## Adding an agent

1. Add a package under `agents/` with a factory, tools, prompt, and exports.
2. Register its factory and model assignment in `agents/team.py` and
   `agents/core/config.py`.
3. Add its name to `agents/core/constants.py` and describe its capabilities in
   `agents/orchestrator_agent/_agent_capabilities.py`.
4. Check it individually and in a workflow that passes artifacts to another agent.

See [agent reference](AGENTS_DOCUMENTATION.md) for the current roles and
[requirements.txt](../requirements.txt) for dependencies.
