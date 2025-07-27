from agents import Agent, InputGuardrail, GuardrailFunctionOutput, Runner, OpenAIResponsesModel, ModelSettings, SQLiteSession
from agents.exceptions import InputGuardrailTripwireTriggered
from pydantic import BaseModel
from typing import List, Dict
import asyncio
import requests
from bs4 import BeautifulSoup
import json
import uuid
from datetime import datetime

# FastAPI imports
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import uvicorn

class RequestClassification(BaseModel):
    request_type: str  # "regular_question" or "scrape_data"
    reasoning: str
    url: str = ""  # Only filled if scrape_data
    question: str = ""  # The actual question to answer

class RegularAnswer(BaseModel):
    answer: str
    explanation: str

class ScrapeResult(BaseModel):
    text: str
    data_found: str = ""  # Simplified to avoid schema issues

# FastAPI request/response models
class ChatRequest(BaseModel):
    message: str
    session_id: str = ""

class ChatResponse(BaseModel):
    response: str
    session_id: str
    request_type: str
    timestamp: str

class ProgressUpdate(BaseModel):
    step: str
    description: str
    progress: int  # 0-100
    session_id: str
    completed: bool = False

# Store active sessions and their progress
active_sessions = {}
progress_store = {}  # Store progress updates by session_id

# Agent 1: Request Classifier - Determines if user wants regular Q&A or web scraping
request_classifier_agent = Agent(
    name="Request Classifier",
    instructions="""You are a request classifier. Analyze the user input and determine if they are asking:

    1. REGULAR QUESTION: General questions, math problems, explanations, advice, follow-up questions, etc.
       - Examples: "What is the capital of France?", "How do I cook pasta?", "Explain photosynthesis"
       - Follow-up questions: "What about Italy?", "Tell me more", "Can you explain that better?", "Summarize the content of the website"
       
    2. SCRAPE DATA: Requests to extract data from websites or URLs
       - Examples: "Scrape data from https://example.com", "Extract information from this website: [URL]", 
         "Get me the content from [URL]", "What's on this page: [URL]"

    CLASSIFICATION RULES:
    - If the input contains a URL (http/https) AND asks to extract/scrape/get data, classify as "scrape_data"
    - If the input mentions scraping, extracting, or getting data from a website, classify as "scrape_data"
    - Everything else is "regular_question" (including follow-up questions)
    
    Extract the URL if present and the core question/request.""",
    output_type=RequestClassification,
    model="gpt-4.1-mini",
)

# Agent 2: Regular Q&A Agent - Handles normal questions
regular_qa_agent = Agent(
    name="Regular Q&A Assistant",
    instructions="""You are a helpful assistant that answers questions clearly and accurately. 
    You can see the conversation history and should reference previous context when relevant.
    Provide comprehensive answers with explanations when helpful. Be conversational and informative.
    
    For follow-up questions, make sure to reference what was discussed previously.""",
    output_type=RegularAnswer,
    model="gpt-4.1-mini",
)

# Agent 3: Web Scraping Agent - Handles data extraction from URLs
web_scraping_agent = Agent(
    name="Web Scraping Specialist",
    instructions="""You are a web scraping specialist. You receive cleaned website content and extract 
    relevant information based on the user's request.
    
    Return a summary of what you found in 'text' and the extracted data in 'data_found' as a formatted string.""",
    output_type=ScrapeResult,
    model="gpt-4.1-mini",
    model_settings=ModelSettings(
        max_tokens=10000,
        temperature=0.2,
    ),
)

# Helper function to scrape website content
def scrape_website_content(url: str) -> str:
    """Scrape and clean website content"""
    try:
        print(f"🌐 Fetching content from: {url}")
        
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; DataExtractor/1.0)"
        }
        
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        clean_text = response.text
        return clean_text
        
    except Exception as e:
        error_msg = f"Error scraping {url}: {str(e)}"
        print(f"❌ {error_msg}")
        return error_msg

