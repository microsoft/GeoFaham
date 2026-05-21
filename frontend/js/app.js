// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

/**
 * GeoFaham Frontend Application
 * Main entry point that initializes all modules
 */

const GeoFahamApp = {
    /**
     * Initialize the application
     */
    init: async function() {
        console.log('GeoFaham Application Initializing...');

        // Fetch per-deployment runtime config (e.g. the Azure Maps key)
        // before any module that depends on it is initialized.
        let runtimeConfig;
        try {
            const response = await fetch(GeoFahamConfig.server.configUrl);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            runtimeConfig = await response.json();
        } catch (error) {
            console.error('Failed to load runtime config from server:', error);
            this._showFatalError(
                'Failed to load application configuration from the server. ' +
                'The map will not load. Please check the server logs.'
            );
            return;
        }

        if (!runtimeConfig || !runtimeConfig.azureMapsKey) {
            console.error('Server returned an empty Azure Maps key.');
            this._showFatalError(
                'Azure Maps key is not configured on the server ' +
                '(AZURE_MAPS_KEY). The map cannot be initialized.'
            );
            return;
        }

        GeoFahamState.runtimeConfig = runtimeConfig;

        // Initialize WebSocket connection
        WebSocketManager.init();
        
        // Initialize Chat UI
        ChatUI.init();
        
        // Initialize Map Controls
        MapControls.init();
        
        // Initialize Map
        MapInit.init(runtimeConfig.azureMapsKey);
        
        // Setup mode selector
        this.setupModeSelector();
        
        // Setup reset button
        this.setupResetButton();
        
        // Initialize modals
        UploadModal.init();
        VisualizeModal.init();
        BenchmarkModal.init();
        
        // Setup debug mode
        this.setupDebugMode();
        
        // Setup test buttons
        this.setupTestButtons();
        
        // Initialize toolbox after map is ready
        this.initializeToolboxWhenReady();
        
        console.log('GeoFaham Application Initialized');
    },

    /**
     * Render a fatal initialization error to the user.
     * Falls back to a plain DOM element if ChatUI is not available yet.
     */
    _showFatalError: function(message) {
        try {
            if (typeof ChatUI !== 'undefined' && typeof ChatUI.displayMessage === 'function') {
                ChatUI.displayMessage(message, 'error');
                return;
            }
        } catch (_) { /* fall through to DOM fallback */ }
        const banner = document.createElement('div');
        banner.setAttribute('role', 'alert');
        banner.style.cssText = 'position:fixed;top:0;left:0;right:0;padding:12px;background:#b00020;color:#fff;font-family:sans-serif;z-index:99999;text-align:center;';
        banner.textContent = message;
        document.body.appendChild(banner);
    },

    /**
     * Setup mode selector
     */
    setupModeSelector: function() {
        const modeSelect = document.getElementById('agent-mode-select');
        if (modeSelect) {
            modeSelect.value = GeoFahamState.currentMode;
            
            modeSelect.addEventListener('change', function(event) {
                WebSocketManager.switchMode(event.target.value);
            });
        }
    },

    /**
     * Setup reset button
     */
    setupResetButton: function() {
        const resetButton = document.getElementById('reset-button');
        if (resetButton) {
            resetButton.addEventListener('click', (event) => {
                event.preventDefault();
                this.handleReset();
            });
        }
        
        // Keyboard shortcut: Ctrl+Shift+R
        document.addEventListener('keydown', (event) => {
            if (event.ctrlKey && event.shiftKey && event.key === 'R') {
                event.preventDefault();
                this.handleReset();
            }
        });
    },

    /**
     * Handle application reset
     */
    handleReset: function() {
        if (confirm('Are you sure you want to reset the application? This will clear all chat messages and map data.\n\nKeyboard shortcut: Ctrl+Shift+R')) {
            this.resetApplication();
        }
    },

    /**
     * Reset application
     */
    resetApplication: function() {
        console.log('Resetting application...');
        
        const resetButton = document.getElementById('reset-button');
        const originalContent = resetButton ? resetButton.innerHTML : '';
        
        if (resetButton) {
            resetButton.disabled = true;
            resetButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Resetting...';
        }
        
        try {
            // Clear chat messages
            ChatUI.clearMessages();
            
            // Clear all map layers
            LayerControls.clearAllMapLayers();
            
            // Reset map view
            MapInit.resetView();
            
            // Reset tools
            MapControls.resetTools();
            
            // Reinitialize data sources
            MapInit.initializeDataSources();
            
            // Call backend reset API
            fetch(GeoFahamConfig.server.resetUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    console.log('Backend state cleared successfully');
                    ChatUI.displayMessage('Application reset successfully. All history and state cleared.', 'system');
                } else {
                    console.error('Backend reset failed:', data);
                    ChatUI.displayMessage('Application reset completed, but there was an issue clearing backend state.', 'system');
                }
            })
            .catch(error => {
                console.error('Error calling reset API:', error);
                ChatUI.displayMessage('Frontend reset completed. Backend state may not be cleared.', 'system');
            })
            .finally(() => {
                setTimeout(() => {
                    if (resetButton) {
                        resetButton.disabled = false;
                        resetButton.innerHTML = originalContent;
                    }
                }, 1000);
            });
            
        } catch (error) {
            console.error('Error during reset:', error);
            ChatUI.displayMessage('Reset completed with some warnings. Check console for details.', 'system');
            setTimeout(() => {
                if (resetButton) {
                    resetButton.disabled = false;
                    resetButton.innerHTML = originalContent;
                }
            }, 1000);
        }
        
        ChatUI.enableInput();
    },

    /**
     * Setup debug mode toggle
     */
    setupDebugMode: function() {
        const debugToggle = document.getElementById('debug-mode-toggle');
        const debugButtons = document.querySelectorAll('.debug-only');
        
        // Load saved debug mode state
        const savedDebugMode = localStorage.getItem('debugMode');
        if (savedDebugMode === 'true') {
            GeoFahamState.debugMode = true;
            debugButtons.forEach(btn => btn.style.display = '');
            if (debugToggle) {
                debugToggle.classList.add('active');
                debugToggle.style.backgroundColor = '#ef4444';
                debugToggle.style.color = '#ffffff';
                debugToggle.style.boxShadow = '0 0 10px #ef4444';
                debugToggle.title = 'Debug Mode ON - Click to disable';
            }
        }
        
        if (debugToggle) {
            debugToggle.addEventListener('click', () => {
                GeoFahamState.debugMode = !GeoFahamState.debugMode;
                
                // Toggle debug buttons
                debugButtons.forEach(btn => {
                    btn.style.display = GeoFahamState.debugMode ? '' : 'none';
                });
                
                // Toggle debug messages
                const messagesContainer = document.getElementById('messages');
                const debugMessages = messagesContainer?.querySelectorAll('[data-debug="true"]');
                debugMessages?.forEach(msg => {
                    msg.style.display = GeoFahamState.debugMode ? '' : 'none';
                });
                
                // Update toggle appearance
                if (GeoFahamState.debugMode) {
                    debugToggle.classList.add('active');
                    debugToggle.style.backgroundColor = '#ef4444';
                    debugToggle.style.color = '#ffffff';
                    debugToggle.style.boxShadow = '0 0 10px #ef4444';
                    debugToggle.title = 'Debug Mode ON - Click to disable';
                } else {
                    debugToggle.classList.remove('active');
                    debugToggle.style.backgroundColor = '';
                    debugToggle.style.color = '';
                    debugToggle.style.boxShadow = '';
                    debugToggle.title = 'Toggle Debug Mode';
                }
                
                // Save state
                localStorage.setItem('debugMode', GeoFahamState.debugMode);
                
                console.log('Debug mode:', GeoFahamState.debugMode ? 'enabled' : 'disabled');
            });
        }
    },

    /**
     * Setup test buttons
     */
    setupTestButtons: function() {
        // Test Mosaic Button
        const testMosaicButton = document.getElementById('test-mosaic-button');
        if (testMosaicButton) {
            testMosaicButton.addEventListener('click', (event) => {
                event.preventDefault();
                this.testTemporalMosaicVisualization();
            });
        }
        
        // Test Multi-Band Button
        const testMultibandButton = document.getElementById('test-multiband-button');
        if (testMultibandButton) {
            testMultibandButton.addEventListener('click', (event) => {
                event.preventDefault();
                this.testMultibandVisualization();
            });
        }
    },

    /**
     * Test temporal mosaic visualization
     */
    testTemporalMosaicVisualization: function() {
        try {
            const userInput = prompt(
                'Paste your temporal mosaic JSON response:\n\n' +
                '(Tip: Copy the JSON object from your server response)',
                ''
            );
            
            if (!userInput || userInput.trim() === '') {
                ChatUI.displayMessage('Test cancelled - no JSON input provided', 'system');
                return;
            }
            
            ChatUI.displayMessage('Loading test temporal mosaic from user input...', 'system');
            
            let temporalMosaicResponse;
            try {
                temporalMosaicResponse = JSON.parse(userInput.trim());
            } catch (parseError) {
                ChatUI.displayMessage(
                    `Invalid JSON format: ${parseError.message}<br>Please ensure you paste a valid JSON object.`,
                    'error'
                );
                return;
            }
            
            if (!temporalMosaicResponse.metadata || !temporalMosaicResponse.metadata.mosaic_jsons) {
                ChatUI.displayMessage(
                    'Invalid temporal mosaic response: missing required fields (metadata.mosaic_jsons)',
                    'error'
                );
                return;
            }
            
            LayerRenderer.renderTemporalMosaic(temporalMosaicResponse);
            
            const mosaicCount = Object.keys(temporalMosaicResponse.metadata.mosaic_jsons).length;
            const collections = temporalMosaicResponse.metadata.collections || ['Unknown'];
            
            ChatUI.displayMessage(
                `Test temporal mosaic loaded successfully!<br>` +
                `Collections: ${collections.join(', ')}<br>` +
                `Timeline shows ${mosaicCount} temporal snapshot${mosaicCount !== 1 ? 's' : ''}.<br>` +
                'Use the slider to navigate between dates.',
                'system'
            );
        } catch (error) {
            console.error('Error testing temporal mosaic:', error);
            ChatUI.displayMessage(`Error loading test mosaic: ${error.message}`, 'error');
        }
    },

    /**
     * Test multi-band visualization
     */
    testMultibandVisualization: function() {
        ChatUI.displayMessage('Multi-band test: Please use the Test Mosaic button and paste STAC item tiles JSON', 'system');
    },

    /**
     * Initialize toolbox when map is ready
     */
    initializeToolboxWhenReady: function() {
        const checkMap = setInterval(() => {
            const map = GeoFahamState.map;
            if (map && map.events) {
                clearInterval(checkMap);
                map.events.add('ready', () => {
                    setTimeout(() => {
                        this.initializeToolbox();
                    }, 500);
                });
            }
        }, 100);
    },

    /**
     * Initialize analysis toolbox
     */
    initializeToolbox: function() {
        const map = GeoFahamState.map;
        
        // Create chat interface wrapper
        const chatInterface = {
            addSystemMessage: function(message, type = 'system') {
                ChatUI.displayMessage(message, type);
            }
        };
        
        // Initialize MapAnalysisTools if available
        if (typeof MapAnalysisTools !== 'undefined') {
            const mapAnalysisTools = new MapAnalysisTools(map, chatInterface);
            
            // Setup toolbox UI
            const toolboxToggle = document.getElementById('toolbox-toggle');
            const toolboxPanel = document.getElementById('toolbox-panel');
            const toolboxClose = document.getElementById('toolbox-close');
            const toolboxToolsContainer = document.getElementById('toolbox-tools');
            
            if (toolboxToggle && toolboxPanel) {
                toolboxToggle.addEventListener('click', () => {
                    const isVisible = toolboxPanel.style.display !== 'none';
                    toolboxPanel.style.display = isVisible ? 'none' : 'block';
                });
            }
            
            if (toolboxClose && toolboxPanel) {
                toolboxClose.addEventListener('click', () => {
                    toolboxPanel.style.display = 'none';
                });
            }
            
            // Load tools
            if (toolboxToolsContainer) {
                const tools = mapAnalysisTools.getAvailableTools();
                toolboxToolsContainer.innerHTML = '';
                
                tools.forEach(tool => {
                    const toolCard = document.createElement('div');
                    toolCard.className = 'tool-card';
                    toolCard.dataset.toolId = tool.id;
                    
                    toolCard.innerHTML = `
                        <div class="tool-icon">${tool.icon}</div>
                        <div class="tool-info">
                            <p class="tool-name">${tool.name}</p>
                            <p class="tool-description">${tool.description}</p>
                        </div>
                    `;
                    
                    toolCard.addEventListener('click', async () => {
                        if (toolCard.classList.contains('analyzing')) return;
                        
                        toolCard.classList.add('analyzing');
                        
                        try {
                            await mapAnalysisTools.executeTool(tool.id);
                        } catch (error) {
                            console.error('Error executing tool:', error);
                        } finally {
                            toolCard.classList.remove('analyzing');
                        }
                    });
                    
                    toolboxToolsContainer.appendChild(toolCard);
                });
            }
            
            console.log('Map analysis toolbox initialized');
        }
    }
};

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    GeoFahamApp.init();
});

// Expose globally
window.GeoFahamApp = GeoFahamApp;

// Export for ES6 modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = GeoFahamApp;
}
