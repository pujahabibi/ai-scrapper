from agents import Agent, InputGuardrail, GuardrailFunctionOutput, Runner, OpenAIResponsesModel, ModelSettings, SQLiteSession
from agents.exceptions import InputGuardrailTripwireTriggered
from pydantic import BaseModel, Field
from typing import List, Dict, Any
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
    raise ValueError("❌ OpenAI API key not found! Please set OAI_API_KEY environment variable")

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

class SearchResult(BaseModel):
    extracted_data: Dict[str, Any] = Field(description="The specific data extracted based on user request")
    source_url: str = Field(description="The URL where this data was found")
    summary: str = Field(description="Brief summary of what was found on this page")

class ScrapeResult(BaseModel):
    text: str
    results: str = ""  # Keep as string for agent compatibility, parse as JSON later

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

# Simple context extraction for scraped data follow-up questions
async def get_scraped_data_context(session: SQLiteSession) -> str:
    """Extract previous scraped data from conversation history for follow-up questions"""
    try:
        # Get recent conversation history using the correct method
        items = await session.get_items()
        if not items:
            return "No previous scraped data found in conversation history."
            
        print(f"✅ Retrieved {len(items)} conversation items")
        
        # Look for assistant responses containing scraped data
        for item in reversed(items):  # Check most recent first
            # Handle different item formats from the agents SDK
            content = ""
            role = ""
            
            if isinstance(item, dict):
                role = item.get('role', '')
                
                # Handle the complex content structure from agents framework
                item_content = item.get('content', '')
                if isinstance(item_content, list) and len(item_content) > 0:
                    # Extract text from the first content item
                    first_content = item_content[0]
                    if isinstance(first_content, dict):
                        content = first_content.get('text', '')
                elif isinstance(item_content, str):
                    content = item_content
            elif hasattr(item, 'content') and hasattr(item, 'role'):
                content = str(item.content)
                role = item.role
            else:
                continue
                
            # Look for assistant messages with scraped data
            if role == 'assistant' and '**Extracted Data:**' in content:
                print(f"✅ Found scraped data in assistant message")
                
                # Extract the JSON part after "**Extracted Data:**"
                try:
                    # Find the start of the JSON data
                    json_start = content.find('**Extracted Data:**')
                    if json_start == -1:
                        continue
                        
                    # Get everything after the "**Extracted Data:**" marker
                    json_section = content[json_start + len('**Extracted Data:**'):].strip()
                    
                    # Find the JSON array (starts with [ and ends with ])
                    bracket_start = json_section.find('[')
                    if bracket_start == -1:
                        continue
                        
                    # Find the matching closing bracket
                    bracket_count = 0
                    json_end = -1
                    for i, char in enumerate(json_section[bracket_start:], bracket_start):
                        if char == '[':
                            bracket_count += 1
                        elif char == ']':
                            bracket_count -= 1
                            if bracket_count == 0:
                                json_end = i + 1
                                break
                    
                    if json_end == -1:
                        continue
                        
                    json_text = json_section[bracket_start:json_end]
                    
                    # Parse the JSON to extract job information
                    import json
                    scraped_results = json.loads(json_text)
                    
                    if not scraped_results:
                        continue
                        
                    print(f"✅ Successfully parsed {len(scraped_results)} result items from JSON data")
                    
                    # Extract all jobs from the new structured format
                    all_jobs = []
                    
                    for result_item in scraped_results:
                        if not isinstance(result_item, dict):
                            continue
                            
                        extracted_data = result_item.get('extracted_data', {})
                        
                        # Handle different formats in extracted_data
                        if isinstance(extracted_data, dict):
                            # Case 1: extracted_data contains a 'jobs' array
                            if 'jobs' in extracted_data and isinstance(extracted_data['jobs'], list):
                                all_jobs.extend(extracted_data['jobs'])
                            # Case 2: extracted_data is a direct job object  
                            elif 'title' in extracted_data or 'role' in extracted_data:
                                all_jobs.append(extracted_data)
                            # Case 3: extracted_data contains job fields directly
                            elif any(key in extracted_data for key in ['title', 'role', 'position', 'job', 'salary', 'location']):
                                all_jobs.append(extracted_data)
                        # Case 4: extracted_data is a list of jobs
                        elif isinstance(extracted_data, list):
                            all_jobs.extend(extracted_data)
                    
                    if not all_jobs:
                        print("⚠️ No job data found in extracted results")
                        continue
                        
                    print(f"✅ Extracted {len(all_jobs)} individual jobs for context")
                    
                    # Create structured context with full job data for salary analysis
                    context = "PREVIOUS SCRAPED JOB DATA:\n\n"
                    context += f"Found {len(all_jobs)} job listings with the following details:\n\n"
                    
                    for i, job in enumerate(all_jobs, 1):
                        # Handle different possible field names
                        title = job.get('title') or job.get('role') or job.get('position') or 'Unknown Position'
                        location = job.get('location') or job.get('place') or 'Unknown Location'
                        salary = job.get('salary') or job.get('payRate') or job.get('pay') or job.get('wage') or 'Not specified'
                        company = job.get('company') or job.get('employer') or job.get('organization') or 'Unknown Company'
                        job_id = job.get('jobId') or job.get('jobNumber') or job.get('id') or ''
                        work_type = job.get('workType') or job.get('type') or job.get('employment_type') or ''
                        
                        context += f"{i}. {title}\n"
                        context += f"   Location: {location}\n"
                        context += f"   Salary: {salary}\n"
                        if company != 'Unknown Company':
                            context += f"   Company: {company}\n"
                        if work_type:
                            context += f"   Type: {work_type}\n"
                        if job_id:
                            context += f"   Job ID: {job_id}\n"
                        context += "\n"
                    
                    return context
                    
                except json.JSONDecodeError as e:
                    print(f"❌ JSON parsing failed: {e}")
                    continue
                except Exception as parse_error:
                    print(f"❌ Error parsing scraped data: {parse_error}")
                    continue
        
        return "No previous scraped data found in conversation history."
        
    except Exception as e:
        print(f"⚠️ Error getting scraped data context: {e}")
        return "Unable to retrieve previous scraped data context."

