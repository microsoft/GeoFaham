// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

/**
 * Layer Renderer Module
 * Handles rendering of different layer types (vector, raster, temporal)
 */

const LayerRenderer = {
    /**
     * Render a vector layer (GeoJSON)
     */
    renderVectorLayer: function(content) {
        const geojson = content.data;
        const source = content.source || 'assistant';
        const state = GeoFahamState;
        const map = state.map;
        
        // Safety check for GeoJSON data
        if (!geojson || !geojson.features) {
            console.error('Invalid GeoJSON data:', geojson);
            ChatUI.displayMessage('Error: Invalid or missing GeoJSON data for vector layer.', 'error');
            return;
        }
        
        // Create unique IDs
        const layerId = `layer-${Date.now()}`;
        const dataSourceId = `source-${Date.now()}`;

        // Create new data source
        const newDataSource = new atlas.source.DataSource(dataSourceId);
        map.sources.add(newDataSource);

        // Get first feature to determine geometry type
        const firstFeature = geojson.features[0];
        if (!firstFeature) {
            ChatUI.displayMessage('No features found in the data.', 'error');
            return;
        }

        const geometryType = firstFeature.geometry.type;

        // Check for GeometryCollection - needs special handling
        if (geometryType === 'GeometryCollection') {
            console.log('Detected GeometryCollection structure');
            this._handleGeometryCollection(geojson, newDataSource, layerId, source, content);
            return;
        }

        // Standard GeoJSON processing
        newDataSource.add(geojson);

        // Fit map to data bounds
        const bounds = atlas.data.BoundingBox.fromData(geojson);
        MapInit.fitToBounds(bounds);

        let layer;

        switch (geometryType) {
            case 'Point':
            case 'MultiPoint':
                layer = this._createPointLayer(newDataSource, layerId, firstFeature.properties);
                break;
            case 'LineString':
            case 'MultiLineString':
                layer = this._createLineLayer(newDataSource, layerId);
                break;
            case 'Polygon':
            case 'MultiPolygon':
                layer = this._createPolygonLayer(newDataSource, layerId, firstFeature.properties, source);
                break;
            default:
                ChatUI.displayMessage(`Unsupported geometry type: ${geometryType}`, 'error');
                return;
        }

        map.layers.add(layer);

        const layerTitle = content.meta && content.meta.layer_name ? content.meta.layer_name : `Layer ${layerId}`;
        
        // Add click events for popups
        this._addLayerInteractions(layer, layerId);

        // Add to layer control
        LayerControls.addLayerToControl(layerId, layer, layerTitle);

        // Check for damage_pct to show legend
        const hasDamagePercentage = geojson.features.some(feature => 
            feature.properties && typeof feature.properties.damage_pct === 'number'
        );
        
        if (hasDamagePercentage && geometryType.includes('Polygon')) {
            this._showDamageLegend();
        }

        ChatUI.displayMessage(`Layer added: ${geojson.features.length} ${geometryType.toLowerCase()} features`, 'system');
    },

    /**
     * Render a raster layer
     * Handles normalized message structure where raster info may be in metadata or data
     */
    renderRasterLayer: function(content) {
        console.log('Rendering raster layer:', content);
        
        // Get raster data from normalized structure (metadata for rasters, data for direct)
        const rasterData = content.metadata || content.data || {};
        
        // Handle single_layer structure from raster_ops_agent
        let layerInfo = rasterData;
        if (rasterData.data && Array.isArray(rasterData.data) && rasterData.data[0]) {
            layerInfo = rasterData.data[0];
        } else if (rasterData.layers && rasterData.layers.length > 0) {
            layerInfo = rasterData.layers[0];
        }
        
        const { url, title, bounds, colormap, rescale_min, rescale_max, minzoom, maxzoom, class_labels, statistics, min_scale, max_scale } = layerInfo;
        const map = GeoFahamState.map;
        
        // Create unique layer ID
        const layerId = `raster-${Date.now()}`;
        
        // Determine rescale values (handle both naming conventions)
        let effectiveRescaleMin = rescale_min ?? min_scale;
        let effectiveRescaleMax = rescale_max ?? max_scale;
        
        if (statistics && (effectiveRescaleMin === undefined || effectiveRescaleMax === undefined)) {
            effectiveRescaleMin = statistics.min;
            effectiveRescaleMax = statistics.max;
            console.log(`Using statistics for rescaling: ${effectiveRescaleMin} to ${effectiveRescaleMax}`);
        }
        
        // Build TiTiler tile URL
        let tileUrl = `/tiles/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png?url=${encodeURIComponent(url)}`;
        
        if (colormap) {
            tileUrl += `&colormap_name=${colormap}`;
        }
        if (effectiveRescaleMin !== undefined && effectiveRescaleMin !== null && 
            effectiveRescaleMax !== undefined && effectiveRescaleMax !== null) {
            tileUrl += `&rescale=${effectiveRescaleMin},${effectiveRescaleMax}`;
        }
        
        console.log('Tile URL template:', tileUrl);
        
        // Create tile layer
        const rasterLayer = new atlas.layer.TileLayer({
            tileUrl: tileUrl,
            tileSize: 256,
            minSourceZoom: minzoom || 0,
            maxSourceZoom: maxzoom || 18,
            opacity: 1.0,
            visible: true
        }, layerId);
        
        // Add layer to map
        map.layers.add(rasterLayer, 'labels');
        
        console.log('Raster layer added to map:', layerId);
        
        // Register raster layer
        if (typeof registerRasterLayer === 'function') {
            registerRasterLayer(layerId, {
                url: url,
                title: title || 'Raster Layer',
                bounds: bounds,
                colormap: colormap,
                rescale_min: effectiveRescaleMin,
                rescale_max: effectiveRescaleMax,
                minzoom: minzoom,
                maxzoom: maxzoom,
                class_labels: class_labels || null,
                statistics: statistics || null
            });
        }
        
        // Store metadata for screenshot analysis
        GeoFahamState.rasterMetadataRegistry.store(layerId, {
            type: 'raster',
            title: title || 'Raster Layer',
            url: url,
            colormap: colormap,
            rescale: (rescale_min !== undefined && rescale_max !== undefined) 
                ? `${rescale_min},${rescale_max}` 
                : null,
            bands: data.bands || null,
            bounds: bounds,
            source: 'COG',
            rendering_type: colormap ? 'single_band_colormap' : 'rgb'
        });
        
        // Fit map to raster bounds
        if (bounds && bounds.length === 4) {
            const bbox = new atlas.data.BoundingBox(bounds);
            MapInit.fitToBounds(bbox);
        }
        
        // Add to layer control
        LayerControls.addLayerToControl(layerId, rasterLayer, title || 'Raster Layer', null, true);
        
        ChatUI.displayMessage(`Raster layer added: ${title || 'Raster'}`, 'system');
    },

    /**
     * Render temporal mosaic
     */
    renderTemporalMosaic: function(content) {
        console.log('Rendering temporal mosaic:', content);
        
        const manager = GeoFahamState.temporalMosaicManager || window.temporalMosaicManager;
        
        if (!manager) {
            console.error('Temporal mosaic manager not initialized');
            ChatUI.displayMessage('Error: Temporal mosaic manager not available', 'error');
            return;
        }
        
        try {
            manager.renderTemporalMosaic(content);
        } catch (error) {
            console.error('Error rendering temporal mosaic:', error);
            ChatUI.displayMessage(`Error rendering temporal mosaic: ${error.message}`, 'error');
        }
    },

    /**
     * Render STAC item tiles
     */
    renderSTACItemTiles: function(content) {
        console.log('=== renderSTACItemTiles called ===');
        
        const { metadata, artifact } = content;
        const { stac_item_tiles, visualization_hints, collections, item_count } = metadata;
        const map = GeoFahamState.map;
        
        if (!stac_item_tiles || Object.keys(stac_item_tiles).length === 0) {
            console.error('No STAC item tiles found in response');
            ChatUI.displayMessage('Error: No STAC item tiles available for multi-band rendering', 'error');
            return;
        }
        
        // Get visualization info
        const vizHints = visualization_hints?.layers?.[0] || {};
        const bands = vizHints.bands || [];
        const collectionId = vizHints.collection_id || 'unknown';
        
        // Get sorted timestamps
        const timestamps = Object.keys(stac_item_tiles).sort();
        console.log('Sorted timestamps:', timestamps);
        
        const addedLayers = [];
        const bbox = metadata.bbox || (metadata.query_params && metadata.query_params.bbox);
        
        // Add tile layers for each timestamp
        timestamps.forEach((timestamp, groupIdx) => {
            const groupData = stac_item_tiles[timestamp];
            const items = groupData.items || [];
            
            items.forEach((item, itemIdx) => {
                const layerId = `stac-item-${collectionId}-${groupIdx}-${itemIdx}-${Date.now()}`;
                const tileUrl = item.tile_url_template;
                
                const layer = new atlas.layer.TileLayer({
                    tileUrl: tileUrl,
                    tileSize: 256,
                    minSourceZoom: 8,
                    maxSourceZoom: 14,
                    opacity: 1,
                    visible: groupIdx === timestamps.length - 1
                }, layerId);
                
                map.layers.add(layer, 'labels');
                addedLayers.push({ layerId, layer, timestamp, itemId: item.item_id });
            });
        });
        
        // Store for timeline control
        const manager = window.temporalMosaicManager;
        if (manager) {
            manager.mosaicData = {
                stac_item_tiles,
                collections: Array.isArray(collections) ? collections : [collectionId],
                item_count,
                bbox,
                visualization_hints,
                tile_mode: 'stac_items'
            };
            
            if (timestamps.length > 1) {
                manager.createSTACItemsTimelineUI(timestamps, addedLayers);
            }
        }
        
        // Fit map to bbox
        if (bbox && bbox.length === 4) {
            setTimeout(() => {
                map.setCamera({
                    bounds: [bbox[0], bbox[1], bbox[2], bbox[3]],
                    padding: { top: 100, bottom: 100, left: 100, right: 100 },
                    type: "fly",
                    duration: 2000
                });
            }, 500);
        }
        
        // Add to layer control
        const layerTitle = `${collectionId} (${bands.join(', ')})`;
        const layersForControl = addedLayers.map(l => ({ layer: l.layer, id: l.layerId }));
        const mainLayerId = `stac-items-${collectionId}-${Date.now()}`;
        LayerControls.addLayerToControl(mainLayerId, layersForControl, layerTitle, null, true);
        
        const bandStr = bands.length > 0 ? bands.join(', ') : 'RGB';
        ChatUI.displayMessage(
            `Multi-band STAC imagery loaded: ${item_count} items<br>` +
            `Collection: ${collectionId}<br>` +
            `Bands: ${bandStr}<br>` +
            `${timestamps.length} temporal snapshots available`,
            'system'
        );
    },

    /**
     * Render temporal COG timeline
     */
    renderTemporalCOGTimeline: function(content) {
        console.log('Rendering temporal COG timeline:', content);
        
        const timelineManager = GeoFahamState.temporalCOGTimelineManager || window.temporalCOGTimelineManager;
        
        if (!timelineManager) {
            console.error('Temporal COG timeline manager not initialized');
            ChatUI.displayMessage('Error: Temporal COG timeline manager not available', 'error');
            return;
        }
        
        // Set metadata from data field if present
        if (content.data) {
            content.metadata = content.data;
        }
        
        const metadata = content.metadata || content;
        const map = GeoFahamState.map;
        
        // Check for nested layers structure
        if (metadata.layers && typeof metadata.layers === 'object') {
            console.log('Detected nested layers structure');
            
            for (const [layerLabel, layerData] of Object.entries(metadata.layers)) {
                console.log(`Processing layer: ${layerLabel}`, layerData);
                
                if (layerData.type === 'temporal_sequence') {
                    const timelineContent = {
                        metadata: {
                            temporal_layers: layerData.temporal_layers,
                            class_labels: metadata.class_labels || null,
                            time_series: metadata.time_series || null,
                            result_type: metadata.result_type || 'timeline',
                            min_scale: layerData.min_scale,
                            max_scale: layerData.max_scale,
                            layer_label: layerLabel,
                            summary: metadata.result_explanation || `Timeline: ${layerLabel}`
                        },
                        summary: `${layerLabel}: ${layerData.temporal_layers.length} periods`
                    };
                    
                    try {
                        const manager = new TemporalCOGTimelineManager(map, layerLabel);
                        manager.renderTemporalCOGTimeline(timelineContent);
                        timelineManager.set(layerLabel, manager);
                    } catch (error) {
                        console.error(`Error rendering timeline for ${layerLabel}:`, error);
                        ChatUI.displayMessage(`Error rendering timeline for ${layerLabel}: ${error.message}`, 'error');
                    }
                    
                } else if (layerData.type === 'single_layer') {
                    const rasterContent = {
                        data_type: 'raster',
                        data: {
                            url: layerData.url,
                            bounds: layerData.bounds,
                            statistics: layerData.statistics,
                            min_scale: layerData.min_scale,
                            max_scale: layerData.max_scale
                        },
                        summary: `${layerLabel}`
                    };
                    
                    try {
                        this.renderRasterLayer(rasterContent);
                    } catch (error) {
                        console.error(`Error rendering raster for ${layerLabel}:`, error);
                        ChatUI.displayMessage(`Error rendering raster for ${layerLabel}: ${error.message}`, 'error');
                    }
                }
            }
            
            const summary = metadata.result_explanation || 'Multi-layer temporal analysis';
            ChatUI.displayMessage(summary, 'system');
            
        } else {
            // Legacy flat structure
            console.log('Using legacy flat temporal_layers structure');
            
            let manager = timelineManager.get('default');
            if (!manager) {
                manager = new TemporalCOGTimelineManager(map, 'default');
                timelineManager.set('default', manager);
            }
            
            try {
                manager.renderTemporalCOGTimeline(content);
            } catch (error) {
                console.error('Error rendering temporal COG timeline:', error);
                ChatUI.displayMessage(`Error rendering temporal COG timeline: ${error.message}`, 'error');
            }
        }
    },

    // Private helper methods

    /**
     * Create point layer
     */
    _createPointLayer: function(dataSource, layerId, properties) {
        return new atlas.layer.SymbolLayer(dataSource, layerId, {
            iconOptions: {
                image: [
                    'case',
                    ['==', ['get', 'damaged'], true], 'pin-red',
                    ['==', ['get', 'damaged'], 1], 'pin-red',
                    'pin-blue'
                ],
                allowOverlap: true,
                ignorePlacement: true,
                size: 0.8
            },
            textOptions: {
                textField: ['get', 'name'],
                offset: [0, 2],
                color: '#2563eb',
                haloColor: 'white',
                haloWidth: 1
            }
        });
    },

    /**
     * Create line layer
     */
    _createLineLayer: function(dataSource, layerId) {
        return new atlas.layer.LineLayer(dataSource, layerId, {
            strokeColor: '#2563eb',
            strokeWidth: 3,
            strokeOpacity: 0.8
        });
    },

    /**
     * Create polygon layer with damage styling
     */
    _createPolygonLayer: function(dataSource, layerId, properties, source) {
        return new atlas.layer.PolygonLayer(dataSource, layerId, {
            fillColor: [
                'case',
                ['==', ['get', 'damaged'], 1], '#ef4444',
                ['==', ['get', 'damaged'], true], '#ef4444',
                [
                    'all',
                    ['has', 'damage_pct'],
                    ['>=', ['get', 'damage_pct'], 0],
                    ['<=', ['get', 'damage_pct'], 1]
                ],
                [
                    'interpolate',
                    ['linear'],
                    ['get', 'damage_pct'],
                    0, '#10b981',
                    0.25, '#f59e0b',
                    0.5, '#f97316',
                    0.75, '#ef4444',
                    1, '#dc2626'
                ],
                '#10b981'
            ],
            fillOpacity: [
                'case',
                ['has', 'damage_pct'],
                [
                    'interpolate',
                    ['linear'],
                    ['get', 'damage_pct'],
                    0, 0.4,
                    1, 0.8
                ],
                0.6
            ],
            strokeColor: [
                'case',
                ['==', ['get', 'damaged'], 1], '#dc2626',
                ['==', ['get', 'damaged'], true], '#dc2626',
                [
                    'all',
                    ['has', 'damage_pct'],
                    ['>=', ['get', 'damage_pct'], 0],
                    ['<=', ['get', 'damage_pct'], 1]
                ],
                [
                    'interpolate',
                    ['linear'],
                    ['get', 'damage_pct'],
                    0, '#059669',
                    0.25, '#d97706',
                    0.5, '#ea580c',
                    0.75, '#dc2626',
                    1, '#991b1b'
                ],
                '#10b981'
            ],
            strokeWidth: [
                'case',
                ['has', 'damage_pct'],
                [
                    'interpolate',
                    ['linear'],
                    ['get', 'damage_pct'],
                    0, 1,
                    1, 3
                ],
                2
            ]
        });
    },

    /**
     * Add layer interactions (click, hover)
     */
    _addLayerInteractions: function(layer, layerId) {
        const map = GeoFahamState.map;
        
        // Hover events
        map.events.add('mousemove', layer, function(e) {
            if (e.shapes && e.shapes.length > 0) {
                map.getCanvasContainer().style.cursor = 'pointer';
            }
        });

        map.events.add('mouseleave', layer, function() {
            map.getCanvasContainer().style.cursor = 'grab';
        });

        // Click events
        map.events.add('click', layer, function(e) {
            if (e.shapes && e.shapes.length > 0) {
                const shape = e.shapes[0];
                const properties = shape.getProperties();
                const coordinates = shape.getCoordinates();
                LayerRenderer._showFeaturePopup(properties, coordinates);
            }
        });
    },

    /**
     * Show feature popup
     */
    _showFeaturePopup: function(properties, coordinates) {
        const popup = GeoFahamState.popup;
        const map = GeoFahamState.map;
        
        let content = '<div style="padding: 10px; max-width: 250px;" class="feature-popup">';
        content += '<h4 style="margin: 0 0 8px 0; color: #1f2937;">Feature Information</h4>';

        if (Object.keys(properties).length === 0) {
            content += '<p style="margin: 0; color: #6b7280;">No additional properties</p>';
        } else {
            Object.entries(properties).forEach(([key, value]) => {
                if (!['stroke', 'stroke-width', 'stroke-opacity', 'fill', 'fill-opacity'].includes(key)) {
                    const displayKey = key.charAt(0).toUpperCase() + key.slice(1).replace(/_/g, ' ');
                    let displayValue = value;

                    if (key === 'damaged') {
                        displayValue = value ? '✓ Yes' : '✗ No';
                    } else if (typeof value === 'boolean') {
                        displayValue = value ? 'Yes' : 'No';
                    }

                    content += `<p style="margin: 4px 0;"><strong>${displayKey}:</strong> ${displayValue}</p>`;
                }
            });
        }

        content += '</div>';

        // Get position for popup
        let position = this._getFirstCoordinate(coordinates);
        if (!position || position.length !== 2) {
            position = map.getCamera().center;
        }

        popup.setOptions({
            content: content,
            position: position,
            pixelOffset: [0, -18]
        });

        popup.open(map);
    },

    /**
     * Get first coordinate from nested coordinates array
     */
    _getFirstCoordinate: function(coords) {
        if (!Array.isArray(coords)) return null;
        
        if (coords.length === 2 && typeof coords[0] === 'number' && typeof coords[1] === 'number') {
            return coords;
        }
        
        if (coords.length > 0 && Array.isArray(coords[0])) {
            return this._getFirstCoordinate(coords[0]);
        }
        
        return null;
    },

    /**
     * Handle GeometryCollection (clusters with boundaries)
     * Note: This is a complex function for handling building clusters with damage
     */
    _handleGeometryCollection: function(geojson, dataSource, baseLayerId, source, content) {
        // This function is very long and handles special cluster visualization
        // For brevity, delegating to the existing implementation
        if (typeof handleGeometryCollection === 'function') {
            handleGeometryCollection(geojson, dataSource, baseLayerId, source, content);
        } else {
            console.warn('GeometryCollection handler not available');
            ChatUI.displayMessage('GeometryCollection rendering not available', 'error');
        }
    },

    /**
     * Show damage legend
     */
    _showDamageLegend: function() {
        // Remove existing legend
        const existingLegend = document.getElementById('damage-legend');
        if (existingLegend) {
            existingLegend.remove();
        }

        const legendContainer = document.createElement('div');
        legendContainer.id = 'damage-legend';
        legendContainer.style.cssText = `
            position: absolute;
            bottom: 100px;
            left: 1rem;
            background: rgba(255, 255, 255, 0.95);
            border-radius: 8px;
            padding: 12px;
            box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
            border: 1px solid #e2e8f0;
            z-index: 1000;
            min-width: 200px;
            backdrop-filter: blur(8px);
        `;

        const title = document.createElement('h4');
        title.textContent = 'Damage Level';
        title.style.cssText = 'margin: 0 0 8px 0; font-size: 14px; font-weight: 600; color: #1f2937;';
        legendContainer.appendChild(title);

        const legendItems = [
            { percentage: 0, label: 'No Damage (0%)', color: '#10b981' },
            { percentage: 25, label: 'Minor (25%)', color: '#f59e0b' },
            { percentage: 50, label: 'Moderate (50%)', color: '#f97316' },
            { percentage: 75, label: 'Severe (75%)', color: '#ef4444' },
            { percentage: 100, label: 'Complete (100%)', color: '#dc2626' }
        ];

        legendItems.forEach(item => {
            const legendItem = document.createElement('div');
            legendItem.style.cssText = 'display: flex; align-items: center; gap: 8px; margin: 4px 0;';

            const colorBox = document.createElement('div');
            colorBox.style.cssText = `width: 16px; height: 16px; background-color: ${item.color}; border-radius: 3px; border: 1px solid rgba(0, 0, 0, 0.2);`;

            const label = document.createElement('span');
            label.textContent = item.label;
            label.style.cssText = 'font-size: 12px; color: #374151;';

            legendItem.appendChild(colorBox);
            legendItem.appendChild(label);
            legendContainer.appendChild(legendItem);
        });

        // Close button
        const closeButton = document.createElement('button');
        closeButton.innerHTML = '×';
        closeButton.style.cssText = `
            position: absolute; top: 4px; right: 6px;
            background: none; border: none; font-size: 18px; color: #6b7280;
            cursor: pointer; width: 24px; height: 24px; border-radius: 4px;
        `;
        closeButton.title = 'Close legend';
        closeButton.addEventListener('click', () => legendContainer.remove());
        legendContainer.appendChild(closeButton);

        const mapSection = document.querySelector('.map-section');
        if (mapSection) {
            mapSection.appendChild(legendContainer);
        }
    }
};

// Expose globally
window.LayerRenderer = LayerRenderer;

// Also expose individual functions for backward compatibility
window.renderLayer = LayerRenderer.renderVectorLayer.bind(LayerRenderer);
window.renderRasterLayer = LayerRenderer.renderRasterLayer.bind(LayerRenderer);
window.renderTemporalMosaic = LayerRenderer.renderTemporalMosaic.bind(LayerRenderer);
window.renderSTACItemTiles = LayerRenderer.renderSTACItemTiles.bind(LayerRenderer);
window.renderTemporalCOGTimeline = LayerRenderer.renderTemporalCOGTimeline.bind(LayerRenderer);

// Export for ES6 modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = LayerRenderer;
}
