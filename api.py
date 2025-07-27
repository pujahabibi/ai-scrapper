from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn
import uuid
from datetime import datetime
from agents import SQLiteSession

# Import from main_agents
from main_agents import process_user_request, active_sessions, progress_store, ProgressUpdate

# FastAPI request/response models
class ChatRequest(BaseModel):
    message: str
    session_id: str = ""

class ChatResponse(BaseModel):
    response: str
    session_id: str
    request_type: str
    timestamp: str

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

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """Main chat endpoint for processing user messages"""
    try:
        # Generate session ID if not provided
        if not request.session_id:
            request.session_id = str(uuid.uuid4())
            print(f"🆔 Generated new session ID: {request.session_id}")
        else:
            print(f"🆔 Using existing session ID: {request.session_id}")
        
        # Get or create session
        if request.session_id not in active_sessions:
            print(f"🆕 Creating new session: {request.session_id}")
            active_sessions[request.session_id] = SQLiteSession(
                request.session_id, 
                "chat_sessions.db"
            )
        else:
            print(f"🔗 Using existing session: {request.session_id}")
        
        session = active_sessions[request.session_id]
        
        print(f"💬 Processing message: '{request.message}' for session: {request.session_id}")
        
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
    print(f"📡 Progress request for session: {session_id}")
    print(f"📊 Available sessions in progress_store: {list(progress_store.keys())}")
    
    if session_id not in progress_store:
        print(f"⚠️ Session {session_id} not found in progress_store")
        return ProgressUpdate(
            step="waiting",
            description="Waiting for processing to start...",
            session_id=session_id,
            completed=False
        )
    
    current_progress = progress_store[session_id]
    print(f"✅ Returning progress: {current_progress.step} - {current_progress.description}")
    return current_progress

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
    with open("templates/index.html", "r") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)

@app.get("/diagnostic", response_class=HTMLResponse)
async def serve_diagnostic_page():
    """Serve the diagnostic page HTML"""
    with open("diagnostic.html", "r") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)

if __name__ == "__main__":
    print("🚀 Starting FastAPI server...")
    uvicorn.run(app, host="0.0.0.0", port=8000) 