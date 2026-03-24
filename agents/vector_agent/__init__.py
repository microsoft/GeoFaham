# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Vector Agent Package

Single-agent approach for PostGIS spatial queries on disaster data.
Uses AssistantAgent with tool reflection for error recovery.
"""

from agents.vector_agent.assistant import create_vector_agent
from agents.vector_agent.tools import VectorQueryExecutor
from agents.vector_agent._prompts import DESCRIPTION

__all__ = [
    "create_vector_agent",
    "VectorQueryExecutor", 
    "DESCRIPTION",
]
