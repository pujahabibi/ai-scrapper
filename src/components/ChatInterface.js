import React, { useState, useEffect, useRef } from 'react';
import { Card, Row, Col } from 'react-bootstrap';
import MessageList from './MessageList';
import InputForm from './InputForm';
import ProgressIndicator from './ProgressIndicator';
import SessionInfo from './SessionInfo';
import axios from 'axios';

function ChatInterface() {
  const [messages, setMessages] = useState([
    {
      id: 1,
      content: `Hi! I'm your AI assistant with multi-agent capabilities. I can:

📚 Answer questions and have conversations
🕷️ Scrape and analyze websites  
🧠 Remember our conversation context

Try asking me something or give me a URL to scrape!`,
      sender: 'bot',
      timestamp: new Date().toISOString(),
      type: 'welcome'
    }
  ]);
  
  const [sessionId, setSessionId] = useState(
    localStorage.getItem('chat_session_id') || ''
  );
  const [isLoading, setIsLoading] = useState(false);
  const [progress, setProgress] = useState(null);
  const [showProgress, setShowProgress] = useState(false);
  
  const progressInterval = useRef(null);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, showProgress]);

  const startProgressPolling = (currentSessionId) => {
    if (!currentSessionId || progressInterval.current) {
      console.log('🚫 Cannot start polling:', { currentSessionId, hasInterval: !!progressInterval.current });
      return;
    }
    
    console.log('🔄 Starting progress polling for session:', currentSessionId);
    
    let pollAttempts = 0;
    const maxAttempts = 100; // Max 30 seconds of polling at 300ms intervals
    
    progressInterval.current = setInterval(async () => {
      pollAttempts++;
      
      try {
        const response = await axios.get(`/progress/${currentSessionId}`);
        
        if (response && response.data) {
          const progressData = response.data;
          console.log(`📊 Poll ${pollAttempts}: ${progressData.step} - ${progressData.description} (${progressData.progress}%)`);
          
          // Update progress for any valid step
          setProgress(progressData);
          
          if (progressData.completed) {
            console.log('✅ Progress completed, stopping polling');
            stopProgressPolling();
            return;
          }
        }
      } catch (error) {
        // Only log errors every 10 attempts to reduce noise
        if (pollAttempts % 10 === 0 || error.response?.status !== 404) {
          if (error.response) {
            console.log(`❌ Poll ${pollAttempts}: HTTP ${error.response.status}`);
          } else {
            console.log(`❌ Poll ${pollAttempts}: ${error.message}`);
          }
        }
      }
      
      // Stop polling after max attempts
      if (pollAttempts >= maxAttempts) {
        console.log('⏰ Max polling attempts reached, stopping');
        stopProgressPolling();
      }
    }, 300); // Poll every 300ms
  };

  const stopProgressPolling = () => {
    if (progressInterval.current) {
      console.log('🛑 Stopping progress polling');
      clearInterval(progressInterval.current);
      progressInterval.current = null;
    }
  };

  const handleSendMessage = async (message) => {
    if (!message.trim()) return;

    setIsLoading(true);
    setShowProgress(true);
    setProgress({
      step: 'initializing',
      description: '🤖 Initializing...',
      progress: 0,
      completed: false
    });

    // Add user message
    const userMessage = {
      id: Date.now(),
      content: message,
      sender: 'user',
      timestamp: new Date().toISOString()
    };
    setMessages(prev => [...prev, userMessage]);

    // Generate session ID on frontend if we don't have one
    // This ensures we can start polling immediately
    let currentSessionId = sessionId;
    if (!currentSessionId) {
      // Generate UUID in the same format as backend
      currentSessionId = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        var r = Math.random() * 16 | 0, v = c == 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
      });
      setSessionId(currentSessionId);
      localStorage.setItem('chat_session_id', currentSessionId);
      console.log('🆔 Generated new session ID:', currentSessionId);
    }

    let responseData = null;

    try {
      console.log('🚀 Starting API call with session ID:', currentSessionId);
      
      // Start progress polling IMMEDIATELY - we now have a guaranteed session ID
      console.log('📡 Starting progress polling immediately for session:', currentSessionId);
      startProgressPolling(currentSessionId);

      // Make the API call with our session ID
      const response = await axios.post('/chat', {
        message,
        session_id: currentSessionId
      });

      responseData = response.data;

      console.log('✅ API response received with session ID:', responseData.session_id);

      // Verify the backend used our session ID (it should)
      if (responseData.session_id !== currentSessionId) {
        console.warn('⚠️ Backend changed session ID from', currentSessionId, 'to', responseData.session_id);
        setSessionId(responseData.session_id);
        localStorage.setItem('chat_session_id', responseData.session_id);
        
        // Restart polling with backend's session ID
        stopProgressPolling();
        startProgressPolling(responseData.session_id);
      }

      // Add bot response
      const botMessage = {
        id: Date.now() + 1,
        content: responseData.response,
        sender: 'bot',
        timestamp: responseData.timestamp,
        type: responseData.request_type
      };
      setMessages(prev => [...prev, botMessage]);

    } catch (error) {
      console.error('❌ Error sending message:', error);
      const errorMessage = {
        id: Date.now() + 1,
        content: 'Sorry, I encountered an error. Please try again.',
        sender: 'bot',
        timestamp: new Date().toISOString(),
        type: 'error'
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
      // Keep progress visible briefly then hide
      setTimeout(() => {
        setShowProgress(false);
        stopProgressPolling();
      }, 2000);
    }
  };

  const handleClearSession = async () => {
    if (!sessionId) return;

    try {
      stopProgressPolling();
      await axios.delete(`/sessions/${sessionId}`);
      
      localStorage.removeItem('chat_session_id');
      setSessionId('');
      setMessages([{
        id: 1,
        content: 'Chat cleared! I\'m ready for a fresh conversation.',
        sender: 'bot',
        timestamp: new Date().toISOString(),
        type: 'system'
      }]);
    } catch (error) {
      console.error('Error clearing session:', error);
    }
  };

  return (
    <Card className="glass-card shadow-lg border-0 h-100 fade-in-up">
      <Card.Body className="d-flex flex-column h-100 p-0">
        <Row className="flex-grow-1 g-0">
          <Col>
            <div 
              className="d-flex flex-column h-100"
              style={{ minHeight: '70vh', maxHeight: '80vh' }}
            >
              {/* Messages Area */}
              <div className="flex-grow-1 overflow-auto custom-scrollbar p-4">
                <MessageList messages={messages} />
                {showProgress && (
                  <ProgressIndicator progress={progress} />
                )}
                <div ref={messagesEndRef} />
              </div>

              {/* Input Area */}
              <div className="border-top border-light bg-light bg-opacity-50 p-4">
                <InputForm 
                  onSendMessage={handleSendMessage}
                  disabled={isLoading}
                />
              </div>

              {/* Session Info */}
              <SessionInfo 
                sessionId={sessionId}
                onClearSession={handleClearSession}
              />
            </div>
          </Col>
        </Row>
      </Card.Body>
    </Card>
  );
}

export default ChatInterface; 