# Agent 1: Request Classifier - Determines if user wants regular Q&A or web scraping
request_classifier_agent = Agent(
    name="Request Classifier",
    instructions="""You are a request classifier. Analyze the user input and determine if they are asking:

    1. REGULAR QUESTION: General questions, math problems, explanations, advice, follow-up questions, etc.
       - Examples: "What is the capital of France?", "How do I cook pasta?", "Explain photosynthesis"
       - Follow-up questions: "What about Italy?", "Tell me more", "Can you explain that better?", "Summarize the content of the website"
       - Questions about previously scraped data: "Which job has the highest salary?", "Tell me more about the first job", "How many jobs were found?"
       
    2. SCRAPE DATA: Requests to extract data from websites or URLs
       - Examples: "Scrape data from https://example.com", "Extract information from this website: [URL]", 
         "Get me the content from [URL]", "What's on this page: [URL]"

    CLASSIFICATION RULES:
    - If the input contains a URL (http/https) AND asks to extract/scrape/get data, classify as "scrape_data"
    - If the input mentions scraping, extracting, or getting data from a website, classify as "scrape_data"
    - Everything else is "regular_question" (including follow-up questions about previously scraped data)
    
    Extract the URL if present and the core question/request.""",
    output_type=RequestClassification,
    model="gpt-4.1-mini",
)

# Agent 2: Regular Q&A Agent - Handles normal questions
regular_qa_agent = Agent(
    name="Regular Q&A Assistant",
    instructions="""You are a helpful assistant that answers questions clearly and accurately. 

    CONTEXT AWARENESS:
    - You have access to conversation history including any previously scraped data
    - When users ask follow-up questions about scraped data, reference the specific data to provide accurate answers
    - For questions like "which job has the highest salary" or "tell me about the first job", use the scraped data context
    
    RESPONSE GUIDELINES:
    - Be conversational and provide comprehensive answers
    - When referencing scraped data, be specific about the details (job titles, salaries, locations, etc.)
    - If asked about comparisons (highest/lowest salary, best location, etc.), analyze the data and provide clear answers
    - Include relevant details from the scraped data to support your answers
    
    For follow-up questions about scraped data, make sure to reference the actual data that was previously extracted.""",
    output_type=RegularAnswer,
    model="gpt-4.1-mini",
    model_settings=ModelSettings(
        max_tokens=20000,
        temperature=0.3,
    ),
)

