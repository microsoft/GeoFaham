// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

/**
 * Raster Layer Controls
 * Handles colormap selection and class label legends for raster layers
 */

// Global registry for raster layers with their metadata
window.rasterLayersRegistry = window.rasterLayersRegistry || new Map();

// Load colormaps from JSON file
let availableColormaps = [];

async function loadColormaps() {
    try {
        const response = await fetch('/titler_colormaps.json');
        if (!response.ok) {
            // throw new Error('Failed to load colormaps');
            console.log("Failed to load colormaps, using fallback");
        }
        availableColormaps = await response.json();
        console.log(`Loaded ${availableColormaps.length} colormaps`);
        return availableColormaps;
    } catch (error) {
        console.error('Error loading colormaps:', error);
        // Fallback to common colormaps if loading fails
        availableColormaps = [
            'viridis', 'plasma', 'inferno', 'magma', 'cividis',
            'turbo', 'rainbow', 'jet', 'hot', 'cool',
            'rdylgn', 'rdylbu', 'spectral', 'terrain', 'earth'
        ];
        return availableColormaps;
    }
}

/**
 * Register a raster layer with its metadata
 */
function registerRasterLayer(layerId, metadata) {
    window.rasterLayersRegistry.set(layerId, {
        ...metadata,
        layerId: layerId,
        currentColormap: metadata.colormap || null
    });
    console.log(`Registered raster layer: ${layerId}`, metadata);
}

/**
 * Get raster layer metadata
 */
function getRasterLayerMetadata(layerId) {
    return window.rasterLayersRegistry.get(layerId);
}

/**
 * Update raster layer colormap
 */
function updateRasterColormap(layerId, newColormap) {
    const metadata = getRasterLayerMetadata(layerId);
    if (!metadata) {
        console.error(`Raster layer ${layerId} not found in registry`);
        return false;
    }

    // Remove old layer
    const oldLayer = map.layers.getLayerById(layerId);
    if (!oldLayer) {
        console.error(`Layer ${layerId} not found on map`);
        return false;
    }

    // Get current layer options
    const oldOptions = oldLayer.getOptions();
    const currentOpacity = oldOptions.opacity || 1.0;
    const currentVisible = oldOptions.visible !== false;

    // Remove old layer
    map.layers.remove(oldLayer);

    // Build new tile URL with updated colormap
    const { url, rescale_min, rescale_max, statistics } = metadata;
    
    // Use rescale values or fall back to statistics
    let effectiveRescaleMin = rescale_min;
    let effectiveRescaleMax = rescale_max;
    if (statistics && (effectiveRescaleMin === undefined || effectiveRescaleMax === undefined)) {
        effectiveRescaleMin = statistics.min;
        effectiveRescaleMax = statistics.max;
    }
    
    let tileUrl = `/tiles/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png?url=${encodeURIComponent(url)}`;
    
    if (newColormap && newColormap !== 'none') {
        tileUrl += `&colormap_name=${newColormap}`;
    }
    if (effectiveRescaleMin !== undefined && effectiveRescaleMin !== null && effectiveRescaleMax !== undefined && effectiveRescaleMax !== null) {
        tileUrl += `&rescale=${effectiveRescaleMin},${effectiveRescaleMax}`;
    }

    // Create new layer with updated colormap
    const newLayer = new atlas.layer.TileLayer({
        tileUrl: tileUrl,
        tileSize: 256,
        minSourceZoom: metadata.minzoom || 0,
        maxSourceZoom: metadata.maxzoom || 18,
        opacity: currentOpacity,
        visible: currentVisible
    }, layerId);

    // Add new layer to map
    map.layers.add(newLayer, 'labels');

    // Update the layer reference in the layer control
    const controlItem = document.querySelector(`[data-layer-id="${layerId}"]`);
    if (controlItem && controlItem._layers) {
        // Update the layer reference so opacity slider and other controls work
        controlItem._layers = controlItem._layers.map(layerInfo => {
            if (layerInfo.id === layerId) {
                return { layer: newLayer, id: layerId };
            }
            return layerInfo;
        });
        console.log(`Updated layer reference in control for ${layerId}`);
    }

    // Update registry
    metadata.currentColormap = newColormap;
    window.rasterLayersRegistry.set(layerId, metadata);

    console.log(`Updated raster layer ${layerId} with colormap: ${newColormap}`);
    return true;
}

// Colormap picker is now part of the floating legend panel
// See showRasterLegend function

/**
 * Create class label legend UI element
 * For classified rasters, the pixel values correspond directly to class IDs
 * The colormap applied by TiTiler handles the visualization
 */
