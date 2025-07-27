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
    result: List[Dict] = []  # Updated to match the new structure

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

# ─── Multi-page Web Scraping Functions ────────────────────────────────────────

def scrape_data_bs(url: str, question: str) -> ScrapeResult:
    """Scrape a single page using BeautifulSoup with Selenium fallback"""
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; MyScraper/1.0; +https://yourdomain.com/bot)"
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # throws if status != 200
        html = response.text
    except Exception as e:
        print(f"Request failed: {e}. Trying with Selenium...")
        try:
            driver = webdriver.Chrome()
            driver.get(url)
            html = driver.page_source
            driver.quit()
        except Exception as selenium_error:
            print(f"Selenium also failed: {selenium_error}")
            return ScrapeResult(
                text="Failed to scrape the website",
                result=[]
            )
    
    system_prompt = """
    Your task is to extract the data from scrape website, and return the data in a structured format based on the user's question or request.
    If there is a content where one of users' request is not found, just return the key with value "-".
    If users give broken or invalid link, return the text that says "The link is broken or invalid" and the result is empty list.
    for example:
        {
            "text": "The text about the content of the page",
            "result": [
                {
                    "key1": "value1",
                    "key2": "-"
                }
            ]
        }
    You must return a valid JSON object with this exact structure:
    {
        "text": "Your descriptive text about what you found",
        "result": [
            {
                "key1": "value1",
                "key2": "value2"
            }
        ]
    }
    """
    
    user_prompt = f"Here is the detail instruction: {question}, here is the html: {html}"

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.2,
        max_tokens=20000,
    )
    
    # Parse the response - prioritize simple JSON parsing
    try:
        response_content = response.choices[0].message.content
        print(f"🔍 Raw response: {response_content[:200]}...")
        result_data = json.loads(response_content)
        return ScrapeResult(
            text=result_data.get("text", ""),
            result=result_data.get("result", [])
        )
    except json.JSONDecodeError as e:
        print(f"❌ JSON parsing failed: {e}")
        # Try with JsonOutputParser as fallback
        try:
            parser = JsonOutputParser(pydantic_object=ScrapeResult)
            parsed_output = parser.parse(response.choices[0].message.content)
            return parsed_output
        except Exception as parser_error:
            print(f"❌ Parser also failed: {parser_error}")
            return ScrapeResult(
                text="Failed to parse response",
                result=[]
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

def flexible_scrape(url: str, question: str, update_progress_callback=None) -> ScrapeResult:
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
        per_page_outputs.append(scrape_data_bs(u, question))

    # if only one page, just return it
    if len(per_page_outputs) == 1:
        return per_page_outputs[0]

    # otherwise, combine them into one ScrapeResult
    if update_progress_callback:
        update_progress_callback("analyzing", f"🧠 Combining data from {total_pages} pages...")
    combined = combine_results(per_page_outputs)
    return combined

def combine_results(scrape_results: List[ScrapeResult]) -> ScrapeResult:
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
    
    # Convert ScrapeResult objects to JSON strings for the prompt
    json_strings = []
    for sr in scrape_results:
        json_strings.append(json.dumps({"text": sr.text, "result": sr.result}, indent=2))
    
    joined = "\n\n".join(json_strings)
    user_prompt = f"Please merge the following JSON objects into one object, combining all result arrays and creating a comprehensive text summary:\n\n{joined}"

    resp = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.1,
        max_tokens=36000,
    )

    try:
        response_content = resp.choices[0].message.content
        result_data = json.loads(response_content)
        return ScrapeResult(
            text=result_data.get("text", ""),
            result=result_data.get("result", [])
        )
    except json.JSONDecodeError as e:
        print(f"❌ JSON parsing failed: {e}")
        # Try with JsonOutputParser as fallback
        try:
            parser = JsonOutputParser(pydantic_object=ScrapeResult)
            parsed_output = parser.parse(resp.choices[0].message.content)
            return parsed_output
        except Exception as parser_error:
            print(f"❌ Parser also failed: {parser_error}")
            return ScrapeResult(
                text="Failed to combine results",
                result=[]
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
                scraped_data = flexible_scrape(url, question, update_progress_callback=update_progress)
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
            
            if scraped_data.result:
                print(f"\nExtracted Data ({len(scraped_data.result)} items):")
                print(json.dumps(scraped_data.result, indent=2))
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
            if scraped_data.result:
                response_text += f"\n\n**Extracted Data ({len(scraped_data.result)} items):**\n"
                response_text += json.dumps(scraped_data.result, indent=2)
            
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