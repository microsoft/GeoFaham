// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

/**
 * Map Analysis Tools
 * Provides screenshot capture and vision-based analysis capabilities
 */

// Global registry for raster metadata (accessible across all modules)
window.rasterMetadataRegistry = window.rasterMetadataRegistry || {
    layers: new Map(), // layerId -> metadata
    
    /**
     * Store metadata for a raster layer
     */
    store: function(layerId, metadata) {
        console.log('📊 Storing raster metadata for layer:', layerId, metadata);
        this.layers.set(layerId, {
            ...metadata,
            timestamp: Date.now(),
            layerId: layerId
        });
    },
    
    /**
     * Remove metadata for a layer
     */
    remove: function(layerId) {
        console.log('📊 Removing raster metadata for layer:', layerId);
        this.layers.delete(layerId);
    },
    
    /**
     * Get all active raster metadata
     */
    getAllActive: function() {
        const metadata = [];
        this.layers.forEach((data, layerId) => {
            metadata.push(data);
        });
        return metadata;
    },
    
    /**
     * Clear all metadata
     */
    clear: function() {
        console.log('📊 Clearing all raster metadata');
        this.layers.clear();
    }
};

class MapAnalysisTools {
    constructor(map, chatInterface) {
        this.map = map;
        this.chatInterface = chatInterface;
        this.isCapturing = false;
        this.availableTools = [
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
        ];
    }

