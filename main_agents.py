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
from openai import OpenAI
from dotenv import load_dotenv
import os
import re
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from selenium import webdriver
from langchain_core.output_parsers import JsonOutputParser

load_dotenv()

# Initialize OpenAI client
openai_api_key = os.getenv("OAI_API_KEY") or os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    raise ValueError("❌ OpenAI API key not found! Please set OAI_API_KEY or OPENAI_API_KEY environment variable")

client = OpenAI(api_key=openai_api_key)
print("✅ OpenAI client initialized successfully")

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
    data_found: str = ""  # Updated to match agent output

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
    instructions="""You are a highly skilled web scraper specializing in complete data extraction from websites.

CRITICAL REQUIREMENTS FOR 100% DATA EXTRACTION:
1. EXTRACT EVERY SINGLE ITEM - You must find ALL data entries, not just the first few
2. SCAN THE ENTIRE CONTENT - Read through ALL content, not just the beginning
3. MULTIPLE PASSES - Look for data in different HTML structures, classes, and sections
4. NO SHORTCUTS - Do not stop until you've found every possible data entry
5. VERIFY COMPLETENESS - Double-check that you haven't missed any items

DATA IDENTIFICATION PATTERNS (look for ALL of these):
- Repeating patterns of structured information
- Lists, tables, or card-based layouts
- Links to individual items/pages
- Reference numbers or IDs
- Prices, dates, locations, names
- Similar formatting patterns
- JSON or structured data embedded in HTML

EXTRACTION STRATEGY:
1. First, identify the main content area and data patterns
2. Scan for obvious containers/cards/list items
3. Look for repeating patterns of similar information
4. Check for any hidden or dynamically loaded content references
5. Look in different sections (main content, sidebars, nested areas)
6. Count items as you find them to ensure completeness

For structured data (like job listings, products, articles), extract:
- All identifying information (titles, names, IDs)
- All descriptive content (descriptions, details)
- All metadata (dates, locations, categories, prices)
- All contact or reference information
- Any additional relevant fields specific to the content type

IMPORTANT: Be thorough and extract EVERY item you find. Don't stop at 10 or 15 items if there are clearly more available. Your goal is 100% capture rate.

SPECIAL INSTRUCTIONS FOR MEDRECRUIT/JOB SITES:
- Each page typically contains 20 job listings
- Look for salary amounts ($ per hour/day)
- Find medical specialties and locations
- Extract job types (Locum, Permanent)
- Get hospital descriptions and job IDs
- Look for "SAVE JOB" buttons as indicators
- Scan for NSW cities and medical terms

You must return a valid JSON object with this exact structure:
{
    "text": "Your comprehensive summary of what you found including count",
    "data_found": "All extracted data in a well-formatted, structured way"
}

Return a comprehensive summary in 'text' that includes the count of items found, and format all extracted data clearly in 'data_found' as a structured, readable format.""",
    output_type=ScrapeResult,
    model="gpt-4.1-mini",
    model_settings=ModelSettings(
        max_tokens=32000,
        temperature=0,  # Lower temperature for more consistent extraction
    ),
)

# ─── Multi-page Web Scraping Functions ────────────────────────────────────────

async def scrape_data_bs(url: str, question: str) -> ScrapeResult:
    """Scrape a single page using requests with Selenium fallback"""
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; MyScraper/1.0; +https://yourdomain.com/bot)"
    }

    # First try to get website content
    html = None
    try:
        print(f"🌐 Fetching content from: {url}")
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()  # throws if status != 200
        html = response.text
        print(f"✅ Successfully fetched with requests (length: {len(html)})")
    except Exception as e:
        print(f"❌ Request failed: {e}. Trying with Selenium...")
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            
            driver = webdriver.Chrome(options=chrome_options)
            driver.get(url)
            html = driver.page_source
            driver.quit()
            print(f"✅ Successfully fetched with Selenium (length: {len(html)})")
        except Exception as selenium_error:
            print(f"❌ Selenium also failed: {selenium_error}")
            return ScrapeResult(
                text="Failed to scrape the website - both requests and Selenium failed",
                result=[]
            )
    
    if not html:
        return ScrapeResult(
            text="Failed to fetch website content",
            data_found=""
        )
    
    # Use the web scraping agent instead of direct API call
    scraping_prompt = f"""
    User Request: {question}
    Website URL: {url}
    Website Content: {html}
    
    Please analyze this website content and extract ALL relevant information based on the user's request.
    Clean the data from HTML tags like <p> and </p> and other HTML tags.
    
    IMPORTANT: For Medrecruit job pages, extract ALL job listings (typically 20 per page).
    Look for job titles, specialties, locations, salaries, dates, hospital info, and job IDs.
    """
    
    # Create a simple session for the agent call
    temp_session = SQLiteSession("scrape_session", "scrape_temp.db")
    
    # Run the web scraping agent
    scrape_result = await Runner.run(
        web_scraping_agent,
        scraping_prompt,
        session=temp_session
    )
    
    # Get the result from the agent
    try:
        scraped_data = scrape_result.final_output_as(ScrapeResult)
        print(f"🔍 Agent extracted: {scraped_data.text[:100]}...")
        return scraped_data
    except Exception as e:
        print(f"❌ Agent extraction failed: {e}")
        return ScrapeResult(
            text="Failed to extract data using agent",
            data_found=""
        )

