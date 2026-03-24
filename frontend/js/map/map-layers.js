// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

/**
 * Layer Controls Module
 * Handles layer control panel functionality (toggle, opacity, remove)
 */

const LayerControls = {
    /**
     * Add a layer to the control panel
     */
    addLayerToControl: function(layerId, layerOrLayers, layerTitle, dataSource = null, isRaster = false) {
        const layerControls = document.getElementById('layer-controls');
        if (!layerControls) return;

        const controlItem = document.createElement('div');
        controlItem.style.cssText = 'display: flex; flex-direction: column; gap: 6px; margin: 8px 0; padding: 8px; border-radius: 6px; background: #f8fafc; border: 1px solid #e2e8f0;';
        controlItem.setAttribute('data-layer-id', layerId);

        // Top row: checkbox, label, and remove button
        const topRow = document.createElement('div');
        topRow.style.cssText = 'display: flex; align-items: center; gap: 8px;';

        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.checked = true;
        checkbox.id = `checkbox-${layerId}`;
        checkbox.style.margin = '0';

        const label = document.createElement('label');
        label.htmlFor = `checkbox-${layerId}`;
        label.style.cssText = 'font-size: 0.75rem; color: #475569; cursor: pointer; flex: 1;';
        label.textContent = layerTitle;

        const removeBtn = document.createElement('button');
        removeBtn.innerHTML = '<i class="fas fa-times"></i>';
        removeBtn.style.cssText = 'border: none; background: #ef4444; color: white; border-radius: 2px; width: 20px; height: 20px; cursor: pointer; font-size: 0.6rem;';
        removeBtn.title = 'Remove layer';

        topRow.appendChild(checkbox);
        topRow.appendChild(label);
        topRow.appendChild(removeBtn);

        // Bottom row: opacity slider
        const opacityRow = document.createElement('div');
        opacityRow.style.cssText = 'display: flex; align-items: center; gap: 6px; padding-left: 24px;';

        const opacityLabel = document.createElement('span');
        opacityLabel.style.cssText = 'font-size: 0.7rem; color: #64748b; min-width: 55px;';
        opacityLabel.textContent = 'Opacity:';

        const opacitySlider = document.createElement('input');
        opacitySlider.type = 'range';
        opacitySlider.min = '0';
        opacitySlider.max = '100';
        opacitySlider.value = '100';
        opacitySlider.className = 'layer-opacity-slider';
        opacitySlider.style.cssText = 'flex: 1; cursor: pointer;';

        const opacityValue = document.createElement('span');
        opacityValue.style.cssText = 'font-size: 0.7rem; color: #475569; min-width: 35px; font-weight: 600;';
        opacityValue.textContent = '100%';

        opacityRow.appendChild(opacityLabel);
        opacityRow.appendChild(opacitySlider);
        opacityRow.appendChild(opacityValue);

        // Handle both single layer and array of layers
        const isMultipleLayers = Array.isArray(layerOrLayers);
        const layers = isMultipleLayers ? layerOrLayers : [{ layer: layerOrLayers, id: layerId }];
        
        // Store layer references
        controlItem._layers = layers;
        controlItem._layerId = layerId;
        controlItem._dataSource = dataSource;

        const map = GeoFahamState.map;

        // Visibility toggle handler
        checkbox.addEventListener('change', () => {
            console.log(`Layer(s) ${layerId} visibility changed to:`, checkbox.checked);
            
            // Update visual feedback
            if (checkbox.checked) {
                controlItem.style.opacity = '1';
                label.style.textDecoration = 'none';
            } else {
                controlItem.style.opacity = '0.6';
                label.style.textDecoration = 'line-through';
            }

            try {
                layers.forEach(layerInfo => {
                    const layer = layerInfo.layer;
                    const currentLayerId = layerInfo.id;
                    
                    if (checkbox.checked) {
                        const existingLayer = map.layers.getLayerById(currentLayerId);
                        if (!existingLayer) {
                            map.layers.add(layer);
                        }
                    } else {
                        const existingLayer = map.layers.getLayerById(currentLayerId);
                        if (existingLayer) {
                            map.layers.remove(layer);
                        }
                    }
                });
            } catch (error) {
                console.error('Error toggling layer visibility:', error);
                ChatUI.displayMessage(`Error toggling layer visibility: ${error.message}`, 'error');
            }
        });

        // Opacity slider handler
        opacitySlider.addEventListener('input', (event) => {
            const opacityPercent = parseInt(event.target.value);
            const opacity = opacityPercent / 100;
            opacityValue.textContent = `${opacityPercent}%`;

            layers.forEach(layerInfo => {
                try {
                    const layer = map.layers.getLayerById(layerInfo.id);
                    if (!layer) return;
                    
                    if (layer.setOptions) {
                        const currentOptions = layer.getOptions();
                        
                        // TileLayer
                        if (currentOptions.tileUrl !== undefined || layer instanceof atlas.layer.TileLayer) {
                            layer.setOptions({ opacity: opacity });
                        }
                        // Polygon layer
                        else if (currentOptions.fillOpacity !== undefined) {
                            layer.setOptions({ 
                                fillOpacity: opacity,
                                strokeOpacity: opacity 
                            });
                        }
                        // Line layer
                        else if (currentOptions.strokeOpacity !== undefined) {
                            layer.setOptions({ strokeOpacity: opacity });
                        }
                        // Symbol layer
                        else if (currentOptions.iconOptions) {
                            layer.setOptions({ 
                                iconOptions: { 
                                    ...currentOptions.iconOptions,
                                    opacity: opacity 
                                }
                            });
                        }
                    } else if (typeof layer.setOpacity === 'function') {
                        layer.setOpacity(opacity);
                    }
                } catch (error) {
                    console.error('Error setting layer opacity:', error, layerInfo);
                }
            });
        });

        // Remove button handler
        removeBtn.addEventListener('click', () => {
            try {
                layers.forEach(layerInfo => {
                    const layer = layerInfo.layer;
                    const currentLayerId = layerInfo.id;
                    
                    const existingLayer = map.layers.getLayerById(currentLayerId);
                    if (existingLayer) {
                        map.layers.remove(layer);
                    }
                    
                    // Remove raster metadata
                    GeoFahamState.rasterMetadataRegistry.remove(currentLayerId);
                });
                
                // Remove data source
                if (dataSource) {
                    const sourceId = dataSource.getId();
                    const source = map.sources.getById(sourceId);
                    if (source) {
                        map.sources.remove(source);
                    }
                } else {
                    layers.forEach(layerInfo => {
                        const layer = layerInfo.layer;
                        if (layer.getSource) {
                            const sourceId = layer.getSource();
                            const source = map.sources.getById(sourceId);
                            if (source) {
                                map.sources.remove(source);
                            }
                        }
                    });
                }
                
                controlItem.remove();
                ChatUI.displayMessage(`Layer removed: ${layerTitle}`, 'system');
                
            } catch (error) {
                console.error('Error removing layer:', error);
                ChatUI.displayMessage(`Error removing layer: ${error.message}`, 'error');
            }
        });

        controlItem.appendChild(topRow);
        controlItem.appendChild(opacityRow);
        
        // Add raster-specific controls if applicable
        if (isRaster && typeof addRasterControls === 'function') {
            const rasterMetadata = getRasterLayerMetadata(layerId);
            if (rasterMetadata) {
                addRasterControls(controlItem, layerId, rasterMetadata);
            }
        }
        
        layerControls.appendChild(controlItem);
    },

    /**
     * Clear all layer controls
     */
    clearAll: function() {
        const layerControls = document.getElementById('layer-controls');
        if (layerControls) {
            layerControls.innerHTML = '';
        }
    },

    /**
     * Clear all map layers
     */
    clearAllMapLayers: function() {
        const map = GeoFahamState.map;
        const state = GeoFahamState;
        
        try {
            // Clear drawing manager
            if (state.drawingManager && state.drawingManager.getSource) {
                state.drawingManager.getSource().clear();
            }
            
            // Clear all data layers
            if (map && map.layers && map.layers.getLayers) {
                const layersToRemove = [];
                
                const allLayers = map.layers.getLayers();
                if (allLayers && allLayers.forEach) {
                    allLayers.forEach(layer => {
                        if (layer && layer.getId) {
                            const layerId = layer.getId();
                            if (layerId && 
                                !layerId.startsWith('microsoft.') && 
                                !layerId.startsWith('base') &&
                                !layerId.includes('road') &&
                                !layerId.includes('satellite') &&
                                !layerId.includes('grayscale')) {
                                layersToRemove.push(layer);
                            }
                        }
                    });
                }
                
                layersToRemove.forEach(layer => {
                    try {
                        map.layers.remove(layer);
                        if (layer.getId) {
                            state.rasterMetadataRegistry.remove(layer.getId());
                        }
                    } catch (error) {
                        console.warn('Error removing layer:', error);
                    }
                });
            }
            
            // Clear all raster metadata
            state.rasterMetadataRegistry.clear();
            
            // Clear data sources
            if (map && map.sources && map.sources.getSources) {
                const sourcesToRemove = [];
                
                const allSources = map.sources.getSources();
                if (allSources && allSources.forEach) {
                    allSources.forEach(source => {
                        if (source && source.getId) {
                            const sourceId = source.getId();
                            if (sourceId && 
                                !sourceId.startsWith('microsoft.') && 
                                !sourceId.startsWith('base')) {
                                sourcesToRemove.push(source);
                            }
                        }
                    });
                }
                
                sourcesToRemove.forEach(source => {
                    try {
                        map.sources.remove(source);
                    } catch (error) {
                        console.warn('Error removing source:', error);
                    }
                });
            }
            
        } catch (error) {
            console.warn('Error during layer cleanup:', error);
        }
        
        // Clear layer controls
        this.clearAll();
        
        // Close popup
        if (state.popup && state.popup.close) {
            state.popup.close();
        }
        
        // Remove damage legend
        const existingLegend = document.getElementById('damage-legend');
        if (existingLegend) {
            existingLegend.remove();
        }
        
        // Clear timeline managers
        const timelineManager = state.temporalCOGTimelineManager || window.temporalCOGTimelineManager;
        if (timelineManager && timelineManager instanceof Map) {
            timelineManager.forEach((manager, label) => {
                try {
                    manager.removeAllLayers();
                    manager.removeTimelineUI();
                } catch (error) {
                    console.warn(`Error clearing timeline manager for ${label}:`, error);
                }
            });
            timelineManager.clear();
        }
        
        // Remove timeline UI elements
        const timelineElements = document.querySelectorAll('.temporal-timeline');
        timelineElements.forEach(el => el.remove());
    }
};

// Expose globally
window.LayerControls = LayerControls;
window.addLayerToControl = LayerControls.addLayerToControl.bind(LayerControls);
window.clearAllMapLayers = LayerControls.clearAllMapLayers.bind(LayerControls);

// Export for ES6 modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = LayerControls;
}
