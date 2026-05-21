// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

/**
 * Map Initialization Module
 * Handles Azure Maps initialization and setup
 */

const MapInit = {
    /**
     * Initialize Azure Maps.
     *
     * @param {string} azureMapsKey - Subscription key fetched from /api/config.
     *   Required; the map will not render without it.
     */
    init: function(azureMapsKey) {
        const config = GeoFahamConfig.map;
        const state = GeoFahamState;

        if (!azureMapsKey) {
            throw new Error('MapInit.init called without an Azure Maps key.');
        }

        state.map = new atlas.Map('map', {
            center: config.defaultCenter,
            zoom: config.defaultZoom,
            style: config.defaultStyle,
            authOptions: {
                authType: 'subscriptionKey',
                subscriptionKey: azureMapsKey
            },
            enableAccessibility: config.enableAccessibility,
            showLogo: config.showLogo,
            showFeedbackLink: config.showFeedbackLink,
            preserveDrawingBuffer: config.preserveDrawingBuffer
        });

        state.map.events.add('ready', function() {
            console.log('Map is ready!');
            
            // Hide any default controls
            MapInit.hideDefaultControls();
            
            // Initialize map components
            MapInit.initializeControls();
            MapInit.initializeDrawingTools();
            MapInit.initializeDataSources();
            
            // Initialize temporal mosaic manager
            if (typeof TemporalMosaicManager !== 'undefined') {
                state.temporalMosaicManager = new TemporalMosaicManager(state.map);
                window.temporalMosaicManager = state.temporalMosaicManager;
                console.log('Temporal mosaic manager initialized');
            }
            
            // Initialize temporal COG timeline manager
            if (typeof TemporalCOGTimelineManager !== 'undefined') {
                state.temporalCOGTimelineManager = new Map();
                window.temporalCOGTimelineManager = state.temporalCOGTimelineManager;
                console.log('Temporal COG timeline manager Map initialized');
            }
            
            // Hide controls again after everything is loaded
            setTimeout(() => {
                MapInit.hideDefaultControls();
            }, 500);
        });
        
        // Expose map globally for compatibility
        window.map = state.map;
    },

    /**
     * Initialize map controls
     */
    initializeControls: function() {
        const state = GeoFahamState;
        
        // Create legend control
        state.legend = new atlas.control.LegendControl({
            title: 'Map Layers',
            resx: {
                low: 'Low',
                high: 'High',
                'no-data': 'No data'
            }
        });

        // Create layer control
        state.layerControl = new atlas.control.LayerControl({
            legendControl: state.legend,
            dynamicLayerGroup: {
                groupTitle: 'Data Layers',
                layout: 'checkbox'
            }
        });

        // Create popup
        state.popup = new atlas.Popup({
            pixelOffset: [0, -18],
            closeButton: true
        });
        
        // Expose globally for compatibility
        window.popup = state.popup;
        window.legend = state.legend;
        window.layerControl = state.layerControl;
    },

    /**
     * Initialize drawing tools
     */
    initializeDrawingTools: function() {
        const state = GeoFahamState;
        
        state.drawingManager = new atlas.drawing.DrawingManager(state.map, {
            mode: 'idle',
            toolbar: null
        });

        // Hide default controls after setup
        setTimeout(() => {
            MapInit.hideDefaultControls();
        }, 100);

        setTimeout(() => {
            MapInit.hideDefaultControls();
        }, 1000);

        // Add drawing events
        state.map.events.add('drawingcomplete', state.drawingManager, function(shape) {
            console.log('Drawing completed:', shape);
            MapControls.showShapeInfo(shape);
        });

        state.map.events.add('drawingchanged', state.drawingManager, function(shape) {
            console.log('Drawing changed:', shape);
        });
        
        // Expose globally
        window.drawingManager = state.drawingManager;
    },

    /**
     * Initialize data sources
     */
    initializeDataSources: function() {
        const state = GeoFahamState;
        
        // Create main data source for query results
        state.dataSource = new atlas.source.DataSource();
        state.map.sources.add(state.dataSource);

        // Create data source for user drawings
        const drawingDataSource = new atlas.source.DataSource();
        state.map.sources.add(drawingDataSource);
        
        // Expose globally
        window.dataSource = state.dataSource;
    },

    /**
     * Hide all Azure Maps default controls
     */
    hideDefaultControls: function() {
        const selectors = [
            '.atlas-control-container',
            '.atlas-control',
            '.atlas-drawing-toolbar',
            '.atlas-map-toolbar',
            '.atlas-control-container-top-right',
            '.atlas-control-container-bottom-left',
            '.atlas-control-container-bottom-right',
            '.atlas-control-container-top-left',
            '.atlas-control-zoom',
            '.atlas-control-pitch',
            '.atlas-control-compass',
            '.atlas-control-style',
            '.atlas-control-layer',
            '.atlas-control-legend',
            '.atlas-drawing-toolbar-container'
        ];

        selectors.forEach(selector => {
            const elements = document.querySelectorAll(selector);
            elements.forEach(element => {
                element.style.display = 'none';
                element.style.visibility = 'hidden';
                element.style.opacity = '0';
            });
        });
    },

    /**
     * Reset map view to default
     */
    resetView: function() {
        const state = GeoFahamState;
        const config = GeoFahamConfig.map;
        
        if (state.map) {
            state.map.setCamera({
                center: config.defaultCenter,
                zoom: config.defaultZoom,
                type: "fly",
                duration: 1000
            });
        }
    },

    /**
     * Fit map to bounds
     */
    fitToBounds: function(bounds, padding = 50, duration = 2000) {
        const state = GeoFahamState;
        
        if (state.map && bounds) {
            state.map.setCamera({
                bounds: bounds,
                padding: padding,
                type: "fly",
                duration: duration
            });
        }
    }
};

// Expose globally
window.MapInit = MapInit;

// Export for ES6 modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = MapInit;
}