# Agent 3: Content Analyzer Agent - Collects relevant links for detailed extraction
content_analyzer_agent = Agent(
    name="Content Analyzer",
    instructions="""You are a highly skilled content analyzer specializing in INTELLIGENT LINK COLLECTION from websites.

CRITICAL REQUIREMENTS FOR INTELLIGENT LINK COLLECTION:
1. ANALYZE USER INTENT - Understand exactly what type of information the user is requesting
2. SELECTIVE LINK COLLECTION - Only collect links that contain the MOST RELEVANT information for the user's specific request
3. AVOID IRRELEVANT LINKS - Do not collect links that don't match the user's intent
4. QUALITY OVER QUANTITY - Better to have fewer highly relevant links than many irrelevant ones
5. CONTEXT-AWARE FILTERING - Consider the user's question context when selecting links

INTELLIGENT ANALYSIS PROCESS:
1. FIRST: Analyze the user's request to understand their intent:
   - What specific type of information are they seeking?
   - What type of links would contain that information?
   - What type of links should be AVOIDED?

2. SECOND: Examine the HTML content with the user's intent in mind
3. THIRD: Collect ONLY the links that are most relevant to their specific request

LINK RELEVANCE MATCHING:
Based on the user's request, collect links that match their intent:

FOR JOB-RELATED REQUESTS:
- If user asks for job details, salaries, positions, roles → Collect job detail page links
- If user asks for company info, employers, organizations → Collect company/employer profile links
- If user asks for contact info → Collect contact/about page links

FOR MEDICAL/HEALTHCARE REQUESTS:
- If user asks for doctor details, specialties, credentials → Collect doctor profile links
- If user asks for hospital/clinic info → Collect facility information links
- If user asks for services/treatments → Collect service detail links

FOR DIRECTORY/LISTING REQUESTS:
- If user asks for member details → Collect individual member profile links
- If user asks for organization info → Collect organization detail links

CRITICAL FILTERING RULES:
- If user asks for JOB DETAILS: Do NOT collect doctor profiles, company general pages, or unrelated content
- If user asks for DOCTOR INFO: Do NOT collect job listings, employment pages, or unrelated content  
- If user asks for COMPANY INFO: Do NOT collect individual job postings or employee profiles
- Always match the link type to the user's specific information need

LINK COLLECTION CRITERIA:
Only collect links that lead to:
- Pages containing the EXACT type of information the user requested
- Detail pages that match the user's intent (job details, doctor profiles, company info, etc.)
- Pages that would directly answer the user's specific question
- Official sources relevant to the user's request type

INTELLIGENT LINK COLLECTION PROCESS:
1. ANALYZE USER REQUEST: Read the user's question carefully to understand their specific intent
   - What exact information do they want? (job details, doctor info, company data, etc.)
   - What would be the best source for this information?

2. FILTER RELEVANT LINK TYPES: Based on user intent, look for:
   - Links with anchor text matching the user's request
   - Links leading to pages that would contain the requested information type
   - Detail pages, profile pages, or information pages relevant to the user's question

3. AVOID IRRELEVANT LINKS: Skip links that:
   - Don't match the user's specific request type
   - Lead to general pages when user wants specific details
   - Lead to different information types than requested

CONTEXT-AWARE LINK PATTERNS:

FOR JOB DETAIL REQUESTS:
- Individual job posting links (containing job IDs, titles, or "apply" links)
- Job detail pages with salary, requirements, and descriptions
- Links like "/jobs/[id]", "/position/[title]", "/apply/[job]"

FOR COMPANY/EMPLOYER REQUESTS:  
- Company profile pages, about pages, company directories
- Employer information pages, organization details
- Links like "/company/[name]", "/about", "/organization/[id]"

FOR PROFESSIONAL DIRECTORY REQUESTS (doctors, lawyers, etc.):
- Individual professional profile pages
- Specialty/service detail pages for professionals
- Links like "/doctor/[name]", "/physician/[id]", "/profile/[professional]"

INTELLIGENT EXTRACTION STRATEGY:
1. READ USER QUESTION to determine their exact information need
2. IDENTIFY PAGE TYPE that would contain this information
3. SCAN HTML for links leading to those specific page types
4. COLLECT only links that match the user's intent
5. IGNORE links that don't serve the user's specific purpose

QUALITY CONTROL:
- If user asks for job details, don't collect company general pages
- If user asks for doctor info, don't collect job listings  
- If user asks for contact info, focus on contact/about pages only
- For items without relevant links, include "-" to maintain count

IMPORTANT: Your goal is to be SELECTIVE and collect only the MOST RELEVANT links that directly serve the user's specific information request. Quality and relevance matter more than quantity.

Return a summary explaining what type of links were collected and why they match the user's request, with all selected links formatted as a JSON string array in the "results" field.""",
    output_type=ScrapeResult,
    model="gpt-4.1-mini",
    model_settings=ModelSettings(
        max_tokens=32000,
        temperature=0,
    ),
)

