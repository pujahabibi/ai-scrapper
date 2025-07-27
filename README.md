# 🤖 AI Scrapper - Multi-Agent Chat

A beautiful, modern web interface for AI-powered conversations and web scraping using React and Bootstrap.

## ✨ Features

- **🎨 Modern UI**: Beautiful React interface with Bootstrap 5 and glassmorphism effects
- **🤖 Multi-Agent System**: Intelligent AI agents for different tasks
- **🕷️ Web Scraping**: Smart web scraping capabilities with progress tracking
- **💬 Interactive Chat**: Real-time chat interface with typing indicators
- **🧠 Context Memory**: Remembers conversation context across sessions
- **📱 Responsive Design**: Works perfectly on desktop and mobile devices
- **⚡ Real-time Progress**: Live progress tracking for long-running tasks

## 🚀 Quick Start

### Prerequisites

- Python 3.8+ with conda environment named 'work'
- Node.js 16+ and npm

### Installation

1. **Clone and setup:**
```bash
git clone <your-repo>
cd ai-scrapper
```

2. **Install dependencies:**
```bash
# Activate conda environment
conda activate work

# Install Python dependencies (if not already installed)
# pip install fastapi uvicorn ...

# Install Node.js dependencies  
npm install
```

3. **Build and run:**
```bash
# Build the React application
npm run build

# Start the server
python run_server.py
```

Or use the development script:
```bash
# Build and start in one command
./dev.sh dev
```

### 🌐 Access the Application

Open your browser and go to: **http://localhost:8000**

## 🛠️ Development

### Project Structure

```
ai-scrapper/
├── src/                     # React source code
│   ├── components/          # React components
│   │   ├── ChatInterface.js # Main chat interface
│   │   ├── Message.js       # Individual message bubbles
│   │   ├── InputForm.js     # Message input form
│   │   ├── ProgressIndicator.js # Progress tracking
│   │   └── ...
│   ├── styles/              # CSS styles
│   └── App.js              # Main React app
├── static/                  # Generated static files
├── templates/               # HTML templates  
├── api.py                   # FastAPI backend
├── main_agents.py           # AI agent logic
└── run_server.py           # Server launcher
```

### Development Commands

```bash
# Build React app
npm run build

# Start development mode (build + start)
./dev.sh dev

# Just start server
./dev.sh start

# Build only
./dev.sh build
```

### 🎨 UI Components

- **Glassmorphism Design**: Modern glass-like effects with backdrop blur
- **Bootstrap 5**: Full responsive grid system and components
- **FontAwesome Icons**: Beautiful icons throughout the interface
- **Custom Animations**: Smooth slide-in animations for messages
- **Progress Tracking**: Real-time progress bars with step indicators
- **Interactive Elements**: Hover effects and smooth transitions

## 🌟 Features in Detail

### 💬 Chat Interface
- Beautiful message bubbles with speech tails
- User and AI avatars
- Message type indicators (Web Scraping, AI Response, etc.)
- Timestamps and animation effects
- Auto-scroll to latest messages

### 📊 Progress Tracking  
- Real-time progress bars
- Step-by-step indicators
- Colored badges for different operation types
- Smooth animations and transitions

### 🔧 Session Management
- Persistent session storage
- Clear conversation functionality
- Session ID display
- Local storage integration

### 📱 Responsive Design
- Mobile-first approach
- Bootstrap responsive grid
- Touch-friendly interface
- Optimized for all screen sizes

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Build and test: `npm run build`
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License.

---

**🎉 Enjoy your beautiful, modern AI Scrapper interface!** 