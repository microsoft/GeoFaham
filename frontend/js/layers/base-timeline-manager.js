// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

/**
 * Base Timeline Manager
 * 
 * Shared functionality for temporal layer management (STAC mosaics and COG timelines).
 * Eliminates ~800 lines of duplicate code between temporal-mosaic.js and temporal-cog-timeline.js.
 */

class BaseTimelineManager {
    constructor(map, layerLabel = 'default') {
        this.map = map;
        this.layerLabel = layerLabel;
        this.timelineContainer = null;
        this.selectedTimestamp = null;
        this.layerCache = new Map();
        this.accessOrder = [];
        this.compareMode = false;
        this.isAnimating = false;
        this.animationInterval = null;
    }

    // =========================================================================
    // TIMELINE UI (shared between both managers)
    // =========================================================================

    /**
     * Create base timeline UI structure
     * @param {Object} config - Timeline configuration
     * @returns {HTMLElement} The timeline container
     */
    createTimelineUIBase(config) {
        const {
            timestamps,
            title,
            icon,
            defaultIndex = 0,
            formatLabel,  // Function to format each label
        } = config;

        this.removeTimelineUI();

        // Create container
        this.timelineContainer = document.createElement('div');
        this.timelineContainer.id = `temporal-timeline-${this.layerLabel}`;
        this.timelineContainer.className = 'temporal-timeline';

        // Header
        const header = this._createHeader(title, icon, timestamps.length);

        // Controls
        const controls = document.createElement('div');
        controls.className = 'timeline-controls';

        // Slider
        const sliderContainer = this._createSlider(timestamps, defaultIndex, formatLabel);

        // Selection display
        const selectionDisplay = document.createElement('div');
        selectionDisplay.className = 'timeline-selection';
        selectionDisplay.id = `timeline-selection-${this.layerLabel}`;

        // Action buttons
        const actions = this._createActionButtons();

        controls.appendChild(sliderContainer);
        controls.appendChild(selectionDisplay);
        controls.appendChild(actions);

        this.timelineContainer.appendChild(header);
        this.timelineContainer.appendChild(controls);

        // Add to map
        const mapSection = document.querySelector('.map-section');
        if (mapSection) {
            mapSection.appendChild(this.timelineContainer);
        }

        return this.timelineContainer;
    }

    _createHeader(title, icon, count) {
        const header = document.createElement('div');
        header.className = 'timeline-header';
        
        const displayLabel = this.layerLabel !== 'default' ? ` - ${this.layerLabel.toUpperCase()}` : '';
        
        header.innerHTML = `
            <div class="timeline-title">
                <i class="fas fa-${icon}"></i>
                <span>${title}${displayLabel}</span>
            </div>
            <div class="timeline-info">
                <span class="timeline-count">${count} snapshots</span>
            </div>
            <button class="timeline-close" title="Close timeline">
                <i class="fas fa-times"></i>
            </button>
        `;

        // Close button handler
        header.querySelector('.timeline-close').addEventListener('click', () => {
            this.removeTimelineUI();
        });

        return header;
    }

    _createSlider(timestamps, defaultIndex, formatLabel) {
        const container = document.createElement('div');
        container.className = 'timeline-slider-container';

        const slider = document.createElement('input');
        slider.type = 'range';
        slider.className = 'timeline-slider';
        slider.id = `timeline-slider-${this.layerLabel}`;
        slider.min = 0;
        slider.max = timestamps.length - 1;
        slider.value = defaultIndex;
        slider.step = 1;

        // Labels
        const labelsContainer = document.createElement('div');
        labelsContainer.className = 'timeline-labels';

        timestamps.forEach((timestamp, index) => {
            const label = document.createElement('div');
            label.className = 'timeline-label';
            if (timestamps.length > 1) {
                label.style.left = `${(index / (timestamps.length - 1)) * 100}%`;
            } else {
                label.style.left = '50%';
            }
            
            const labelText = formatLabel ? formatLabel(timestamp, index) : this.formatTimestamp(timestamp, 'short');
            
            label.innerHTML = `
                <div class="timeline-marker"></div>
                <div class="timeline-date">${labelText}</div>
            `;
            labelsContainer.appendChild(label);
        });

        container.appendChild(slider);
        container.appendChild(labelsContainer);

        return container;
    }