# ─── OpenAI Search Function for Link Processing ────────────────────────────────

async def search_single_link_with_openai(link: str, user_question: str, index: int, total_links: int) -> Dict:
    """
    Search a single link using OpenAI's search API
    """
    # Skip links marked as "-" (no website available)
    if link == "-":
        print(f"⏭️  Skipping link {index}/{total_links}: No website available")
        return {
            "extracted_data": {},
            "source_url": "-",
            "summary": "No website available for this club"
        }
    
    try:
        print(f"🔍 Searching link {index}/{total_links}: {link}")
        
        # Create a focused search prompt that extracts REAL data from the website
        search_prompt = f"""CRITICAL: You must extract REAL, ACTUAL data from this specific website: {link}

USER REQUEST: {user_question}

STRICT EXTRACTION REQUIREMENTS:
1. ACCESS THE ACTUAL WEBSITE CONTENT at {link}
2. Extract REAL data - NO dummy examples, NO placeholders, NO generic samples
3. Use the EXACT text, numbers, and details found on the actual webpage
4. If you cannot access real data from the site, return empty extracted_data object
5. DO NOT generate example data like "Job Role 1", "Pay details 1", "Location 1"

REAL DATA EXTRACTION RULES:
- Extract ACTUAL job titles, company names, salary figures, locations from the webpage
- Use REAL contact information (emails, phone numbers, addresses) if present
- Copy EXACT product names, prices, descriptions from the site
- Preserve ACTUAL dates, reference numbers, and specific details
- Use the PRECISE wording and formatting from the original webpage

RESPONSE FORMAT:
Return your response as a valid JSON object with this exact structure:
{{
    "extracted_data": {{
        // REAL data fields with ACTUAL values from the website
        // For jobs: actual "title", "location", "salary", "company", "jobId"
        // For contacts: actual "name", "email", "phone", "address"  
        // For products: actual "name", "price", "description", "sku"
    }},
    "source_url": "{link}",
    "summary": "Brief description of the REAL information found on this specific webpage"
}}

CRITICAL WARNINGS:
- DO NOT use placeholder text like "Job Role 1", "Details 1", "Location A"
- DO NOT generate sample data - only extract what actually exists on the page
- If the page is inaccessible or contains no relevant data, return empty extracted_data
- The user wants REAL scraped data, not examples or templates"""
        
        # Use OpenAI search API with structured output requirement
        completion = client.chat.completions.create(
            model="gpt-4o-mini-search-preview",
            web_search_options={"search_context_size": "high"},
            messages=[
                {
                    "role": "user",
                    "content": search_prompt,
                }
            ]
        )
        
        response_content = completion.choices[0].message.content
        
        # Parse the structured JSON response
        try:
            import json
            import re
            
            # First, try to parse the entire response as JSON
            try:
                result_data = json.loads(response_content)
            except json.JSONDecodeError:
                # If that fails, look for JSON object in the response
                json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response_content, re.DOTALL)
                if json_match:
                    result_data = json.loads(json_match.group())
                else:
                    # Fallback: create structured data from response
                    result_data = {
                        "extracted_data": {"content": response_content},
                        "source_url": link,
                        "summary": "Data extracted but not in expected JSON format"
                    }
            
            # Validate the expected structure
            if "extracted_data" in result_data and "source_url" in result_data and "summary" in result_data:
                print(f"✅ Successfully extracted structured data from: {link}")
                return result_data
            else:
                # Fallback structure if format is incorrect
                print(f"⚠️ Extracted data with format issues from: {link}")
                return {
                    "extracted_data": result_data.get("extracted_data", result_data),
                    "source_url": link,
                    "summary": result_data.get("summary", "Data extracted but format was incorrect")
                }
                
        except (json.JSONDecodeError, Exception) as e:
            print(f"❌ JSON parsing error for {link}: {e}")
            return {
                "extracted_data": {"raw_content": response_content[:500]},
                "source_url": link,
                "summary": f"Failed to parse response as JSON: {str(e)}"
            }
            
    except Exception as e:
        print(f"❌ Error searching {link}: {e}")
        return {
            "extracted_data": {},
            "source_url": link,
            "summary": f"Error accessing page: {str(e)}"
        }

