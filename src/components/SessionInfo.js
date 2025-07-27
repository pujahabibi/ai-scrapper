import React from 'react';
import { Button, Badge } from 'react-bootstrap';

function SessionInfo({ sessionId, onClearSession }) {
  const shortId = sessionId ? sessionId.substring(0, 8) + '...' : 'New Session';

  const handleClearSession = () => {
    if (window.confirm('Clear this conversation? This cannot be undone.')) {
      onClearSession();
    }
  };

  return (
    <div className="d-flex justify-content-between align-items-center p-3 bg-light bg-opacity-50 border-top border-light">
      <div className="d-flex align-items-center">
        <Badge bg="secondary" className="me-2 px-2 py-1">
          <i className="fas fa-id-card me-1"></i>
          Session
        </Badge>
        <small className="text-muted fw-medium">
          {shortId}
        </small>
      </div>
      
      <div className="d-flex gap-2">
        <Button 
          variant="outline-danger" 
          size="sm"
          onClick={handleClearSession}
          disabled={!sessionId}
          className="px-3"
        >
          <i className="fas fa-trash me-1"></i>
          Clear Chat
        </Button>
      </div>
    </div>
  );
}

export default SessionInfo; 