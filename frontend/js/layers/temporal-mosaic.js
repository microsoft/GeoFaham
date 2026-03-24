// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

/**
 * Temporal Mosaic Manager
 * 
 * Extends BaseTimelineManager for STAC mosaic-specific functionality.
 * Handles rendering of temporal raster mosaics with timeline UI.
 */

const MAX_CACHED_MOSAIC_LAYERS = 5;

class TemporalMosaicManager extends BaseTimelineManager {
    constructor(map) {
        super(map, 'mosaic');
        
        this.mosaicData = null;
    }

    /**
     * Render temporal mosaic from server response
     */
    renderTemporalMosaic(content) {
        console.log('Rendering temporal mosaic:', content);

        const { metadata, artifact } = content;
        const { mosaic_jsons, collections, item_count, date_range } = metadata;
        const bbox = metadata.bbox || metadata.query_params?.bbox;

        if (!mosaic_jsons || Object.keys(mosaic_jsons).length === 0) {
            console.error('No mosaic JSONs found');
            ChatUI.displayMessage('Error: No temporal mosaics available', 'error');
            return;
        }

        // Normalize collections
        let collectionsArray = this._normalizeCollections(collections);

        // Store mosaic data
        this.mosaicData = {
            mosaic_jsons,
            collections: collectionsArray,
            item_count,
            date_range,
            bbox,
            visualization_hints: metadata.visualization_hints,
            query_params: metadata.query_params
        };

        // Sort timestamps
        const timestamps = Object.keys(mosaic_jsons).sort();
        this.selectedTimestamp = timestamps[timestamps.length - 1]; // Most recent

        // Create UI
        this.createTimelineUI(timestamps);

        // Load default mosaic
        this.loadMosaic(this.selectedTimestamp);

        // Fit map to bbox
        this.fitMapToBounds(bbox);

        // Show success message
        const dateRangeFormatted = this._formatDateRange(timestamps);
        ChatUI.displayMessage(
            `Temporal mosaic loaded: ${item_count} items from ${collectionsArray.join(', ')}<br>` +
            `Date range: ${dateRangeFormatted}<br>` +
            `${timestamps.length} temporal snapshots available`,
            'system'
        );

        // Show legend if colormap used
        this._showLegendIfNeeded(metadata);
    }

    _normalizeCollections(collections) {
        if (Array.isArray(collections)) return collections;
        if (collections && typeof collections === 'object') {
            return Object.values(collections).flatMap(group => 
                group.collection_ids || [Object.keys(collections)]
            );
        }
        return ['Unknown'];
    }

    _formatDateRange(timestamps) {
        if (timestamps.length === 1) return this.formatTimestamp(timestamps[0], 'date-only');
        return `${this.formatTimestamp(timestamps[0], 'date-only')} to ${this.formatTimestamp(timestamps[timestamps.length - 1], 'date-only')}`;
    }

    _showLegendIfNeeded(metadata) {
        const vizHints = metadata.visualization_hints;
        if (vizHints?.layers?.[0]?.colormap) {
            this.showMosaicLegend(vizHints.layers[0]);
        }
    }

    /**
     * Create timeline UI
     */
    createTimelineUI(timestamps) {
        this.createTimelineUIBase({
            timestamps,
            title: 'Temporal Selection',
            icon: 'clock',
            defaultIndex: timestamps.length - 1, // Most recent
            formatLabel: (ts) => this.formatTimestamp(ts, 'short')
        });

        // Update selection display
        this.updateSelectionDisplay(this.selectedTimestamp);

        // Setup events
        this.setupTimelineEvents(timestamps, (ts, idx) => {
            this.selectedTimestamp = ts;
            this.updateSelectionDisplay(ts);
            this.loadMosaic(ts);
        });
    }

    updateSelectionDisplay(timestamp) {
        const display = document.getElementById(`timeline-selection-${this.layerLabel}`);
        if (display) {
            display.innerHTML = `
                <div class="selection-label">Selected Date:</div>
                <div class="selection-date">${this.formatTimestamp(timestamp, 'full')}</div>
            `;
        }
    }

    /**
     * Load mosaic for timestamp
     */
    async loadMosaic(timestamp) {
        console.log('Loading mosaic:', timestamp);

        // Check cache
        if (this.layerCache.has(timestamp)) {
            this.switchToTimestamp(timestamp);
            return;
        }

        // Manage cache
        this.manageCacheSize(MAX_CACHED_MOSAIC_LAYERS);

        const mosaicPath = this.mosaicData.mosaic_jsons[timestamp];
        if (!mosaicPath) {
            console.error('Mosaic path not found:', timestamp);
            return;
        }

        // Build tile URL
        const tileUrl = this._buildTileUrl(mosaicPath);
        const layerId = `temporal-mosaic-${this._normalizeTimestamp(timestamp)}-${Date.now()}`;

        // Create layer
        const layer = new atlas.layer.TileLayer({
            tileUrl,
            tileSize: 256,
            minSourceZoom: this.mosaicData.query_params?.minzoom || 8,
            maxSourceZoom: this.mosaicData.query_params?.maxzoom || 14,
            opacity: 1,
            visible: false
        }, layerId);

        this.map.layers.add(layer, 'labels');

        // Cache
        this.layerCache.set(timestamp, {
            layer,
            layerId,
            isVisible: false,
            opacity: 1
        });

        this.recordCacheAccess(timestamp);
        this.updateCachedCount();

        // Register for metadata
        this._registerRasterMetadata(layerId, timestamp, mosaicPath);

        // Switch to this timestamp
        this.switchToTimestamp(timestamp);

        // Add to layer control on first load
        if (this.layerCache.size === 1) {
            this.addToLayerControl(timestamp);
        }
    }