async def search_links_with_openai(links: List[str], user_question: str, update_progress_callback=None) -> List[Dict]:
    """
    Use OpenAI's search API to extract specific information from a list of links using parallel processing
    """
    total_links = len(links)
    print(f"🚀 Starting parallel processing of {total_links} links...")
    
    if update_progress_callback:
        update_progress_callback("searching", f"🚀 Starting parallel search of {total_links} links...")
    
    # Create tasks for parallel processing
    tasks = []
    for i, link in enumerate(links, 1):
        task = search_single_link_with_openai(link, user_question, i, total_links)
        tasks.append(task)
    
    # Execute all tasks in parallel with progress updates
    print(f"⚡ Processing {len(tasks)} links in parallel...")
    
    # Use asyncio.gather to run all searches concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Handle any exceptions that occurred during parallel processing
    processed_results = []
    successful_results = 0
    
    for i, result in enumerate(results, 1):
        if isinstance(result, Exception):
            print(f"❌ Exception in link {i}: {result}")
            processed_results.append({
                "extracted_data": {},
                "source_url": links[i-1] if i <= len(links) else "unknown",
                "summary": f"Exception occurred during processing: {str(result)}"
            })
        else:
            processed_results.append(result)
            if result.get("extracted_data"):
                successful_results += 1
    
    print(f"🏁 Parallel processing completed: {successful_results}/{total_links} links successful")
    
    if update_progress_callback:
        update_progress_callback("searching", f"✅ Parallel search completed: {successful_results}/{total_links} successful")
    
    return processed_results

# ─── Multi-page Web Scraping Functions ────────────────────────────────────────

