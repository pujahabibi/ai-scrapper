import React from 'react';
import { Badge } from 'react-bootstrap';

function Message({ message }) {
  const { content, sender, timestamp, type } = message;

  const getTypeIcon = (type) => {
    switch (type) {
      case 'scrape_data': return { icon: 'fas fa-spider', color: 'success', text: 'Web Scraping' };
      case 'regular_question': return { icon: 'fas fa-brain', color: 'primary', text: 'AI Response' };
      case 'welcome': return { icon: 'fas fa-hand-wave', color: 'info', text: 'Welcome' };
      case 'system': return { icon: 'fas fa-cog', color: 'secondary', text: 'System' };
      case 'error': return { icon: 'fas fa-exclamation-triangle', color: 'danger', text: 'Error' };
      default: return { icon: 'fas fa-robot', color: 'primary', text: 'AI Assistant' };
    }
  };

  const isUser = sender === 'user';
  const typeInfo = getTypeIcon(type);

  return (
    <div className={`d-flex mb-4 ${isUser ? 'justify-content-end slide-in-right' : 'slide-in-left'}`}>
      <div className={`position-relative ${isUser ? 'order-2' : ''}`} style={{ maxWidth: '75%' }}>
        {/* Message bubble */}
        <div
          className={`p-3 rounded-4 shadow-sm position-relative ${
            isUser 
              ? 'bg-primary text-white ms-3' 
              : 'bg-white border'
          }`}
          style={{
            borderRadius: isUser ? '20px 20px 5px 20px' : '20px 20px 20px 5px'
          }}
        >
          {/* Type badge for bot messages */}
          {!isUser && type && type !== 'welcome' && (
            <div className="mb-2">
              <Badge bg={typeInfo.color} className="px-2 py-1 rounded-pill">
                <i className={`${typeInfo.icon} me-1`}></i>
                {typeInfo.text}
              </Badge>
            </div>
          )}
          
          {/* Message content */}
          <div 
            className={`${isUser ? 'text-white' : 'text-dark'}`}
            style={{ 
              whiteSpace: 'pre-wrap',
              lineHeight: '1.5',
              fontSize: '0.95rem' 
            }}
          >
            {content}
          </div>
          
          {/* Timestamp */}
          <div 
            className={`mt-2 small ${
              isUser ? 'text-white-50' : 'text-muted'
            }`}
            style={{ fontSize: '0.75rem' }}
          >
            {new Date(timestamp).toLocaleTimeString()}
          </div>

          {/* Speech bubble tail */}
          <div
            className={`position-absolute ${
              isUser 
                ? 'bg-primary' 
                : 'bg-white border-start border-bottom'
            }`}
            style={{
              width: '12px',
              height: '12px',
              bottom: '8px',
              [isUser ? 'right' : 'left']: '-6px',
              clipPath: isUser 
                ? 'polygon(0 0, 100% 100%, 0 100%)' 
                : 'polygon(100% 0, 0 100%, 100% 100%)',
              zIndex: -1
            }}
          />
        </div>
      </div>
      
      {/* Avatar */}
      <div className={`d-flex align-items-end ${isUser ? 'order-1 me-2' : 'ms-2'}`}>
        <div 
          className={`rounded-circle d-flex align-items-center justify-content-center shadow-sm ${
            isUser ? 'bg-primary' : 'bg-white border'
          }`}
          style={{ width: '40px', height: '40px' }}
        >
          <i 
            className={`${isUser ? 'fas fa-user text-white' : `${typeInfo.icon} text-${typeInfo.color}`}`}
            style={{ fontSize: '0.9rem' }}
          ></i>
        </div>
      </div>
    </div>
  );
}

export default Message; 