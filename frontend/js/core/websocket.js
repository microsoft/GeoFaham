// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

/**
 * WebSocket Management Module
 * Handles WebSocket connection with automatic HTTP polling fallback
 * when WebSocket is blocked (e.g., by dev tunnels or proxies).
 */

const WebSocketManager = {
    _wsAttempts: 0,
    _pollingTimer: null,
    _usingPolling: false,
    _sessionId: null,

    /**
     * Initialize connection - tries WebSocket first, falls back to polling
     */
    init: function(mode = 'multi-agent') {
        const state = GeoFahamState;

        // Clean up previous connection
        state._intentionalClose = true;
        if (state.ws && state.ws.readyState === WebSocket.OPEN) {
            state.ws.close();
        }
        this._stopPolling();
        if (state.reconnectInterval) {
            clearInterval(state.reconnectInterval);
            state.reconnectInterval = null;
        }
        state._intentionalClose = false;
        state.currentMode = mode;
        this._wsAttempts = 0;
        this._usingPolling = false;
        this._sessionId = null;

        this._tryWebSocket(mode);
    },

    /* ------------------------------------------------------------------ */
    /*  WebSocket path                                                     */
    /* ------------------------------------------------------------------ */

    _tryWebSocket: function(mode) {
        const state = GeoFahamState;
        this._wsAttempts++;
        const maxAttempts = GeoFahamConfig.websocket.maxReconnectAttempts;

        const wsUrl = `${GeoFahamConfig.server.wsUrl}?mode=${mode}`;
        console.log(`WS attempt ${this._wsAttempts}/${maxAttempts}: ${wsUrl}`);

        try {
            state.ws = new WebSocket(wsUrl);
        } catch (e) {
            console.error('WebSocket constructor failed:', e);
            this._fallbackToPolling(mode);
            return;
        }

        // Timeout: if not open within 5 s, give up on this attempt
        const timeout = setTimeout(() => {
            if (state.ws && state.ws.readyState !== WebSocket.OPEN) {
                console.log('WS open timeout');
                state._intentionalClose = true;
                state.ws.close();
                state._intentionalClose = false;
                this._handleWsFail(mode);
            }
        }, 5000);

        state.ws.onopen = () => {
            clearTimeout(timeout);
            this._wsAttempts = 0;
            console.log('WebSocket connected');
            this.updateConnectionStatus(true);
            ChatUI.enableInput();
            const modeNames = GeoFahamConfig.agentModes;
            ChatUI.displayMessage(
                `Connected in ${modeNames[state.currentMode]} mode. Ready to assist!`,
                'system'
            );
        };

        state.ws.onmessage = (event) => {
            const message = JSON.parse(event.data);
            console.log("WS message:", message.type);
            MessageHandler.handleMessage(message);
        };

        state.ws.onerror = (error) => {
            clearTimeout(timeout);
            console.error('WebSocket error:', error);
        };

        state.ws.onclose = () => {
            clearTimeout(timeout);
            if (state._intentionalClose) return;
            console.log('WebSocket closed');
            this.updateConnectionStatus(false);
            this._handleWsFail(mode);
        };
    },

    _handleWsFail: function(mode) {
        const max = GeoFahamConfig.websocket.maxReconnectAttempts;
        if (this._wsAttempts < max) {
            console.log(`WS retry ${this._wsAttempts}/${max} in 2s...`);
            setTimeout(() => this._tryWebSocket(mode), 2000);
        } else {
            console.log('WS failed after max attempts, switching to HTTP polling');
            this._fallbackToPolling(mode);
        }
    },

    /* ------------------------------------------------------------------ */
    /*  HTTP Polling fallback                                              */
    /* ------------------------------------------------------------------ */

    _fallbackToPolling: function(mode) {
        this._usingPolling = true;
        ChatUI.displayMessage('WebSocket unavailable — using HTTP polling mode.', 'system');

        fetch(GeoFahamConfig.polling.initUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode: mode })
        })
        .then(r => r.json())
        .then(data => {
            this._sessionId = data.session_id;
            console.log('Polling session:', this._sessionId);
            this.updateConnectionStatus(true);
            ChatUI.enableInput();
            ChatUI.displayMessage(
                `Connected in ${GeoFahamConfig.agentModes[mode]} mode (polling). Ready to assist!`,
                'system'
            );
            this._startPolling();
        })
        .catch(err => {
            console.error('Polling init failed:', err);
            ChatUI.displayMessage('Failed to connect. Please reload.', 'error');
        });
    },

    _startPolling: function() {
        this._stopPolling();
        this._pollingTimer = setInterval(() => this._poll(), GeoFahamConfig.polling.interval);
    },

    _stopPolling: function() {
        if (this._pollingTimer) {
            clearInterval(this._pollingTimer);
            this._pollingTimer = null;
        }
    },

    _poll: function() {
        if (!this._sessionId) return;
        fetch(`${GeoFahamConfig.polling.pollUrl}?session_id=${this._sessionId}`)
            .then(r => r.json())
            .then(data => {
                if (data.messages) {
                    data.messages.forEach(msg => {
                        console.log("Poll message:", msg.type);
                        MessageHandler.handleMessage(msg);
                    });
                }
            })
            .catch(err => console.error('Poll error:', err));
    },

    /* ------------------------------------------------------------------ */
    /*  Public API                                                         */
    /* ------------------------------------------------------------------ */

    updateConnectionStatus: function(connected) {
        GeoFahamState.isConnected = connected;
        const statusElement = document.getElementById('connection-status');
        const statusText = document.getElementById('status-text');
        if (statusElement && statusText) {
            statusElement.className = 'connection-status ' + (connected ? 'connected' : 'disconnected');
            statusText.textContent = connected ? 'Connected' : 'Disconnected';
        }
    },

    sendMessage: function(content, userRawJson = '') {
        const state = GeoFahamState;
        if (!state.isConnected) {
            ChatUI.displayMessage('Not connected. Please wait.', 'error');
            return false;
        }

        if (this._usingPolling) {
            return this._sendViaPolling(content, userRawJson);
        }
        return this._sendViaWs(content, userRawJson);
    },

    _sendViaWs: function(content, userRawJson) {
        const state = GeoFahamState;
        try {
            state.ws.send(JSON.stringify({ content, source: 'user', user_raw_json: userRawJson }));
            return true;
        } catch (e) {
            console.error('WS send error:', e);
            ChatUI.displayMessage('Failed to send message.', 'error');
            return false;
        }
    },

    _sendViaPolling: function(content, userRawJson) {
        fetch(GeoFahamConfig.polling.sendUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: this._sessionId, content, user_raw_json: userRawJson })
        })
        .then(r => {
            if (!r.ok) {
                return r.text().then(t => {
                    let detail = 'Send failed';
                    try { detail = JSON.parse(t).detail || detail; } catch (_) {}
                    throw new Error(`${r.status}: ${detail}`);
                });
            }
        })
        .catch(err => {
            console.error('Polling send error:', err);
            ChatUI.displayMessage('Failed to send: ' + err.message, 'error');
        });
        return true;
    },

    switchMode: function(newMode) {
        const state = GeoFahamState;
        console.log(`Switching mode: ${state.currentMode} → ${newMode}`);
        ChatUI.displayMessage(`Switching to ${GeoFahamConfig.agentModes[newMode]} mode...`, 'system');
        this.init(newMode);
    }
};

// Expose globally
window.WebSocketManager = WebSocketManager;

if (typeof module !== 'undefined' && module.exports) {
    module.exports = WebSocketManager;
}
