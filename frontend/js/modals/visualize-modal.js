// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

/**
 * Visualize Modal Module
 * Handles GeoJSON visualization without upload
 */

const VisualizeModal = {
    selectedFile: null,

    /**
     * Initialize visualize modal
     */
    init: function() {
        const visualizeButton = document.getElementById('visualize-button');
        const visualizeModal = document.getElementById('visualize-modal');
        const closeModal = document.getElementById('close-visualize-modal');
        const cancelVisualize = document.getElementById('cancel-visualize');
        const fileInput = document.getElementById('visualize-file-input');
        const dropZone = document.getElementById('visualize-drop-zone');
        const filePreview = document.getElementById('visualize-file-preview');
        const fileName = document.getElementById('visualize-file-name');
        const removeFileBtn = document.getElementById('remove-visualize-file');
        const submitButton = document.getElementById('visualize-submit');
        const visualizeError = document.getElementById('visualize-error');
        
        if (!visualizeModal) return;

        // Open modal
        if (visualizeButton) {
            visualizeButton.addEventListener('click', (e) => {
                e.preventDefault();
                visualizeModal.classList.add('show');
                this.resetForm();
            });
        }
        
        // Close modal handlers
        const closeModalHandler = () => {
            visualizeModal.classList.remove('show');
            this.resetForm();
        };
        
        if (closeModal) closeModal.addEventListener('click', closeModalHandler);
        if (cancelVisualize) cancelVisualize.addEventListener('click', closeModalHandler);
        
        // Close on backdrop click
        visualizeModal.addEventListener('click', (e) => {
            if (e.target === visualizeModal) {
                closeModalHandler();
            }
        });
        
        // Browse link click
        const browseLink = dropZone?.querySelector('.browse-link');
        if (browseLink) {
            browseLink.addEventListener('click', (e) => {
                e.stopPropagation();
                fileInput.click();
            });
        }
        
        // Drop zone click
        if (dropZone) {
            dropZone.addEventListener('click', () => fileInput.click());
        }
        
        // File input change
        if (fileInput) {
            fileInput.addEventListener('change', (e) => {
                this.handleFileSelect(e.target.files[0]);
            });
        }
        
        // Drag and drop
        if (dropZone) {
            dropZone.addEventListener('dragover', (e) => {
                e.preventDefault();
                dropZone.classList.add('drag-over');
            });
            
            dropZone.addEventListener('dragleave', () => {
                dropZone.classList.remove('drag-over');
            });
            
            dropZone.addEventListener('drop', (e) => {
                e.preventDefault();
                dropZone.classList.remove('drag-over');
                this.handleFileSelect(e.dataTransfer.files[0]);
            });
        }
        
        // Remove file
        if (removeFileBtn) {
            removeFileBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.selectedFile = null;
                if (fileInput) fileInput.value = '';
                if (filePreview) filePreview.style.display = 'none';
                if (dropZone) dropZone.querySelector('.drop-zone-content').style.display = 'block';
                if (submitButton) submitButton.disabled = true;
            });
        }
        
        // Submit button
        if (submitButton) {
            submitButton.addEventListener('click', async (e) => {
                e.preventDefault();
                await this.handleVisualize(closeModalHandler);
            });
        }
    },

    /**
     * Reset form state
     */
    resetForm: function() {
        const fileInput = document.getElementById('visualize-file-input');
        const filePreview = document.getElementById('visualize-file-preview');
        const dropZone = document.getElementById('visualize-drop-zone');
        const submitButton = document.getElementById('visualize-submit');
        const errorDiv = document.getElementById('visualize-error');
        
        this.selectedFile = null;
        if (fileInput) fileInput.value = '';
        if (filePreview) filePreview.style.display = 'none';
        if (dropZone) dropZone.querySelector('.drop-zone-content').style.display = 'block';
        if (submitButton) submitButton.disabled = true;
        if (errorDiv) errorDiv.style.display = 'none';
    },

    /**
     * Handle file selection
     */
    handleFileSelect: function(file) {
        const visualizeError = document.getElementById('visualize-error');
        const filePreview = document.getElementById('visualize-file-preview');
        const fileName = document.getElementById('visualize-file-name');
        const dropZone = document.getElementById('visualize-drop-zone');
        const submitButton = document.getElementById('visualize-submit');
        
        if (visualizeError) visualizeError.style.display = 'none';
        
        if (!file) return;
        
        // Validate file type
        if (!file.name.toLowerCase().endsWith('.geojson') && !file.name.toLowerCase().endsWith('.json')) {
            this.showError('Please select a valid GeoJSON file (.geojson or .json)');
            return;
        }
        
        this.selectedFile = file;
        if (fileName) fileName.textContent = file.name;
        if (dropZone) dropZone.querySelector('.drop-zone-content').style.display = 'none';
        if (filePreview) filePreview.style.display = 'flex';
        if (submitButton) submitButton.disabled = false;
    },

    /**
     * Show error message
     */
    showError: function(message) {
        const visualizeError = document.getElementById('visualize-error');
        if (visualizeError) {
            visualizeError.textContent = message;
            visualizeError.style.display = 'block';
        }
    },

    /**
     * Handle visualization
     */
    handleVisualize: async function(closeModalHandler) {
        if (!this.selectedFile) {
            this.showError('Please select a file');
            return;
        }
        
        const submitButton = document.getElementById('visualize-submit');
        
        if (submitButton) {
            submitButton.disabled = true;
            submitButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Loading...';
        }
        
        try {
            // Read file content
            const fileContent = await this.selectedFile.text();
            const geojson = JSON.parse(fileContent);
            
            // Validate GeoJSON structure
            if (!geojson.type || (geojson.type !== 'FeatureCollection' && geojson.type !== 'Feature')) {
                throw new Error('Invalid GeoJSON: must be a Feature or FeatureCollection');
            }
            
            // Normalize to FeatureCollection
            let featureCollection;
            if (geojson.type === 'Feature') {
                featureCollection = {
                    type: 'FeatureCollection',
                    features: [geojson]
                };
            } else {
                featureCollection = geojson;
            }
            
            if (!featureCollection.features || featureCollection.features.length === 0) {
                throw new Error('GeoJSON contains no features');
            }
            
            // Close modal
            closeModalHandler();
            
            // Render layer
            const content = {
                data: featureCollection,
                source: 'user',
                meta: {
                    layer_name: this.selectedFile.name.replace(/\.(geo)?json$/i, '')
                }
            };
            
            LayerRenderer.renderVectorLayer(content);
            
            ChatUI.displayMessage(
                `✓ Visualized "${this.selectedFile.name}" with ${featureCollection.features.length} feature(s)`,
                'system'
            );
            
        } catch (error) {
            console.error('Visualization error:', error);
            this.showError(error.message || 'Failed to visualize file. Please ensure it is valid GeoJSON.');
            if (submitButton) {
                submitButton.disabled = false;
                submitButton.innerHTML = '<i class="fas fa-eye"></i> Visualize';
            }
        }
    }
};

// Expose globally
window.VisualizeModal = VisualizeModal;

// Export for ES6 modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = VisualizeModal;
}
