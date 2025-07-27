import React from 'react';
import { Card, Badge } from 'react-bootstrap';

function ProgressIndicator({ progress }) {
  if (!progress) {
    return (
      <div className="d-flex justify-content-center mb-3 slide-in-left">
        <Card className="bg-light border-0 shadow-sm">
          <Card.Body className="d-flex align-items-center py-3 px-4">
            <div className="d-flex me-3">
              <span className="typing-dot"></span>
              <span className="typing-dot"></span>
              <span className="typing-dot"></span>
            </div>
            <div>
              <div className="fw-semibold text-primary mb-1">
                <i className="fas fa-cog fa-spin me-2"></i>
                Initializing...
              </div>
              <small className="text-muted">Starting up the AI agents</small>
            </div>
          </Card.Body>
        </Card>
      </div>
    );
  }

  // Handle 'waiting' state specially
  if (progress.step === 'waiting') {
    return (
      <div className="d-flex justify-content-center mb-3 slide-in-left">
        <Card className="bg-light border-0 shadow-sm">
          <Card.Body className="d-flex align-items-center py-3 px-4">
            <div className="d-flex me-3">
              <span className="typing-dot"></span>
              <span className="typing-dot"></span>
              <span className="typing-dot"></span>
            </div>
            <div>
              <div className="fw-semibold text-info mb-1">
                <i className="fas fa-clock me-2"></i>
                {progress.description || 'Waiting for processing to start...'}
              </div>
              <small className="text-muted">Session ready, preparing AI agents...</small>
            </div>
          </Card.Body>
        </Card>
      </div>
    );
  }

  const getStepIcon = (step) => {
    switch (step) {
      case 'analyzing': return 'fas fa-search';
      case 'scraping': return 'fas fa-spider';
      case 'processing': return 'fas fa-brain';
      case 'generating': return 'fas fa-magic';
      case 'finalizing': return 'fas fa-check-circle';
      default: return 'fas fa-cog fa-spin';
    }
  };

  const getStepColor = (step) => {
    switch (step) {
      case 'analyzing': return 'info';
      case 'scraping': return 'success';
      case 'processing': return 'warning';
      case 'generating': return 'primary';
      case 'finalizing': return 'success';
      default: return 'secondary';
    }
  };

  return (
    <div className="d-flex justify-content-center mb-3 slide-in-left">
      <Card className="bg-light border-0 shadow-sm" style={{ minWidth: '350px' }}>
        <Card.Body className="py-3 px-4">
          <div className="d-flex align-items-center mb-3">
            <div className="me-3">
              {!progress.completed ? (
                <div className="d-flex">
                  <span className="typing-dot"></span>
                  <span className="typing-dot"></span>
                  <span className="typing-dot"></span>
                </div>
              ) : (
                <i className="fas fa-check-circle text-success fs-4"></i>
              )}
            </div>
            <div className="flex-grow-1">
              <div className="d-flex align-items-center mb-2">
                <Badge 
                  bg={getStepColor(progress.step)} 
                  className="me-2 px-2 py-1"
                >
                  <i className={`${getStepIcon(progress.step)} me-1`}></i>
                  {progress.step || 'Processing'}
                </Badge>
                <span className="fw-semibold text-dark">
                  {progress.description || 'Working on your request...'}
                </span>
              </div>
              
              {/* Status indicator */}
              <div className="d-flex justify-content-between align-items-center">
                <small className="text-muted">
                  <i className="fas fa-clock me-1"></i>
                  Processing your request...
                </small>
                {progress.completed && (
                  <small className="text-success fw-semibold">
                    <i className="fas fa-check me-1"></i>
                    Completed!
                  </small>
                )}
              </div>
            </div>
          </div>
        </Card.Body>
      </Card>
    </div>
  );
}

export default ProgressIndicator; 