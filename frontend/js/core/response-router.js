// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

/**
 * Response Router Module
 * Single source of truth for determining how to handle agent responses.
 * 
 * This module eliminates duplicate type-checking logic scattered across
 * chat-ui.js and message-handler.js by centralizing routing decisions.
 */

const ResponseRouter = {
    /**
     * Determine the appropriate renderer for a layer response.
     * 
     * @param {Object} response - The layer response from backend
     * @returns {string} Renderer type: 'stac_items', 'temporal_mosaic', 'temporal_cog', 'raster', 'vector', 'unknown'
     */
    getLayerRendererType: function(response) {
        // Get metadata from either field (backend sends it differently based on data_type)
        const metadata = response.metadata || response.data || {};
        const dataType = response.data_type;
        
        // Check for specific metadata markers (order matters - most specific first)
        if (metadata.stac_item_tiles) {
            return 'stac_items';
        }
        
        if (metadata.mosaic_jsons) {
            return 'temporal_mosaic';
        }
        
        // Check for temporal COG timeline (nested layers or flat temporal_layers)
        // Note: Check for non-empty objects since empty {} is truthy in JS
        const hasTemporalLayers = metadata.temporal_layers && 
            (Array.isArray(metadata.temporal_layers) ? metadata.temporal_layers.length > 0 : true);
        const hasLayers = metadata.layers && 
            (typeof metadata.layers === 'object' ? Object.keys(metadata.layers).length > 0 : true);
        
        if (hasTemporalLayers || hasLayers) {
            return 'temporal_cog';
        }
        
        // Check visualization hints for tile mode
        const vizHints = metadata.visualization_hints;
        if (vizHints?.layers?.[0]?.tile_mode === 'stac_items') {
            return 'stac_items';
        }
        
        // Fall back to data_type
        if (dataType === 'timeline') {
            return 'temporal_cog';
        }
        
        if (dataType === 'raster' || dataType === 'raster_multi') {
            return 'raster';
        }
        
        if (dataType === 'vector') {
            return 'vector';
        }
        
        return 'unknown';
    },

    /**
     * Normalize a layer message to a consistent structure for renderers.
     * Handles the various formats the backend might send.
     * 
     * @param {Object} message - Raw message from WebSocket
     * @returns {Object} Normalized message with consistent structure
     */
    normalizeLayerMessage: function(message) {
        // Already normalized
        if (message._normalized) {
            return message;
        }

        const normalized = {
            _normalized: true,
            type: message.type,
            data_type: message.data_type,
            source: message.source,
            artifact: message.artifact || null,
            summary: message.summary || '',
        };

        // Normalize metadata access - backend sometimes puts metadata in 'data' field
        if (message.metadata && Object.keys(message.metadata).length > 0) {
            normalized.metadata = message.metadata;
            normalized.data = message.data || [];  // Always set data when metadata exists
        } else if (message.data && typeof message.data === 'object' && !Array.isArray(message.data)) {
            // Check if data looks like metadata (has known metadata keys)
            const dataKeys = Object.keys(message.data);
            const metadataKeys = ['mosaic_jsons', 'stac_item_tiles', 'temporal_layers', 'layers', 
                                  'visualization_hints', 'bbox', 'collections'];
            const isMetadata = metadataKeys.some(k => dataKeys.includes(k));
            
            if (isMetadata) {
                normalized.metadata = message.data;
                normalized.data = [];
            } else {
                normalized.data = message.data;
                normalized.metadata = {};
            }
        } else {
            normalized.data = message.data || [];
            normalized.metadata = {};
        }

        return normalized;
    },

    /**
     * Check if a message is a layer type that should be rendered on the map.
     * 
     * @param {Object} message - Message to check
     * @returns {boolean} True if this is a renderable layer
     */
    isRenderableLayer: function(message) {
        return message.type === 'layer' && 
               ['vector', 'raster', 'raster_multi', 'timeline', 'stac_items'].includes(message.data_type);
    },

    /**
     * Check if a message is a data response (not a layer).
     * 
     * @param {Object} message - Message to check
     * @returns {boolean} True if this is a data response
     */
    isDataResponse: function(message) {
        return message.type === 'data' || 
               ['tabular', 'json', 'stats', 'message'].includes(message.data_type);
    }
};

// Expose globally
window.ResponseRouter = ResponseRouter;

// Export for ES6 modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ResponseRouter;
}
