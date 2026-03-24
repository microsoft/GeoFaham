// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

/**
 * Map Controls Module
 * Handles map style controls, drawing tools, and tool interactions
 */

const MapControls = {
    /**
     * Setup map style controls
     */
    setupStyleControls: function() {
        const styleButtons = document.querySelectorAll('.style-btn');

        styleButtons.forEach(button => {
            button.addEventListener('click', function() {
                const style = this.getAttribute('data-style');

                // Update active state
                styleButtons.forEach(btn => btn.classList.remove('active'));
                this.classList.add('active');

                // Change map style
                GeoFahamState.map.setStyle({
                    style: style
                });
            });
        });
    },

    /**
     * Setup drawing tools
     */
    setupDrawingTools: function() {
        const toolButtons = document.querySelectorAll('.tool-btn');

        toolButtons.forEach(button => {
            button.addEventListener('click', function() {
                const tool = this.getAttribute('data-tool');
                MapControls.activateTool(tool);

                // Update active state
                toolButtons.forEach(btn => btn.classList.remove('active'));
                if (tool !== 'clear') {
                    this.classList.add('active');
                }
            });
        });
    },

    /**
     * Activate a drawing tool
     */
    activateTool: function(tool) {
        const state = GeoFahamState;
        state.currentTool = tool;

        switch (tool) {
            case 'select':
                state.drawingManager.setOptions({ mode: 'idle' });
                break;
            case 'draw-point':
                state.drawingManager.setOptions({ mode: 'draw-point' });
                break;
            case 'draw-line':
                state.drawingManager.setOptions({ mode: 'draw-line' });
                break;
            case 'draw-polygon':
                state.drawingManager.setOptions({ mode: 'draw-polygon' });
                break;
            case 'draw-rectangle':
                state.drawingManager.setOptions({ mode: 'draw-rectangle' });
                break;
            case 'draw-circle':
                state.drawingManager.setOptions({ mode: 'draw-circle' });
                break;
            case 'measure':
                this.enableMeasureTool();
                break;
            case 'clear':
                this.clearAllDrawings();
                break;
        }
    },

    /**
     * Enable measure tool
     */
    enableMeasureTool: function() {
        GeoFahamState.drawingManager.setOptions({ mode: 'draw-line' });
        ChatUI.displayMessage('Measure tool activated. Draw a line to measure distance.', 'system');
    },

    /**
     * Clear all drawings
     */
    clearAllDrawings: function() {
        const state = GeoFahamState;
        
        if (state.drawingManager) {
            state.drawingManager.getSource().clear();
        }

        // Clear any popup
        if (state.popup) {
            state.popup.close();
        }

        ChatUI.displayMessage('All drawings cleared.', 'system');
    },

    /**
     * Show shape info after drawing
     */
    showShapeInfo: function(shape) {
        const coords = shape.getCoordinates();
        const properties = shape.getProperties();
        let info = '';
        let geojson = null;

        // Check if this is a Circle
        if (shape.circlePolygon && properties && properties.subType === 'Circle') {
            const radius = properties.radius;
            const area = atlas.math.getArea(shape.circlePolygon);
            info = `Circle: Radius ${radius.toFixed(2)} m, Area ${(area / 1000000).toFixed(2)} km²`;
            
            geojson = {
                type: "Feature",
                geometry: shape.circlePolygon.geometry,
                properties: {
                    subType: 'Circle',
                    radius_m: parseFloat(radius.toFixed(2)),
                    area_km2: parseFloat((area / 1000000).toFixed(2)),
                    center: coords
                }
            };
        } else {
            // Handle other shape types
            switch (shape.getType()) {
                case 'Point':
                    info = `Point: [${coords[1].toFixed(6)}, ${coords[0].toFixed(6)}]`;
                    geojson = {
                        type: "Feature",
                        geometry: {
                            type: "Point",
                            coordinates: [coords[0], coords[1]]
                        },
                        properties: {
                            file_type: "user_drawn"
                        }
                    };
                    break;
                case 'LineString':
                    const distance = atlas.math.getDistanceTo(coords[0], coords[coords.length - 1]);
                    info = `Line: ${(distance / 1000).toFixed(2)} km`;
                    geojson = {
                        type: "Feature",
                        geometry: {
                            type: "LineString",
                            coordinates: coords
                        },
                        properties: {
                            distance_km: parseFloat((distance / 1000).toFixed(2)),
                            file_type: "user_drawn"
                        }
                    };
                    break;
                case 'Polygon':
                    const area = atlas.math.getArea(shape);
                    info = `Polygon: Area ${(area / 1000000).toFixed(2)} km²`;
                    geojson = {
                        type: "Feature",
                        geometry: {
                            type: "Polygon",
                            coordinates: coords
                        },
                        properties: {
                            area_km2: parseFloat((area / 1000000).toFixed(2)),
                            file_type: "user_drawn"
                        }
                    };
                    break;
                case 'Rectangle':
                    const rectArea = atlas.math.getArea(shape);
                    info = `Rectangle: Area ${(rectArea / 1000000).toFixed(2)} km²`;
                    geojson = {
                        type: "Feature",
                        geometry: {
                            type: "Polygon",
                            coordinates: coords
                        },
                        properties: {
                            subType: 'Rectangle',
                            area_km2: parseFloat((rectArea / 1000000).toFixed(2)),
                            file_type: "user_drawn"
                        }
                    };
                    break;
            }
        }

        if (info) {
            ChatUI.displayMessage(`Shape created: ${info}`, 'system');
            
            // Store GeoJSON for use in chat
            if (geojson) {
                const geojsonComp = {
                    type: "FeatureCollection",
                    features: [geojson]
                };
                console.log('GeoJSON created:', geojsonComp);
                document.getElementById('user_raw_json').value = JSON.stringify(geojsonComp);
            }
        }
    },

    /**
     * Reset tools to default state
     */
    resetTools: function() {
        const state = GeoFahamState;
        
        state.currentTool = 'select';
        if (state.drawingManager) {
            state.drawingManager.setOptions({ mode: 'idle' });
        }
        
        // Reset tool button states
        const toolButtons = document.querySelectorAll('.tool-btn');
        toolButtons.forEach(btn => btn.classList.remove('active'));
        
        const selectButton = document.getElementById('select-tool');
        if (selectButton) {
            selectButton.classList.add('active');
        }
    },

    /**
     * Initialize all map controls
     */
    init: function() {
        this.setupStyleControls();
        this.setupDrawingTools();
    }
};

// Expose globally
window.MapControls = MapControls;

// Export for ES6 modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = MapControls;
}