# Main workflow orchestrator with session support and progress tracking
async def process_user_request(user_input: str, session: SQLiteSession):
    """Main workflow that classifies and routes user requests with session memory and progress tracking"""
    
    session_id = session.session_id
    
    # Initialize progress tracking
    def update_progress(step: str, description: str, progress: int, completed: bool = False):
        progress_store[session_id] = ProgressUpdate(
            step=step,
            description=description,
            progress=progress,
            session_id=session_id,
            completed=completed
        )
    
    print("🤖 Multi-Agent Request Processor with Session Memory")
    print("=" * 60)
    print(f"📝 User Input: {user_input}")
    print(f"🔗 Session ID: {session.session_id}")
    print("=" * 60)
    
    try:
        # Step 1: Initialize processing
        update_progress("initializing", "🤖 Starting AI analysis...", 10)
        
        # Step 2: Classify the request (with session context)
        update_progress("analyzing", "🔍 Analyzing the type of question...", 25)
        print("Step 1: Classifying request type...")
        
        classification_result = await Runner.run(
            request_classifier_agent, 
            user_input,
            session=session  # Session provides conversation context
        )
        classification = classification_result.final_output_as(RequestClassification)
        
        print(f"🔍 Classification: {classification.request_type}")
        print(f"💭 Reasoning: {classification.reasoning}")
        
        # Step 3: Route to appropriate agent (with session context)
        if classification.request_type == "regular_question":
            update_progress("processing", "📚 Generating answer to your question...", 50)
            print("\n📚 Routing to Regular Q&A Agent...")
            
            # Handle regular question with session memory
            qa_result = await Runner.run(
                regular_qa_agent, 
                user_input,
                session=session  # Agent can see conversation history
            )
            answer = qa_result.final_output_as(RegularAnswer)
            
            update_progress("finalizing", "✅ Preparing response...", 90)
            
            print("\n" + "=" * 60)
            print("🎯 REGULAR Q&A RESULT:")
            print(f"Question: {user_input}")
            print(f"Answer: {answer.answer}")
            if answer.explanation:
                print(f"Explanation: {answer.explanation}")
            print("=" * 60)
            
            # Format response for API
            response_text = answer.answer
            if answer.explanation:
                response_text += f"\n\n{answer.explanation}"
            
            # Mark as completed
            update_progress("completed", "✅ Answer ready!", 100, completed=True)
            
            return {
                "response": response_text,
                "request_type": classification.request_type,
                "success": True
            }
            
        elif classification.request_type == "scrape_data":
            update_progress("processing", "🕷️ Preparing to scrape website...", 40)
            print("\n🕷️ Routing to Web Scraping Agent...")
            
            # Extract URL and question
            url = classification.url
            question = classification.question or "Extract all relevant information from this website"
            
            if not url:
                print("❌ No URL found in scraping request")
                update_progress("error", "❌ No URL found in request", 100, completed=True)
                return {
                    "response": "Sorry, I need a URL to scrape data. Please provide a valid website URL.",
                    "request_type": classification.request_type,
                    "success": False
                }
            
            # Step 4: Scrape website content
            update_progress("scraping", f"🌐 Scraping data from {url[:50]}...", 60)
            website_content = scrape_website_content(url)
            
            if website_content.startswith("Error"):
                update_progress("error", "❌ Failed to scrape website", 100, completed=True)
                return {
                    "response": f"Failed to scrape website: {website_content}",
                    "request_type": classification.request_type,
                    "success": False
                }
            
            # Step 5: Process scraped content with AI
            update_progress("analyzing", "🧠 Analyzing scraped content with AI...", 80)
            
            scraping_prompt = f"""
            User Request: {question}
            Website URL: {url}
            Website Content: {website_content}
            
            Please analyze this website content and extract relevant information based on the user's request.
            """
            
            scrape_result = await Runner.run(
                web_scraping_agent, 
                scraping_prompt,
                session=session  # Session context for follow-up scraping questions
            )
            scraped_data = scrape_result.final_output_as(ScrapeResult)
            
            update_progress("finalizing", "📋 Formatting extracted data...", 95)
            
            print("\n" + "=" * 60)
            print("🕸️ WEB SCRAPING RESULT:")
            print(f"URL: {url}")
            print(f"Request: {question}")
            print(f"Summary: {scraped_data.text}")
            
            if scraped_data.data_found:
                print("\nExtracted Data:")
                print(scraped_data.data_found)
            else:
                print("\nNo specific data extracted.")
            
            print("=" * 60)
            
            # Format response for API
            response_text = f"**Scraped from:** {url}\n\n**Summary:** {scraped_data.text}"
            if scraped_data.data_found:
                response_text += f"\n\n**Extracted Data:**\n{scraped_data.data_found}"
            
            # Mark as completed
            update_progress("completed", "✅ Scraping complete!", 100, completed=True)
            
            return {
                "response": response_text,
                "request_type": classification.request_type,
                "success": True
            }
            
        else:
            print(f"❌ Unknown request type: {classification.request_type}")
            update_progress("error", "❌ Unknown request type", 100, completed=True)
            return {
                "response": "Sorry, I couldn't understand your request type.",
                "request_type": "unknown",
                "success": False
            }
            
    except Exception as e:
        print(f"❌ Error in workflow: {e}")
        update_progress("error", f"❌ Error: {str(e)}", 100, completed=True)
        return {
            "response": f"An error occurred: {str(e)}",
            "request_type": "error",
            "success": False
        }

