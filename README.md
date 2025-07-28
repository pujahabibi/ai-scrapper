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
├── src/               # React frontend
└── templates/         # HTML templates
```

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

## 🤖 How It Works

1. **Request Classification**: Determines if user wants scraping or Q&A
2. **Link Discovery**: Finds all relevant detail page links
3. **Parallel Extraction**: Uses OpenAI search on each link concurrently  
4. **Data Combination**: Merges results into structured format
5. **Follow-up Support**: Answers questions about scraped data

## 🔧 Troubleshooting

**Common Issues:**

**❌ "OpenAI API key not found" Error:**
- Make sure `.env` file exists in the project root
- Verify both `OAI_API_KEY` and `OPENAI_API_KEY` are set in `.env`
- Check that there are no extra spaces around the `=` sign
- Ensure your API key starts with `sk-proj-` or `sk-`

**❌ "401 Unauthorized" Error:**
- Your API key may be invalid or expired
- Generate a new API key at [OpenAI Platform](https://platform.openai.com/api-keys)
- Make sure you have sufficient credits in your OpenAI account

**❌ Application won't start:**
- Run `python -c "from dotenv import load_dotenv; import os; load_dotenv(); print('API Key found:', bool(os.getenv('OAI_API_KEY')))"` to test
- Check that all dependencies are installed: `pip install -r requirements.txt`

## 📝 License

MIT License - see LICENSE file for details. 