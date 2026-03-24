// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

/**
 * Message Handler Module
 * Processes incoming WebSocket messages and routes them appropriately.
 * 
 * Uses ResponseRouter for consistent layer type detection (DRY principle).
 */

const MessageHandler = {
    /**
     * Handle incoming message from WebSocket
     */
    handleMessage: function(message) {
        console.log("Message received:", message.type, message.data_type);

        // Handle user input request
        if (message.type === 'UserInputRequestedEvent') {
            ChatUI.enableInput();
            return;
        }
        
        // Handle error messages
        if (message.type === 'error') {
            ChatUI.displayMessage(message.data, 'error');
            ChatUI.enableInput();
            return;
        }
        
        // Handle layer messages - route to appropriate renderer
        if (message.type === 'layer') {
            this._handleLayerMessage(message);
        }
        // Handle data messages - display as text
        else if (message.type === 'data') {
            ChatUI.displayMessage(message.data, message.source, message.debug_msg);
        }
        
        // Enable input when processing is finished
        if (message.finished) {
            ChatUI.enableInput();
        }
    },

    /**
     * Handle layer-type messages using ResponseRouter for consistent routing
     */
    _handleLayerMessage: function(message) {
        // Normalize the message structure first
        const normalized = ResponseRouter.normalizeLayerMessage(message);
        
        // Get renderer type from single source of truth
        const rendererType = ResponseRouter.getLayerRendererType(normalized);
        
        console.log(`Layer routing: data_type=${normalized.data_type}, renderer=${rendererType}`);
        
        switch (rendererType) {
            case 'stac_items':
                LayerRenderer.renderSTACItemTiles(normalized);
                break;
                
            case 'temporal_mosaic':
                LayerRenderer.renderTemporalMosaic(normalized);
                break;
                
            case 'temporal_cog':
                LayerRenderer.renderTemporalCOGTimeline(normalized);
                break;
                
            case 'raster':
                LayerRenderer.renderRasterLayer(normalized);
                break;
                
            case 'vector':
                LayerRenderer.renderVectorLayer(normalized);
                break;
                
            default:
                console.warn(`Unknown layer renderer type: ${rendererType}`, normalized);
                ChatUI.displayMessage(`Unsupported layer type: ${normalized.data_type}`, 'error');
        }
    }
};

// Expose globally
window.MessageHandler = MessageHandler;

// Export for ES6 modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = MessageHandler;
}
