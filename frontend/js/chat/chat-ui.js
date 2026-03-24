// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

/**
 * Chat UI Module
 * Handles chat interface display and user input
 */

const ChatUI = {
    /**
     * Display a message in the chat
     * NOTE: This method is for TEXT display only. Layer rendering is handled by MessageHandler.
     */
    displayMessage: function(content, source, isDebugMsg = false) {
        console.log('displayMessage called with isDebugMsg:', isDebugMsg, 'debugMode:', GeoFahamState.debugMode);
        
        // Handle object content - convert to string for display
        // Layer routing is handled by MessageHandler, not here
        if (typeof content === 'object' && content !== null) {
            content = JSON.stringify(content, null, 2);
        }
        
        // Parse markdown if string
        if (typeof content === 'string') {
            content = GeoFahamUtils.parseMarkdown(content);
        }
        
        // Error messages are always debug messages
        if (source === 'error') {
            isDebugMsg = true;
        }
        
        const clsName = (source === "system" || source === "user" || source === "error") ? source : "assistant";
        const messagesContainer = document.getElementById('messages');
        
        if (!messagesContainer) return;
        
        const messageElement = document.createElement('div');
        messageElement.className = `message ${clsName}`;
        
        // Add debug attribute and hide if debug mode is off
        if (isDebugMsg) {
            messageElement.setAttribute('data-debug', 'true');
            if (!GeoFahamState.debugMode) {
                messageElement.style.display = 'none';
            }
        }

        const messageBubble = document.createElement('div');
        messageBubble.className = 'message-bubble';

        const labelElement = document.createElement('div');
        labelElement.className = 'message-label';
        labelElement.textContent = source.charAt(0).toUpperCase() + source.slice(1);

        const contentElement = document.createElement('div');
        contentElement.className = 'message-content';
        contentElement.innerHTML = content;

        messageBubble.appendChild(labelElement);
        messageBubble.appendChild(contentElement);
        messageElement.appendChild(messageBubble);
        messagesContainer.appendChild(messageElement);

        // Smooth scroll to bottom
        messagesContainer.scrollTo({
            top: messagesContainer.scrollHeight,
            behavior: GeoFahamConfig.ui.messageScrollBehavior
        });
    },

    /**
     * Add a system message (alias for displayMessage with 'system' source)
     */
    addSystemMessage: function(content, type = 'system') {
        this.displayMessage(content, type);
    },

    /**
     * Send message from user input
     */
    sendMessage: function() {
        console.log('sendMessage function called');
        
        const input = document.getElementById('message-input');
        const userRawJsonInput = document.getElementById("user_raw_json");
        
        const message = input ? input.value.trim() : '';
        const userRawJson = userRawJsonInput ? userRawJsonInput.value.trim() : '';

        console.log('Message:', message);
        console.log('Is connected:', GeoFahamState.isConnected);

        if (!message) {
            console.log('No message to send');
            return;
        }

        // Display user message immediately
        this.displayMessage(message, 'user');

        // Clear input and show loading state
        if (input) input.value = '';
        if (userRawJsonInput) userRawJsonInput.value = '';
        this.showLoadingState();

        // Send through WebSocket
        if (!WebSocketManager.sendMessage(message, userRawJson)) {
            this.enableInput();
        }
    },

    /**
     * Show loading state on send button
     */
    showLoadingState: function() {
        const button = document.getElementById('send-button');
        const input = document.getElementById('message-input');

        if (input) input.disabled = true;
        if (button) {
            button.disabled = true;
            button.innerHTML = '<div class="loading-indicator"><div class="spinner"></div>Processing...</div>';
        }
    },

    /**
     * Enable chat input
     */
    enableInput: function() {
        const input = document.getElementById('message-input');
        const button = document.getElementById('send-button');

        if (input) {
            input.disabled = false;
            input.focus();
        }
        if (button) {
            button.disabled = false;
            button.innerHTML = '<i class="fas fa-paper-plane"></i>Send';
        }
    },

    /**
     * Disable chat input
     */
    disableInput: function() {
        const input = document.getElementById('message-input');
        const button = document.getElementById('send-button');

        if (input) input.disabled = true;
        if (button) button.disabled = true;
    },

    /**
     * Clear all chat messages
     */
    clearMessages: function() {
        const messagesContainer = document.getElementById('messages');
        if (messagesContainer) {
            messagesContainer.innerHTML = '';
        }
    },

    /**
     * Setup input event handlers
     */
    setupInputHandlers: function() {
        const input = document.getElementById('message-input');
        const sendButton = document.getElementById('send-button');

        if (input) {
            // Auto-resize textarea
            input.addEventListener('input', function() {
                this.style.height = 'auto';
                this.style.height = Math.min(this.scrollHeight, GeoFahamConfig.ui.maxTextareaHeight) + 'px';
            });

            // Handle Enter key (Shift+Enter for new line)
            input.addEventListener('keydown', function(event) {
                if (event.key === 'Enter' && !event.shiftKey && !this.disabled) {
                    event.preventDefault();
                    ChatUI.sendMessage();
                }
            });
        }

        if (sendButton) {
            sendButton.addEventListener('click', function(event) {
                event.preventDefault();
                ChatUI.sendMessage();
            });
        }
    },

    /**
     * Setup expand chat button
     */
    setupExpandButton: function() {
        const expandButton = document.getElementById('expand-chat-btn');
        const chatSection = document.querySelector('.chat-section');
        
        if (expandButton && chatSection) {
            expandButton.addEventListener('click', function() {
                chatSection.classList.toggle('expanded');
                GeoFahamState.isChatExpanded = chatSection.classList.contains('expanded');
                
                const icon = expandButton.querySelector('i');
                if (GeoFahamState.isChatExpanded) {
                    icon.className = 'fas fa-compress';
                    expandButton.title = 'Collapse Chat';
                } else {
                    icon.className = 'fas fa-expand';
                    expandButton.title = 'Expand Chat';
                }
            });
        }
    },

    /**
     * Load chat history from server
     */
    loadHistory: async function() {
        try {
            const response = await fetch(GeoFahamConfig.server.historyUrl);
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            const history = await response.json();
            history.forEach(message => {
                this.displayMessage(message.content, message.source);
            });
        } catch (error) {
            console.error('Error loading history:', error);
            this.displayMessage('Could not load chat history.', 'system', true);
        }
    },

    /**
     * Toggle debug mode
     */
    toggleDebugMode: function() {
        GeoFahamState.debugMode = !GeoFahamState.debugMode;
        
        const debugButton = document.getElementById('debug-mode-toggle');
        const debugElements = document.querySelectorAll('.debug-only');
        const debugMessages = document.querySelectorAll('[data-debug="true"]');
        
        if (GeoFahamState.debugMode) {
            // Show debug elements
            debugElements.forEach(el => el.style.display = '');
            debugMessages.forEach(el => el.style.display = '');
            if (debugButton) debugButton.classList.add('active');
            this.displayMessage('Debug mode enabled', 'system');
        } else {
            // Hide debug elements
            debugElements.forEach(el => el.style.display = 'none');
            debugMessages.forEach(el => el.style.display = 'none');
            if (debugButton) debugButton.classList.remove('active');
        }
    },

    /**
     * Initialize all chat UI components
     */
    init: function() {
        this.setupInputHandlers();
        this.setupExpandButton();
        this.loadHistory();
        
        // Debug mode toggle is handled by GeoFahamApp.setupDebugMode()
    }
};

// Expose globally
window.ChatUI = ChatUI;

// Export for ES6 modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ChatUI;
}
