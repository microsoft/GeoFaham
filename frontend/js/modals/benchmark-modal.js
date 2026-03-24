// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

/**
 * Benchmark Modal Module
 * Handles saving benchmark ground truth
 */

const BenchmarkModal = {
    /**
     * Initialize benchmark modal
     */
    init: function() {
        const saveGtButton = document.getElementById('save-gt-button');
        const saveGtModal = document.getElementById('save-gt-modal');
        const closeModal = document.getElementById('close-save-gt-modal');
        const cancelSaveGt = document.getElementById('cancel-save-gt');
        const submitSaveGt = document.getElementById('submit-save-gt');
        const questionInput = document.getElementById('question-number-input');
        const saveGtError = document.getElementById('save-gt-error');
        const saveGtSuccess = document.getElementById('save-gt-success');
        
        if (!saveGtButton || !saveGtModal) return;

        // Open modal
        saveGtButton.addEventListener('click', () => {
            saveGtModal.classList.add('show');
            if (saveGtError) saveGtError.style.display = 'none';
            if (saveGtSuccess) saveGtSuccess.style.display = 'none';
            if (questionInput) {
                questionInput.value = '';
                questionInput.focus();
            }
        });
        
        // Close modal handlers
        const closeModalHandler = () => {
            saveGtModal.classList.remove('show');
            if (saveGtError) saveGtError.style.display = 'none';
            if (saveGtSuccess) saveGtSuccess.style.display = 'none';
            if (questionInput) questionInput.value = '';
        };
        
        if (closeModal) closeModal.addEventListener('click', closeModalHandler);
        if (cancelSaveGt) cancelSaveGt.addEventListener('click', closeModalHandler);
        
        // Close on backdrop click
        saveGtModal.addEventListener('click', (e) => {
            if (e.target === saveGtModal) {
                closeModalHandler();
            }
        });
        
        // Submit handler
        if (submitSaveGt) {
            submitSaveGt.addEventListener('click', async () => {
                await this.handleSubmit(closeModalHandler);
            });
        }
        
        // Allow Enter key to submit
        if (questionInput) {
            questionInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter' && submitSaveGt) {
                    submitSaveGt.click();
                }
            });
        }
    },

    /**
     * Handle form submission
     */
    handleSubmit: async function(closeModalHandler) {
        const questionInput = document.getElementById('question-number-input');
        const submitSaveGt = document.getElementById('submit-save-gt');
        const saveGtError = document.getElementById('save-gt-error');
        const saveGtSuccess = document.getElementById('save-gt-success');
        
        const questionNumber = questionInput?.value.trim();
        
        if (!questionNumber) {
            if (saveGtError) {
                saveGtError.textContent = 'Please enter a question number (e.g., Q001)';
                saveGtError.style.display = 'block';
            }
            return;
        }
        
        if (saveGtError) saveGtError.style.display = 'none';
        if (saveGtSuccess) saveGtSuccess.style.display = 'none';
        
        if (submitSaveGt) {
            submitSaveGt.disabled = true;
            submitSaveGt.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...';
        }
        
        try {
            const response = await fetch(GeoFahamConfig.server.saveBenchmarkUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ question_number: questionNumber }),
            });
            
            const result = await response.json();
            
            if (response.ok && result.success) {
                if (saveGtSuccess) {
                    saveGtSuccess.innerHTML = `<i class="fas fa-check-circle"></i> Saved to <strong>${result.path}</strong><br>Files: ${result.files_copied.join(', ')}`;
                    saveGtSuccess.style.display = 'block';
                }
                
                // Auto-close after 3 seconds
                setTimeout(() => {
                    closeModalHandler();
                }, 3000);
            } else {
                if (saveGtError) {
                    saveGtError.textContent = result.detail || 'Failed to save benchmark GT';
                    saveGtError.style.display = 'block';
                }
            }
        } catch (error) {
            if (saveGtError) {
                saveGtError.textContent = `Error: ${error.message}`;
                saveGtError.style.display = 'block';
            }
        } finally {
            if (submitSaveGt) {
                submitSaveGt.disabled = false;
                submitSaveGt.innerHTML = '<i class="fas fa-save"></i> Save GT';
            }
        }
    }
};

// Expose globally
window.BenchmarkModal = BenchmarkModal;

// Export for ES6 modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = BenchmarkModal;
}
