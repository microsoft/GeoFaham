// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

/**
 * Temporal COG Timeline Manager
 * 
 * Extends BaseTimelineManager for COG-specific functionality.
 * Handles rendering of temporal COG rasters with timeline UI and raster controls.
 */

const MAX_CACHED_COG_LAYERS = 10;

class TemporalCOGTimelineManager extends BaseTimelineManager {
    constructor(map, layerLabel = 'default') {
        super(map, layerLabel);
        
        this.timelineData = null;
        this.currentColormap = null;
        this.rasterControlsPanel = null;
        this.isTimelineVisible = false;
        this.timelineLayerId = null;
    }

    /**
     * Render temporal COG timeline from server response
     */
    renderTemporalCOGTimeline(content) {
        console.log('Rendering temporal COG timeline:', this.layerLabel);

        const metadata = content.metadata || content;
        const { temporal_layers, class_labels, time_series } = metadata;
        
        if (!temporal_layers || temporal_layers.length === 0) {
            console.error('No temporal layers found');
            ChatUI.displayMessage('Error: No temporal layers available', 'error');
            return;
        }

        // Store timeline data
        this.timelineData = {
            temporal_layers,
            class_labels: class_labels || null,
            time_series: time_series || null,
            result_type: metadata.result_type || 'raster',
            bounds: temporal_layers[0].bounds,
            min_scale: metadata.min_scale ?? null,
            max_scale: metadata.max_scale ?? null
        };

        // Extract timestamps
        const timestamps = temporal_layers.map(layer => 
            layer.label || layer.statistics?.date_start || layer.date_start
        );

        this.selectedTimestamp = timestamps[0];
        this.timelineLayerId = `temporal-timeline-${this.layerLabel}-${Date.now()}`;

        // Determine visibility
        const existingCount = window.temporalCOGTimelineManager?.size || 0;
        this.isTimelineVisible = existingCount === 0;

        // Create UI using base class
        this.createTimelineUI(timestamps, temporal_layers);

        // Load first layer
        this.loadCOGLayer(this.selectedTimestamp);

        // Fit map to bounds
        this.fitMapToBounds(this.timelineData.bounds);

        // Show summary
        const summary = content.summary || metadata.summary || 
            `Temporal timeline with ${temporal_layers.length} periods`;
        ChatUI.displayMessage(summary, 'system');
    }

    /**
     * Create timeline UI (COG-specific implementation)
     */
    createTimelineUI(timestamps, layers) {
        // Use base class for common UI
        this.createTimelineUIBase({
            timestamps,
            title: 'Temporal Analysis Timeline',
            icon: 'layer-group',
            defaultIndex: 0,
            formatLabel: (ts, idx) => {
                const layer = layers[idx];
                return layer.label || this.formatTimestamp(
                    layer.statistics?.date_start || layer.date_start, 
                    'short'
                );
            }
        });

        // Update selection display
        this.updateSelectionDisplay(layers[0]);

        // Setup event handlers
        this.setupTimelineEvents(timestamps, (ts, idx) => {
            this.selectedTimestamp = ts;
            this.updateSelectionDisplay(layers[idx]);
            this.loadCOGLayer(ts);
        });

        // Add COG-specific controls (colormap selector)
        this.addColormapControls();

        // Set visibility
        if (!this.isTimelineVisible && this.timelineContainer) {
            this.timelineContainer.style.display = 'none';
        }
    }

    /**
     * Update selection display with layer statistics
     */
    updateSelectionDisplay(layer) {
        const display = document.getElementById(`timeline-selection-${this.layerLabel}`);
        if (!display) return;

        const stats = layer.statistics || {};
        const label = layer.label || this.formatTimestamp(
            stats.date_start || layer.date_start, 
            'full'
        );

        let html = `
            <div class="selection-label">Selected Period:</div>
            <div class="selection-date">${label}</div>
        `;

        // Add statistics if available
        if (stats.min !== undefined && stats.max !== undefined) {
            html += `
                <div class="selection-stats">
                    Range: ${stats.min.toFixed(3)} to ${stats.max.toFixed(3)}
                    ${stats.mean !== undefined ? ` | Mean: ${stats.mean.toFixed(3)}` : ''}
                </div>
            `;
        }

        display.innerHTML = html;
    }

    /**
     * Add colormap selector controls
     */
    addColormapControls() {
        if (!this.timelineContainer) return;

        const controlsDiv = document.createElement('div');
        controlsDiv.className = 'timeline-colormap-controls';
        controlsDiv.innerHTML = `
            <label>Colormap:</label>
            <select id="colormap-select-${this.layerLabel}" class="colormap-select">
                <option value="">Default</option>
                <option value="viridis">Viridis</option>
                <option value="plasma">Plasma</option>
                <option value="rdylgn">RdYlGn</option>
                <option value="spectral">Spectral</option>
                <option value="turbo">Turbo</option>
            </select>
        `;

        const controls = this.timelineContainer.querySelector('.timeline-controls');
        if (controls) {
            controls.appendChild(controlsDiv);
        }

        // Setup colormap change handler
        const select = document.getElementById(`colormap-select-${this.layerLabel}`);
        if (select) {
            select.addEventListener('change', (e) => {
                this.currentColormap = e.target.value || null;
                this.refreshAllLayers();
            });
        }
    }

