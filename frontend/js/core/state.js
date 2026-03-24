// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

/**
 * Global State Management
 * Centralized state for the GeoFaham frontend application
 */

const GeoFahamState = {
    // WebSocket state
    ws: null,
    isConnected: false,
    reconnectInterval: null,
    currentMode: 'multi-agent',
    
    // UI state
    debugMode: false,
    currentTool: 'select',
    isChatExpanded: false,
    
    // Map state
    map: null,
    popup: null,
    dataSource: null,
    drawingManager: null,
    legend: null,
    layerControl: null,
    measureTool: null,
    
    // Layer managers
    temporalMosaicManager: null,
    temporalCOGTimelineManager: null,
    
    // Layer tracking
    activeLayers: new Map(),
    layerCounter: 0,
    
    // Raster registries
    rasterLayersRegistry: new Map(),
    rasterMetadataRegistry: {
        layers: new Map(),
        
        store: function(layerId, metadata) {
            console.log('📊 Storing raster metadata for layer:', layerId, metadata);
            this.layers.set(layerId, {
                ...metadata,
                timestamp: Date.now(),
                layerId: layerId
            });
        },
        
        remove: function(layerId) {
            console.log('📊 Removing raster metadata for layer:', layerId);
            this.layers.delete(layerId);
        },
        
        getAllActive: function() {
            const metadata = [];
            this.layers.forEach((data, layerId) => {
                metadata.push(data);
            });
            return metadata;
        },
        
        clear: function() {
            console.log('📊 Clearing all raster metadata');
            this.layers.clear();
        }
    },
    
    /**
     * Reset all state to initial values
     */
    reset: function() {
        this.isConnected = false;
        this.currentTool = 'select';
        this.activeLayers.clear();
        this.layerCounter = 0;
        this.rasterLayersRegistry.clear();
        this.rasterMetadataRegistry.clear();
    },
    
    /**
     * Generate unique layer ID
     */
    generateLayerId: function(prefix = 'layer') {
        this.layerCounter++;
        return `${prefix}_${this.layerCounter}_${Date.now()}`;
    }
};

// Expose globally for cross-module access
window.GeoFahamState = GeoFahamState;

// Also expose rasterMetadataRegistry globally for backward compatibility
window.rasterMetadataRegistry = GeoFahamState.rasterMetadataRegistry;
window.rasterLayersRegistry = GeoFahamState.rasterLayersRegistry;

// Export for ES6 modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = GeoFahamState;
}
