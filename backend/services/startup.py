# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Check local configuration and dependencies before accepting requests."""

import asyncio
import json
import logging
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryFile

import psycopg2
from psycopg2 import sql

from agents.base.client import init_model_client
from agents.core.config import get_config
from backend.routes import config as route_config

logger = logging.getLogger(__name__)
MODEL_ROLES = (
    "VECTOR_AGENT", "MAPS_AGENT", "STAC_AGENT", "RASTER_AGENT",
    "ORCHESTRATOR_PLANNER", "ORCHESTRATOR_PROGRESS",
)


def _check_files(config):
    for path in (config.paths.stac_band_metadata, config.paths.schema_cache_path):
        path = Path(path)
        if path == config.paths.schema_cache_path and not path.exists():
            continue  # Vector can regenerate its schema cache from the database.
        try:
            data = json.loads(path.read_text())
            if not isinstance(data, list) or not data or not all(isinstance(row, dict) for row in data):
                raise ValueError("Expected a non-empty JSON array of objects")
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"Cannot read metadata file {path}: {exc}") from None

    files = [Path(getattr(route_config, name)) for name in (
        "TEAM_STATE_PATH", "CONVERSATION_HISTORY_PATH", "RESPONSE_STORE_PATH",
        "ARTIFACTS_LEDGER_PATH", "USER_ARTIFACTS_JSON",
    )]
    files.extend((config.paths.team_state_path, config.paths.conversation_history_path,
                  config.paths.response_store_path, config.paths.user_artifacts_path))
    try:
        directories = {
            config.paths.export_dir, config.paths.state_dir, config.paths.history_dir,
            config.paths.user_data_dir, Path(route_config.USER_DATA_PATH),
            *(path.parent for path in files),
        }
    except OSError as exc:
        raise RuntimeError(f"Cannot prepare runtime directories: {exc}") from None
    if not config.paths.schema_cache_path.exists():
        directories.add(config.paths.schema_cache_path.parent)
    for directory in directories:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            with TemporaryFile(dir=directory) as probe:
                probe.write(b"startup check")
                probe.flush()
        except OSError as exc:
            raise RuntimeError(f"Runtime directory is not writable: {directory}: {exc}") from None
    for path in files:
        if path.exists():
            try:
                with path.open("r+"):
                    pass
            except OSError as exc:
                raise RuntimeError(f"Runtime file is not readable and writable: {path}: {exc}") from None


def _check_database(config):
    database = config.database
    stage = "connection (check POSTGRES_* settings)"
    try:
        with closing(psycopg2.connect(
            host=database.host, port=database.port, dbname=database.database,
            user=database.user, password=database.password, connect_timeout=5,
        )) as connection:
            connection.set_session(readonly=True)
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL statement_timeout = 5000")
                stage = "PostGIS functions (install PostGIS in the configured database)"
                cursor.execute("SELECT PostGIS_Version()")
                for table in ("disasters", "building_damage_assessment", "flood_maps"):
                    stage = f"SELECT access to {table} (restore the database and check permissions)"
                    cursor.execute(sql.SQL("SELECT * FROM {} LIMIT 0").format(sql.Identifier(table)))
    except psycopg2.Error:
        # Driver errors can contain connection credentials; report the failing check instead.
        raise RuntimeError(f"Database startup check failed: {stage}.") from None


async def check_startup():
    config = get_config()
    for role in MODEL_ROLES:
        try:
            component = config.get_model_client_component(role)
            _check_environment_references(component)
            client = init_model_client(client_key=role, config=config)
            await client.close()
        except Exception as exc:
            raise RuntimeError(
                f"Cannot initialize {role} model client ({type(exc).__name__}). "
                "Check its model configuration, credentials, and provider package."
            ) from None
    await asyncio.to_thread(_check_files, config)
    await asyncio.to_thread(_check_database, config)
    logger.info("Startup checks passed: model clients, metadata, runtime paths, and PostGIS.")


def _check_environment_references(value):
    if isinstance(value, dict):
        for item in value.values():
            _check_environment_references(item)
    elif isinstance(value, list):
        for item in value:
            _check_environment_references(item)
    elif isinstance(value, str) and value.startswith("$"):
        raise ValueError("Unresolved environment variable in model configuration")
