// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

/**
 * Frontend Configuration
 * Centralized configuration for all frontend modules
 */

const GeoFahamConfig = {
    // Server configuration
    server: {
        wsUrl: `wss://***REMOVED-DEVTUNNEL-URL***/ws/chat`,
        apiBaseUrl: '',  // Same origin
        historyUrl: '/history',
        resetUrl: '/api/reset',
        uploadUrl: '/api/upload-geojson',
        analyzeRasterUrl: '/api/analyze-raster',
        testRasterUrl: '/api/test-raster',
        saveBenchmarkUrl: '/api/save-benchmark-gt',
        colormapsUrl: '/titiler_colormaps.json'
    },

    // Azure Maps configuration
    map: {
        authOptions: {
            authType: 'subscriptionKey',
            subscriptionKey: '***REMOVED-AZURE-MAPS-KEY***'
        },
        defaultCenter: [0, 20],
        defaultZoom: 2,
        defaultStyle: 'satellite_road_labels',
        preserveDrawingBuffer: true,
        enableAccessibility: true,
        showLogo: false,
        showFeedbackLink: false
    },

    // WebSocket configuration
    websocket: {
        reconnectInterval: 3000,
        maxReconnectAttempts: 10
    },

    // HTTP polling fallback configuration
    polling: {
        initUrl: '/api/polling/init',
        sendUrl: '/api/polling/send',
        pollUrl: '/api/polling/poll',
        interval: 1000  // ms between poll requests
    },

    // Agent modes
    agentModes: {
        'multi-agent': 'Multi-Agent Team',
        'postgis': 'PostGIS Agent',
        'map_search': 'Map Search Agent',
        'stac': 'STAC Agent',
        'raster_ops': 'RasterOps Agent'
    },

    // Layer configuration
    layers: {
        maxCachedLayers: 5,
        defaultOpacity: 0.8,
        defaultPointRadius: 6,
        defaultLineWidth: 3
    },

    // UI configuration
    ui: {
        messageScrollBehavior: 'smooth',
        maxTextareaHeight: 120,
        toastDuration: 3000
    },

    // Analysis tool types
    analysisTools: [
        {
            id: 'analyze-general',
            name: 'Analyze Map View',
            icon: '🔍',
            description: 'General analysis of visible features',
            analysisType: 'general'
        },
        {
            id: 'analyze-damage',
            name: 'Damage Assessment',
            icon: '⚠️',
            description: 'Focus on damage and impacts',
            analysisType: 'damage'
        },
        {
            id: 'analyze-infrastructure',
            name: 'Infrastructure Analysis',
            icon: '🏗️',
            description: 'Analyze roads, buildings, utilities',
            analysisType: 'infrastructure'
        },
        {
            id: 'analyze-change',
            name: 'Change Detection',
            icon: '🔄',
            description: 'Identify changes and patterns',
            analysisType: 'change'
        }
    ],

    // Color palettes for vector layers
    colorPalettes: {
        categorical: [
            '#e6194B', '#3cb44b', '#ffe119', '#4363d8', '#f58231',
            '#911eb4', '#42d4f4', '#f032e6', '#bfef45', '#fabed4',
            '#469990', '#dcbeff', '#9A6324', '#fffac8', '#800000',
            '#aaffc3', '#808000', '#ffd8b1', '#000075', '#a9a9a9'
        ],
        sequential: ['#feedde', '#fdbe85', '#fd8d3c', '#e6550d', '#a63603']
    }
};

// Freeze config to prevent accidental modifications
Object.freeze(GeoFahamConfig);
Object.freeze(GeoFahamConfig.server);
Object.freeze(GeoFahamConfig.map);
Object.freeze(GeoFahamConfig.websocket);
Object.freeze(GeoFahamConfig.polling);
Object.freeze(GeoFahamConfig.agentModes);
Object.freeze(GeoFahamConfig.layers);
Object.freeze(GeoFahamConfig.ui);

// Export for ES6 modules (if used)
if (typeof module !== 'undefined' && module.exports) {
    module.exports = GeoFahamConfig;
}
