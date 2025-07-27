import React from 'react';
import { Navbar, Container, Badge } from 'react-bootstrap';

function Header() {
  return (
    <Navbar className="glass-card shadow-sm py-3" expand="lg">
      <Container>
        <Navbar.Brand className="d-flex align-items-center text-white fw-bold fs-3">
          <i className="fas fa-robot me-3 text-primary"></i>
          AI Scrapper
          <Badge bg="primary" className="ms-3 fs-6">Multi-Agent</Badge>
        </Navbar.Brand>
        <div className="d-flex align-items-center text-white-50">
          <small className="me-3">
            <i className="fas fa-brain me-1"></i>
            Intelligent Conversations
          </small>
          <small className="me-3">
            <i className="fas fa-spider me-1"></i>
            Web Scraping
          </small>
          <small>
            <i className="fas fa-memory me-1"></i>
            Context Memory
          </small>
        </div>
      </Container>
    </Navbar>
  );
}

export default Header; 