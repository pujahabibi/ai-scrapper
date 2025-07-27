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
    data_found: str = ""  # Simplified to avoid schema issues

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

# Web Scraping Function - Uses direct OpenAI client
async def web_scraping_function(user_request: str, url: str, website_content: str) -> ScrapeResult:
    """Web scraping function using direct OpenAI client"""
    
    system_prompt = """You are a web scraping specialist.  Your task is to extract the data from scrape website, and return the data in a structured format based on the user's question or request. 
    ALL relevant information based on the user's request - not just the first few items.

    IMPORTANT EXTRACTION RULES:
    1. Extract ALL relevant data from the entire content, not just the beginning
    2. If the user asks for a list, extract ALL items in that list
    3. If the user asks for data extraction, be comprehensive and thorough
    4. Scan through the ENTIRE content provided to find all matching information
    5. Don't limit yourself to the first 5-10 items - extract everything relevant
    6. Do not take the html tags into account, just the text content
    
    RESPONSE FORMAT:
    You must respond with a JSON object containing exactly these two fields:
    - "text": Provide a comprehensive summary of what you found and how much data was extracted
    - "data_found": Extract ALL relevant data in a well-formatted, structured way
    
    Be thorough and comprehensive in your extraction. The user expects ALL matching data, not a sample."""
    
    user_prompt = f"""
    User Request: {user_request}
    Website URL: {url}
    Website Content: {website_content}
    
    Please analyze this website content and extract ALL relevant information based on the user's request.
    Return your response as a JSON object with "text" and "data_found" fields.
    Clean the data_found from the html tags like <p> and </p> and other html tags.
    """
    
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.1,
        max_tokens=26000,
    )
    
    try:
        # Parse the response as JSON
        response_content = response.choices[0].message.content
        result_data = json.loads(response_content)
        
        # Ensure data_found is a string
        data_found = result_data.get("data_found", "")
        if isinstance(data_found, dict):
            data_found = json.dumps(data_found, indent=2)
        elif not isinstance(data_found, str):
            data_found = str(data_found)
        
        return ScrapeResult(
            text=result_data.get("text", ""),
            data_found=data_found
        )
    except json.JSONDecodeError:
        # Fallback if JSON parsing fails
        response_content = response.choices[0].message.content
        return ScrapeResult(
            text="Successfully extracted data from the website",
            data_found=response_content
        )

# Helper function to scrape website content
def scrape_website_content(url: str) -> str:
    """Scrape and clean website content"""
    try:
        print(f"🌐 Fetching content from: {url}")
        
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; DataExtractor/1.0)"
        }
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        clean_text = response.text
        return clean_text
        
    except Exception as e:
        error_msg = f"Error scraping {url}: {str(e)}"
        print(f"❌ {error_msg}")
        return error_msg

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
            
            # Step 4: Scrape website content
            update_progress("scraping", f"🌐 Scraping data from {url[:50]}...")
            website_content = scrape_website_content(url)
            
            if website_content.startswith("Error"):
                update_progress("error", "❌ Failed to scrape website", completed=True)
                return {
                    "response": f"Failed to scrape website: {website_content}",
                    "request_type": classification.request_type,
                    "success": False
                }
            
            # Step 5: Process scraped content with AI
            update_progress("analyzing", "🧠 Analyzing scraped content with AI...")
            
            # Use the direct OpenAI client function
            scraped_data = await web_scraping_function(question, url, website_content)
            
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
            response_text = f"**Scraped from:** {url}\n\n**Summary:** {scraped_data.text}"
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