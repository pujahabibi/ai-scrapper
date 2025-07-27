#!/usr/bin/env python3
"""
Simple launcher script for the Multi-Agent Chat Server
Run with: python run_server.py
"""

import sys
import os
import subprocess

def main():
    print("🚀 Starting Multi-Agent Chat Server...")
    print("Make sure you have activated your conda environment 'work'")
    print("If not, run: conda activate work")
    print("-" * 50)
    
    try:
        # Run the FastAPI server using the api.py file
        from api import app
        import uvicorn
        
        print("✅ Starting server on http://localhost:8000")
        print("✅ Chat interface will be available at http://localhost:8000")
        print("Press Ctrl+C to stop the server")
        print("-" * 50)
        
        uvicorn.run(app, host="0.0.0.0", port=8000)
        
    except KeyboardInterrupt:
        print("\n👋 Server stopped by user")
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Make sure you have activated the 'work' conda environment")
        print("Run: conda activate work")
    except Exception as e:
        print(f"❌ Error starting server: {e}")

if __name__ == "__main__":
    main() 