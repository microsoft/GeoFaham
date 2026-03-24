# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

import json
import logging
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from backend.crud.db import get_conn_cursor
from backend.crud.geo import parse_geojson_to_multipolygon, coerce_to_multipolygon
from backend.crud.schemas import BuildingDamageIn, Pagination, DisasterIn, FloodMapIn

logger = logging.getLogger(__name__)
router = APIRouter()

# --------- Lookup endpoints for dropdowns (lightweight lists) ---------
@router.get('/lookups/disasters')
async def lookup_disasters(q: str | None = None, limit: int | None = None):
    sql = 'SELECT id, area, disaster_type, disaster_date FROM disasters'
    params: list = []
    if q:
        sql += ' WHERE disaster_type ILIKE %s'
        params.append(f'%{q}%')
    sql += ' ORDER BY disaster_date DESC NULLS LAST, id DESC'
    if limit:
        sql += ' LIMIT %s'
        params.append(limit)
    with get_conn_cursor() as (conn, cur):
        cur.execute(sql, tuple(params))
        rows_raw = cur.fetchall()
        cols = [c[0] for c in cur.description]
    rows = []
    for r in rows_raw:
        item = dict(zip(cols, r))
        date_part = f" ({item['disaster_date']})" if item.get('disaster_date') else ''
        item['label'] = f"{item['disaster_type']}{date_part}"
        rows.append(item)
    return rows

# Disasters
@router.get('/disasters')
async def list_disasters(page: int = 1, page_size: int = 50):
    offset = (page - 1) * page_size
    with get_conn_cursor() as (conn, cur):
        cur.execute('SELECT count(*) FROM disasters')
        total = cur.fetchone()[0]
        cur.execute('''SELECT id, disaster_type, disaster_date, description, area, city, county, state, country, updated_at
                       FROM disasters
                       ORDER BY disaster_date DESC NULLS LAST, id DESC
                       LIMIT %s OFFSET %s''', (page_size, offset))
        rows = [dict(zip([c[0] for c in cur.description], r)) for r in cur.fetchall()]
    return Pagination(total=total, items=rows, page=page, page_size=page_size)

@router.get('/disasters/{item_id}')
async def get_disaster(item_id: int):
    with get_conn_cursor() as (conn, cur):
        cur.execute('''SELECT id, disaster_type, disaster_date, description, area, city, county, state, country, updated_at,
                       ST_AsGeoJSON(geom) as geom
                       FROM disasters WHERE id=%s''', (item_id,))
        r = cur.fetchone()
        if not r:
            raise HTTPException(status_code=404, detail='Not found')
        data = dict(zip([c[0] for c in cur.description], r))
        if data.get('geom'):
            data['geojson'] = json.loads(data.pop('geom'))
    return data

@router.post('/disasters')
async def create_disaster(payload: DisasterIn):
    with get_conn_cursor() as (conn, cur):
        cur.execute('''INSERT INTO disasters (disaster_type, disaster_date, description, area, city, county, state, country)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id''',
                    (payload.disaster_type, payload.disaster_date, payload.description, 
                     payload.area, payload.city, payload.county, payload.state, payload.country))
        new_id = cur.fetchone()[0]
    return {'id': new_id}

@router.put('/disasters/{item_id}')
async def update_disaster(item_id: int, payload: DisasterIn):
    with get_conn_cursor() as (conn, cur):
        cur.execute('''UPDATE disasters
                       SET disaster_type=%s, disaster_date=%s, description=%s, area=%s, city=%s, county=%s, state=%s, country=%s
                       WHERE id=%s''',
                    (payload.disaster_type, payload.disaster_date, payload.description,
                     payload.area, payload.city, payload.county, payload.state, payload.country, item_id))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail='Not found')
    return {'status': 'ok'}

