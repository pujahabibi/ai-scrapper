import React, { useState, useRef, useEffect } from 'react';
import { Form, Button, InputGroup } from 'react-bootstrap';

function InputForm({ onSendMessage, disabled }) {
  const [message, setMessage] = useState('');
  const inputRef = useRef(null);

  useEffect(() => {
    if (!disabled) {
      inputRef.current?.focus();
    }
  }, [disabled]);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (message.trim() && !disabled) {
      onSendMessage(message);
      setMessage('');
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  return (
    <Form onSubmit={handleSubmit}>
      <InputGroup size="lg">
        <Form.Control
          ref={inputRef}
          type="text"
          placeholder="Type your message or paste a URL to scrape..."
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyPress={handleKeyPress}
          disabled={disabled}
          maxLength={1000}
          className="glass-input border-0 shadow-sm"
          style={{
            borderRadius: '25px 0 0 25px',
            fontSize: '1rem',
            padding: '0.75rem 1.25rem'
          }}
        />
        <Button 
          type="submit"
          disabled={disabled || !message.trim()}
          className="btn-gradient px-4 shadow-sm"
          style={{
            borderRadius: '0 25px 25px 0',
            minWidth: '100px'
          }}
        >
          {disabled ? (
            <>
              <div className="spinner-border spinner-border-sm me-2" role="status">
                <span className="visually-hidden">Loading...</span>
              </div>
              Sending...
            </>
          ) : (
            <>
              <i className="fas fa-paper-plane me-2"></i>
              Send
            </>
          )}
        </Button>
      </InputGroup>
      
      {/* Character counter */}
      <div className="d-flex justify-content-between mt-2">
        <small className="text-muted">
          <i className="fas fa-info-circle me-1"></i>
          Press Enter to send, Shift+Enter for new line
        </small>
        <small className={`${message.length > 900 ? 'text-warning' : 'text-muted'}`}>
          {message.length}/1000
        </small>
      </div>
    </Form>
  );
}

export default InputForm; 