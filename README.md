# AI Scrapper - Multi-Agent Web Scraping Chat

An intelligent web scraping application powered by OpenAI agents that can extract structured data from websites and answer follow-up questions about the scraped data.

**📋 Requirements:** OpenAI API key required - get yours at [platform.openai.com](https://platform.openai.com/api-keys)

## 🚀 Quick Start with Docker

**⚠️ IMPORTANT: You must set up your OpenAI API key before running the application!**

**Prerequisites:**
- Docker installed and running
- OpenAI API key from [OpenAI Platform](https://platform.openai.com/api-keys)

**Setup Steps:**

**1. Configure Environment Variables:**
```bash
# Copy the example environment file
cp .env.example .env

# Edit .env file and add your OpenAI API key
# Replace 'your-openai-api-key-here' with your actual API key
```
- Edit .env file and add your OpenAI API key
- Replace 'your-openai-api-key-here' with your actual API key

**2. Run the Application:**
```bash
./docker-run.sh
```

The script will:
1. Check that your `.env` file is properly configured
2. Build the Docker image
3. Start the application on `http://localhost:8000`

**🛑 Note:** The application will not work without a valid OpenAI API key in the `.env` file.

## 🔧 Manual Setup

**1. Clone and setup:**
```bash
git clone <repository-url>
cd ai-scrapper
```

**2. Environment setup (REQUIRED FIRST):**
```bash
# Copy the example environment file
cp .env.example .env

# Edit .env file and add your OpenAI API key
# Replace 'your-openai-api-key-here' with your actual API key from:
# https://platform.openai.com/api-keys
```

**3. Install dependencies:**
```bash
# Python dependencies
pip install -r requirements.txt

# Frontend dependencies  
npm install
npm run build
```

**4. Run application:**
```bash
python run_server.py
```

**⚠️ Important:** Make sure to complete step 2 (environment setup) before running the application. The application will fail to start without a valid OpenAI API key.

## 📋 Features

- **Smart Web Scraping**: Multi-page scraping with link discovery
- **AI-Powered Extraction**: Uses OpenAI search for precise data extraction
- **Follow-up Questions**: Ask questions about previously scraped data
- **Parallel Processing**: Fast concurrent link processing
- **Session Memory**: Remembers conversation history
- **Modern UI**: React-based chat interface

## 🔍 Usage Examples

**Scraping:**
```
https://example.com/jobs Get all job titles, locations and salaries from page 1 to 3
```

**Follow-up Questions:**
```
Which jobs pay more than $50,000?
How many jobs were found in total?
List all jobs in New York
```

## 🐳 Docker Commands

**⚠️ Reminder:** Make sure your `.env` file is configured with your OpenAI API key before running these commands.

```bash
# Run application (requires .env file with API key)
./docker-run.sh

# View logs
./docker-run.sh logs

# Stop application  
./docker-run.sh stop

# Restart application
./docker-run.sh restart

# Rebuild image only
./docker-run.sh build
```

## 📁 Project Structure

```
ai-scrapper/
├── main_agents.py      # Core multi-agent logic
├── api.py             # FastAPI server
├── run_server.py      # Application launcher
├── Dockerfile         # Docker configuration
├── docker-run.sh      # Docker runner script
├── requirements.txt   # Python dependencies
├── .env.example       # Environment template
├── SYSTEM_DESIGN.md   # Architecture documentation
├── src/               # React frontend
└── templates/         # HTML templates
```

## 📖 System Design & Architecture

### **📋 Complete Documentation**
- **[SYSTEM_DESIGN.md](SYSTEM_DESIGN.md)**: Comprehensive technical documentation covering the multi-agent system, detailed workflow, and complete architecture

### **🎯 System Overview**

The AI Scrapper employs a **3-phase intelligent workflow**:

```
Phase 1: Link Discovery    Phase 2: Parallel Extraction    Phase 3: Result Combination
┌─────────────────────┐   ┌──────────────────────────┐   ┌─────────────────────────┐
│ Content Analyzer    │   │ OpenAI Search (Parallel) │   │ JSON Merge & Storage    │
│ Agent finds relevant│──▶│ Extract data from each   │──▶│ Combine all results     │
│ detail page links   │   │ link concurrently        │   │ into structured format  │
└─────────────────────┘   └──────────────────────────┘   └─────────────────────────┘
```

### **🤖 Multi-Agent Architecture**

**Three Specialized AI Agents:**
- **🔍 Request Classifier**: Determines scraping vs. Q&A requests
- **📊 Content Analyzer**: Intelligently discovers relevant links from web pages  
- **💬 Q&A Assistant**: Handles follow-up questions about scraped data

### **⚡ Key Technical Features**

- **Intelligent Link Selection**: AI analyzes user intent to find only relevant links (job details vs. company pages vs. contact info)
- **Parallel Processing**: Multiple links scraped simultaneously using `asyncio.gather()`
- **OpenAI Search Integration**: Advanced AI-powered data extraction from each discovered link
- **Session Memory**: Conversation history and scraped data preserved for follow-up questions
- **Robust Fallbacks**: HTTP → Selenium → Manual parsing for maximum reliability

### **🛠️ Technology Stack**
- **Backend**: FastAPI + OpenAI API + Selenium + WebDriver Manager
- **Frontend**: React + Webpack
- **Infrastructure**: Docker + SQLite + Environment-based configuration

### **🔄 Workflow Steps**

1. **Request Classification**: AI determines if user wants scraping or Q&A
2. **Link Discovery**: Content Analyzer finds all relevant detail page links
3. **Parallel Extraction**: OpenAI search processes each link concurrently  
4. **Data Combination**: Results merged into structured JSON format
5. **Session Storage**: Data saved for follow-up questions and context
6. **Follow-up Support**: Q&A Assistant answers questions about scraped data

## ⚙️ Configuration

**Required Environment Variables:**

Create a `.env` file in the project root with your OpenAI API key:

```bash
# OpenAI API Key (REQUIRED)
# Get your API key from: https://platform.openai.com/api-keys
OAI_API_KEY=sk-proj-your-actual-api-key-here
OPENAI_API_KEY=sk-proj-your-actual-api-key-here  # Same value (OpenAI library compatibility)

# Optional Configuration
PYTHONPATH=/app
PYTHONUNBUFFERED=1
```

**🔑 Getting Your OpenAI API Key:**
1. Visit [OpenAI Platform](https://platform.openai.com/api-keys)
2. Sign in to your OpenAI account
3. Click "Create new secret key"
4. Copy the key and paste it in your `.env` file

**💡 Note:** Both `OAI_API_KEY` and `OPENAI_API_KEY` should have the same value for compatibility.

## 📝 License

MIT License - see LICENSE file for details. 