@router.delete('/disasters/{item_id}')
async def delete_disaster(item_id: int):
    with get_conn_cursor() as (conn, cur):
        cur.execute('DELETE FROM disasters WHERE id=%s', (item_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail='Not found')
    return {'status': 'deleted'}

@router.get('/building_damage')
async def list_bda(page: int = 1, page_size: int = 50):
    offset = (page - 1) * page_size
    with get_conn_cursor() as (conn, cur):
        cur.execute('SELECT count(*) FROM building_damage_assessment')
        total = cur.fetchone()[0]
        cur.execute('SELECT id, damaged, damage_pct, disaster_id FROM building_damage_assessment ORDER BY id DESC LIMIT %s OFFSET %s', (page_size, offset))
        rows = [dict(zip([c[0] for c in cur.description], r)) for r in cur.fetchall()]
    return Pagination(total=total, items=rows, page=page, page_size=page_size)

# /building_damage/json
@router.get('/building_damage/json')
async def list_bda_json(page: int = 1, page_size: int = 50):
    offset = (page - 1) * page_size
    with get_conn_cursor() as (conn, cur):
        cur.execute('SELECT count(*) FROM building_damage_assessment')
        total = cur.fetchone()[0]
        cur.execute('SELECT id, damaged, damage_pct, disaster_id, ST_AsGeoJSON(geom) as geom FROM building_damage_assessment WHERE damaged=true ORDER BY id DESC LIMIT %s OFFSET %s', (page_size, offset))
        rows = [dict(zip([c[0] for c in cur.description], r)) for r in cur.fetchall()]
    # return geojson
    features = []
    for r in rows:
        geom = r.pop('geom', None)
        if geom:
            try:
                geom_json = json.loads(geom)
            except Exception:
                geom_json = None
        features.append({
            "type": "Feature",
            "geometry": geom_json,
            "properties": r
        })
    return Pagination(total=total, items=features, page=page, page_size=page_size)



@router.get('/building_damage/{item_id}')
async def get_bda(item_id: int):
    with get_conn_cursor() as (conn, cur):
        cur.execute('SELECT id, damaged, damage_pct, disaster_id, ST_AsGeoJSON(geom) as geom FROM building_damage_assessment WHERE id=%s', (item_id,))
        r = cur.fetchone()
        if not r:
            raise HTTPException(status_code=404, detail='Not found')
        data = dict(zip([c[0] for c in cur.description], r))
        if data.get('geom'):
            data['geojson'] = json.loads(data.pop('geom'))
    return data

@router.post('/building_damage')
async def create_bda(payload: BuildingDamageIn):
    geom_sql = None
    if payload.geojson:
        try:
            geom_sql = parse_geojson_to_multipolygon(payload.geojson)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f'Invalid GeoJSON: {e}')
    with get_conn_cursor() as (conn, cur):
        cur.execute('''INSERT INTO building_damage_assessment (damaged, damage_pct, disaster_id, geom) VALUES (%s,%s,%s, ST_SetSRID(ST_GeomFromGeoJSON(%s),4326)) RETURNING id''',
                    (payload.damaged, payload.damage_pct, payload.disaster_id, geom_sql) if geom_sql else (payload.damaged, payload.damage_pct, payload.disaster_id, None))
        new_id = cur.fetchone()[0]
    return {'id': new_id}

