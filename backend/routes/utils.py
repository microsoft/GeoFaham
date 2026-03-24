# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

import pandas as pd
import geopandas as gpd
from shapely.geometry import LineString



def clusters2bounds(features):
    df = gpd.GeoDataFrame.from_features(features)
    gdf = df.dissolve(by='cluster_id')
    gdf['geometry'] = gdf.geometry.convex_hull.exterior.apply(lambda ring: LineString(ring.coords))
    cluster_analysis = {}
    for cluster_id, df_group in df.groupby('cluster_id'):
        cluster_key = cluster_id
        cluster_analysis[cluster_key] = {}
        if 'damage_status' in df_group.columns:
            cluster_analysis[cluster_key].update(df_group['damage_status'].value_counts().to_dict())
        if 'damage_pct' in df_group.columns:
            # float so .describe().to_dict()
            damage_pct_desc = {f"damage_pct_{k}": v for k, v in df_group['damage_pct'].describe().to_dict().items()}
            cluster_analysis[cluster_key].update(damage_pct_desc)
        if 'damaged' in df_group.columns:
            cluster_analysis[cluster_key].update({f"damaged_{k}": v for k, v in df_group['damaged'].value_counts().to_dict().items()})
    df1 = pd.DataFrame(cluster_analysis).T.reset_index().rename(columns={'index': 'cluster_id'})
    gdf = gdf[['geometry']].reset_index()
    gdf = gdf.merge(df1, on='cluster_id', how='left', suffixes=('', '_y'))
    return gdf.to_geo_dict()