# Create FastAPI app
app = FastAPI(title="Multi-Agent Chat API", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store active sessions
active_sessions = {}

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """Main chat endpoint for processing user messages"""
    try:
        # Generate session ID if not provided
        if not request.session_id:
            request.session_id = str(uuid.uuid4())
        
        # Get or create session
        if request.session_id not in active_sessions:
            active_sessions[request.session_id] = SQLiteSession(
                request.session_id, 
                "chat_sessions.db"
            )
        
        session = active_sessions[request.session_id]
        
        # Process the request
        result = await process_user_request(request.message, session)
        
        # Create response
        response = ChatResponse(
            response=result["response"],
            session_id=request.session_id,
            request_type=result["request_type"],
            timestamp=datetime.now().isoformat()
        )
        
        return response
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing request: {str(e)}")

@app.get("/progress/{session_id}", response_model=ProgressUpdate)
async def get_progress(session_id: str):
    """Get current progress for a session"""
    if session_id not in progress_store:
        return ProgressUpdate(
            step="waiting",
            description="Waiting for processing to start...",
            progress=0,
            session_id=session_id,
            completed=False
        )
    
    return progress_store[session_id]

@app.get("/sessions/{session_id}/history")
async def get_session_history(session_id: str):
    """Get conversation history for a session"""
    try:
        if session_id not in active_sessions:
            return {"history": [], "session_id": session_id}
        
        session = active_sessions[session_id]
        items = await session.get_items()
        
        return {
            "history": items,
            "session_id": session_id
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving history: {str(e)}")

@app.delete("/sessions/{session_id}")
async def clear_session(session_id: str):
    """Clear a session's conversation history"""
    try:
        if session_id in active_sessions:
            session = active_sessions[session_id]
            await session.clear_session()
            del active_sessions[session_id]
        
        return {"message": f"Session {session_id} cleared successfully"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error clearing session: {str(e)}")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "message": "Multi-Agent Chat API is running"}

# Serve static files (for the frontend)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def serve_chat_interface():
    """Serve the chat interface HTML"""
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Multi-Agent Chat Interface</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            
            .chat-container {
                width: 90%;
                max-width: 800px;
                height: 80vh;
                background: white;
                border-radius: 20px;
                box-shadow: 0 20px 40px rgba(0,0,0,0.1);
                display: flex;
                flex-direction: column;
                overflow: hidden;
            }
            
            .chat-header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 20px;
                text-align: center;
            }
            
            .chat-header h1 {
                font-size: 24px;
                margin-bottom: 5px;
            }
            
            .chat-header p {
                opacity: 0.9;
                font-size: 14px;
            }
            
            .chat-messages {
                flex: 1;
                padding: 20px;
                overflow-y: auto;
                background-color: #f8f9fa;
            }
            
            .message {
                margin-bottom: 15px;
                display: flex;
                align-items: flex-start;
            }
            
            .message.user {
                justify-content: flex-end;
            }
            
            .message-content {
                max-width: 70%;
                padding: 12px 16px;
                border-radius: 18px;
                word-wrap: break-word;
                white-space: pre-wrap;
            }
            
            .message.user .message-content {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
            }
            
            .message.bot .message-content {
                background: white;
                color: #333;
                border: 1px solid #e1e5e9;
            }
            
            .message-time {
                font-size: 11px;
                color: #666;
                margin-top: 5px;
            }
            
            .typing-indicator {
                display: none;
                padding: 20px;
                text-align: center;
                color: #666;
            }
            
            .typing-dot {
                display: inline-block;
                width: 8px;
                height: 8px;
                border-radius: 50%;
                background-color: #667eea;
                animation: typing 1.4s infinite ease-in-out;
                margin: 0 2px;
            }
            
            .typing-dot:nth-child(1) { animation-delay: -0.32s; }
            .typing-dot:nth-child(2) { animation-delay: -0.16s; }
            
            @keyframes typing {
                0%, 80%, 100% { transform: scale(0.8); opacity: 0.5; }
                40% { transform: scale(1); opacity: 1; }
            }
            
            .chat-input {
                padding: 20px;
                border-top: 1px solid #e1e5e9;
                background: white;
            }
            
            .input-group {
                display: flex;
                gap: 10px;
            }
            
            .message-input {
                flex: 1;
                padding: 15px;
                border: 2px solid #e1e5e9;
                border-radius: 25px;
                outline: none;
                font-size: 14px;
                transition: border-color 0.3s;
            }
            
            .message-input:focus {
                border-color: #667eea;
            }
            
            .send-button {
                padding: 15px 20px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border: none;
                border-radius: 25px;
                cursor: pointer;
                font-weight: 600;
                transition: transform 0.2s;
                min-width: 80px;
            }
            
            .send-button:hover {
                transform: translateY(-2px);
            }
            
            .send-button:disabled {
                opacity: 0.6;
                cursor: not-allowed;
                transform: none;
            }
            
            .session-info {
                padding: 10px 20px;
                background: #f8f9fa;
                border-top: 1px solid #e1e5e9;
                font-size: 12px;
                color: #666;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            
            .clear-button {
                background: #dc3545;
                color: white;
                border: none;
                padding: 5px 10px;
                border-radius: 12px;
                cursor: pointer;
                font-size: 11px;
            }
        </style>
    </head>
    <body>
        <div class="chat-container">
            <div class="chat-header">
                <h1>🤖 Multi-Agent Chat</h1>
                <p>Ask questions or request web scraping - I remember our conversation!</p>
            </div>
            
            <div class="chat-messages" id="chatMessages">
                <div class="message bot">
                    <div class="message-content">
                        Hi! I'm your AI assistant with multi-agent capabilities. I can:
                        
                        📚 Answer questions and have conversations
                        🕷️ Scrape and analyze websites
                        🧠 Remember our conversation context
                        
                        Try asking me something or give me a URL to scrape!
                    </div>
                </div>
            </div>
            
            <div class="typing-indicator" id="typingIndicator">
                <span class="typing-dot"></span>
                <span class="typing-dot"></span>
                <span class="typing-dot"></span>
                AI is thinking...
            </div>
            
            <div class="chat-input">
                <div class="input-group">
                    <input 
                        type="text" 
                        class="message-input" 
                        id="messageInput" 
                        placeholder="Type your message or paste a URL to scrape..."
                        maxlength="1000"
                    >
                    <button class="send-button" id="sendButton">Send</button>
                </div>
            </div>
            
            <div class="session-info">
                <span id="sessionInfo">Session: Initializing...</span>
                <button class="clear-button" id="clearButton">Clear Chat</button>
            </div>
        </div>

        <script>
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
                    
                    // Disable input while processing
                    this.setInputEnabled(false);
                    
                    // Add user message to chat
                    this.addMessage(message, 'user');
                    this.messageInput.value = '';
                    
                    // Show progress tracking
                    this.showProgress(true);
                    this.startProgressPolling();
                    
                    try {
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
                        
                        if (!response.ok) {
                            throw new Error(`HTTP error! status: ${response.status}`);
                        }
                        
                        const data = await response.json();
                        
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
                        console.error('Error:', error);
                        this.stopProgressPolling();
                        this.addMessage('Sorry, I encountered an error. Please try again.', 'bot', 'error');
                    } finally {
                        this.showProgress(false);
                        this.setInputEnabled(true);
                        this.messageInput.focus();
                    }
                }
                
                startProgressPolling() {
                    if (!this.sessionId || this.progressInterval) return;
                    
                    this.progressInterval = setInterval(async () => {
                        try {
                            const response = await fetch(`/progress/${this.sessionId}`);
                            if (response.ok) {
                                const progress = await response.json();
                                this.updateProgressDisplay(progress);
                                
                                // Stop polling if completed
                                if (progress.completed) {
                                    this.stopProgressPolling();
                                }
                            }
                        } catch (error) {
                            console.error('Progress polling error:', error);
                        }
                    }, 500); // Poll every 500ms
                }
                
                stopProgressPolling() {
                    if (this.progressInterval) {
                        clearInterval(this.progressInterval);
                        this.progressInterval = null;
                    }
                }
                
                updateProgressDisplay(progress) {
                    const progressElement = document.getElementById('typingIndicator');
                    if (progressElement && progressElement.style.display !== 'none') {
                        
                        // Create or update progress content
                        let progressHtml = `
                            <div style="display: flex; align-items: center; gap: 10px;">
                                <div style="display: flex; gap: 5px;">
                                    <span class="typing-dot"></span>
                                    <span class="typing-dot"></span>
                                    <span class="typing-dot"></span>
                                </div>
                                <div>
                                    <div style="font-weight: 600; color: #667eea;">
                                        ${progress.description}
                                    </div>
                                    <div style="font-size: 11px; color: #666; margin-top: 2px;">
                                        Step: ${progress.step} • Progress: ${progress.progress}%
                                    </div>
                                </div>
                            </div>
                        `;
                        
                        progressElement.innerHTML = progressHtml;
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
        </script>
    </body>
    </html>
    """

# Interactive mode with persistent session (for CLI use)
async def interactive_agent_with_session():
    """Interactive mode with session memory for follow-up questions"""
    
    # Create a persistent session
    session = SQLiteSession("multi_agent_session", "conversation_history.db")
    
    print("🤖" * 20)
    print("Multi-Agent Request Processor with Session Memory!")
    print("🤖" * 20)
    print("\nI can handle two types of requests and remember our conversation:")
    print("1. 📚 Regular Questions: Ask me anything! (I'll remember context)")
    print("2. 🕷️ Web Scraping: Extract data from websites")
    print("\nExamples:")
    print("• 'What is the capital of France?'")
    print("• 'What about Italy?' (follow-up question)")
    print("• 'How do I cook pasta?'")
    print("• 'Scrape data from https://example.com'")
    print("• 'Extract more details from that site' (follow-up)")
    print(f"\n🔗 Session ID: {session.session_id}")
    print("💾 Conversation will be saved and remembered!")
    print("\nType 'exit' to quit")
    print("=" * 60)
    
    while True:
        try:
            # Get user input
            user_input = input("\n🎤 Your request: ").strip()
            
            if user_input.lower() in ['exit', 'quit', 'bye']:
                print("👋 Thanks for using the Multi-Agent Processor! Your conversation is saved.")
                break
            
            if not user_input:
                print("Please enter a request!")
                continue
            
            # Process the request with session memory
            result = await process_user_request(user_input, session)
            
        except KeyboardInterrupt:
            print("\n👋 Thanks for using the Multi-Agent Processor! Your conversation is saved.")
            break
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            continue

async def demo_session_functionality():
    """Demo showing session memory in action"""
    
    session = SQLiteSession("demo_session", "demo_conversation.db")
    
    print("🧪 DEMO: Session Memory Functionality")
    print("=" * 60)
    
    # First question
    print("Demo 1: Initial question about France")
    await process_user_request("What is the capital of France?", session)
    
    print("\n" + "🔄" * 20 + "\n")
    
    # Follow-up question (should reference France)
    print("Demo 2: Follow-up question (should remember France)")
    await process_user_request("What about the population of that city?", session)
    
    print("\n" + "🔄" * 20 + "\n")
    
    # Another follow-up
    print("Demo 3: Another follow-up (should remember Paris)")
    await process_user_request("What are some famous landmarks there?", session)
    
    print("\n" + "🔄" * 20 + "\n")
    
    # Web scraping example
    print("Demo 4: Web scraping request")
    await process_user_request("Scrape data from https://example.com", session)
    
    print("\n" + "🔄" * 20 + "\n")
    
    # Follow-up about scraped data
    print("Demo 5: Follow-up about scraped data")
    await process_user_request("Can you tell me more about that domain information?", session)

async def main():
    """Main function to demonstrate the session-enabled workflow"""
    
    # Run demo first
    #await demo_session_functionality()
    
    print("\n" + "🔄" * 20 + "\n")
    
    # Start interactive mode
    await interactive_agent_with_session()

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "server":
        # Run as FastAPI server
        print("🚀 Starting FastAPI server...")
        uvicorn.run(app, host="0.0.0.0", port=8000)
    else:
        # Run as CLI
        asyncio.run(main())