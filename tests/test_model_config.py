import importlib.util
import os
import unittest
from unittest.mock import patch

AUTOGEN_AVAILABLE = importlib.util.find_spec("autogen_agentchat") is not None

if AUTOGEN_AVAILABLE:
    from agents.core.config import AgentsConfig
else:
    AgentsConfig = None


@unittest.skipUnless(AUTOGEN_AVAILABLE, "AutoGen dependencies are not installed")
class ModelConfigTests(unittest.TestCase):
    def test_agent_uses_default_model_client(self):
        raw_config = (
            '{"provider":"autogen_ext.models.openai.OpenAIChatCompletionClient",'
            '"config":{"model":"gpt-4o-mini","api_key":"$OPENAI_API_KEY"}}'
        )
        with patch.dict(
            os.environ,
            {
                "GEOFAHAM_DEFAULT_MODEL_CLIENT": raw_config,
                "OPENAI_API_KEY": "test-key",
            },
            clear=True,
        ):
            config = AgentsConfig()
            component = config.get_model_client_component("MAPS_AGENT")

        self.assertEqual(component["config"]["model"], "gpt-4o-mini")
        self.assertEqual(component["config"]["api_key"], "test-key")
        self.assertEqual(component["config"]["model_info"]["family"], "unknown")

    def test_complex_agent_uses_reasoning_model_client(self):
        default_config = (
            '{"provider":"autogen_ext.models.openai.OpenAIChatCompletionClient",'
            '"config":{"model":"gpt-4o-mini"}}'
        )
        reasoning_config = (
            '{"provider":"autogen_ext.models.openai.OpenAIChatCompletionClient",'
            '"config":{"model":"gpt-5.1"}}'
        )
        with patch.dict(
            os.environ,
            {
                "GEOFAHAM_DEFAULT_MODEL_CLIENT": default_config,
                "GEOFAHAM_REASONING_MODEL_CLIENT": reasoning_config,
            },
            clear=True,
        ):
            config = AgentsConfig()
            component = config.get_model_client_component("VECTOR_AGENT")

        self.assertEqual(component["config"]["model"], "gpt-5.1")

    def test_agent_override_wins(self):
        default_config = (
            '{"provider":"autogen_ext.models.openai.OpenAIChatCompletionClient",'
            '"config":{"model":"gpt-4o-mini"}}'
        )
        agent_config = (
            '{"provider":"autogen_ext.models.openai.OpenAIChatCompletionClient",'
            '"config":{"model":"gpt-4.1-mini"}}'
        )
        with patch.dict(
            os.environ,
            {
                "GEOFAHAM_DEFAULT_MODEL_CLIENT": default_config,
                "GEOFAHAM_MAPS_AGENT_MODEL_CLIENT": agent_config,
            },
            clear=True,
        ):
            config = AgentsConfig()
            component = config.get_model_client_component("MAPS_AGENT")

        self.assertEqual(component["config"]["model"], "gpt-4.1-mini")

    def test_explicit_model_info_wins_over_defaults(self):
        raw_config = (
            '{"provider":"autogen_ext.models.openai.OpenAIChatCompletionClient",'
            '"config":{"model":"custom-model","model_info":{"family":"gpt-4o","vision":true}}}'
        )
        with patch.dict(
            os.environ,
            {"GEOFAHAM_DEFAULT_MODEL_CLIENT": raw_config},
            clear=True,
        ):
            config = AgentsConfig()
            component = config.get_model_client_component("MAPS_AGENT")

        self.assertEqual(component["config"]["model_info"]["family"], "gpt-4o")
        self.assertTrue(component["config"]["model_info"]["vision"])
        self.assertTrue(component["config"]["model_info"]["function_calling"])


if __name__ == "__main__":
    unittest.main()
