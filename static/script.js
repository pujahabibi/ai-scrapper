class ChatInterface {
    constructor() {
        this.sessionId = localStorage.getItem('chat_session_id') || '';
        this.messagesContainer = document.getElementById('chatMessages');
        this.messageInput = document.getElementById('messageInput');
        this.sendButton = document.getElementById('sendButton');
        this.typingIndicator = document.getElementById('typingIndicator');
        this.sessionInfo = document.getElementById('sessionInfo');
        this.clearButton = document.getElementById('clearButton');
        this.progressInterval = null;
        
        this.initializeEventListeners();
        this.updateSessionInfo();
    }
    
    initializeEventListeners() {
        this.sendButton.addEventListener('click', () => this.sendMessage());
        this.messageInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });
        this.clearButton.addEventListener('click', () => this.clearSession());
    }
    
    async sendMessage() {
        const message = this.messageInput.value.trim();
        if (!message) return;
        
        console.log('Sending message:', message);
        
        // Disable input while processing
        this.setInputEnabled(false);
        
        // Add user message to chat
        this.addMessage(message, 'user');
        this.messageInput.value = '';
        
        // Show progress tracking
        this.showProgress(true);
        this.startProgressPolling();
        
        try {
            console.log('Making API request...');
            
            const response = await fetch('/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    message: message,
                    session_id: this.sessionId
                })
            });
            
            console.log('API response received:', response.status);
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const data = await response.json();
            console.log('Response data:', data);
            
            // Update session ID if new
            if (data.session_id !== this.sessionId) {
                this.sessionId = data.session_id;
                localStorage.setItem('chat_session_id', this.sessionId);
                this.updateSessionInfo();
            }
            
            // Stop progress polling
            this.stopProgressPolling();
            
            // Add bot response
            this.addMessage(data.response, 'bot', data.request_type);
            
        } catch (error) {
            console.error('Error in sendMessage:', error);
            this.stopProgressPolling();
            this.addMessage('Sorry, I encountered an error. Please try again.', 'bot', 'error');
        } finally {
            this.showProgress(false);
            this.setInputEnabled(true);
            this.messageInput.focus();
        }
    }
    
    startProgressPolling() {
        if (!this.sessionId || this.progressInterval) {
            console.log('Progress polling not started:', !this.sessionId ? 'No session ID' : 'Already polling');
            return;
        }
        
        console.log('🔄 Starting progress polling for session:', this.sessionId);
        
        this.progressInterval = setInterval(async () => {
            try {
                const response = await fetch(`/progress/${this.sessionId}`);
                
                if (response.ok) {
                    const progress = await response.json();
                    console.log('📊 Progress received:', progress);
                    this.updateProgressDisplay(progress);
                    
                    // Stop polling if completed
                    if (progress.completed) {
                        console.log('✅ Progress completed, stopping polling');
                        this.stopProgressPolling();
                    }
                } else {
                    console.error('Progress polling failed:', response.status);
                    this.stopProgressPolling(); // Stop polling on error
                }
            } catch (error) {
                console.error('Progress polling error:', error);
                this.stopProgressPolling(); // Stop polling on error
            }
        }, 500); // Poll every 500ms
    }
    
    stopProgressPolling() {
        if (this.progressInterval) {
            console.log('🛑 Stopping progress polling');
            clearInterval(this.progressInterval);
            this.progressInterval = null;
        }
    }
    
    updateProgressDisplay(progress) {
        const progressElement = document.getElementById('typingIndicator');
        if (progressElement && progressElement.style.display !== 'none') {
            try {
                // Safely create progress content
                let progressHtml = `
                    <div style="display: flex; align-items: center; gap: 10px;">
                        <div style="display: flex; gap: 5px;">
                            <span class="typing-dot"></span>
                            <span class="typing-dot"></span>
                            <span class="typing-dot"></span>
                        </div>
                        <div>
                            <div style="font-weight: 600; color: #667eea;">
                                ${progress.description || 'Processing...'}
                            </div>
                            <div style="font-size: 11px; color: #666; margin-top: 2px;">
                                Step: ${progress.step || 'unknown'} • Progress: ${progress.progress || 0}%
                            </div>
                        </div>
                    </div>
                `;
                
                progressElement.innerHTML = progressHtml;
            } catch (error) {
                console.error('Error updating progress display:', error);
            }
        }
    }
    
    addMessage(content, sender, type = '') {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${sender}`;
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        contentDiv.textContent = content;
        
        // Add type indicator for bot messages
        if (sender === 'bot' && type) {
            const typeSpan = document.createElement('div');
            typeSpan.style.fontSize = '11px';
            typeSpan.style.opacity = '0.7';
            typeSpan.style.marginBottom = '5px';
            
            const typeEmoji = type === 'scrape_data' ? '🕷️' : 
                             type === 'regular_question' ? '📚' : '🤖';
            typeSpan.textContent = `${typeEmoji} ${type.replace('_', ' ')}`;
            contentDiv.insertBefore(typeSpan, contentDiv.firstChild);
        }
        
        const timeDiv = document.createElement('div');
        timeDiv.className = 'message-time';
        timeDiv.textContent = new Date().toLocaleTimeString();
        
        messageDiv.appendChild(contentDiv);
        messageDiv.appendChild(timeDiv);
        
        this.messagesContainer.appendChild(messageDiv);
        this.scrollToBottom();
    }
    
    showProgress(show) {
        this.typingIndicator.style.display = show ? 'block' : 'none';
        if (show) {
            // Reset to default state
            this.typingIndicator.innerHTML = `
                <span class="typing-dot"></span>
                <span class="typing-dot"></span>
                <span class="typing-dot"></span>
                🤖 Initializing...
            `;
            this.scrollToBottom();
        }
    }
    
    setInputEnabled(enabled) {
        this.messageInput.disabled = !enabled;
        this.sendButton.disabled = !enabled;
    }
    
    scrollToBottom() {
        setTimeout(() => {
            this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
        }, 100);
    }
    
    updateSessionInfo() {
        const shortId = this.sessionId ? this.sessionId.substring(0, 8) + '...' : 'New';
        this.sessionInfo.textContent = `Session: ${shortId}`;
    }
    
    async clearSession() {
        if (!this.sessionId) return;
        
        if (confirm('Clear this conversation? This cannot be undone.')) {
            try {
                // Stop any active progress polling
                this.stopProgressPolling();
                
                await fetch(`/sessions/${this.sessionId}`, {
                    method: 'DELETE'
                });
                
                // Clear local session
                localStorage.removeItem('chat_session_id');
                this.sessionId = '';
                this.updateSessionInfo();
                
                // Clear messages
                this.messagesContainer.innerHTML = `
                    <div class="message bot">
                        <div class="message-content">
                            Chat cleared! I'm ready for a fresh conversation.
                        </div>
                    </div>
                `;
                
            } catch (error) {
                console.error('Error clearing session:', error);
                alert('Error clearing session. Please try again.');
            }
        }
    }
}

// Initialize chat interface when page loads
document.addEventListener('DOMContentLoaded', () => {
    new ChatInterface();
}); 