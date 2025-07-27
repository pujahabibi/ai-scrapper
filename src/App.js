import React from 'react';
import { Container } from 'react-bootstrap';
import ChatInterface from './components/ChatInterface';
import Header from './components/Header';

function App() {
  return (
    <div className="min-vh-100 d-flex flex-column">
      <Header />
      <Container fluid className="flex-grow-1 d-flex justify-content-center align-items-center py-4">
        <div className="w-100" style={{ maxWidth: '1000px' }}>
          <ChatInterface />
        </div>
      </Container>
    </div>
  );
}

export default App; 