    _createActionButtons() {
        const actions = document.createElement('div');
        actions.className = 'timeline-actions';
        
        const prefix = `timeline-${this.layerLabel}`;
        
        actions.innerHTML = `
            <button class="timeline-btn" id="${prefix}-play" title="Animate through time">
                <i class="fas fa-play"></i> Animate
            </button>
            <button class="timeline-btn" id="${prefix}-prev" title="Previous">
                <i class="fas fa-chevron-left"></i>
            </button>
            <button class="timeline-btn" id="${prefix}-next" title="Next">
                <i class="fas fa-chevron-right"></i>
            </button>
            <button class="timeline-btn timeline-btn-secondary" id="${prefix}-compare" title="Toggle compare mode">
                <i class="fas fa-layer-group"></i> Compare (<span id="${prefix}-cached-count">0</span>)
            </button>
        `;

        return actions;
    }

    /**
     * Setup event handlers for timeline controls
     */
    setupTimelineEvents(timestamps, onTimestampChange) {
        const prefix = `timeline-${this.layerLabel}`;
        const slider = document.getElementById(`timeline-slider-${this.layerLabel}`);

        if (slider) {
            slider.addEventListener('input', (e) => {
                const index = parseInt(e.target.value);
                this.selectedTimestamp = timestamps[index];
                onTimestampChange(this.selectedTimestamp, index);
            });
        }

        // Play/Pause
        const playBtn = document.getElementById(`${prefix}-play`);
        if (playBtn) {
            playBtn.addEventListener('click', () => this.toggleAnimation(timestamps, onTimestampChange));
        }

        // Prev/Next
        const prevBtn = document.getElementById(`${prefix}-prev`);
        const nextBtn = document.getElementById(`${prefix}-next`);
        
        if (prevBtn) {
            prevBtn.addEventListener('click', () => {
                const currentIndex = timestamps.indexOf(this.selectedTimestamp);
                if (currentIndex > 0) {
                    slider.value = currentIndex - 1;
                    slider.dispatchEvent(new Event('input'));
                }
            });
        }
        
        if (nextBtn) {
            nextBtn.addEventListener('click', () => {
                const currentIndex = timestamps.indexOf(this.selectedTimestamp);
                if (currentIndex < timestamps.length - 1) {
                    slider.value = currentIndex + 1;
                    slider.dispatchEvent(new Event('input'));
                }
            });
        }

        // Compare toggle
        const compareBtn = document.getElementById(`${prefix}-compare`);
        if (compareBtn) {
            compareBtn.addEventListener('click', () => this.toggleCompareMode());
        }
    }

    // =========================================================================
    // ANIMATION (shared)
    // =========================================================================

    toggleAnimation(timestamps, onTimestampChange) {
        const prefix = `timeline-${this.layerLabel}`;
        const playBtn = document.getElementById(`${prefix}-play`);
        
        if (this.isAnimating) {
            this.stopAnimation();
            if (playBtn) {
                playBtn.innerHTML = '<i class="fas fa-play"></i> Animate';
            }
        } else {
            this.startAnimation(timestamps, onTimestampChange);
            if (playBtn) {
                playBtn.innerHTML = '<i class="fas fa-pause"></i> Pause';
            }
        }
    }

    startAnimation(timestamps, onTimestampChange, interval = 1500) {
        this.isAnimating = true;
        const slider = document.getElementById(`timeline-slider-${this.layerLabel}`);
        
        this.animationInterval = setInterval(() => {
            let currentIndex = timestamps.indexOf(this.selectedTimestamp);
            currentIndex = (currentIndex + 1) % timestamps.length;
            
            this.selectedTimestamp = timestamps[currentIndex];
            if (slider) {
                slider.value = currentIndex;
            }
            onTimestampChange(this.selectedTimestamp, currentIndex);
        }, interval);
    }

    stopAnimation() {
        this.isAnimating = false;
        if (this.animationInterval) {
            clearInterval(this.animationInterval);
            this.animationInterval = null;
        }
    }

    // =========================================================================
    // COMPARE MODE (shared)
    // =========================================================================

    toggleCompareMode() {
        this.compareMode = !this.compareMode;
        const prefix = `timeline-${this.layerLabel}`;
        const compareBtn = document.getElementById(`${prefix}-compare`);
        
        if (compareBtn) {
            if (this.compareMode) {
                compareBtn.classList.add('active');
                ChatUI.displayMessage('Compare mode enabled. Cached layers will remain visible.', 'system');
            } else {
                compareBtn.classList.remove('active');
                ChatUI.displayMessage('Compare mode disabled.', 'system');
            }
        }
    }

    updateCachedCount() {
        const prefix = `timeline-${this.layerLabel}`;
        const countSpan = document.getElementById(`${prefix}-cached-count`);
        if (countSpan) {
            countSpan.textContent = this.layerCache.size;
        }
    }

