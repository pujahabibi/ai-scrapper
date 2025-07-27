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
                    job_data = json.loads(json_text)
                    
                    if not job_data:
                        continue
                        
                    print(f"✅ Successfully parsed {len(job_data)} jobs from JSON data")
                    
                    # Create structured context with full job data for salary analysis
                    context = "PREVIOUS SCRAPED JOB DATA:\n\n"
                    context += f"Found {len(job_data)} job listings with the following details:\n\n"
                    
                    for i, job in enumerate(job_data, 1):
                        context += f"{i}. {job.get('title', 'Unknown Position')}\n"
                        context += f"   Location: {job.get('location', 'Unknown')}\n"
                        context += f"   Salary: {job.get('payRate', 'Not specified')}\n"
                        context += f"   Type: {job.get('workType', 'Unknown')}\n"
                        if job.get('jobNumber'):
                            context += f"   Job ID: {job.get('jobNumber')}\n"
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
    instructions="""You are a highly skilled content analyzer specializing in LINK COLLECTION from websites.

CRITICAL REQUIREMENTS FOR COMPREHENSIVE LINK COLLECTION:
1. FIND ALL RELEVANT LINKS - You must find ALL links that might contain the requested information
2. SCAN THE ENTIRE CONTENT - Read through ALL content, not just the beginning
3. MULTIPLE PASSES - Look for links in different HTML structures, classes, and sections
4. NO SHORTCUTS - Do not stop until you've found every possible relevant link
5. VERIFY COMPLETENESS - Double-check that you haven't missed any links

ANALYSIS TASK:
1. Examine the provided HTML content THOROUGHLY
2. Identify ALL links that might contain the specific information requested by the user
3. Focus on finding detail pages, profile pages, individual item pages, contact pages
4. DO NOT attempt direct data extraction - focus only on link collection

LINK COLLECTION CRITERIA:
Look for links that lead to:
- Individual item details (job details, product details, member profiles)
- Contact pages or about pages
- Detail pages with more comprehensive information
- Official websites or external links
- Pages that would contain the specific data the user is requesting

WHEN COLLECTING LINKS:
- Extract ALL URLs that might contain the requested information
- Look for links in different sections: main content, sidebars, navigation, cards, lists, tables
- Include links with relevant anchor text or context
- Include both internal and external links that seem relevant
- Focus on links that would lead to pages with detailed information
- For clubs or items WITHOUT websites, include "-" as the link to maintain count
- Format all found links as a JSON string array in the "results" field

DATA IDENTIFICATION PATTERNS FOR LINK COLLECTION:
- Links within repeating patterns (job cards, member listings, product grids)
- "Read more", "View details", "Learn more", "See Details", "Apply" type links
- Profile links, detail page links, contact page links
- Official website links, external reference links
- Links with relevant anchor text matching the user's request
- JOB SPECIFIC: Individual job listing links (usually containing job IDs or titles)
- JOB SPECIFIC: Links that lead to individual job detail pages (not the main list page)

EXTRACTION STRATEGY FOR LINKS:
1. First, identify the main content area and repeating patterns
2. Scan for obvious link containers/cards/list items
3. Look for "detail" or "more info" type links within each item
4. Check navigation and sidebar areas for relevant category links
5. Look for external/official website links
6. Extract ALL relevant URLs found

IMPORTANT: Your goal is to collect ALL potentially relevant links that could contain the information the user is requesting. Do not attempt to extract data directly - focus only on finding the right links to search.

Return a summary of how many links were found and what types of pages they lead to, and format all collected links as a JSON string array in the "results" field.""",
    output_type=ScrapeResult,
    model="gpt-4.1-mini",
    model_settings=ModelSettings(
        max_tokens=32000,
        temperature=0,
    ),
)

# ─── OpenAI Search Function for Link Processing ────────────────────────────────