def update_url_page(url: str, page: int) -> str:
    """
    Given a URL with a `page` query param (or without), returns a new URL
    with `page=...` set to the desired value.
    """
    p = urlparse(url)
    qs = parse_qs(p.query)
    qs["page"] = [str(page)]
    new_query = urlencode(qs, doseq=True)
    return urlunparse(p._replace(query=new_query))

def extract_page_range(question: str):
    """
    Look for patterns like 'page X until Y' or 'pages X to Y' in the question.
    Returns (start, end) as ints, or None if not found.
    """
    # Try different patterns for page ranges
    patterns = [
        r"page(?:s)?\s*(\d+)\s*(?:to|until|-)\s*(\d+)",  # "pages 1 to 5", "page 1-3"
        r"page\s+(\d+)\s+to\s+page\s+(\d+)",             # "page 1 to page 10"
        r"from\s+page\s*(\d+)\s*(?:to|until|-)\s*(?:page\s*)?(\d+)"  # "from page 1 to 5"
    ]
    
    for pattern in patterns:
        m = re.search(pattern, question, re.IGNORECASE)
        if m:
            return int(m.group(1)), int(m.group(2))
    return None

async def flexible_scrape(url: str, question: str, update_progress_callback=None) -> ScrapeResult:
    """
    If `question` specifies a page range, loops from start→end; otherwise
    scrapes just the single `url`. Returns a ScrapeResult object.
    """
    pr = extract_page_range(question)
    if pr:
        start, end = pr
        urls = [update_url_page(url, p) for p in range(start, end + 1)]
        print(f"📄 Multi-page scraping detected: pages {start} to {end} ({len(urls)} pages)")
    else:
        urls = [url]
        print(f"📄 Single page scraping: {url}")

    per_page_outputs = []
    total_pages = len(urls)
    
    for i, u in enumerate(urls, 1):
        if update_progress_callback:
            update_progress_callback("scraping", f"🌐 Scraping page {i}/{total_pages}: {u[:50]}...")
        print(f"Scraping {u} ({i}/{total_pages})...")
        per_page_outputs.append(await scrape_data_bs(u, question))

    # if only one page, just return it
    if len(per_page_outputs) == 1:
        return per_page_outputs[0]

    # otherwise, combine them into one ScrapeResult
    if update_progress_callback:
        update_progress_callback("analyzing", f"🧠 Combining data from {total_pages} pages...")
    combined = await combine_results(per_page_outputs)
    return combined

async def combine_results(scrape_results: List[ScrapeResult]) -> ScrapeResult:
    """
    Takes multiple ScrapeResult objects and asks the LLM to merge them
    into one valid ScrapeResult.
    """
    print("Combining results...")
    system_prompt = '''Your task is to combine multiple JSON objects into a single, valid JSON object with this exact structure:
    {
        "text": "Combined descriptive text about all the data found",
        "result": [
            // All items from all the input results combined into one array
        ]
    }
    '''
    
    # Use the web scraping agent to combine results
    combined_text_parts = []
    combined_data_parts = []
    
    for sr in scrape_results:
        combined_text_parts.append(sr.text)
        if sr.data_found:
            combined_data_parts.append(sr.data_found)
    
    combination_prompt = f"""
    Please combine and consolidate the following scraped data from multiple pages:
    
    Text summaries from each page:
    {chr(10).join([f"Page {i+1}: {text}" for i, text in enumerate(combined_text_parts)])}
    
    Data from each page:
    {chr(10).join([f"--- Page {i+1} Data ---{chr(10)}{data}{chr(10)}" for i, data in enumerate(combined_data_parts)])}
    
    Please create a comprehensive combined summary and merge all the data into a single, well-formatted result.
    """
    
    # Create a simple session for the combination
    temp_session = SQLiteSession("combine_session", "combine_temp.db")
    
    # Run the web scraping agent to combine results
    combine_result = await Runner.run(
        web_scraping_agent,
        combination_prompt,
        session=temp_session
    )
    
    try:
        combined_data = combine_result.final_output_as(ScrapeResult)
        return combined_data
    except Exception as e:
        print(f"❌ Agent combination failed: {e}")
        return ScrapeResult(
            text="Failed to combine results using agent",
            data_found=""
        )