    // =========================================================================
    // UTILITIES (shared)
    // =========================================================================

    /**
     * Format timestamp for display
     */
    formatTimestamp(timestamp, format = 'short') {
        if (!timestamp) return '';
        
        // Handle temporal ranges (e.g., "2023-10-01T00:00:00Z/2023-10-31T23:59:59Z")
        let dateStr = timestamp;
        let endDateStr = null;
        
        if (typeof timestamp === 'string' && timestamp.includes('/')) {
            const parts = timestamp.split('/');
            dateStr = parts[0];
            endDateStr = parts[1];
        }
        
        try {
            const date = new Date(dateStr);
            
            if (format === 'short') {
                if (endDateStr) {
                    const endDate = new Date(endDateStr);
                    return this._formatDateRange(date, endDate, 'short');
                }
                return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
            } else if (format === 'full') {
                if (endDateStr) {
                    const endDate = new Date(endDateStr);
                    return this._formatDateRange(date, endDate, 'full');
                }
                return date.toLocaleDateString('en-US', { 
                    weekday: 'long', 
                    year: 'numeric', 
                    month: 'long', 
                    day: 'numeric' 
                });
            } else if (format === 'date-only') {
                return date.toLocaleDateString('en-US', { 
                    year: 'numeric', 
                    month: 'short', 
                    day: 'numeric' 
                });
            }
        } catch (e) {
            console.warn('Error formatting timestamp:', timestamp, e);
        }
        
        return timestamp;
    }

    _formatDateRange(startDate, endDate, format) {
        const startMonth = startDate.toLocaleDateString('en-US', { month: 'short' });
        const endMonth = endDate.toLocaleDateString('en-US', { month: 'short' });
        const startDay = startDate.getDate();
        const endDay = endDate.getDate();
        
        if (format === 'short') {
            if (startMonth === endMonth) {
                return `${startMonth} ${startDay}-${endDay}`;
            }
            return `${startMonth} ${startDay} - ${endMonth} ${endDay}`;
        } else {
            const year = startDate.getFullYear();
            if (startMonth === endMonth) {
                return `${startMonth} ${startDay}-${endDay}, ${year}`;
            }
            return `${startMonth} ${startDay} - ${endMonth} ${endDay}, ${year}`;
        }
    }

    /**
     * Remove timeline UI
     */
    removeTimelineUI() {
        this.stopAnimation();
        
        if (this.timelineContainer) {
            this.timelineContainer.remove();
            this.timelineContainer = null;
        }
    }

    /**
     * Fit map to bounds
     */
    fitMapToBounds(bounds, padding = 100) {
        if (!bounds || bounds.length !== 4) return;
        
        setTimeout(() => {
            this.map.setCamera({
                bounds: bounds,
                padding: {
                    top: padding,
                    bottom: padding + 50, // Extra for timeline
                    left: padding,
                    right: padding
                },
                type: "fly",
                duration: 2000
            });
        }, 500);
    }

    // =========================================================================
    // LAYER CACHE MANAGEMENT (shared)
    // =========================================================================

    /**
     * LRU cache management - evict oldest if over limit
     */
    manageCacheSize(maxSize = 5) {
        while (this.layerCache.size > maxSize && this.accessOrder.length > 0) {
            const oldestKey = this.accessOrder.shift();
            const cached = this.layerCache.get(oldestKey);
            
            if (cached && cached.layer) {
                try {
                    this.map.layers.remove(cached.layer);
                } catch (e) {
                    console.warn('Error removing cached layer:', e);
                }
            }
            
            this.layerCache.delete(oldestKey);
        }
        
        this.updateCachedCount();
    }

    /**
     * Record cache access for LRU
     */
    recordCacheAccess(key) {
        const index = this.accessOrder.indexOf(key);
        if (index > -1) {
            this.accessOrder.splice(index, 1);
        }
        this.accessOrder.push(key);
    }

    /**
     * Clear all cached layers
     */
    clearCache() {
        this.layerCache.forEach((cached) => {
            if (cached && cached.layer) {
                try {
                    this.map.layers.remove(cached.layer);
                } catch (e) {
                    console.warn('Error removing layer:', e);
                }
            }
        });
        
        this.layerCache.clear();
        this.accessOrder = [];
        this.updateCachedCount();
    }
}

// Expose globally
window.BaseTimelineManager = BaseTimelineManager;

// Export for ES6 modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = BaseTimelineManager;
}