async def search_links_with_openai(links: List[str], user_question: str, update_progress_callback=None) -> List[Dict]:
    """
    Use OpenAI's search API to extract specific information from a list of links
    """
    results = []
    total_links = len(links)
    
    for i, link in enumerate(links, 1):
        if update_progress_callback:
            update_progress_callback("searching", f"🔍 Processing link {i}/{total_links}: {link[:50] if link != '-' else 'No website available'}...")
        
        # Skip links marked as "-" (no website available)
        if link == "-":
            print(f"⏭️  Skipping link {i}/{total_links}: No website available")
            results.append({
                "extracted_data": {},
                "source_url": "-",
                "summary": "No website available for this club"
            })
            continue
        
        try:
            print(f"🔍 Searching link {i}/{total_links}: {link}")
            
            # Create a focused search prompt that only extracts user-requested information
            search_prompt = f"""Extract ONLY the specific information requested by the user from this link: {link}

USER REQUEST: {user_question}

EXTRACTION RULES:
1. ONLY extract information that directly relates to the user's specific request
2. DO NOT extract general website information unless specifically requested
3. Focus on the exact data type the user is asking for
4. If the page doesn't contain the requested information, return empty data

RESPONSE FORMAT:
Return your response as a valid JSON object with this exact structure:
{{
    "extracted_data": {{
        // Only include fields that match the user's request
        // Use appropriate field names based on what the user is asking for
        // Example for job request: "title", "location", "salary", "company"
        // Example for contact request: "name", "email", "phone", "address"
        // Example for product request: "name", "price", "description", "specifications"
    }},
    "source_url": "{link}",
    "summary": "Brief description of what specific information was found (or not found) related to the user's request"
}}

IMPORTANT: 
- Only extract data that the user specifically requested
- Use field names that match the type of information being requested
- If no relevant information is found, return empty extracted_data object
- Be precise and focused on the user's actual request"""
            
            # Use OpenAI search API with structured output requirement
            completion = client.chat.completions.create(
                model="gpt-4o-mini-search-preview",
                web_search_options={"search_context_size": "low"},
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
                    results.append(result_data)
                    print(f"✅ Successfully extracted structured data from: {link}")
                else:
                    # Fallback structure if format is incorrect
                    results.append({
                        "extracted_data": result_data.get("extracted_data", result_data),
                        "source_url": link,
                        "summary": result_data.get("summary", "Data extracted but format was incorrect")
                    })
                    print(f"⚠️ Extracted data with format issues from: {link}")
                    
            except (json.JSONDecodeError, Exception) as e:
                print(f"❌ JSON parsing error for {link}: {e}")
                results.append({
                    "extracted_data": {"raw_content": response_content[:500]},
                    "source_url": link,
                    "summary": f"Failed to parse response as JSON: {str(e)}"
                })
                
        except Exception as e:
            print(f"❌ Error searching {link}: {e}")
            results.append({
                "extracted_data": {},
                "source_url": link,
                "summary": f"Error accessing page: {str(e)}"
            })
    
    return results

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
    
    COMPREHENSIVE LINK COLLECTION ANALYSIS:
    
    1. THOROUGH LINK SCAN: Examine EVERY section of this HTML content for relevant links
    2. COMPLETE LINK COLLECTION: Find ALL links that might contain the information requested by the user
    3. LINK IDENTIFICATION: Look in all areas - main content, sidebars, headers, footers, nested sections, cards, lists, tables
    4. STRUCTURED OUTPUT: Format all collected links as a JSON string array
    
    SPECIFIC INSTRUCTIONS FOR "{question}":
    
    PHASE 1 - LINK IDENTIFICATION:
    - Scan the ENTIRE HTML content thoroughly for relevant links
    - Look for ALL links that might lead to detailed information about the user's request
    - Check main content areas, navigation, sidebars, footers, and nested sections
    - Find EVERY link that could contain the requested data
    
    PHASE 2 - LINK COLLECTION:
    - Collect ALL links that lead to detail pages, profile pages, contact pages
    - Include links within repeating patterns (job cards, member listings, product cards)
    - Focus on "Read more", "View details", "Contact", "About" type links
    - Include official website links and external reference links
    - For clubs/items that exist but have no website link, include "-" in the array
    - Format all collected links as a JSON string array in the "results" field
    - Each link should be a separate URL string or "-" in the array
    
    LINK COLLECTION REQUIREMENTS:
    - For job listings: Collect ALL links that lead to individual job detail pages (typically 10-20 per page)
    - For job listings: Look for links in job titles, "Apply" buttons, "View Details" buttons  
    - For job listings: DO NOT include the main listing page URL - focus on individual job URLs
    - For contact information: Collect ALL links that lead to contact pages, about pages, official websites
    - For member directories: Collect ALL links that lead to individual member profiles or contact pages
    - For product listings: Collect ALL links that lead to individual product detail pages
    - For club directories: Collect ALL links to club websites, even if they're external links
    - For any structured data: Collect EVERY link that might contain detailed information
    
    SPECIAL FOCUS FOR CLUB DIRECTORIES:
- Scan the ENTIRE page for ALL club website links (look for <a href="..."> tags)
- Include ALL external club website URLs (even if they're not on the same domain)
- Look for patterns like figcaption links, image links, and text links to club websites
- For clubs that exist but have NO website link, include "-" to maintain the total count
- Do NOT limit the number of links - collect ALL clubs (with links or "-" for no link)
    
        CRITICAL REQUIREMENTS BASED ON CONTENT TYPE:
    
    FOR CLUB DIRECTORIES (like Arizona Soccer Association):
    - This page should contain approximately 73 member clubs
    - Each club may or may not have a link to their official website
    - Scan THOROUGHLY for ALL <a href="..."> tags that point to club websites
    - Look in ALL sections: main content, image captions, club listings, etc.
    - For clubs WITHOUT website links, include "-" to maintain the count of 73
    - Do NOT stop at 10 links - find ALL ~73 clubs (with links OR "-" for no link)
    
    FOR JOB LISTINGS (like medrecruit.com):
    - This page should contain 10-20 individual job listings per page
    - Each job has a detail link pattern like "/jobs/[grade]/[specialty]/[job-id]"
    - Look for <a> tags with href containing "/jobs/" or class names like "JobCard_title"
    - DO NOT include the main listing page URL - only individual job detail URLs
    - Scan for job cards, articles with data-testid="job-card", or similar containers
    - Each job listing should have its own detail page link
    
    IMPORTANT: Your goal is to find ALL potentially relevant links for the content type (expected ~73 for club directories, ~10-20 for job listings). Do not attempt direct data extraction - focus only on collecting links that can be searched later using OpenAI search API.
    
    Return a summary of how many links were collected and what types of pages they lead to, with all links formatted as a JSON string array in the "results" field.
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
    print("Combining results...")
    
    # Use the content analyzer to combine results
    combined_text_parts = []
    combined_results_parts = []
    
    for sr in scrape_results:
        combined_text_parts.append(sr.text)
        if sr.results and sr.results != "[]":
            try:
                import json
                parsed_results = json.loads(sr.results)
                if isinstance(parsed_results, list):
                    # Handle the new structured format
                    for result in parsed_results:
                        if isinstance(result, dict) and result.get("extracted_data"):
                            combined_results_parts.append(result)
                        elif isinstance(result, dict):
                            # Legacy format support
                            combined_results_parts.append(result)
                else:
                    combined_results_parts.append(parsed_results)
            except json.JSONDecodeError:
                # If parsing fails, treat as raw text
                combined_results_parts.append({"extracted_data": {"content": sr.results}, "source_url": "unknown", "summary": "Raw data from parsing error"})
    
    combination_prompt = f"""
    Please combine and consolidate the following scraped data from multiple pages:
    
    Text summaries from each page:
    {chr(10).join([f"Page {i+1}: {text}" for i, text in enumerate(combined_text_parts)])}
    
    Combined results from all pages:
    Total items to merge: {len(combined_results_parts)}
    
    Please create a comprehensive combined summary and return all the merged data in the "results" field as a JSON array.
    Each item should be a separate object in the results array.
    """
    
    # Create a simple session for the combination
    temp_session = SQLiteSession("combine_session", "combine_temp.db")
    
    # Run the content analyzer to combine results
    combine_result = await Runner.run(
        content_analyzer_agent,
        combination_prompt,
        session=temp_session
    )
    
    try:
        combined_data = combine_result.final_output_as(ScrapeResult)
        return combined_data
    except Exception as e:
        print(f"❌ Agent combination failed: {e}")
        # Return combined results directly if agent fails
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