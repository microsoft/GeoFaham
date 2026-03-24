# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Vector Query Executor

Handles PostGIS query execution with GeoJSON integration.
Refactored for clarity, maintainability, and proper error handling.
"""

import json
import os
import re
import datetime
from contextlib import contextmanager
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union

import psycopg2
import psycopg2.extras
from psycopg2 import pool
from pyproj import CRS, Transformer
from shapely import wkt
from shapely.geometry import shape, mapping
from shapely.ops import transform, unary_union
from dotenv import load_dotenv

from agents.core.types import GeoFahamToolResponse, DataType
from agents.core.config import get_config
from agents.shared.responses import (
    build_layer_response,
    build_data_response,
    build_error_response,
    build_empty_response,
)
from agents.core.constants import (
    AGENT_NAMES,
    POINT_TYPES,
    LINE_TYPES,
    POLYGON_TYPES,
    MAX_DATA_ROWS,
    MAX_RESPONSE_SIZE_BYTES,
)
from agents.core.exceptions import (
    QueryExecutionError,
    QueryValidationError,
    GeoJSONParseError,
    ResponseNotFoundError,
    ArtifactNotFoundError,
)
from agents.core.response_store import get_response_store
from agents.core.logging import get_logger
from agents.shared.geojson import results_to_geojson, generate_response_id
from agents.shared.serialization import serialize_properties

load_dotenv(override=True)

logger = get_logger("vector.executor")
AGENT_NAME = AGENT_NAMES["VECTOR_AGENT"]

# =============================================================================
# Database Connection
# =============================================================================


def _create_connection_pool() -> pool.SimpleConnectionPool:
    """Create a PostgreSQL connection pool from configuration."""
    config = get_config()
    return pool.SimpleConnectionPool(
        minconn=1,
        maxconn=20,
        user=config.database.user,
        password=config.database.password,
        host=config.database.host,
        port=config.database.port,
        database=config.database.database,
    )


# =============================================================================
# GeoJSON Parsing
# =============================================================================


def _classify_geometry_type(geom_type: str) -> str:
    """Map GeoJSON geometry type to category (points/lines/polygons)."""
    if geom_type in POINT_TYPES:
        return "points"
    elif geom_type in LINE_TYPES:
        return "lines"
    elif geom_type in POLYGON_TYPES:
        return "polygons"
    raise ValueError(f"Unknown geometry type: {geom_type}")


def _is_wkb_hex(value: str) -> bool:
    """
    Check if a string looks like WKB hex (PostGIS raw geometry output).
    
    WKB hex strings start with byte order + geometry type codes:
    - '01' or '00' for byte order
    - Followed by geometry type (e.g., '01000000' for Point, '06000000' for MultiPolygon)
    """
    if not isinstance(value, str) or len(value) < 10:
        return False
    # WKB hex is all hex characters, starts with 00 or 01, and is very long for complex geoms
    if not all(c in '0123456789abcdefABCDEF' for c in value[:20]):
        return False
    # GeoJSON starts with '{', WKB hex starts with 0 or 1
    return value[0] in '01' and not value.startswith('{')


def _validate_geometry_value(geom_value: Any, col_name: str) -> str:
    """
    Validate and normalize a geometry value from query results.
    
    Args:
        geom_value: The geometry value (should be GeoJSON string from ST_AsGeoJSON)
        col_name: Column name for error messages
        
    Returns:
        Valid GeoJSON string
        
    Raises:
        QueryExecutionError: If geometry is WKB or invalid format
    """
    if geom_value is None:
        raise QueryExecutionError(f"Geometry column '{col_name}' is NULL")
    
    if not isinstance(geom_value, str):
        raise QueryExecutionError(
            f"Geometry column '{col_name}' has unexpected type {type(geom_value).__name__}. "
            f"Use ST_AsGeoJSON() to convert geometry to JSON format."
        )
    
    # Detect WKB hex (common mistake: forgot ST_AsGeoJSON)
    if _is_wkb_hex(geom_value):
        size_bytes = len(geom_value.encode('utf-8'))
        size_mb = size_bytes / (1024 * 1024)
        raise QueryExecutionError(
            f"Geometry column '{col_name}' contains raw WKB binary ({size_mb:.1f}MB) instead of GeoJSON. "
            f"Wrap geometry output with ST_AsGeoJSON(). "
            f"Example: ST_AsGeoJSON(ST_Union(geom)) AS {col_name}"
        )
    
    # Should be valid GeoJSON - verify it starts with '{'
    if not geom_value.strip().startswith('{'):
        raise QueryExecutionError(
            f"Geometry column '{col_name}' is not valid GeoJSON. "
            f"Use ST_AsGeoJSON() to convert geometry to JSON format."
        )
    
    return geom_value


def _truncate_data_for_response(
    rows: List[Dict], 
    max_rows: int = 50,
    max_size_bytes: int = MAX_RESPONSE_SIZE_BYTES
) -> tuple[List[Dict], bool, str]:
    """
    Truncate data rows to fit within response size limits.
    
    Args:
        rows: List of data rows
        max_rows: Maximum number of rows to return
        max_size_bytes: Maximum size in bytes for the data
        
    Returns:
        Tuple of (truncated_rows, was_truncated, truncation_reason)
    """
    if not rows:
        return rows, False, ""
    
    # First apply row limit
    if len(rows) > max_rows:
        truncated = rows[:max_rows]
        return truncated, True, f"row limit ({max_rows} of {len(rows)} rows)"
    
    # Check size
    import json
    data_str = json.dumps(rows, default=str)
    if len(data_str.encode('utf-8')) <= max_size_bytes:
        return rows, False, ""
    
    # Binary search for optimal row count that fits size limit
    low, high = 1, len(rows)
    best_count = 1
    
    while low <= high:
        mid = (low + high) // 2
        test_str = json.dumps(rows[:mid], default=str)
        if len(test_str.encode('utf-8')) <= max_size_bytes:
            best_count = mid
            low = mid + 1
        else:
            high = mid - 1
    
    truncated = rows[:best_count]
    size_kb = max_size_bytes / 1024
    return truncated, True, f"size limit ({best_count} of {len(rows)} rows to fit {size_kb:.0f}KB)"


def _parse_geojson_files(paths: Union[str, List[str]]) -> Dict[str, Any]:
    """
    Parse one or more GeoJSON files into a unified structure.
    
    Returns:
        Dict with keys:
        - features: list of all features
        - features_by_type: {"points": [...], "lines": [...], "polygons": [...]}
        - feature_count: total count
    """
    if isinstance(paths, str):
        paths = [paths]
    
    all_features = []
    all_geom_types = POINT_TYPES | LINE_TYPES | POLYGON_TYPES
    
    for path in paths:
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            raise GeoJSONParseError(f"Failed to parse GeoJSON: {e}", file_path=path)
        
        if data.get("type") == "FeatureCollection":
            all_features.extend(data.get("features", []))
        elif data.get("type") == "Feature":
            all_features.append(data)
        elif data.get("type") in all_geom_types:
            # Raw geometry - wrap as Feature
            all_features.append({
                "type": "Feature",
                "geometry": data,
                "properties": {}
            })
        else:
            raise GeoJSONParseError(f"Unsupported GeoJSON type: {data.get('type')}", file_path=path)
    
    if not all_features:
        raise GeoJSONParseError("No features found in GeoJSON files")
    
    # Group by geometry type
    features_by_type = {"points": [], "lines": [], "polygons": []}
    for feature in all_features:
        geom_type = feature["geometry"]["type"]
        category = _classify_geometry_type(geom_type)
        features_by_type[category].append(feature)
    
    return {
        "features": all_features,
        "features_by_type": features_by_type,
        "feature_count": len(all_features),
    }


# =============================================================================
# SQL Generation Helpers
# =============================================================================


def _escape_sql_string(value: str) -> str:
    """Escape single quotes for SQL strings."""
    return str(value).replace("'", "''")


def _format_property_value(value: Any, prop_type: str) -> str:
    """Format a property value for SQL based on its declared type."""
    if value is None:
        return "NULL"
    
    if prop_type == "str":
        return f"'{_escape_sql_string(value)}'"
    elif prop_type in ("int", "float"):
        return str(value)
    elif prop_type == "bool":
        if isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        elif isinstance(value, str):
            return "TRUE" if value.lower() in ("true", "t", "1") else "FALSE"
        return "TRUE" if value else "FALSE"
    else:
        # Default to string
        return f"'{_escape_sql_string(value)}'"


def _get_null_typed(prop_type: str) -> str:
    """Get NULL with appropriate SQL type cast."""
    type_map = {
        "str": "NULL::text",
        "int": "NULL::integer",
        "float": "NULL::float",
        "bool": "NULL::boolean",
    }
    return type_map.get(prop_type, "NULL::text")


def _geojson_to_postgis(geometry: Dict[str, Any]) -> str:
    """Convert GeoJSON geometry to PostGIS ST_GeomFromGeoJSON expression."""
    return f"ST_GeomFromGeoJSON('{json.dumps(geometry)}')"


def _normalize_property_type(ptype: Any) -> str:
    """Extract type string from property_keys value (handles nested dict or plain string)."""
    if isinstance(ptype, dict):
        return ptype.get("type", "str")
    return str(ptype)


def _resolve_response_ids(response_ids: List[str]) -> tuple[List[str], Dict[str, Dict[str, str]]]:
    """
    Resolve response_ids to geojson_paths and property_keys using the response store.
    
    Args:
        response_ids: List of response IDs from previous agent outputs
        
    Returns:
        Tuple of (geojson_paths, merged_property_keys)
        
    Raises:
        ResponseNotFoundError: If response ID not found
        ArtifactNotFoundError: If response has no artifact
    """
    store = get_response_store()
    geojson_paths = []
    merged_property_keys = {"points": {}, "lines": {}, "polygons": {}}
    
    for rid in response_ids:
        response = store.get(rid)  # Raises ResponseNotFoundError if not found
        
        artifact = response.artifact
        if artifact is None:
            raise ArtifactNotFoundError(rid)
        
        geojson_paths.append(artifact.path)
        
        # Merge property_keys from artifact
        if artifact.property_keys:
            for geom_type in ["points", "lines", "polygons"]:
                if geom_type in artifact.property_keys:
                    # Extract just the type string from nested dicts if needed
                    for prop_name, prop_info in artifact.property_keys[geom_type].items():
                        merged_property_keys[geom_type][prop_name] = _normalize_property_type(prop_info)
    
    return geojson_paths, merged_property_keys


def _build_cte_for_geometry_type(
    features: List[Dict],
    cte_name: str,
    property_keys: Dict[str, str]
) -> str:
    """
    Build a CTE (Common Table Expression) for a list of features.
    
    Args:
        features: List of GeoJSON features
        cte_name: Name of the CTE (e.g., 'points_from_geojson')
        property_keys: Dict mapping property names to types (e.g., {'name': 'str'} or {'name': {'type': 'str', ...}})
    
    Returns:
        SQL CTE definition string
    """
    if not features:
        # Empty CTE with correct column structure
        if property_keys:
            null_values = [_get_null_typed(_normalize_property_type(t)) for t in property_keys.values()]
            columns = f"id, {', '.join(property_keys.keys())}, geom"
            return f"{cte_name}({columns}) AS (SELECT NULL::integer AS id, {', '.join(null_values)}, NULL::geometry AS geom WHERE FALSE)"
        else:
            return f"{cte_name}(id, name, type, geom) AS (SELECT NULL::integer, NULL::text, NULL::text, NULL::geometry WHERE FALSE)"
    
    values = []
    for i, feature in enumerate(features):
        geom_sql = _geojson_to_postgis(feature["geometry"])
        props = feature.get("properties", {})
        
        if property_keys:
            prop_values = [
                _format_property_value(props.get(name), _normalize_property_type(ptype))
                for name, ptype in property_keys.items()
            ]
            values.append(f"({i + 1}, {', '.join(prop_values)}, {geom_sql})")
            columns = f"id, {', '.join(property_keys.keys())}, geom"
        else:
            # Default columns
            name = _escape_sql_string(props.get("name", f"Feature_{i + 1}"))
            type_val = _escape_sql_string(props.get("type", props.get("category", "unknown")))
            values.append(f"({i + 1}, '{name}', '{type_val}', {geom_sql})")
            columns = "id, name, type, geom"
    
    return f"{cte_name}({columns}) AS (VALUES {', '.join(values)})"


# =============================================================================
# Placeholder Processing
# =============================================================================

# Compiled regex patterns for placeholder detection
_PATTERN_POINTS = re.compile(r"\{+\s*GEOJSON_POINTS_CTE\s*\}+")
_PATTERN_LINES = re.compile(r"\{+\s*GEOJSON_LINES_CTE\s*\}+")
_PATTERN_POLYGONS = re.compile(r"\{+\s*GEOJSON_POLYGONS_CTE\s*\}+")
_PATTERN_ALL = re.compile(r"\{+\s*GEOJSON_GEOMTYPE_CTES\s*\}+")


def _process_geojson_placeholders(
    query: str,
    geom_info: Dict[str, Any],
    property_keys: Optional[Dict[str, Dict[str, str]]]
) -> str:
    """
    Replace GeoJSON placeholders in query with actual CTEs.
    
    Placeholders:
    - {{GEOJSON_POINTS_CTE}} -> points_from_geojson CTE
    - {{GEOJSON_LINES_CTE}} -> lines_from_geojson CTE
    - {{GEOJSON_POLYGONS_CTE}} -> polygons_from_geojson CTE
    - {{GEOJSON_GEOMTYPE_CTES}} -> all applicable CTEs
    """
    if geom_info.get("feature_count", 0) == 0:
        return query
    
    features_by_type = geom_info.get("features_by_type", {})
    property_keys = property_keys or {}
    
    points_props = property_keys.get("points", {})
    lines_props = property_keys.get("lines", {})
    polygons_props = property_keys.get("polygons", {})
    
    
    result = query
    
    # Individual CTEs
    if _PATTERN_POINTS.search(result):
        cte = _build_cte_for_geometry_type(
            features_by_type.get("points", []), "points_from_geojson", points_props
        )
        result = _PATTERN_POINTS.sub(cte, result)
    
    if _PATTERN_LINES.search(result):
        cte = _build_cte_for_geometry_type(
            features_by_type.get("lines", []), "lines_from_geojson", lines_props
        )
        result = _PATTERN_LINES.sub(cte, result)
    
    if _PATTERN_POLYGONS.search(result):
        cte = _build_cte_for_geometry_type(
            features_by_type.get("polygons", []), "polygons_from_geojson", polygons_props
        )
        result = _PATTERN_POLYGONS.sub(cte, result)
    
    # Combined CTEs
    if _PATTERN_ALL.search(result):
        ctes = []
        if features_by_type.get("points"):
            ctes.append(_build_cte_for_geometry_type(
                features_by_type["points"], "points_from_geojson", points_props
            ))
        if features_by_type.get("lines"):
            ctes.append(_build_cte_for_geometry_type(
                features_by_type["lines"], "lines_from_geojson", lines_props
            ))
        if features_by_type.get("polygons"):
            ctes.append(_build_cte_for_geometry_type(
                features_by_type["polygons"], "polygons_from_geojson", polygons_props
            ))
        
        ctes_sql = ", ".join(ctes) if ctes else "empty_cte(id) AS (SELECT NULL::integer WHERE FALSE)"
        result = _PATTERN_ALL.sub(ctes_sql, result)
    
    return result


# =============================================================================
# Query Safety Validation
# =============================================================================

# Compiled regex pattern for forbidden SQL keywords with word boundaries
_FORBIDDEN_PATTERN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE)\b",
    re.IGNORECASE
)

# Patterns to strip SQL comments before safety check
_SQL_LINE_COMMENT = re.compile(r"--[^\n]*")
_SQL_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def _strip_sql_comments(query: str) -> str:
    """Remove SQL comments (-- and /* */) from query."""
    result = _SQL_BLOCK_COMMENT.sub("", query)
    result = _SQL_LINE_COMMENT.sub("", result)
    return result


def _is_safe_query(query: str) -> bool:
    """
    Check if query is read-only (SELECT only).
    
    Uses word-boundary matching and strips comments to avoid false positives
    from words like 'create' in comments or 'alter' in data values.
    """
    # Strip comments first - they may contain words like "create", "update"
    query_no_comments = _strip_sql_comments(query)
    return _FORBIDDEN_PATTERN.search(query_no_comments) is None


# =============================================================================
# Main Executor Class
# =============================================================================


class VectorQueryExecutor:
    """
    Execute PostGIS queries with optional GeoJSON integration.
    
    Provides:
    - execute_query: Run SELECT queries, optionally with GeoJSON CTEs
    - execute_query_with_geojson: Convenience wrapper requiring GeoJSON
    - get_schema_info: Retrieve database schema
    - get_list_of_disasters: Get available disasters
    
    Uses connection pooling with proper resource management.
    """
    
    def __init__(self):
        self._pool = _create_connection_pool()
        self._conn = None
    
    @contextmanager
    def _get_connection(self):
        """Context manager for database connections."""
        conn = self._pool.getconn()
        try:
            yield conn
        finally:
            self._pool.putconn(conn)
    
    def _get_or_create_connection(self):
        """Get persistent connection for backward compatibility."""
        if self._conn is None:
            self._conn = self._pool.getconn()
        return self._conn
    
    def close(self, close_pool: bool = False):
        """Return connection to pool and optionally close pool."""
        if self._conn is not None:
            self._pool.putconn(self._conn)
            self._conn = None
        if close_pool:
            self._pool.closeall()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    # =========================================================================
    # Schema and Metadata
    # =========================================================================
    
    def get_schema_info(self) -> str:
        """Get database schema as JSON string (cached to file)."""
        config = get_config()
        schema_path = str(config.paths.schema_cache_path)
        
        try:
            with open(schema_path, "r") as f:
                return json.dumps(json.load(f), indent=2)
        except FileNotFoundError:
            pass
        
        # Fetch from database
        query = """
        SELECT
            cols.table_schema,
            cols.table_name,
            cols.column_name,
            cols.data_type,
            cols.is_nullable,
            cons.constraint_type,
            cons.constraint_name,
            fk.references_table AS referenced_table,
            fk.references_column AS referenced_column
        FROM information_schema.columns cols
        LEFT JOIN information_schema.key_column_usage kcu
            ON cols.table_schema = kcu.table_schema
            AND cols.table_name = kcu.table_name
            AND cols.column_name = kcu.column_name
        LEFT JOIN information_schema.table_constraints cons
            ON kcu.table_schema = cons.table_schema
            AND kcu.table_name = cons.table_name
            AND kcu.constraint_name = cons.constraint_name
        LEFT JOIN (
            SELECT
                rc.constraint_name,
                kcu.table_name AS references_table,
                kcu.column_name AS references_column
            FROM information_schema.referential_constraints rc
            JOIN information_schema.key_column_usage kcu
                ON rc.unique_constraint_name = kcu.constraint_name
        ) fk ON cons.constraint_name = fk.constraint_name
        WHERE cols.table_schema = 'public'
        ORDER BY cols.table_schema, cols.table_name, cols.ordinal_position;
        """
        
        conn = self._get_or_create_connection()
        with conn.cursor() as cur:
            cur.execute(query)
            columns = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
        
        schema_info = [dict(zip(columns, row)) for row in rows]
        
        # Serialize datetime objects
        for item in schema_info:
            for k, v in item.items():
                if hasattr(v, "isoformat"):
                    item[k] = v.isoformat()
        
        # Cache to file
        with open(schema_path, "w") as f:
            json.dump(schema_info, f)
        
        return json.dumps(schema_info, indent=2)
    
    def get_list_of_disasters(self, return_dict: bool = False) -> Union[str, tuple]:
        """Get list of disasters from database."""
        query = """
        SELECT 
            d.*,
            CASE WHEN EXISTS (SELECT 1 FROM building_damage_assessment WHERE disaster_id = d.id) 
                THEN 'yes' ELSE 'no' END AS has_building_damage_assessment_map,
            CASE WHEN EXISTS (SELECT 1 FROM flood_maps WHERE disaster_id = d.id) 
                THEN 'yes' ELSE 'no' END AS has_flood_maps
        FROM disasters d
        ORDER BY d.disaster_date DESC NULLS LAST, d.id DESC
        """
        
        conn = self._get_or_create_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(query)
            rows = cur.fetchall()
        
        result = []
        for row in rows:
            row_dict = dict(row)
            # Simplify geometry representation
            if "geom" in row_dict:
                row_dict["geom"] = "[geometry exists in database]"
            # Serialize datetime objects
            for k, v in row_dict.items():
                if isinstance(v, (datetime.datetime, datetime.date)):
                    row_dict[k] = v.isoformat()
            result.append(row_dict)
        
        if return_dict:
            return json.dumps(result), result
        return json.dumps(result)
    
    # =========================================================================
    # Query Execution
    # =========================================================================
    
    async def _execute_query_impl(
        self,
        query: str,
        return_layer: bool,
        results_description: str,
        return_aggregated_data: bool = False,
    ) -> str:
        """
        Internal query execution - assumes safety already verified.
        
        Not exposed to LLM. Use execute_query or execute_query_with_geojson instead.
        """
        response_id = generate_response_id()
        conn = self._get_or_create_connection()
        
        # Execute query
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute(query)
                rows = [dict(r) for r in cur.fetchall()]
        except psycopg2.Error as e:
            conn.rollback()
            logger.error(f"Database error: {e}", extra={"query": query[:200]})
            return self._error_response(response_id, f"Database error: {e}")
        
        if not rows:
            return build_empty_response(
                source=AGENT_NAME,
                summary="No data found.",
                response_id=response_id,
            )
        
        # Process results
        return await self._process_results(
            rows, response_id, results_description, return_layer, return_aggregated_data
        )
    
    async def execute_query(
        self,
        query: str,
        return_layer: bool,
        results_description: str,
        return_aggregated_data: bool = False,
    ) -> str:
        """
        Execute a PostGIS SELECT query.
        
        Args:
            query: SQL SELECT statement
            return_layer: If True and geometry present, return GeoJSON layer
            results_description: Human-readable description of results
            return_aggregated_data: If True, return both data and layer for aggregated queries
        
        Returns:
            JSON string of GeoFahamToolResponse
        """
        # Normalize escaped newlines/tabs that may come through from LLM function calls
        query = query.replace('\\n', '\n').replace('\\t', '\t')
        
        # Safety check on user-provided query
        if not _is_safe_query(query):
            return self._error_response(generate_response_id(), "Only SELECT queries are allowed.")
        
        return await self._execute_query_impl(query, return_layer, results_description, return_aggregated_data)
    
    async def execute_query_with_geojson(
        self,
        query: str,
        return_layer: bool,
        results_description: str,
        response_ids: List[str],
        return_aggregated_data: bool = False,
    ) -> str:
        """
        Execute query with GeoJSON integration using response IDs.
        
        Automatically resolves paths and property_keys from the response store
        using the provided response IDs. This simplifies usage - just pass the
        response IDs from previous agent outputs.
        
        Args:
            query: SQL with GeoJSON placeholders (e.g., {{GEOJSON_POINTS_CTE}})
            return_layer: If True, return GeoJSON layer for map visualization
            results_description: Human-readable description of results
            response_ids: List of response IDs from previous agent outputs.
                The geojson paths and property_keys are automatically resolved.
            return_aggregated_data: If True, return both layer and tabular data
        
        Returns:
            JSON string of GeoFahamToolResponse
        """
        resp_id = generate_response_id()
        
        # Normalize escaped newlines/tabs that may come through from LLM function calls
        query = query.replace('\\n', '\n').replace('\\t', '\t')
        
        if not response_ids:
            return self._error_response(resp_id, "response_ids is required.")
        
        # Safety check on raw template query BEFORE expanding placeholders
        # This prevents false positives from GeoJSON property values (e.g., "Walters Lane" contains "ALTER")
        if not _is_safe_query(query):
            return self._error_response(resp_id, "Only SELECT queries are allowed.")
        
        try:
            geojson_paths, property_keys = _resolve_response_ids(response_ids)
        except Exception as e:
            return self._error_response(resp_id, f"Failed to resolve response IDs: {e}")
        
        # Process GeoJSON placeholders
        try:
            geom_info = _parse_geojson_files(geojson_paths)
            enhanced_query = _process_geojson_placeholders(query, geom_info, property_keys)
        except Exception as e:
            return self._error_response(resp_id, f"GeoJSON processing error: {e}")
        
        # Call internal impl directly - safety already verified on template
        return await self._execute_query_impl(
            enhanced_query, return_layer, results_description, return_aggregated_data
        )
    
    # =========================================================================
    # Result Processing
    # =========================================================================
    
    async def _process_results(
        self,
        rows: List[Dict],
        response_id: str,
        description: str,
        return_layer: bool,
        return_aggregated_data: bool,
    ) -> str:
        """Process query results into appropriate response format."""
        # Detect geometry columns
        geom_col = self._find_geometry_column(rows[0])
        has_feature = "feature" in rows[0]
        
        if (geom_col or has_feature) and return_layer:
            return await self._build_layer_response(
                rows, response_id, description, geom_col, has_feature, return_aggregated_data
            )
        else:
            return self._build_data_response(rows, response_id, description, geom_col)
    
    def _find_geometry_column(self, row: Dict) -> Optional[str]:
        """Find geometry column in result row."""
        # First check by column name
        for key in row.keys():
            if any(term in key.lower() for term in ("geom", "geometry", "geojson", "_aoi")):
                return key
        
        # Also check by value content (detect WKB hex or GeoJSON)
        for key, value in row.items():
            if isinstance(value, str):
                # Check for WKB hex pattern
                if _is_wkb_hex(value):
                    return key
                # Check for GeoJSON pattern
                if value.strip().startswith('{"type":'):
                    return key
        return None
    
    async def _build_layer_response(
        self,
        rows: List[Dict],
        response_id: str,
        description: str,
        geom_col: Optional[str],
        has_feature: bool,
        return_aggregated_data: bool,
    ) -> str:
        """Build GeoJSON layer response."""
        features = []
        effective_geom_col = geom_col or "geom"
        
        for row in rows:
            if has_feature and "feature" in row:
                # Pre-built feature objects
                feature = row["feature"]
                if isinstance(feature, str):
                    feature = json.loads(feature)
                self._serialize_properties(feature.get("properties", {}))
                features.append(feature)
            else:
                # Build feature from geometry column
                geom = row.get(geom_col) if geom_col else row.get("geom") or row.get("geometry")
                if geom is None:
                    continue
                
                # Validate geometry format and size
                try:
                    geom = _validate_geometry_value(geom, effective_geom_col)
                except QueryExecutionError as e:
                    return self._error_response(response_id, str(e))
                
                props = {k: v for k, v in row.items() if k not in (geom_col, "geom", "geometry", "metadata")}
                self._serialize_properties(props)
                
                features.append({
                    "type": "Feature",
                    "geometry": json.loads(geom) if isinstance(geom, str) else geom,
                    "properties": props,
                })
        
        fc = {"type": "FeatureCollection", "features": features}
        artifact = await results_to_geojson(fc, compute_stats=True)
        
        if isinstance(artifact, str):
            return self._error_response(response_id, artifact)
        
        if return_aggregated_data:
            # Remove geometry columns from data rows for aggregated responses
            clean_rows = []
            for row in rows:
                clean = {k: v for k, v in row.items() if k not in (geom_col, "geom", "geometry", "feature")}
                self._serialize_properties(clean)
                clean_rows.append(clean)
            
            # Truncate to fit response size limits
            truncated_rows, was_truncated, reason = _truncate_data_for_response(clean_rows, max_rows=100)
            
            truncation_note = ""
            if was_truncated:
                truncation_note = f" (showing {len(truncated_rows)} of {len(clean_rows)} rows due to {reason}; full data in artifact file)"
            
            return build_layer_response(
                source=AGENT_NAME,
                artifact_path=artifact.path,
                summary=description + truncation_note,
                response_id=response_id,
                features_count=artifact.features_count,
                stats=artifact.stats,
                property_keys=artifact.property_keys,
                geom_types=artifact.geom_types,
                data=truncated_rows,
            )
        else:
            return build_layer_response(
                source=AGENT_NAME,
                artifact_path=artifact.path,
                summary=description,
                response_id=response_id,
                features_count=artifact.features_count,
                stats=artifact.stats,
                property_keys=artifact.property_keys,
                geom_types=artifact.geom_types,
            )
    
    def _build_data_response(
        self,
        rows: List[Dict],
        response_id: str,
        description: str,
        geom_col: Optional[str],
    ) -> str:
        """Build tabular data response."""
        # Remove geometry columns from data response
        clean_rows = []
        for row in rows:
            clean = {k: v for k, v in row.items() if k not in (geom_col, "geom", "geometry", "feature")}
            self._serialize_properties(clean)
            clean_rows.append(clean)
        
        # Truncate to fit response size limits
        truncated_rows, was_truncated, reason = _truncate_data_for_response(clean_rows)
        
        if was_truncated:
            summary = f"{description} (showing {len(truncated_rows)} of {len(rows)} rows due to {reason})"
        else:
            summary = description
            
        return build_data_response(
            source=AGENT_NAME,
            data=truncated_rows,
            summary=summary,
            response_id=response_id,
            data_type=DataType.TABULAR,
        )
    
    def _serialize_properties(self, props: Dict) -> None:
        """Convert datetime objects to ISO format in-place."""
        serialize_properties(props)
    
    def _error_response(self, response_id: str, message: str) -> str:
        """Create error response."""
        logger.warning(f"Query error: {message}")
        return build_error_response(source=AGENT_NAME, error_message=message, response_id=response_id)
    
    # =========================================================================
    # Spatial Geometry Operations
    # =========================================================================
    
    async def create_buffer(
        self,
        response_ids: List[str],
        distance: float,
        distance_unit: Literal["kilometers", "meters", "miles"] = "kilometers",
        merge_results: bool = True,
        results_description: str = "Buffer polygon",
    ) -> str:
        """
        Create buffer polygon(s) around input geometries.
        
        This tool creates distance-based buffer polygons around point, line, or polygon
        geometries. Use this when queries require "within X distance of" analysis.
        
        Args:
            response_ids: List of response IDs containing source geometries.
                Can be points, lines, or polygons from any agent.
            distance: Buffer distance (positive number).
            distance_unit: Unit for distance - "kilometers", "meters", or "miles".
                Defaults to "kilometers".
            merge_results: If True (default), merge all buffers into a single polygon.
                If False, create separate buffer for each input feature.
            results_description: Human-readable description of the buffer output.
        
        Returns:
            JSON string of GeoFahamToolResponse with buffer polygon GeoJSON.
        
        Examples:
            - 50km buffer around a point: distance=50, distance_unit="kilometers"
            - 500m buffer around a road: distance=500, distance_unit="meters"
            - 2 mile buffer around multiple POIs: distance=2, distance_unit="miles"
        """
        response_id = generate_response_id()
        
        # Validate inputs
        if not response_ids:
            return self._error_response(response_id, "response_ids is required.")
        
        if distance <= 0:
            return self._error_response(response_id, "distance must be a positive number.")
        
        # Convert distance to meters for consistent processing
        distance_meters = self._convert_to_meters(distance, distance_unit)
        
        # Resolve response IDs to get geometries
        try:
            geojson_paths, _ = _resolve_response_ids(response_ids)
        except Exception as e:
            return self._error_response(response_id, f"Failed to resolve response IDs: {e}")
        
        # Parse GeoJSON files
        try:
            geom_info = _parse_geojson_files(geojson_paths)
        except Exception as e:
            return self._error_response(response_id, f"Failed to parse GeoJSON: {e}")
        
        features = geom_info.get("features", [])
        if not features:
            return self._error_response(response_id, "No features found in input geometries.")
        
        # Create buffers using pure Python (shapely + pyproj)
        try:
            buffer_features = self._create_buffers(
                features, distance_meters, merge_results
            )
        except Exception as e:
            logger.error(f"Buffer creation failed: {e}")
            return self._error_response(response_id, f"Buffer creation failed: {e}")
        
        # Build feature collection
        fc = {"type": "FeatureCollection", "features": buffer_features}
        
        # Save artifact
        artifact = await results_to_geojson(fc, compute_stats=True)
        if isinstance(artifact, str):
            return self._error_response(response_id, artifact)
        
        # Build summary
        input_count = len(features)
        output_count = len(buffer_features)
        unit_label = distance_unit.rstrip("s")  # "kilometers" -> "kilometer"
        summary = f"{results_description}: {distance} {unit_label} buffer around {input_count} feature(s)"
        if merge_results and input_count > 1:
            summary += " (merged into single polygon)"
        
        return build_layer_response(
            source=AGENT_NAME,
            artifact_path=artifact.path,
            summary=summary,
            response_id=response_id,
            features_count=artifact.features_count,
            stats=artifact.stats,
            property_keys=artifact.property_keys,
            geom_types=artifact.geom_types,
        )
    
    def _convert_to_meters(self, distance: float, unit: str) -> float:
        """Convert distance to meters."""
        conversions = {
            "meters": 1.0,
            "kilometers": 1000.0,
            "miles": 1609.344,
        }
        return distance * conversions.get(unit, 1000.0)
    
    def _create_buffers(
        self,
        features: List[Dict],
        distance_meters: float,
        merge: bool
    ) -> List[Dict]:
        """
        Create buffer polygons around features using shapely.
        
        Uses UTM projection for accurate distance-based buffering.
        """
        buffered_geoms = []
        
        for feature in features:
            geom = feature.get("geometry")
            if not geom:
                continue
            
            # Convert GeoJSON to shapely geometry
            shp_geom = shape(geom)
            
            # Get centroid for UTM zone calculation
            centroid = shp_geom.centroid
            utm_crs = self._get_utm_crs(centroid.y, centroid.x)
            
            # Create transformers
            wgs84 = CRS.from_epsg(4326)
            to_utm = Transformer.from_crs(wgs84, utm_crs, always_xy=True)
            to_wgs84 = Transformer.from_crs(utm_crs, wgs84, always_xy=True)
            
            # Transform to UTM, buffer, transform back
            projected = transform(to_utm.transform, shp_geom)
            buffered = projected.buffer(distance_meters)
            result = transform(to_wgs84.transform, buffered)
            
            buffered_geoms.append((result, feature.get("properties", {})))
        
        if not buffered_geoms:
            return []
        
        if merge and len(buffered_geoms) > 1:
            # Merge all buffers into single geometry
            merged = unary_union([g for g, _ in buffered_geoms])
            return [{
                "type": "Feature",
                "geometry": mapping(merged),
                "properties": {
                    "buffer_distance_m": distance_meters,
                    "source_features": len(buffered_geoms),
                    "buffer_type": "merged"
                }
            }]
        else:
            # Return individual buffers
            result_features = []
            for i, (geom, props) in enumerate(buffered_geoms):
                result_features.append({
                    "type": "Feature",
                    "geometry": mapping(geom),
                    "properties": {
                        **props,
                        "buffer_distance_m": distance_meters,
                        "buffer_type": "individual"
                    }
                })
            return result_features
    
    def _get_utm_crs(self, lat: float, lon: float) -> CRS:
        """Get appropriate UTM CRS for a given lat/lon."""
        # Calculate UTM zone
        zone = int((lon + 180) // 6) + 1
        # Northern or southern hemisphere
        if lat >= 0:
            epsg = 32600 + zone  # Northern hemisphere
        else:
            epsg = 32700 + zone  # Southern hemisphere
        return CRS.from_epsg(epsg)
