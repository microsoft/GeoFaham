# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
GeoFaham Tests Package

Test runners for GeoFaham agents.

Interactive testing:
    python -m tests.console_test                    # Interactive agent console
    python -m tests.console_test --agent vector     # Test specific agent
    python -m tests.tool_test                       # Interactive tool tester
    python -m tests.tool_test --agent maps --list   # List tools for an agent

Unit tests:
    python -m tests.test_vector_agent
    python -m tests.test_maps_agent
    python -m tests.test_stac_agent
    python -m tests.test_raster_agent
    python -m tests.test_all_agents
"""