    /**
     * Capture the map canvas as a base64 image
     * Excludes UI elements like chatbox, controls, etc.
     * 
     * ENHANCED: Forces Azure Maps to render before capture to work around WebGL buffer clearing
     */
    async captureMapScreenshot() {
        return new Promise((resolve, reject) => {
            try {
                console.log('📸 MapView: Starting screenshot capture...');
                
                this.isCapturing = true;

                const mapContainer = document.getElementById('map');
                if (!mapContainer) {
                    this.isCapturing = false;
                    reject(new Error('Could not find map container'));
                    return;
                }

                const canvases = mapContainer.querySelectorAll('canvas');
                console.log(`📸 MapView: Found ${canvases.length} canvas element(s)`);
                
                if (canvases.length === 0) {
                    this.isCapturing = false;
                    reject(new Error('Could not find map canvas'));
                    return;
                }

                // Find the largest canvas (main map canvas, not overlays)
                let largestCanvas = null;
                let maxArea = 0;
                
                canvases.forEach((canvas, index) => {
                    const area = canvas.width * canvas.height;
                    console.log(`📸 Canvas ${index}: ${canvas.width}x${canvas.height} (area: ${area})`);
                    if (area > maxArea) {
                        maxArea = area;
                        largestCanvas = canvas;
                    }
                });
                
                if (!largestCanvas) {
                    this.isCapturing = false;
                    reject(new Error('Could not identify main map canvas'));
                    return;
                }
                
                const canvas = largestCanvas;
                console.log(`📸 MapView: Using canvas: ${canvas.width}x${canvas.height}`);
                
                // CRITICAL FIX: Force Azure Maps to render by triggering a map event
                // This ensures the WebGL context draws right before we capture
                console.log('📸 Forcing map render...');
                
                // Trigger a render by slightly moving the camera and moving it back
                const originalCamera = this.map.getCamera();
                const forceRender = () => {
                    // Trigger render by setting camera (even to same position)
                    this.map.setCamera({
                        center: originalCamera.center,
                        zoom: originalCamera.zoom,
                        type: 'ease',
                        duration: 0
                    });
                };
                
                forceRender();
                
                // Wait for render to complete, then capture in next frame
                console.log('📸 Scheduling capture after render...');
                
                // Use multiple animation frames to ensure render completes
                requestAnimationFrame(() => {
                    requestAnimationFrame(() => {
                        try {
                            console.log('📸 Capturing after forced render...');
                            
                            // Try multiple capture methods
                            let dataUrl = null;
                            
                            // Method 1: Composite all visible canvases (BEST for Azure Maps)
                            console.log('📸 Method 1: Compositing all canvases...');
                            try {
                                const compositeCanvas = document.createElement('canvas');
                                compositeCanvas.width = canvas.width;
                                compositeCanvas.height = canvas.height;
                                const ctx = compositeCanvas.getContext('2d', { willReadFrequently: true });
                                
                                // Fill with white background first
                                ctx.fillStyle = '#ffffff';
                                ctx.fillRect(0, 0, compositeCanvas.width, compositeCanvas.height);
                                
                                // Draw all canvases in order (bottom to top)
                                canvases.forEach((c, i) => {
                                    if (c.width > 0 && c.height > 0) {
                                        try {
                                            console.log(`📸 Drawing canvas ${i}: ${c.width}x${c.height}`);
                                            ctx.drawImage(c, 0, 0);
                                        } catch (e) {
                                            console.warn(`📸 Could not draw canvas ${i}:`, e);
                                        }
                                    }
                                });
                                
                                dataUrl = compositeCanvas.toDataURL('image/png', 1.0);
                                console.log('📸 Method 1 - length:', dataUrl.length);
                            } catch (e) {
                                console.warn('📸 Method 1 failed:', e);
                            }
                            
                            // Method 2: Direct capture from main canvas
                            if (!dataUrl || dataUrl.length < 5000) {
                                console.log('📸 Method 2: Direct canvas capture...');
                                try {
                                    dataUrl = canvas.toDataURL('image/png', 1.0);
                                    console.log('📸 Method 2 - length:', dataUrl.length);
                                } catch (e) {
                                    console.warn('📸 Method 2 failed:', e);
                                }
                            }
                            
                            // Method 3: Canvas copy with retry
                            if (!dataUrl || dataUrl.length < 5000) {
                                console.log('📸 Method 3: Canvas copy...');
                                try {
                                    const copyCanvas = document.createElement('canvas');
                                    copyCanvas.width = canvas.width;
                                    copyCanvas.height = canvas.height;
                                    const ctx = copyCanvas.getContext('2d');
                                    ctx.fillStyle = '#ffffff';
                                    ctx.fillRect(0, 0, copyCanvas.width, copyCanvas.height);
                                    ctx.drawImage(canvas, 0, 0);
                                    dataUrl = copyCanvas.toDataURL('image/png', 1.0);
                                    console.log('📸 Method 3 - length:', dataUrl.length);
                                } catch (e) {
                                    console.warn('📸 Method 3 failed:', e);
                                }
                            }
                            
                            // Check if we got a valid image (not just a blank/white canvas)
                            if (!dataUrl || dataUrl.length < 5000) {
                                console.error('❌ All capture methods failed or returned blank image');
                                console.error('❌ This likely means WebGL buffer was cleared before capture');
                                this.isCapturing = false;
                                reject(new Error('Screenshot capture returned empty/blank image. Azure Maps WebGL context may not preserve drawing buffer.'));
                                return;
                            }
                            
                            const base64Image = dataUrl.split(',')[1];
                            console.log(`✅ Screenshot captured (${base64Image.length} chars, ~${Math.round(base64Image.length/1024)}KB)`);
                            
                            this.isCapturing = false;
                            resolve(base64Image);
                            
                        } catch (error) {
                            console.error('❌ Error in capture frame:', error);
                            this.isCapturing = false;
                            reject(error);
                        }
                    });
                });
                
            } catch (error) {
                console.error('❌ Error in screenshot setup:', error);
                this.isCapturing = false;
                reject(error);
            }
        });
    }

    /**
     * Wait for map to finish rendering
     */
    waitForMapIdle() {
        return new Promise((resolve) => {
            // Azure Maps - wait for idle event or timeout
            let resolved = false;
            
            const finish = () => {
                if (!resolved) {
                    resolved = true;
                    resolve();
                }
            };
            
            // Listen for idle event
            this.map.events.addOnce('idle', finish);
            
            // Also set a timeout as fallback (2 seconds)
            setTimeout(finish, 2000);
        });
    }