# Main workflow orchestrator with session support and progress tracking
async def process_user_request(user_input: str, session: SQLiteSession):
    """Main workflow that classifies and routes user requests with session memory and progress tracking"""
    
    session_id = session.session_id
    
    # Initialize progress tracking
    def update_progress(step: str, description: str, completed: bool = False):
        progress_update = ProgressUpdate(
            step=step,
            description=description,
            session_id=session_id,
            completed=completed
        )
        progress_store[session_id] = progress_update
        print(f"🔄 Progress Update: {step} - {description} [Session: {session_id}]")
        print(f"📤 Progress stored in progress_store for session: {session_id}")
        print(f"📊 Current progress_store keys: {list(progress_store.keys())}")
    
    print("🤖 Multi-Agent Request Processor with Session Memory")
    print("=" * 60)
    print(f"📝 User Input: {user_input}")
    print(f"🔗 Session ID: {session.session_id}")
    print("=" * 60)
    
    try:
        # Step 1: Initialize processing
        update_progress("initializing", "🤖 Starting AI analysis...")
        
        # Step 2: Classify the request (with session context)
        update_progress("analyzing", "🔍 Analyzing the type of question...")
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
            update_progress("processing", "📚 Generating answer to your question...")
            print("\n📚 Routing to Regular Q&A Agent...")
            
            # Handle regular question with session memory
            qa_result = await Runner.run(
                regular_qa_agent, 
                user_input,
                session=session  # Agent can see conversation history
            )
            answer = qa_result.final_output_as(RegularAnswer)
            
            update_progress("finalizing", "✅ Preparing response...")
            
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
            update_progress("completed", "✅ Answer ready!", completed=True)
            
            return {
                "response": response_text,
                "request_type": classification.request_type,
                "success": True
            }
            
        elif classification.request_type == "scrape_data":
            update_progress("processing", "🕷️ Preparing to scrape website...")
            print("\n🕷️ Routing to Web Scraping Agent...")
            
            # Extract URL and question
            url = classification.url
            question = classification.question or "Extract all relevant information from this website"
            
            if not url:
                print("❌ No URL found in scraping request")
                update_progress("error", "❌ No URL found in request", completed=True)
                return {
                    "response": "Sorry, I need a URL to scrape data. Please provide a valid website URL.",
                    "request_type": classification.request_type,
                    "success": False
                }
            
            # Step 4: Flexible scraping (single or multi-page)
            update_progress("scraping", f"🌐 Analyzing scraping requirements...")
            
            # Check if user specified page range
            page_range = extract_page_range(question)
            if page_range:
                start, end = page_range
                print(f"📄 Multi-page scraping requested: pages {start} to {end}")
                update_progress("scraping", f"🌐 Preparing to scrape {end - start + 1} pages...")
            else:
                print(f"📄 Single page scraping: {url}")
                update_progress("scraping", f"🌐 Scraping data from {url[:50]}...")
            
            # Use the new flexible scraping function with progress callback
            try:
                scraped_data = await flexible_scrape(url, question, update_progress_callback=update_progress)
            except Exception as scrape_error:
                print(f"❌ Scraping failed: {scrape_error}")
                update_progress("error", "❌ Failed to scrape website", completed=True)
                return {
                    "response": f"Failed to scrape website: {str(scrape_error)}",
                    "request_type": classification.request_type,
                    "success": False
                }
            
            update_progress("finalizing", "📋 Formatting extracted data...")
            
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
            page_info = ""
            page_range = extract_page_range(question)
            if page_range:
                start, end = page_range
                page_info = f" (Pages {start}-{end})"
            
            response_text = f"**Scraped from:** {url}{page_info}\n\n**Summary:** {scraped_data.text}"
            if scraped_data.data_found:
                response_text += f"\n\n**Extracted Data:**\n{scraped_data.data_found}"
            
            # Mark as completed
            update_progress("completed", "✅ Scraping complete!", completed=True)
            
            return {
                "response": response_text,
                "request_type": classification.request_type,
                "success": True
            }
            
        else:
            print(f"❌ Unknown request type: {classification.request_type}")
            update_progress("error", "❌ Unknown request type", completed=True)
            return {
                "response": "Sorry, I couldn't understand your request type.",
                "request_type": "unknown",
                "success": False
            }
            
    except Exception as e:
        print(f"❌ Error in workflow: {e}")
        update_progress("error", f"❌ Error: {str(e)}", completed=True)
        return {
            "response": f"An error occurred: {str(e)}",
            "request_type": "error",
            "success": False
        }

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

async def main():
    """Main function to demonstrate the session-enabled workflow"""
    
    # Run demo first
    #await demo_session_functionality()
    
    print("\n" + "🔄" * 20 + "\n")
    
    # Start interactive mode
    await interactive_agent_with_session()

if __name__ == "__main__":
    asyncio.run(main())