function createClassLabelLegend(classLabels) {
    const legendContainer = document.createElement('div');
    legendContainer.style.cssText = 'margin-top: 6px; padding: 6px; background: #f1f5f9; border-radius: 4px; font-size: 0.7rem;';

    const legendTitle = document.createElement('div');
    legendTitle.style.cssText = 'font-weight: 600; color: #475569; margin-bottom: 4px;';
    legendTitle.textContent = 'Class Labels:';
    legendContainer.appendChild(legendTitle);

    // Sort class labels by key (numeric order)
    const sortedEntries = Object.entries(classLabels).sort((a, b) => {
        const aNum = parseInt(a[0]);
        const bNum = parseInt(b[0]);
        return aNum - bNum;
    });

    // Create legend items (no color boxes - colormap handles visualization)
    sortedEntries.forEach(([classValue, classLabel]) => {
        const item = document.createElement('div');
        item.style.cssText = 'display: flex; align-items: center; gap: 6px; margin: 2px 0; padding-left: 4px;';

        const labelText = document.createElement('span');
        labelText.style.cssText = 'color: #475569; font-size: 0.65rem;';
        labelText.textContent = `${classValue}: ${classLabel}`;

        item.appendChild(labelText);
        legendContainer.appendChild(item);
    });

    return legendContainer;
}

/**
 * Create colormap visualization (gradient image)
 */
function createColormapVisualization(colormap, rescale_min, rescale_max) {
    if (!colormap || colormap === 'none') {
        return null;
    }

    const vizContainer = document.createElement('div');
    vizContainer.style.cssText = 'margin-top: 6px; padding: 6px; background: #f1f5f9; border-radius: 4px;';

    const vizTitle = document.createElement('div');
    vizTitle.style.cssText = 'font-size: 0.7rem; font-weight: 600; color: #475569; margin-bottom: 4px;';
    vizTitle.textContent = 'Colormap:';
    vizContainer.appendChild(vizTitle);

    // Colormap gradient image from TiTiler (relative URL for tunnel/proxy compatibility)
    const gradientImg = document.createElement('img');
    gradientImg.src = `/tiles/colormap/colorMaps/${colormap}?f=png&orientation=horizontal`;
    gradientImg.style.cssText = 'width: 100%; height: 20px; border-radius: 4px; border: 1px solid #cbd5e1; display: block;';
    gradientImg.alt = `${colormap} colormap`;
    vizContainer.appendChild(gradientImg);

    // Add value labels if rescale is provided
    if (rescale_min !== undefined && rescale_min !== null && rescale_max !== undefined && rescale_max !== null) {
        const labelsContainer = document.createElement('div');
        labelsContainer.style.cssText = 'display: flex; justify-content: space-between; font-size: 0.65rem; color: #6b7280; margin-top: 2px;';
        labelsContainer.innerHTML = `<span>${rescale_min}</span><span>${rescale_max}</span>`;
        vizContainer.appendChild(labelsContainer);
    }

    return vizContainer;
}

// Colormap visualization is now handled in the floating legend panel
// See updateRasterLegendVisualization function

/**
 * Add raster-specific controls to layer control item
 */
function addRasterControls(controlItem, layerId, metadata) {
    // Add a small indicator button to show/hide raster legend
    const legendButton = document.createElement('button');
    legendButton.className = 'raster-legend-toggle';
    legendButton.style.cssText = 'margin-top: 4px; margin-left: 24px; padding: 4px 8px; font-size: 0.65rem; background: #3b82f6; color: white; border: none; border-radius: 4px; cursor: pointer;';
    legendButton.innerHTML = '<i class="fas fa-palette"></i> Raster Controls';
    legendButton.title = 'Show raster colormap and controls';
    
    legendButton.addEventListener('click', () => {
        showRasterLegend(layerId, metadata);
    });
    
    controlItem.appendChild(legendButton);
}

/**
 * Show raster legend and controls in a floating panel
 */
