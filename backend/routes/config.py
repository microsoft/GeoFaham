# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Routes configuration - uses centralized agents config.
"""
import os
from agents.core.config import get_config

# Get paths from centralized config
_config = get_config()

# State and history paths (handle empty env vars)
_team_state_env = os.getenv('TEAM_STATE_PATH', '')
_conv_history_env = os.getenv('CONVERSATION_HISTORY_PATH', '')
_resp_store_env = os.getenv('RESPONSE_STORE_PATH', '')
TEAM_STATE_PATH = _team_state_env if _team_state_env else str(_config.paths.team_state_path)
CONVERSATION_HISTORY_PATH = _conv_history_env if _conv_history_env else str(_config.paths.conversation_history_path)
RESPONSE_STORE_PATH = _resp_store_env if _resp_store_env else str(_config.paths.response_store_path)
# User data paths
USER_DATA_PATH = os.getenv('USER_DATA_PATH', str(_config.paths.user_data_dir))
USER_ARTIFACTS_JSON = str(_config.paths.user_artifacts_path)

# Artifacts and response storage
ARTIFACTS_LEDGER_PATH = os.getenv('ARTIFACTS_LEDGER_PATH', './dump/artifacts_ledger.jsonl')

# Benchmark path
BENCHMARK_GT_PATH = os.getenv('BENCHMARK_GT_PATH', './benchmark_gt')
