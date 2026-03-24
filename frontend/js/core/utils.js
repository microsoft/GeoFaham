// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

/**
 * Utility Functions
 * Common helper functions used across the application
 */

const GeoFahamUtils = {
    /**
     * Format number with thousands separator
     */
    formatNumber: function(num) {
        if (num === null || num === undefined) return 'N/A';
        return num.toLocaleString();
    },

    /**
     * Format file size in human-readable format
     */
    formatFileSize: function(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    },

    /**
     * Format timestamp to human-readable date
     */
    formatTimestamp: function(timestamp) {
        if (!timestamp) return 'Unknown';
        const date = new Date(timestamp * 1000);
        return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
    },

    /**
     * Debounce function
     */
    debounce: function(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    },

    /**
     * Throttle function
     */
    throttle: function(func, limit) {
        let inThrottle;
        return function(...args) {
            if (!inThrottle) {
                func.apply(this, args);
                inThrottle = true;
                setTimeout(() => inThrottle = false, limit);
            }
        };
    },

    /**
     * Deep clone an object
     */
    deepClone: function(obj) {
        return JSON.parse(JSON.stringify(obj));
    },

    /**
     * Generate a random color
     */
    randomColor: function() {
        const colors = GeoFahamConfig.colorPalettes.categorical;
        return colors[Math.floor(Math.random() * colors.length)];
    },

    /**
     * Get color from palette by index
     */
    getColorByIndex: function(index) {
        const colors = GeoFahamConfig.colorPalettes.categorical;
        return colors[index % colors.length];
    },

    /**
     * Validate GeoJSON structure
     */
    isValidGeoJSON: function(obj) {
        if (!obj || typeof obj !== 'object') return false;
        if (!obj.type) return false;
        
        const validTypes = ['Feature', 'FeatureCollection', 'Point', 'MultiPoint', 
                           'LineString', 'MultiLineString', 'Polygon', 'MultiPolygon', 
                           'GeometryCollection'];
        return validTypes.includes(obj.type);
    },

    /**
     * Calculate bounding box from GeoJSON
     */
    calculateBbox: function(geojson) {
        if (!geojson) return null;
        
        let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        
        const processCoords = (coords) => {
            if (typeof coords[0] === 'number') {
                // Single coordinate [lng, lat]
                minX = Math.min(minX, coords[0]);
                maxX = Math.max(maxX, coords[0]);
                minY = Math.min(minY, coords[1]);
                maxY = Math.max(maxY, coords[1]);
            } else {
                // Array of coordinates
                coords.forEach(processCoords);
            }
        };
        
        const processGeometry = (geometry) => {
            if (!geometry) return;
            if (geometry.coordinates) {
                processCoords(geometry.coordinates);
            }
        };
        
        if (geojson.type === 'FeatureCollection') {
            geojson.features.forEach(f => processGeometry(f.geometry));
        } else if (geojson.type === 'Feature') {
            processGeometry(geojson.geometry);
        } else {
            processGeometry(geojson);
        }
        
        if (minX === Infinity) return null;
        return [minX, minY, maxX, maxY];
    },

    /**
     * Show toast notification
     */
    showToast: function(message, type = 'info', duration = 3000) {
        // Create toast element
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        toast.style.cssText = `
            position: fixed;
            bottom: 20px;
            right: 20px;
            padding: 12px 24px;
            border-radius: 8px;
            background: ${type === 'error' ? '#ef4444' : type === 'success' ? '#10b981' : '#3b82f6'};
            color: white;
            font-weight: 500;
            z-index: 9999;
            animation: slideIn 0.3s ease;
        `;
        
        document.body.appendChild(toast);
        
        setTimeout(() => {
            toast.style.animation = 'slideOut 0.3s ease';
            setTimeout(() => toast.remove(), 300);
        }, duration);
    },

    /**
     * Parse markdown content (uses marked library)
     */
    parseMarkdown: function(content) {
        if (typeof marked !== 'undefined') {
            return marked.parse(content);
        }
        return content;
    },

    /**
     * Escape HTML special characters
     */
    escapeHtml: function(text) {
        const map = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#039;'
        };
        return text.replace(/[&<>"']/g, m => map[m]);
    },

    /**
     * Check if value is empty (null, undefined, empty string, empty array, empty object)
     */
    isEmpty: function(value) {
        if (value === null || value === undefined) return true;
        if (typeof value === 'string') return value.trim() === '';
        if (Array.isArray(value)) return value.length === 0;
        if (typeof value === 'object') return Object.keys(value).length === 0;
        return false;
    }
};

// Expose globally
window.GeoFahamUtils = GeoFahamUtils;

// Export for ES6 modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = GeoFahamUtils;
}
