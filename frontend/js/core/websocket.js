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
    _connectionVersion: 0,

    /**
     * Initialize connection - tries WebSocket first, falls back to polling
     */
    init: function(mode = 'multi-agent') {
        this.disconnect();
        GeoFahamState.currentMode = mode;
        this._wsAttempts = 0;
        this._tryWebSocket(mode);
    },

    disconnect: function() {
        const state = GeoFahamState;
        this._connectionVersion++;
        // Clean up previous connection
        const previousSocket = state.ws;
        state.ws = null;
        if (previousSocket && previousSocket.readyState < WebSocket.CLOSING) {
            previousSocket.close();
        }
        this._stopPolling();
        if (state.reconnectInterval) {
            clearTimeout(state.reconnectInterval);
            state.reconnectInterval = null;
        }
        this.updateConnectionStatus(false);
        ChatUI.disableInput();
        this._wsAttempts = 0;
        this._usingPolling = false;
        this._sessionId = null;

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

        let ws;
        let ready = false;
        let initializationFailed = false;
        try {
            ws = new WebSocket(wsUrl);
            state.ws = ws;
        } catch (e) {
            console.error('WebSocket constructor failed:', e);
            this._fallbackToPolling(mode);
            return;
        }

        // Timeout: if not open within 5 s, give up on this attempt
        const timeout = setTimeout(() => {
            if (state.ws === ws && ws.readyState === WebSocket.CONNECTING) {
                console.log('WS open timeout');
                ws.close();
            }
        }, 5000);

        ws.onopen = () => {
            clearTimeout(timeout);
            if (state.ws !== ws) return;
            console.log('WebSocket connected; waiting for agents');
        };

        ws.onmessage = (event) => {
            if (state.ws !== ws) return;
            const message = JSON.parse(event.data);
            console.log("WS message:", message.type);
            if (message.type === 'status' && (message.ready === true || message.data === 'Agents ready.')) {
                ready = true;
                this._wsAttempts = 0;
                this.updateConnectionStatus(true);
                ChatUI.enableInput();
                ChatUI.displayMessage(
                    `Connected in ${GeoFahamConfig.agentModes[mode]} mode. Ready to assist!`,
                    'system'
                );
            }
            if (message.type === 'error' && !ready) {
                // Agent/configuration failures cannot be repaired by changing transport.
                initializationFailed = true;
            }
            MessageHandler.handleMessage(message);
            if (initializationFailed) {
                this.updateConnectionStatus(false);
                ChatUI.disableInput();
                ws.close();
            }
        };

        ws.onerror = (error) => {
            clearTimeout(timeout);
            console.error('WebSocket error:', error);
        };

        ws.onclose = () => {
            clearTimeout(timeout);
            if (state.ws !== ws) return;
            console.log('WebSocket closed');
            this.updateConnectionStatus(false);
            ChatUI.disableInput();
            if (!initializationFailed) this._handleWsFail(mode);
        };
    },

    _handleWsFail: function(mode) {
        const max = GeoFahamConfig.websocket.maxReconnectAttempts;
        if (this._wsAttempts < max) {
            console.log(`WS retry ${this._wsAttempts}/${max} in 2s...`);
            GeoFahamState.reconnectInterval = setTimeout(() => {
                GeoFahamState.reconnectInterval = null;
                this._tryWebSocket(mode);
            }, 2000);
        } else {
            console.log('WS failed after max attempts, switching to HTTP polling');
            this._fallbackToPolling(mode);
        }
    },

    /* ------------------------------------------------------------------ */
    /*  HTTP Polling fallback                                              */
    /* ------------------------------------------------------------------ */

    _fallbackToPolling: function(mode) {
        const version = this._connectionVersion;
        this._usingPolling = true;
        ChatUI.displayMessage('WebSocket unavailable — using HTTP polling mode.', 'system');

        fetch(GeoFahamConfig.polling.initUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode: mode })
        })
        .then(async r => {
            const data = await r.json();
            if (!r.ok) throw new Error(data.detail || 'Polling initialization failed');
            if (!data.session_id) throw new Error('Missing polling session ID');
            return data;
        })
        .then(data => {
            if (version !== this._connectionVersion) return;
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
            if (version !== this._connectionVersion) return;
            console.error('Polling init failed:', err);
            this.updateConnectionStatus(false);
            ChatUI.disableInput();
            ChatUI.displayMessage('Failed to connect: ' + err.message, 'error');
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
        const sessionId = this._sessionId;
        fetch(`${GeoFahamConfig.polling.pollUrl}?session_id=${sessionId}`)
            .then(r => r.json())
            .then(data => {
                if (sessionId !== this._sessionId) return;
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