    _normalizeTimestamp(timestamp) {
        if (timestamp.includes('/')) {
            return timestamp.split('/')[0];
        }
        return timestamp.replace(/[^a-zA-Z0-9]/g, '_');
    }

    _buildTileUrl(mosaicPath) {
        let tileUrl = `/tiles/mosaicjson/tiles/WebMercatorQuad/{z}/{x}/{y}@1x.png?url=${encodeURIComponent(mosaicPath)}`;

        const isTCI = mosaicPath.includes('TCI') || mosaicPath.toLowerCase().includes('true_color');
        const vizHints = this.mosaicData.visualization_hints;

        if (vizHints && !isTCI) {
            const primaryVis = vizHints.layers?.[0];
            if (primaryVis) {
                if (primaryVis.colormap) {
                    tileUrl += `&colormap_name=${primaryVis.colormap}`;
                }
                if (primaryVis.rescale) {
                    tileUrl += `&rescale=${primaryVis.rescale}`;
                }
                if (primaryVis.color_formula) {
                    tileUrl += `&color_formula=${encodeURIComponent(primaryVis.color_formula)}`;
                }
            }
        }

        return tileUrl;
    }

    _registerRasterMetadata(layerId, timestamp, mosaicPath) {
        if (!window.rasterMetadataRegistry) return;

        const vizHints = this.mosaicData.visualization_hints;
        const primaryVis = vizHints?.layers?.[0] || {};
        const isTCI = mosaicPath.includes('TCI');

        window.rasterMetadataRegistry.store(layerId, {
            type: 'temporal_mosaic',
            title: `Sentinel-2 ${this.formatTimestamp(timestamp, 'short')}`,
            timestamp,
            collections: this.mosaicData.collections,
            bands: primaryVis.bands || null,
            colormap: primaryVis.colormap || null,
            rescale: primaryVis.rescale || null,
            rendering_type: primaryVis.rendering_type || (isTCI ? 'true_color' : 'multi_band'),
            bounds: this.mosaicData.bbox,
            source: 'STAC'
        });
    }

    /**
     * Switch to timestamp
     */
    switchToTimestamp(timestamp) {
        this.layerCache.forEach((cached, ts) => {
            const shouldShow = this.compareMode || ts === timestamp;
            cached.layer.setOptions({ visible: shouldShow });
            cached.isVisible = shouldShow;
        });

        this.recordCacheAccess(timestamp);
    }

    /**
     * Add to layer control
     */
    addToLayerControl(timestamp) {
        if (typeof LayerControls === 'undefined') return;

        const layerTitle = `Sentinel-2 ${this.formatTimestamp(timestamp, 'short')}`;
        const layers = Array.from(this.layerCache.values()).map(c => ({
            layer: c.layer,
            id: c.layerId
        }));

        LayerControls.addLayerToControl(`temporal-mosaic-group`, layers, layerTitle, null, true);
    }

    /**
     * Show mosaic legend
     */
    showMosaicLegend(vizConfig) {
        const existingLegend = document.getElementById('mosaic-legend');
        if (existingLegend) existingLegend.remove();

        if (!vizConfig.colormap) return;

        const legend = document.createElement('div');
        legend.id = 'mosaic-legend';
        legend.className = 'mosaic-legend';
        legend.innerHTML = `
            <div class="legend-title">${vizConfig.colormap}</div>
            <img src="/tiles/colormap/colorMaps/${vizConfig.colormap}?f=png&orientation=horizontal" 
                 alt="${vizConfig.colormap}" class="legend-gradient">
            ${vizConfig.rescale ? `<div class="legend-range">${vizConfig.rescale}</div>` : ''}
            <button class="legend-close" onclick="this.parentElement.remove()">×</button>
        `;

        const mapSection = document.querySelector('.map-section');
        if (mapSection) mapSection.appendChild(legend);
    }

    /**
     * Create STAC items timeline UI (for per-item tiles)
     */
    createSTACItemsTimelineUI(timestamps, addedLayers) {
        this.createTimelineUIBase({
            timestamps,
            title: 'STAC Items Timeline',
            icon: 'satellite',
            defaultIndex: timestamps.length - 1,
            formatLabel: (ts) => this.formatTimestamp(ts, 'short')
        });

        // Setup events for STAC items
        this.setupTimelineEvents(timestamps, (ts, idx) => {
            // Show only layers for selected timestamp
            addedLayers.forEach(({ layer, timestamp }) => {
                const visible = timestamp === ts;
                layer.setOptions({ visible });
            });
            this.updateSelectionDisplay(ts);
        });
    }
}

// Global instance
window.temporalMosaicManager = null;

// Factory function
window.getTemporalMosaicManager = function(map) {
    if (!window.temporalMosaicManager) {
        window.temporalMosaicManager = new TemporalMosaicManager(map);
    }
    return window.temporalMosaicManager;
};

// Expose class
window.TemporalMosaicManager = TemporalMosaicManager;

// Export for ES6 modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = TemporalMosaicManager;
}