async def scrape_data_bs(url: str, question: str, update_progress_callback=None) -> ScrapeResult:
    """Enhanced scraping with link collection and OpenAI search workflow"""
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; MyScraper/1.0; +https://yourdomain.com/bot)"
    }

    # Step 1: Fetch website content
    html = None
    try:
        print(f"🌐 Fetching content from: {url}")
        if update_progress_callback:
            update_progress_callback("fetching", f"🌐 Fetching content from: {url[:50]}...")
            
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()  # throws if status != 200
        html = response.text
        print(f"✅ Successfully fetched with requests (length: {len(html)})")
    except Exception as e:
        print(f"❌ Request failed: {e}. Trying with Selenium...")
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from webdriver_manager.chrome import ChromeDriverManager
            from selenium.webdriver.chrome.service import Service
            
            print("🔧 Setting up Chrome with WebDriver Manager for automatic version matching...")
            
            # Configure Chrome options with robust compatibility settings
            chrome_options = Options()
            
            # Essential options for server/Docker environment
            chrome_options.add_argument("--headless")  # Required for server environments
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--disable-software-rasterizer")
            
            # Window and display options
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("--start-maximized")
            
            # Stability and compatibility options
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_argument("--disable-extensions")
            chrome_options.add_argument("--disable-plugins")
            chrome_options.add_argument("--disable-web-security")
            chrome_options.add_argument("--disable-features=VizDisplayCompositor")
            chrome_options.add_argument("--disable-dev-tools")
            chrome_options.add_argument("--no-first-run")
            chrome_options.add_argument("--no-default-browser-check")
            chrome_options.add_argument("--ignore-certificate-errors")
            chrome_options.add_argument("--ignore-ssl-errors")
            
            # User agent to avoid blocking
            chrome_options.add_argument("--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36")
            
            # Try to initialize Chrome with WebDriver Manager for automatic version matching
            driver = None
            try:
                # WebDriver Manager automatically downloads and manages the correct ChromeDriver version
                service = Service(ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service, options=chrome_options)
                print("✅ Chrome initialized with WebDriver Manager (automatic version matching)")
            except Exception as driver_error:
                print(f"❌ WebDriver Manager failed: {driver_error}")
                print("🔄 Trying fallback with system ChromeDriver...")
                try:
                    # Fallback to system ChromeDriver with minimal options
                    minimal_options = Options()
                    minimal_options.add_argument("--headless")
                    minimal_options.add_argument("--no-sandbox")
                    minimal_options.add_argument("--disable-dev-shm-usage")
                    minimal_options.add_argument("--disable-gpu")
                    driver = webdriver.Chrome(options=minimal_options)
                    print("✅ Chrome initialized with system ChromeDriver (fallback)")
                except Exception as fallback_error:
                    print(f"❌ System ChromeDriver also failed: {fallback_error}")
                    raise Exception(f"All ChromeDriver methods failed: {driver_error}, {fallback_error}")
            if driver:
                driver.get(url)
                html = driver.page_source
                driver.quit()
                print(f"✅ Successfully fetched with Selenium (length: {len(html)})")
            else:
                raise Exception("Failed to initialize Chrome driver")
        except Exception as selenium_error:
            print(f"❌ Selenium also failed: {selenium_error}")
            return ScrapeResult(
                text="Failed to scrape the website - both requests and Selenium failed",
                results="[]"
            )
    
    if not html:
        return ScrapeResult(
            text="Failed to fetch website content",
            results="[]"
        )
    
    # Step 2: Analyze content to collect relevant links
    if update_progress_callback:
        update_progress_callback("analyzing", "🔍 Analyzing content for relevant links...")
        
    analysis_prompt = f"""
    User Request: {question}
    Website URL: {url}
    Website Content: {html}
    
    INTELLIGENT LINK SELECTION ANALYSIS:
    
    STEP 1 - ANALYZE USER INTENT:
    First, analyze what the user is specifically asking for in their request: "{question}"
    
    Determine:
    - What TYPE of information do they want? (job details, doctor profiles, company info, contact details, etc.)
    - What KIND of links would contain this specific information?
    - What links should be AVOIDED because they don't match the user's intent?
    
    STEP 2 - INTELLIGENT LINK FILTERING:
    Based on the user's intent, apply these selection rules:
    
    IF USER ASKS FOR JOB DETAILS/POSITIONS/SALARIES/ROLES:
    - COLLECT: Individual job posting links, job detail pages, position-specific URLs
    - COLLECT: Links with job IDs, position titles, salary information, job descriptions
    - AVOID: Company general pages, employer profiles, contact pages, doctor listings
    
    IF USER ASKS FOR COMPANY/EMPLOYER/ORGANIZATION INFO:
    - COLLECT: Company profile pages, about pages, organization details, employer information
    - COLLECT: Links to company websites, organizational structure, business information
    - AVOID: Individual job postings, employee profiles, unrelated listings
    
    IF USER ASKS FOR DOCTOR/PHYSICIAN/MEDICAL PROFESSIONAL INFO:
    - COLLECT: Doctor profile pages, physician directories, medical professional details
    - COLLECT: Links with specialties, credentials, medical practice information
    - AVOID: Job listings, company pages, non-medical content
    
    IF USER ASKS FOR CONTACT INFORMATION:
    - COLLECT: Contact pages, about pages, directory listings with contact details
    - COLLECT: Links that lead to phone numbers, emails, addresses
    - AVOID: Job postings, detailed product pages, unrelated content
    
    IF USER ASKS FOR MEMBER/CLUB DIRECTORIES:
    - COLLECT: Individual member/club profile pages, organization websites
    - COLLECT: Links to specific clubs, member details, organizational information
    - Include "-" for members/clubs without website links to maintain count
    
    STEP 3 - SELECTIVE LINK COLLECTION:
    Only collect links that DIRECTLY serve the user's specific information need:
    - Scan HTML content for links matching the identified intent
    - Focus on links with relevant anchor text, URLs, or context
    - Prioritize links that would contain the exact information requested
    - Skip links that don't match the user's specific request type
    
    QUALITY CONTROL:
    - If user wants job details, don't collect general company pages
    - If user wants company info, don't collect individual job postings  
    - If user wants doctor info, don't collect job or company listings
    - Always match link selection to user's SPECIFIC information need
    
    IMPORTANT: Be SELECTIVE and intelligent. Collect only the MOST RELEVANT links that directly answer the user's specific question. Quality and relevance are more important than quantity.
    
    Return a summary explaining what type of links were selected based on the user's intent, and format the selected links as a JSON string array in the "results" field.
    """
    
    # Create a session for the analysis
    temp_session = SQLiteSession("analysis_session", "analysis_temp.db")
    
    # Run the content analyzer
    analysis_result = await Runner.run(
        content_analyzer_agent,
        analysis_prompt,
        session=temp_session
    )
    
    try:
        analysis_data = analysis_result.final_output_as(ScrapeResult)
        print(f"🔍 Link collection analysis: {analysis_data.text[:200]}...")
        
        # Extract collected links from the results field
        results_text = str(analysis_data.results) if analysis_data.results else ""
        
    except Exception as analysis_error:
        print(f"⚠️ Analysis parsing error: {analysis_error}")
        # Create a fallback result
        analysis_data = ScrapeResult(
            text="Failed to parse analysis result - using fallback",
            results="[]"
        )
        results_text = ""
        
    # Step 3: Extract links from the analysis results
    print("📋 Proceeding to link-based extraction using OpenAI search...")
    
    links = []
    import re
    from urllib.parse import urljoin, urlparse
    
    # Get base URL for converting relative links to absolute
    parsed_url = urlparse(url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
    
    # Try to parse links from JSON results first
    try:
        import json
        if analysis_data.results and analysis_data.results != "[]":
            parsed_links = json.loads(analysis_data.results)
            if isinstance(parsed_links, list):
                for link in parsed_links:
                    if isinstance(link, str):
                        if link == '-':
                            links.append(link)  # Keep "-" placeholders
                        elif link.startswith('http'):
                            links.append(link)  # Already absolute URL
                        elif link.startswith('/'):
                            # Convert relative URL to absolute
                            full_url = urljoin(base_url, link)
                            links.append(full_url)
    except json.JSONDecodeError:
        pass
    
    # CRITICAL: Extract URLs from HTML directly as fallback (for medrecruit-style job links)
    if not links or len(links) < 5:  # If we found few links, try direct HTML extraction
        print("🔍 Few links found from analysis, trying direct HTML extraction...")
        
        # Look specifically for job detail links in the HTML
        job_link_patterns = [
            r'href="(/jobs/[^"]+)"',  # Relative job links like /jobs/registrar/...
            r'href="(https?://[^"]*jobs[^"]*)"',  # Absolute job links
        ]
        
        for pattern in job_link_patterns:
            matches = re.findall(pattern, html, re.IGNORECASE)
            for match in matches:
                if match.startswith('/'):
                    # Convert relative to absolute
                    full_url = urljoin(base_url, match)
                    if full_url not in links:
                        links.append(full_url)
                elif match.startswith('http') and match not in links:
                    links.append(match)
        
        print(f"🔍 Direct HTML extraction found {len(links)} additional job links")
    
    # Also extract URLs from text fields as additional fallback
    combined_text = f"{analysis_data.text} {results_text}"
    url_pattern = r'https?://[^\s<>"]{2,}'
    found_urls = re.findall(url_pattern, combined_text)
    
    # Clean and deduplicate URLs
    for url_found in found_urls:
        clean_url = url_found.rstrip('.,;:')  # Remove trailing punctuation
        if clean_url not in links and len(clean_url) > 10:
            links.append(clean_url)
    
    # Process all found links without limiting
    print(f"🔗 Processing all {len(links)} links found (no limit applied)")
    
    if not links:
        return ScrapeResult(
            text=f"No relevant links found for: {question}. The page may not contain links to detailed information.",
            results="[]"
        )
    
    print(f"🔗 Found {len(links)} links to search")
    
    # Step 4: Search through links using OpenAI
    if update_progress_callback:
        update_progress_callback("searching", f"🔍 Searching {len(links)} links with OpenAI...")
        
    search_results = await search_links_with_openai(links, question, update_progress_callback)
    
    # Step 5: Combine and format the search results
    combined_results = []
    successful_results = 0
    
    for result in search_results:
        # Check for successful extraction based on new format
        if result.get("extracted_data") and result["extracted_data"]:  # Non-empty extracted_data
            # Use the structured format directly
            combined_results.append(result)
            successful_results += 1
        elif result.get("summary"):  # Even if no data, include the summary for completeness
            combined_results.append(result)
    
    if combined_results:
        import json
        return ScrapeResult(
            text=f"Successfully searched {len(links)} links and found relevant information in {successful_results} of them related to: {question}",
            results=json.dumps(combined_results)
        )
    else:
        return ScrapeResult(
            text=f"Searched {len(links)} links but no relevant information found for: {question}",
            results="[]"
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
        per_page_outputs.append(await scrape_data_bs(u, question, update_progress_callback))

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
    Takes multiple ScrapeResult objects and combines them into one ScrapeResult.
    """
    print(f"🔄 Combining results from {len(scrape_results)} pages...")
    
    # Debug: Show what data we're starting with
    for i, sr in enumerate(scrape_results, 1):
        print(f"📄 Page {i} summary: {sr.text[:100]}...")
        if sr.results and sr.results != "[]":
            try:
                import json
                parsed = json.loads(sr.results)
                print(f"📊 Page {i} has {len(parsed)} items")
                # Show first item as sample
                if parsed and len(parsed) > 0:
                    first_item = parsed[0]
                    if isinstance(first_item, dict):
                        sample_data = first_item.get("extracted_data", first_item)
                        print(f"📋 Page {i} sample: {str(sample_data)[:200]}...")
            except:
                print(f"⚠️ Page {i} results parsing failed")
    
    # Directly combine the results without using content analyzer (which might be generating dummy data)
    combined_text_parts = []
    combined_results_parts = []
    
    for sr in scrape_results:
        combined_text_parts.append(sr.text)
        if sr.results and sr.results != "[]":
            try:
                import json
                parsed_results = json.loads(sr.results)
                if isinstance(parsed_results, list):
                    # Add all results directly - don't process through content analyzer
                    combined_results_parts.extend(parsed_results)
                else:
                    combined_results_parts.append(parsed_results)
            except json.JSONDecodeError as e:
                print(f"❌ JSON parsing error in combine_results: {e}")
                # If parsing fails, treat as raw text
                combined_results_parts.append({"extracted_data": {"content": sr.results}, "source_url": "unknown", "summary": "Raw data from parsing error"})
    
    print(f"🎯 Direct combination completed: {len(combined_results_parts)} total items")
    
    # Return combined results directly without using content analyzer agent
    import json
    return ScrapeResult(
        text=f"Combined {len(combined_results_parts)} items from {len(scrape_results)} pages",
        results=json.dumps(combined_results_parts)
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
            
            # Get scraped data context for follow-up questions
            scraped_context = await get_scraped_data_context(session)
            
            # Enhanced prompt with scraped data context
            qa_prompt = f"""
            User Question: {user_input}
            
            {scraped_context}
            
            Please answer the user's question. If it relates to previously scraped data shown above, use that information to provide a specific, detailed answer.
            """
            
            # Handle regular question with session memory and scraped data context
            qa_result = await Runner.run(
                regular_qa_agent, 
                qa_prompt,
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
            
            if scraped_data.results and scraped_data.results != "[]":
                try:
                    import json
                    parsed_results = json.loads(scraped_data.results)
                    print(f"\nExtracted Results: {len(parsed_results)} items")
                    for i, item in enumerate(parsed_results[:3], 1):  # Show first 3 items
                        print(f"  {i}. {str(item)[:100]}...")
                except json.JSONDecodeError as e:
                    print(f"❌ JSON decode error: {e}")
                    print(f"\nExtracted Results: Raw data")
                    print(f"  {scraped_data.results[:200]}...")
            else:
                print("\nNo specific data extracted.")
            
            print("=" * 60)
            
            # Format response for API in the requested JSON structure
            page_info = ""
            page_range = extract_page_range(question)
            if page_range:
                start, end = page_range
                page_info = f" (Pages {start}-{end})"
            
            # Format response for API (maintain consistent format with regular questions)
            response_text = f"**Scraped from:** {url}{page_info}\n\n**Summary:** {scraped_data.text}"
            if scraped_data.results and scraped_data.results != "[]":
                try:
                    import json
                    parsed_results = json.loads(scraped_data.results)
                    response_text += f"\n\n**Extracted Data:**\n{json.dumps(parsed_results, indent=2)}"
                    print(f"✅ Successfully parsed {len(parsed_results)} results from {url}")
                except json.JSONDecodeError as e:
                    print(f"❌ JSON decode error: {e}")
                    response_text += f"\n\n**Extracted Data:**\n{scraped_data.results}"
            
            # Store the scraped response in the session for future reference
            await session.add_items([
                {"role": "assistant", "content": response_text}
            ])
            print("✅ Stored scraped data in session for future reference")
            
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