@router.post('/building_damage/bulk_geojson')
async def bulk_building_damage(file: UploadFile = File(...), disaster_id: int = Form(...), damaged: bool | None = Form(default=None)):
    """Bulk insert building damage polygons/multipolygons from GeoJSON FeatureCollection.
    Each feature geometry is stored; optional property 'damage_pct' overrides global; if missing, uses property or null.
    Global 'damaged' flag can be provided; if damage_pct > 0 sets damaged true automatically.
    """
    logger.info("Bulk upload received: disaster_id=%s, damaged=%s", disaster_id, damaged)
    raw = await file.read()
    try:
        gj = json.loads(raw)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f'Invalid JSON: {e}')
    if gj.get('type') != 'FeatureCollection':
        raise HTTPException(status_code=400, detail='Expected FeatureCollection')
    feats = gj.get('features', [])
    if not feats:
        raise HTTPException(status_code=400, detail='No features found')
    inserted = 0
    logger.info("Features to process: %d", len(feats))
    with get_conn_cursor() as (conn, cur):
        for feat in feats:
            if not isinstance(feat, dict):
                continue
            geom = feat.get('geometry')
            props = feat.get('properties', {}) or {}
            damage_pct = props.get('damage_pct')
            try:
                if damage_pct is not None:
                    damage_pct = float(damage_pct)
            except ValueError:
                damage_pct = None
            # local_damaged = damaged
            local_damaged = props.get('damaged') or props.get('DAMAGED') or props.get('Damaged')
            local_damaged = bool(local_damaged)
            if local_damaged == False and damage_pct > 0:
                damage_pct = 0.0
            if local_damaged is None and damage_pct is not None:
                local_damaged = damage_pct > 0
            try:
                geom_json = coerce_to_multipolygon(geom)
            except Exception:
                continue
            cur.execute('''INSERT INTO building_damage_assessment (damaged, damage_pct, disaster_id, geom)
                           VALUES (%s,%s,%s, ST_SetSRID(ST_GeomFromGeoJSON(%s),4326))''',
                        (local_damaged, damage_pct, disaster_id, geom_json))
            inserted += 1
    return {'inserted_count': inserted}

@router.put('/building_damage/{item_id}')
async def update_bda(item_id: int, payload: BuildingDamageIn):
    fields = [payload.damaged, payload.damage_pct, payload.disaster_id, item_id]
    geom_clause = ''
    if payload.geojson is not None:
        try:
            geom_json = parse_geojson_to_multipolygon(payload.geojson)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        geom_clause = ', geom = ST_SetSRID(ST_GeomFromGeoJSON(%s),4326)'
        fields.insert(3, geom_json)
    with get_conn_cursor() as (conn, cur):
        cur.execute(f'UPDATE building_damage_assessment SET damaged=%s, damage_pct=%s, disaster_id=%s{geom_clause} WHERE id=%s', tuple(fields))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail='Not found')
    return {'status': 'ok'}

