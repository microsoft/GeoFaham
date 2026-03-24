# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Test Tool Calls Directly

This module lets you test individual tool functions without LLM involvement.

Run: python -m tests.test_tool_calls
"""

import asyncio
import json
from typing import Any


def print_result(name: str, result: str):
    """Pretty print a tool result."""
    print(f"\n{'='*60}")
    print(f"Tool: {name}")
    print('='*60)
    
    try:
        data = json.loads(result)
        print(f"Type: {data.get('type')}")
        print(f"Data Type: {data.get('data_type')}")
        print(f"Summary: {data.get('summary', '')[:200]}")
        
        if data.get('error_message'):
            print(f"Error: {data.get('error_message')}")
        
        if data.get('artifact'):
            art = data['artifact']
            print(f"Artifact: {art.get('path')}")
            print(f"Features: {art.get('features_count')}")
        
        if data.get('data') and len(data['data']) > 0:
            print(f"Data rows: {len(data['data'])}")
            print(f"Sample: {json.dumps(data['data'][0], indent=2)[:300]}...")
            
    except json.JSONDecodeError:
        print(f"Raw: {result[:500]}")


class VectorToolTests:
    """Test vector agent tools."""
    
    @staticmethod
    async def test_execute_query():
        from agents.vector_agent.tools import VectorQueryExecutor
        
        executor = VectorQueryExecutor()
        try:
            result = await executor.execute_query(
                query="""
                    SELECT id, name, disaster_type, disaster_date 
                    FROM disasters 
                    ORDER BY disaster_date DESC 
                    LIMIT 5
                """,
                return_layer=False,
                results_description="Recent disasters"
            )
            print_result("execute_query", result)
        finally:
            executor.close()
    
    @staticmethod
    async def test_execute_query_with_geom():
        from agents.vector_agent.tools import VectorQueryExecutor
        
        executor = VectorQueryExecutor()
        try:
            result = await executor.execute_query(
                query="""
                    SELECT id, name, disaster_type, ST_AsGeoJSON(geom) as geom
                    FROM disasters 
                    WHERE geom IS NOT NULL
                    LIMIT 2
                """,
                return_layer=True,
                results_description="Disasters with geometry"
            )
            print_result("execute_query (with geom)", result)
        finally:
            executor.close()


class MapsToolTests:
    """Test maps agent tools."""
    
    @staticmethod
    async def test_geocode():
        from agents.maps_agent.tools import get_address_coordinates
        
        result = await get_address_coordinates("Empire State Building, New York")
        print_result("get_address_coordinates", result)
    
    @staticmethod
    async def test_bbox():
        from agents.maps_agent.tools import get_place_bounding_box
        
        result = await get_place_bounding_box("Manhattan, New York, USA")
        print_result("get_place_bounding_box", result)


class STACToolTests:
    """Test STAC agent tools."""
    
    @staticmethod
    async def test_collection_info():
        from agents.stac_agent.tools import get_collection_details
        
        result = await get_collection_details("sentinel-2-l2a")
        print_result("get_collection_details", result)


async def run_vector_tests():
    print("\n" + "#" * 60)
    print("# VECTOR AGENT TOOL TESTS")
    print("#" * 60)
    
    await VectorToolTests.test_execute_query()
    await VectorToolTests.test_execute_query_with_geom()


async def run_maps_tests():
    print("\n" + "#" * 60)
    print("# MAPS AGENT TOOL TESTS")
    print("#" * 60)
    
    await MapsToolTests.test_geocode()
    await MapsToolTests.test_bbox()


async def run_stac_tests():
    print("\n" + "#" * 60)
    print("# STAC AGENT TOOL TESTS")
    print("#" * 60)
    
    await STACToolTests.test_collection_info()


async def main():
    """Run all tool tests."""
    print("=" * 60)
    print("TOOL CALL TESTS")
    print("=" * 60)
    print("\nThese tests call tool functions directly without LLM.")
    
    # Uncomment the tests you want to run:
    await run_vector_tests()
    await run_maps_tests()
    await run_stac_tests()
    
    print("\n" + "=" * 60)
    print("ALL TOOL TESTS COMPLETED")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
