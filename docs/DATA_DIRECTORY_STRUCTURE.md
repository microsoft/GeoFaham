# Data, outputs, and session state

Paths are defined in [PathsConfig](../agents/core/config.py). Reference data
lives under `data/`; generated files and session state live under `runtime/`.

```text
data/
  stac/stac_output_mpc_clean.json   Satellite band metadata
  db/schema.json                  Cached database column schema
  db/sql/schema.sql               SQL table definitions
  backups/                        Downloaded database snapshot and checksum
runtime/
  artifacts/query_jsons/          Generated GeoJSON, rasters, and imagery files
  state/response_store.jsonl      Tool response registry
  state/team_state.json           Team checkpoint
  history/conversation_history.json  Conversation history
  user_data/                     Uploaded files and user_artifacts.json
```

## Required inputs

| Input | Used by | Notes |
|-------|---------|-------|
| Populated PostGIS database | Vector Agent and full team | Provides disaster, building-damage, and flood records |
| STAC band metadata JSON | STAC tooling | Used for band metadata and display settings |
| Database schema cache | Vector prompt and Orchestrator module | Vector can query the database if absent |
| Database backup | Setup script | Used during restore, not read during normal analysis |

The database snapshot contains schema and records; the schema cache contains
column descriptions used in prompts. Follow [database setup](../data/backups/README.md) to restore it.

`disasters_summary.json` is a reference file; the Vector Agent retrieves its
disaster catalog from the database. The current schema-cache writer expects its
parent directory to exist, so create `data/db/` if regenerating a missing cache.

## Overrides

| Variable | Default or effect |
|----------|-------------------|
| `GEOFAHAM_BASE_DIR` | `./runtime` |
| `GEOFAHAM_DATA_DIR` | `./data` |
| `STAC_BAND_METADATA_PATH` | Overrides the STAC metadata JSON path |
| `RESPONSE_STORE_PATH` | Backend override for the response-store path |
| `TEAM_STATE_PATH` | Backend override for the team checkpoint |
| `CONVERSATION_HISTORY_PATH` | Backend override for conversation history |

Use a separate base directory for independent runs. The default paths can share
outputs and state when multiple instances use the same working directory.

## Cleanup

Deleting artifacts breaks references to them in the response registry and saved
team state. Reset or archive the associated state when discarding an analysis.
Uploaded data may be needed by follow-up queries; retain it for the session.

`runtime/` and downloaded SQL backups are Git-ignored.
