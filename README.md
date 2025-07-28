# AI Scrapper - Multi-Agent Web Scraping Chat

An intelligent web scraping application powered by OpenAI agents that can extract structured data from websites and answer follow-up questions about the scraped data.

## 🚀 Quick Start with Docker

**Single command setup:**
```bash
./docker-run.sh
```

**Prerequisites:**
- Docker installed and running
- OpenAI API key

The script will:
1. Copy `.env.example` to `.env` (add your OpenAI API key)
2. Build the Docker image
3. Start the application on `http://localhost:8000`

## 🔧 Manual Setup

**1. Clone and setup:**
```bash
git clone <repository-url>
cd ai-scrapper
```

**2. Install dependencies:**
```bash
# Python dependencies
pip install -r requirements.txt

# Frontend dependencies  
npm install
npm run build
```

**3. Environment setup:**
```bash
# Copy example file and edit with your API key
cp .env.example .env
# Edit .env file with your actual OpenAI API key
```

**4. Run application:**
```bash
python run_server.py
```

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

```bash
# Run application
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
├── src/               # React frontend
└── templates/         # HTML templates
```

## ⚙️ Configuration

Environment variables in `.env`:
```bash
OAI_API_KEY=your-openai-api-key-here
OPENAI_API_KEY=your-openai-api-key-here  # Same value (OpenAI library compatibility)
```

## 🤖 How It Works

1. **Request Classification**: Determines if user wants scraping or Q&A
2. **Link Discovery**: Finds all relevant detail page links
3. **Parallel Extraction**: Uses OpenAI search on each link concurrently  
4. **Data Combination**: Merges results into structured format
5. **Follow-up Support**: Answers questions about scraped data

## 📝 License

MIT License - see LICENSE file for details. 