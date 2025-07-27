#!/bin/bash

# AI Scrapper Development Script
# Usage: ./dev.sh [build|start|dev]

set -e

echo "🤖 AI Scrapper - Multi-Agent Chat"
echo "================================="

case "${1:-start}" in
  "build")
    echo "📦 Building React application..."
    npm run build
    echo "✅ Build completed!"
    ;;
    
  "start")
    echo "🚀 Starting production server..."
    conda activate work 2>/dev/null || echo "⚠️  Note: Run 'conda activate work' first"
    python run_server.py
    ;;
    
  "dev")
    echo "🔧 Starting development mode..."
    echo "This will build the React app and start the server"
    npm run build
    echo "📦 Build completed, starting server..."
    conda activate work 2>/dev/null || echo "⚠️  Note: Run 'conda activate work' first"
    python run_server.py
    ;;
    
  *)
    echo "Usage: $0 [build|start|dev]"
    echo ""
    echo "Commands:"
    echo "  build  - Build the React application"
    echo "  start  - Start the production server"  
    echo "  dev    - Build and start in development mode"
    echo ""
    echo "Default: start"
    ;;
esac 