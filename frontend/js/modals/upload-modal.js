// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

/**
 * Upload Modal Module
 * Handles GeoJSON file upload functionality
 */

const UploadModal = {
    selectedFile: null,

    /**
     * Initialize upload modal
     */
    init: function() {
        const uploadButton = document.getElementById('upload-button');
        const uploadModal = document.getElementById('upload-modal');
        const closeModal = document.getElementById('close-modal');
        const cancelUpload = document.getElementById('cancel-upload');
        const uploadForm = document.getElementById('upload-form');
        const fileInput = document.getElementById('file-input');
        const dropZone = document.getElementById('drop-zone');
        const filePreview = document.getElementById('file-preview');
        const fileName = document.getElementById('file-name');
        const removeFileBtn = document.getElementById('remove-file');
        const submitButton = document.getElementById('submit-upload');
        const uploadError = document.getElementById('upload-error');
        const uploadProgress = document.getElementById('upload-progress');
        
        if (!uploadButton || !uploadModal) return;

        // Open modal
        uploadButton.addEventListener('click', () => {
            uploadModal.classList.add('show');
            this.resetForm();
        });
        
        // Close modal handlers
        const closeModalHandler = () => {
            uploadModal.classList.remove('show');
            this.resetForm();
        };
        
        if (closeModal) closeModal.addEventListener('click', closeModalHandler);
        if (cancelUpload) cancelUpload.addEventListener('click', closeModalHandler);
        
        // Close on backdrop click
        uploadModal.addEventListener('click', (e) => {
            if (e.target === uploadModal) {
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
        
        // Input validation
        const titleInput = document.getElementById('file-title');
        const descInput = document.getElementById('file-description');
        
        if (titleInput) titleInput.addEventListener('input', () => this.validateForm());
        if (descInput) descInput.addEventListener('input', () => this.validateForm());
        
        // Form submission
        if (uploadForm) {
            uploadForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                await this.handleSubmit(closeModalHandler);
            });
        }
    },

    /**
     * Reset form state
     */
    resetForm: function() {
        const uploadForm = document.getElementById('upload-form');
        const filePreview = document.getElementById('file-preview');
        const dropZone = document.getElementById('drop-zone');
        const submitButton = document.getElementById('submit-upload');
        const uploadError = document.getElementById('upload-error');
        const uploadProgress = document.getElementById('upload-progress');
        
        if (uploadForm) uploadForm.reset();
        this.selectedFile = null;
        if (filePreview) filePreview.style.display = 'none';
        if (dropZone) dropZone.querySelector('.drop-zone-content').style.display = 'block';
        if (submitButton) submitButton.disabled = true;
        if (uploadError) uploadError.style.display = 'none';
        if (uploadProgress) uploadProgress.style.display = 'none';
    },

    /**
     * Handle file selection
     */
    handleFileSelect: function(file) {
        const uploadError = document.getElementById('upload-error');
        const filePreview = document.getElementById('file-preview');
        const fileName = document.getElementById('file-name');
        const dropZone = document.getElementById('drop-zone');
        
        if (uploadError) uploadError.style.display = 'none';
        
        if (!file) return;
        
        // Validate file type
        if (!file.name.toLowerCase().endsWith('.geojson') && !file.name.toLowerCase().endsWith('.json')) {
            this.showError('Please select a valid GeoJSON file (.geojson or .json)');
            return;
        }
        
        // Validate file size (max 10MB)
        if (file.size > 10 * 1024 * 1024) {
            this.showError('File size must be less than 10MB');
            return;
        }
        
        this.selectedFile = file;
        if (fileName) fileName.textContent = file.name;
        if (dropZone) dropZone.querySelector('.drop-zone-content').style.display = 'none';
        if (filePreview) filePreview.style.display = 'flex';
        
        this.validateForm();
    },

    /**
     * Validate form
     */
    validateForm: function() {
        const title = document.getElementById('file-title')?.value.trim();
        const submitButton = document.getElementById('submit-upload');
        
        if (submitButton) {
            submitButton.disabled = !(title && this.selectedFile);
        }
    },

    /**
     * Show error message
     */
    showError: function(message) {
        const uploadError = document.getElementById('upload-error');
        if (uploadError) {
            uploadError.textContent = message;
            uploadError.style.display = 'block';
        }
    },

    /**
     * Handle form submission
     */
    handleSubmit: async function(closeModalHandler) {
        if (!this.selectedFile) {
            this.showError('Please select a file');
            return;
        }
        
        const title = document.getElementById('file-title')?.value.trim();
        const description = document.getElementById('file-description')?.value.trim() || '';
        const submitButton = document.getElementById('submit-upload');
        const uploadProgress = document.getElementById('upload-progress');
        const uploadError = document.getElementById('upload-error');
        
        // Show progress
        if (submitButton) submitButton.disabled = true;
        if (uploadProgress) uploadProgress.style.display = 'block';
        if (uploadError) uploadError.style.display = 'none';
        
        try {
            const formData = new FormData();
            formData.append('file', this.selectedFile);
            formData.append('title', title);
            formData.append('description', description);
            
            const response = await fetch(GeoFahamConfig.server.uploadUrl, {
                method: 'POST',
                body: formData
            });
            
            const result = await response.json();
            
            if (!response.ok) {
                throw new Error(result.detail || 'Upload failed');
            }
            
            ChatUI.displayMessage(`✓ Successfully uploaded "${title}"! The file is now available in the artifacts ledger.`, 'system');
            closeModalHandler();
            
        } catch (error) {
            console.error('Upload error:', error);
            this.showError(error.message || 'Failed to upload file. Please try again.');
            if (submitButton) submitButton.disabled = false;
        } finally {
            if (uploadProgress) uploadProgress.style.display = 'none';
        }
    }
};

// Expose globally
window.UploadModal = UploadModal;

// Export for ES6 modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = UploadModal;
}
