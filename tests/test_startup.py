# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import psycopg2
from fastapi.testclient import TestClient

from agents.core.config import AgentsConfig
from backend.services import startup


class StartupTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.config = AgentsConfig()
        self.config.paths.base_dir = self.root / "runtime"
        self.config.paths.data_dir = self.root / "data"
        self.config.paths.stac_band_metadata.parent.mkdir(parents=True)
        self.config.paths.stac_band_metadata.write_text(json.dumps([
            {"id": "sentinel-2-l2a", "available_bands": []},
        ]))
        paths = {name: str(self.root / "overrides" / name) for name in (
            "TEAM_STATE_PATH", "CONVERSATION_HISTORY_PATH", "RESPONSE_STORE_PATH",
            "ARTIFACTS_LEDGER_PATH", "USER_ARTIFACTS_JSON", "USER_DATA_PATH",
        )}
        self.paths = paths
        self.route_patch = patch.multiple(startup.route_config, **paths)
        self.route_patch.start()
        self.addCleanup(self.route_patch.stop)

    async def test_initializes_and_closes_every_role_before_checking_dependencies(self):
        clients = [Mock(close=AsyncMock()) for _ in startup.MODEL_ROLES]
        self.config.get_model_client_component = Mock(return_value={"config": {}})
        with patch.object(startup, "get_config", return_value=self.config), \
                patch.object(startup, "init_model_client", side_effect=clients) as factory, \
                patch.object(startup, "_check_files") as files, \
                patch.object(startup, "_check_database") as database:
            await startup.check_startup()
        self.assertEqual([call.kwargs["client_key"] for call in factory.call_args_list],
                         list(startup.MODEL_ROLES))
        for client in clients:
            client.close.assert_awaited_once()
        files.assert_called_once_with(self.config)
        database.assert_called_once_with(self.config)

    async def test_unresolved_credentials_stop_before_client_or_database(self):
        self.config.get_model_client_component = Mock(return_value={"config": {"api_key": "$MISSING_KEY"}})
        with patch.object(startup, "get_config", return_value=self.config), \
                patch.object(startup, "init_model_client") as factory, \
                patch.object(startup, "_check_database") as database:
            with self.assertRaisesRegex(RuntimeError, "VECTOR_AGENT"):
                await startup.check_startup()
        factory.assert_not_called()
        database.assert_not_called()

    async def test_invalid_provider_error_does_not_expose_configuration(self):
        self.config.get_model_client_component = Mock(return_value={"config": {}})
        with patch.object(startup, "get_config", return_value=self.config), \
                patch.object(startup, "init_model_client", side_effect=ValueError("secret credential")):
            with self.assertRaises(RuntimeError) as error:
                await startup.check_startup()
        self.assertNotIn("secret", str(error.exception))

    def test_files_and_override_directories_preserve_existing_state(self):
        state = Path(self.paths["TEAM_STATE_PATH"])
        state.parent.mkdir(parents=True)
        state.write_bytes(b'{"existing": true}\n')
        before = state.read_bytes()
        startup._check_files(self.config)
        self.assertEqual(state.read_bytes(), before)
        self.assertTrue(self.config.paths.schema_cache_path.parent.is_dir())
        self.assertTrue(Path(self.paths["USER_DATA_PATH"]).is_dir())
        self.assertEqual(list(self.config.paths.export_dir.iterdir()), [])

    def test_missing_or_malformed_metadata_blocks_startup(self):
        metadata = self.config.paths.stac_band_metadata
        for content in (None, "not json", "{}", "[]", '["wrong"]'):
            with self.subTest(content=content):
                if content is None:
                    metadata.unlink()
                else:
                    metadata.write_text(content)
                with self.assertRaisesRegex(RuntimeError, "metadata file"):
                    startup._check_files(self.config)

    def test_invalid_existing_schema_cache_blocks_startup(self):
        path = self.config.paths.schema_cache_path
        path.parent.mkdir(parents=True)
        path.write_text("invalid")
        with self.assertRaisesRegex(RuntimeError, "schema.json"):
            startup._check_files(self.config)

    def test_unwritable_directory_blocks_startup(self):
        with patch.object(startup, "TemporaryFile", side_effect=PermissionError("denied")):
            with self.assertRaisesRegex(RuntimeError, "directory is not writable"):
                startup._check_files(self.config)

    def test_database_checks_are_read_only_bounded_and_close_connection(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value = Mock()
        with patch.object(startup.psycopg2, "connect", return_value=connection) as connect:
            startup._check_database(self.config)
        self.assertEqual(connect.call_args.kwargs["connect_timeout"], 5)
        connection.set_session.assert_called_once_with(readonly=True)
        connection.close.assert_called_once()
        calls = cursor.execute.call_args_list
        self.assertEqual(calls[0].args[0], "SET LOCAL statement_timeout = 5000")
        self.assertEqual(calls[1].args[0], "SELECT PostGIS_Version()")
        self.assertEqual(len(calls), 5)
        for table, call in zip(("disasters", "building_damage_assessment", "flood_maps"), calls[2:]):
            self.assertIn(table, repr(call.args[0]))

    def test_database_failure_reports_stage_and_closes_connection(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value = Mock()
        cursor.execute.side_effect = [None, None, None, psycopg2.ProgrammingError("secret connection string")]
        with patch.object(startup.psycopg2, "connect", return_value=connection):
            with self.assertRaisesRegex(RuntimeError, "SELECT access to building_damage_assessment") as error:
                startup._check_database(self.config)
        connection.close.assert_called_once()
        self.assertNotIn("secret", str(error.exception))

    def test_database_connection_failure_reports_settings(self):
        with patch.object(startup.psycopg2, "connect", side_effect=psycopg2.OperationalError("secret")):
            with self.assertRaisesRegex(RuntimeError, "POSTGRES") as error:
                startup._check_database(self.config)
        self.assertNotIn("secret", str(error.exception))


class ServerStartupTests(unittest.TestCase):
    def test_server_runs_checks_before_serving_requests(self):
        import server
        with patch.object(server, "check_startup", new_callable=AsyncMock) as check:
            with TestClient(server.app) as client:
                check.assert_awaited_once()
                self.assertEqual(client.get("/openapi.json").status_code, 200)

    def test_failed_check_prevents_server_start(self):
        import server
        with patch.object(server, "check_startup", new_callable=AsyncMock,
                          side_effect=RuntimeError("Database startup check failed")):
            with self.assertRaisesRegex(RuntimeError, "Database startup check failed"):
                with TestClient(server.app):
                    self.fail("Requests must not be accepted after a failed startup check")