    /**
     * Load a COG layer for a timestamp
     */
    async loadCOGLayer(timestamp) {
        console.log('Loading COG layer:', timestamp);

        // Check cache
        if (this.layerCache.has(timestamp)) {
            this.switchToTimestamp(timestamp);
            return;
        }

        // Manage cache size
        this.manageCacheSize(MAX_CACHED_COG_LAYERS);

        // Find layer data
        const layerData = this.timelineData.temporal_layers.find(
            l => (l.label || l.statistics?.date_start || l.date_start) === timestamp
        );

        if (!layerData) {
            console.error('Layer data not found:', timestamp);
            return;
        }

        // Create layer
        const layerId = `temporal-cog-${this.layerLabel}-${Date.now()}`;
        const layer = this.createCOGLayer(layerData);

        // Add to map
        this.map.layers.add(layer, 'labels');

        // Set visibility
        const shouldBeVisible = this.isTimelineVisible && (timestamp === this.selectedTimestamp);
        layer.setOptions({ visible: shouldBeVisible });

        // Cache
        this.layerCache.set(timestamp, {
            layer,
            layerId,
            isVisible: shouldBeVisible,
            opacity: 1.0,
            metadata: {
                url: layerData.url,
                bounds: layerData.bounds,
                statistics: layerData.statistics
            }
        });

        this.recordCacheAccess(timestamp);
        this.updateCachedCount();

        // Switch to this timestamp
        this.switchToTimestamp(timestamp);

        // Add to layer control on first load
        if (this.layerCache.size === 1) {
            this.addToLayerControl();
        }
    }

    /**
     * Create a COG tile layer
     */
    createCOGLayer(layerData, opacity = 1.0) {
        const { url, statistics } = layerData;

        let tileUrl = `/tiles/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png?url=${encodeURIComponent(url)}`;

        if (this.currentColormap) {
            tileUrl += `&colormap_name=${this.currentColormap}`;
        }

        // Add rescale
        const min = this.timelineData.min_scale ?? statistics?.min;
        const max = this.timelineData.max_scale ?? statistics?.max;
        if (min !== undefined && max !== undefined) {
            tileUrl += `&rescale=${min},${max}`;
        }

        return new atlas.layer.TileLayer({
            tileUrl,
            tileSize: 256,
            minSourceZoom: 0,
            maxSourceZoom: 18,
            opacity,
            visible: false
        });
    }

    /**
     * Switch visible layer to timestamp
     */
    switchToTimestamp(timestamp) {
        this.layerCache.forEach((cached, ts) => {
            const shouldShow = ts === timestamp && this.isTimelineVisible;
            cached.layer.setOptions({ visible: shouldShow && !this.compareMode });
            cached.isVisible = shouldShow;
        });

        // In compare mode, show all cached layers
        if (this.compareMode) {
            this.layerCache.forEach((cached) => {
                cached.layer.setOptions({ visible: this.isTimelineVisible });
            });
        }

        this.recordCacheAccess(timestamp);
    }

    /**
     * Refresh all layers with new colormap
     */
    refreshAllLayers() {
        const timestamps = Array.from(this.layerCache.keys());
        
        // Clear cache and reload
        this.clearCache();
        
        // Reload current timestamp
        if (this.selectedTimestamp) {
            this.loadCOGLayer(this.selectedTimestamp);
        }
    }

    /**
     * Add timeline to layer control panel
     */
    addToLayerControl() {
        const layerTitle = `${this.layerLabel.toUpperCase()} Timeline`;
        
        if (typeof LayerControls !== 'undefined' && LayerControls.addLayerToControl) {
            const layers = Array.from(this.layerCache.values()).map(c => ({
                layer: c.layer,
                id: c.layerId
            }));
            LayerControls.addLayerToControl(this.timelineLayerId, layers, layerTitle, null, true);
        }
    }

    /**
     * Set timeline visibility
     */
    setTimelineVisibility(visible) {
        this.isTimelineVisible = visible;
        
        if (this.timelineContainer) {
            this.timelineContainer.style.display = visible ? 'block' : 'none';
        }

        // Update layer visibility
        this.layerCache.forEach((cached, ts) => {
            const shouldShow = visible && (ts === this.selectedTimestamp || this.compareMode);
            cached.layer.setOptions({ visible: shouldShow });
        });
    }

    /**
     * Override removeTimelineUI to clean up COG-specific resources
     */
    removeTimelineUI() {
        super.removeTimelineUI();
        
        // Remove from layer control
        if (this.timelineLayerId) {
            const controlItem = document.querySelector(`[data-layer-id="${this.timelineLayerId}"]`);
            if (controlItem) {
                controlItem.remove();
            }
        }

        // Clear all layers from map
        this.clearCache();

        // Remove from global manager
        if (window.temporalCOGTimelineManager?.has(this.layerLabel)) {
            window.temporalCOGTimelineManager.delete(this.layerLabel);
        }
    }
}

// Global manager for multiple timelines
window.temporalCOGTimelineManager = window.temporalCOGTimelineManager || new Map();

// Expose globally
window.TemporalCOGTimelineManager = TemporalCOGTimelineManager;

// Export for ES6 modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = TemporalCOGTimelineManager;
}
