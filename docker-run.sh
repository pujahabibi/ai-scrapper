#!/bin/bash

# AI Scrapper Docker Runner
# Single command to build and run the AI Scrapper application

set -e  # Exit on any error

echo "🚀 AI Scrapper Docker Runner"
echo "================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
CONTAINER_NAME="ai-scrapper"
IMAGE_NAME="ai-scrapper:latest"
PORT=8000

# Function to check if Docker is running
check_docker() {
    if ! docker info > /dev/null 2>&1; then
        echo -e "${RED}❌ Docker is not running. Please start Docker first.${NC}"
        exit 1
    fi
}

# Function to check for environment variables
check_env() {
    if [ ! -f .env ]; then
        echo -e "${YELLOW}⚠️ No .env file found. Creating from template...${NC}"
        if [ -f .env.example ]; then
            cp .env.example .env
            echo -e "${YELLOW}📝 Created .env from .env.example${NC}"
        else
            echo -e "${RED}❌ No .env.example template found${NC}"
            exit 1
        fi
        echo -e "${YELLOW}📝 Please edit .env file with your OpenAI API key${NC}"
        exit 1
    fi
    
    # Check if API key is set
    if grep -q "your-openai-api-key-here" .env; then
        echo -e "${RED}❌ Please set your OpenAI API key in .env file${NC}"
        echo -e "${YELLOW}💡 Set both OAI_API_KEY and OPENAI_API_KEY to the same value${NC}"
        exit 1
    fi
}

# Function to stop existing container
stop_existing() {
    if [ "$(docker ps -q -f name=$CONTAINER_NAME)" ]; then
        echo -e "${YELLOW}🛑 Stopping existing container...${NC}"
        docker stop $CONTAINER_NAME
    fi
    
    if [ "$(docker ps -aq -f name=$CONTAINER_NAME)" ]; then
        echo -e "${YELLOW}🗑️ Removing existing container...${NC}"
        docker rm $CONTAINER_NAME
    fi
}

# Function to build Docker image
build_image() {
    echo -e "${GREEN}🔨 Building Docker image...${NC}"
    docker build -t $IMAGE_NAME .
    echo -e "${GREEN}✅ Image built successfully!${NC}"
}

# Function to run container
run_container() {
    echo -e "${GREEN}🚀 Starting AI Scrapper container...${NC}"
    docker run -d \
        --name $CONTAINER_NAME \
        --env-file .env \
        -p $PORT:$PORT \
        -v $(pwd)/data:/app/data \
        --restart unless-stopped \
        $IMAGE_NAME
    
    echo -e "${GREEN}✅ Container started successfully!${NC}"
    echo ""
    echo "🌐 Access the application at: http://localhost:$PORT"
    echo "📊 Health check: http://localhost:$PORT/health"
    echo ""
    echo "📋 Useful commands:"
    echo "  docker logs $CONTAINER_NAME -f    # View logs"
    echo "  docker stop $CONTAINER_NAME       # Stop container"
    echo "  docker restart $CONTAINER_NAME    # Restart container"
}

# Function to show logs
show_logs() {
    echo -e "${GREEN}📋 Showing container logs (Ctrl+C to exit)...${NC}"
    docker logs $CONTAINER_NAME -f
}

# Main execution
main() {
    check_docker
    check_env
    stop_existing
    build_image
    run_container
    
    # Ask if user wants to see logs
    echo ""
    read -p "📋 Show live logs? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        show_logs
    fi
}

# Parse command line arguments
case "${1:-}" in
    "logs")
        docker logs $CONTAINER_NAME -f
        ;;
    "stop")
        docker stop $CONTAINER_NAME
        echo -e "${GREEN}✅ Container stopped${NC}"
        ;;
    "restart")
        docker restart $CONTAINER_NAME
        echo -e "${GREEN}✅ Container restarted${NC}"
        ;;
    "build")
        build_image
        ;;
    *)
        main
        ;;
esac 