function showRasterLegend(layerId, metadata) {
    // Remove existing raster legend if present
    const existingLegend = document.getElementById('raster-legend');
    if (existingLegend) {
        existingLegend.remove();
    }

    // Create legend container
    const legendContainer = document.createElement('div');
    legendContainer.id = 'raster-legend';
    legendContainer.style.cssText = `
        position: absolute;
        bottom: 120px;
        left: 1rem;
        background: rgba(255, 255, 255, 0.95);
        border-radius: 8px;
        padding: 12px;
        box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
        border: 1px solid #e2e8f0;
        z-index: 1000;
        min-width: 250px;
        max-width: 300px;
        backdrop-filter: blur(8px);
    `;

    // Legend title
    const title = document.createElement('h4');
    title.textContent = metadata.title || 'Raster Layer';
    title.style.cssText = `
        margin: 0 0 8px 0;
        font-size: 14px;
        font-weight: 600;
        color: #1f2937;
    `;
    legendContainer.appendChild(title);

    // Colormap picker
    const pickerLabel = document.createElement('div');
    pickerLabel.style.cssText = 'font-size: 0.75rem; color: #475569; margin-bottom: 4px; font-weight: 500;';
    pickerLabel.textContent = 'Select Colormap:';
    legendContainer.appendChild(pickerLabel);

    const pickerSelect = document.createElement('select');
    pickerSelect.className = 'colormap-picker';
    pickerSelect.style.cssText = 'width: 100%; padding: 4px 6px; font-size: 0.75rem; border: 1px solid #cbd5e1; border-radius: 4px; background: white; cursor: pointer; margin-bottom: 8px;';

    // Add "Default (RGB)" option
    const defaultOption = document.createElement('option');
    defaultOption.value = 'none';
    defaultOption.textContent = 'Default (RGB)';
    pickerSelect.appendChild(defaultOption);

    // Add colormap options
    availableColormaps.forEach(colormap => {
        const option = document.createElement('option');
        option.value = colormap;
        option.textContent = colormap;
        if (colormap === metadata.currentColormap) {
            option.selected = true;
        }
        pickerSelect.appendChild(option);
    });

    // Set current colormap
    if (!metadata.currentColormap || metadata.currentColormap === 'none') {
        defaultOption.selected = true;
    }

    // Add change event listener
    pickerSelect.addEventListener('change', (event) => {
        const newColormap = event.target.value === 'none' ? null : event.target.value;
        const success = updateRasterColormap(layerId, newColormap);
        if (success) {
            displayMessage(`Colormap changed to: ${newColormap || 'Default (RGB)'}`, 'system');
            
            // Update colormap visualization in the legend
            updateRasterLegendVisualization(layerId, newColormap, legendContainer);
        } else {
            displayMessage('Failed to update colormap', 'error');
        }
    });

    legendContainer.appendChild(pickerSelect);

    // Add colormap visualization if a colormap is selected
    if (metadata.currentColormap && metadata.currentColormap !== 'none') {
        const colormapViz = createColormapVisualization(
            metadata.currentColormap,
            metadata.rescale_min,
            metadata.rescale_max
        );
        if (colormapViz) {
            colormapViz.id = 'raster-legend-viz';
            legendContainer.appendChild(colormapViz);
        }
    }

    // Add class label legend if available
    if (metadata.class_labels && Object.keys(metadata.class_labels).length > 0) {
        const classLegend = createClassLabelLegend(metadata.class_labels);
        legendContainer.appendChild(classLegend);
    }

    // Add statistics if available
    if (metadata.statistics) {
        const statsContainer = document.createElement('div');
        statsContainer.style.cssText = 'margin-top: 8px; padding-top: 8px; border-top: 1px solid #e5e7eb; font-size: 0.7rem; color: #6b7280;';
        statsContainer.innerHTML = `
            <div style="font-weight: 600; margin-bottom: 4px;">Statistics:</div>
            <div>Min: ${metadata.statistics.min}</div>
            <div>Max: ${metadata.statistics.max}</div>
            ${metadata.statistics.mean !== undefined ? `<div>Mean: ${metadata.statistics.mean.toFixed(2)}</div>` : ''}
            ${metadata.statistics.std !== undefined ? `<div>Std Dev: ${metadata.statistics.std.toFixed(2)}</div>` : ''}
        `;
        legendContainer.appendChild(statsContainer);
    }

    // Add close button
    const closeButton = document.createElement('button');
    closeButton.innerHTML = '×';
    closeButton.style.cssText = `
        position: absolute;
        top: 4px;
        right: 6px;
        background: none;
        border: none;
        font-size: 18px;
        color: #6b7280;
        cursor: pointer;
        width: 24px;
        height: 24px;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: 4px;
    `;
    closeButton.title = 'Close legend';
    closeButton.addEventListener('click', () => {
        legendContainer.remove();
    });
    closeButton.addEventListener('mouseenter', () => {
        closeButton.style.background = '#f3f4f6';
    });
    closeButton.addEventListener('mouseleave', () => {
        closeButton.style.background = 'none';
    });

    legendContainer.appendChild(closeButton);

    // Add to map container
    const mapSection = document.querySelector('.map-section');
    mapSection.appendChild(legendContainer);
}

/**
 * Update colormap visualization in the raster legend
 */
function updateRasterLegendVisualization(layerId, newColormap, legendContainer) {
    const metadata = getRasterLayerMetadata(layerId);
    if (!metadata) return;

    // Remove existing visualization
    const existingViz = legendContainer.querySelector('#raster-legend-viz');
    if (existingViz) {
        existingViz.remove();
    }

    // Add new visualization if colormap is selected
    if (newColormap && newColormap !== 'none') {
        const colormapViz = createColormapVisualization(
            newColormap,
            metadata.rescale_min,
            metadata.rescale_max
        );
        if (colormapViz) {
            colormapViz.id = 'raster-legend-viz';
            
            // Insert after the select element
            const select = legendContainer.querySelector('.colormap-picker');
            if (select) {
                select.insertAdjacentElement('afterend', colormapViz);
            }
        }
    }
}

/**
 * Check if a layer is a raster layer
 */
function isRasterLayer(layerId) {
    return window.rasterLayersRegistry.has(layerId);
}

// Initialize colormaps when page loads
document.addEventListener('DOMContentLoaded', async () => {
    await loadColormaps();
    console.log('Raster controls initialized');
});