@router.delete('/building_damage/{item_id}')
async def delete_bda(item_id: int):
    with get_conn_cursor() as (conn, cur):
        cur.execute('DELETE FROM building_damage_assessment WHERE id=%s', (item_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail='Not found')
    return {'status': 'deleted'}

# Flood Maps
@router.get('/flood_maps')
async def list_flood_maps(page: int = 1, page_size: int = 50):
    offset = (page - 1) * page_size
    with get_conn_cursor() as (conn, cur):
        cur.execute('SELECT count(*) FROM flood_maps')
        total = cur.fetchone()[0]
        cur.execute('''SELECT id, disaster_id, source, metadata, created_at 
                       FROM flood_maps 
                       ORDER BY id DESC 
                       LIMIT %s OFFSET %s''', (page_size, offset))
        rows = [dict(zip([c[0] for c in cur.description], r)) for r in cur.fetchall()]
    return Pagination(total=total, items=rows, page=page, page_size=page_size)

@router.get('/flood_maps/json')
async def list_flood_maps_json(page: int = 1, page_size: int = 50):
    offset = (page - 1) * page_size
    with get_conn_cursor() as (conn, cur):
        cur.execute('SELECT count(*) FROM flood_maps')
        total = cur.fetchone()[0]
        cur.execute('''SELECT id, disaster_id, source, metadata, 
                       ST_AsGeoJSON(geom) as geom 
                       FROM flood_maps 
                       ORDER BY id DESC 
                       LIMIT %s OFFSET %s''', (page_size, offset))
        rows = [dict(zip([c[0] for c in cur.description], r)) for r in cur.fetchall()]
    
    features = []
    for r in rows:
        geom = r.pop('geom', None)
        if geom:
            try:
                geom_json = json.loads(geom)
            except Exception:
                geom_json = None
        features.append({
            "type": "Feature",
            "geometry": geom_json,
            "properties": r
        })
    return Pagination(total=total, items=features, page=page, page_size=page_size)

@router.get('/flood_maps/{item_id}')
async def get_flood_map(item_id: int):
    with get_conn_cursor() as (conn, cur):
        cur.execute('''SELECT id, disaster_id, source, metadata, created_at,
                       ST_AsGeoJSON(geom) as geom 
                       FROM flood_maps 
                       WHERE id=%s''', (item_id,))
        r = cur.fetchone()
        if not r:
            raise HTTPException(status_code=404, detail='Not found')
        data = dict(zip([c[0] for c in cur.description], r))
        if data.get('geom'):
            data['geojson'] = json.loads(data.pop('geom'))
    return data

@router.post('/flood_maps/upload_geojson')
async def upload_flood_map_geojson(
    file: UploadFile = File(...), 
    disaster_id: int = Form(...),
    source: str = Form(None)
):
    """Upload a GeoJSON FeatureCollection of flood map polygons.
    Features are merged into MultiPolygon records."""
    
    raw = await file.read()
    try:
        gj = json.loads(raw)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f'Invalid JSON: {e}')
    
    if gj.get('type') != 'FeatureCollection':
        raise HTTPException(status_code=400, detail='Expected FeatureCollection')
    
    features = gj.get('features', [])
    if not features:
        raise HTTPException(status_code=400, detail='No features found')
    
    # Collect all polygon coordinates and metadata
    all_polygons = []
    all_metadata = []
    
    for feature in features:
        if feature.get('type') != 'Feature':
            continue
        
        properties = feature.get('properties', {})
        geom = feature.get('geometry')
        if not geom:
            continue
        
        gtype = geom.get('type')
        if gtype == 'Polygon':
            all_polygons.append(geom['coordinates'])
        elif gtype == 'MultiPolygon':
            all_polygons.extend(geom['coordinates'])
        
        all_metadata.append(properties)
    
    if not all_polygons:
        raise HTTPException(status_code=400, detail='No valid polygon geometries found')
    
    # Create merged MultiPolygon
    multipolygon = {"type": "MultiPolygon", "coordinates": all_polygons}
    geom_json = json.dumps(multipolygon)
    metadata = {"feature_count": len(all_metadata), "properties": all_metadata}
    
    with get_conn_cursor() as (conn, cur):
        cur.execute('''INSERT INTO flood_maps (disaster_id, source, metadata, geom)
                       VALUES (%s, %s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))
                       RETURNING id''',
                    (disaster_id, source, json.dumps(metadata), geom_json))
        
        new_id = cur.fetchone()[0]
    
    return {
        'inserted_count': 1,
        'records': [{'id': new_id}]
    }

@router.put('/flood_maps/{item_id}')
async def update_flood_map(item_id: int, payload: FloodMapIn):
    fields = [payload.source, payload.disaster_id]
    
    metadata_clause = ''
    if payload.metadata is not None:
        metadata_clause = ', metadata = %s'
        fields.append(json.dumps(payload.metadata))
    
    geom_clause = ''
    if payload.geojson is not None:
        try:
            geom_json = parse_geojson_to_multipolygon(payload.geojson)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        geom_clause = ', geom = ST_SetSRID(ST_GeomFromGeoJSON(%s),4326)'
        fields.append(geom_json)
    
    fields.append(item_id)
    
    with get_conn_cursor() as (conn, cur):
        cur.execute(f'''UPDATE flood_maps 
                       SET source=%s, disaster_id=%s{metadata_clause}{geom_clause}
                       WHERE id=%s''', tuple(fields))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail='Not found')
    return {'status': 'ok'}

@router.delete('/flood_maps/{item_id}')
async def delete_flood_map(item_id: int):
    with get_conn_cursor() as (conn, cur):
        cur.execute('DELETE FROM flood_maps WHERE id=%s', (item_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail='Not found')
    return {'status': 'deleted'}