    /**
     * Get current map metadata
     */
    getMapMetadata() {
        const camera = this.map.getCamera();
        const center = camera.center;
        const zoom = camera.zoom;
        const bounds = camera.bounds;

        // Get current map style
        const styleUri = this.map.getStyle();
        let basemapType = 'road';
        if (styleUri) {
            if (styleUri.includes && styleUri.includes('satellite')) {
                if (styleUri.includes('road') || styleUri.includes('labels')) {
                    basemapType = 'hybrid';
                } else {
                    basemapType = 'satellite';
                }
            } else if (styleUri.includes && styleUri.includes('grayscale')) {
                basemapType = 'grayscale';
            }
        }

        // Get visible layers (from layer control if available)
        const visibleLayers = [];
        // Try to get visible data layers from the map
        try {
            const layers = this.map.layers.getLayers();
            if (layers && layers.length > 0) {
                layers.forEach(layer => {
                    if (layer.getId && layer.getId()) {
                        visibleLayers.push(layer.getId());
                    }
                });
            }
        } catch (e) {
            // Layer enumeration not available, continue with empty array
        }
        
        // Get raster metadata for active layers
        const rasterMetadata = window.rasterMetadataRegistry.getAllActive();
        console.log('📊 Retrieved raster metadata for screenshot:', rasterMetadata);
        
        return {
            zoom: Math.round(zoom * 100) / 100, // Round to 2 decimals
            center: [center[1], center[0]], // lat, lon (Azure Maps uses lon, lat)
            bounds: bounds ? [
                [bounds[1], bounds[0]], // sw: lat, lon
                [bounds[3], bounds[2]]  // ne: lat, lon
            ] : null,
            // visible_layers: visibleLayers,
            basemap: basemapType,
            raster_layers: rasterMetadata // Include raster metadata
        };
    }

    /**
     * Analyze the current map view
     */
    async analyzeMapView(analysisType = 'general', customPrompt = null) {
        try {
            // Show loading message in chat
            this.chatInterface.addSystemMessage('📸 Capturing map screenshot...');

            // Capture screenshot
            const imageBase64 = await this.captureMapScreenshot();
            
            // Get metadata
            const metadata = this.getMapMetadata();

            this.chatInterface.addSystemMessage(`🤖 Analyzing map view (${analysisType})...`);

            // Send to backend for analysis
            const response = await fetch('/api/analyze-raster', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    image_base64: imageBase64,
                    analysis_type: analysisType,
                    custom_prompt: customPrompt,
                    metadata: metadata
                })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Analysis failed');
            }

            const result = await response.json();

            // Display results in chat
            this.displayAnalysisResults(result);

        } catch (error) {
            console.error('Error analyzing map:', error);
            this.chatInterface.addSystemMessage(`❌ Error: ${error.message}`, 'error');
        }
    }

    /**
     * Display analysis results in the chat interface
     */
    displayAnalysisResults(result) {
        if (!result.success) {
            this.chatInterface.addSystemMessage(`❌ Analysis failed: ${result.error}`, 'error');
            return;
        }

        // Format the analysis text with markdown-like formatting
        const analysis = result.analysis || 'No analysis available';
        
        // Add header
        let formattedMessage = `## 🗺️ Map Analysis Results\n\n`;
        formattedMessage += `**Analysis Type:** ${result.analysis_type}\n\n`;
        formattedMessage += `---\n\n`;
        formattedMessage += analysis;
        formattedMessage += `\n\n---\n\n`;
        
        // Add usage info
        if (result.usage) {
            formattedMessage += `*Tokens used: ${result.usage.total_tokens}*`;
        }

        // Display in chat
        this.chatInterface.addSystemMessage(formattedMessage, 'analysis');
    }

    /**
     * Get available tools
     */
    getAvailableTools() {
        return this.availableTools;
    }

    /**
     * Execute a tool by ID
     */
    async executeTool(toolId) {
        const tool = this.availableTools.find(t => t.id === toolId);
        if (!tool) {
            console.error('Tool not found:', toolId);
            return;
        }

        await this.analyzeMapView(tool.analysisType);
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = MapAnalysisTools;
}
