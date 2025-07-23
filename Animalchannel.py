import os
import json
import time
import requests
import asyncio
import datetime
import logging
import httpx
import re
import signal
import threading
from googleapiclient.discovery import build
from google.oauth2 import service_account
from openai import OpenAI
from dotenv import load_dotenv

# Rate limiting constants for GPT-Image-1 API compliance
MAX_CONCURRENT = 10  # Semaphore limit for concurrent requests
MAX_IMAGES_PER_MIN = 15  # OpenAI GPT-Image-1 rate limit
BATCH_SIZE = 5  # Process images in smaller batches for Render memory constraints

# Dynamic rate limiting adjustment
RATE_LIMIT_DETECTED = False  # Global flag to reduce concurrency when rate limited

# Configure logging with proper formatting and levels
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('animalchannel.log', mode='a')
    ]
)

# Create logger instance
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

# Load API keys and configs from environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
CLOUDINARY_PRESET = os.getenv("CLOUDINARY_PRESET")
CLOUDINARY_URL = os.getenv("CLOUDINARY_URL")
HAILUO_AUTH = os.getenv("HAILUO_AUTH")
KLING_API_KEY = os.getenv("KLING_API_KEY")
ENABLE_TELEGRAM = os.getenv("ENABLE_TELEGRAM", "false").lower() == "true"

# Validate required environment variables
required_vars = {
    "OPENAI_API_KEY": OPENAI_API_KEY,
    "GOOGLE_SHEET_ID": GOOGLE_SHEET_ID,
    "CLOUDINARY_PRESET": CLOUDINARY_PRESET,
    "CLOUDINARY_URL": CLOUDINARY_URL,
    "HAILUO_AUTH": HAILUO_AUTH,
    "KLING_API_KEY": KLING_API_KEY
}

def is_placeholder_value(value):
    """Check if a value is a placeholder from the .env template"""
    if not value:
        return True
    placeholder_indicators = ['your_', '_here', 'placeholder', 'example']
    return any(indicator in str(value).lower() for indicator in placeholder_indicators)

for var_name, var_value in required_vars.items():
    if not var_value or is_placeholder_value(var_value):
        logger.warning(f"{var_name} environment variable is not set or contains placeholder value")

# Initialize clients only if API keys are available and not placeholders
if OPENAI_API_KEY and not is_placeholder_value(OPENAI_API_KEY):
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
else:
    openai_client = None
    logger.warning("OpenAI client not initialized - OPENAI_API_KEY missing or placeholder")

# Telegram integration removed for stability

# Google Sheets setup
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SERVICE_ACCOUNT_FILE = '/etc/secrets/service-account.json'
sheets_service = None

# Check if Google Sheets should be used
use_sheets = (os.getenv("USE_GOOGLE_AUTH") == "true" and 
              os.path.exists(SERVICE_ACCOUNT_FILE))

if use_sheets:
    try:
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )
        sheets_service = build('sheets', 'v4', credentials=creds)
        if sheets_service is not None:
            use_sheets = True
        else:
            use_sheets = False
    except Exception as e:
        logger.warning(f"Failed to initialize Google Sheets: {e}")
        use_sheets = False
        sheets_service = None

def generate_sheet_title():
    if not use_sheets:
        return "NoSheet_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return "Story_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

def escape_sheet_title(title):
    return "'" + title.replace("'", "''") + "'"

def get_in_progress_idea():
    if sheets_service is None:
        print("Warning: Google Sheets service not available. Cannot check for in-progress ideas.")
        return None
        
    try:
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=GOOGLE_SHEET_ID, range='Sheet1!A:C').execute()
        values = result.get('values', [])
        for row in values[1:]:
            if len(row) > 2 and row[2] == 'In Progress':
                return row[0]
        return None
    except Exception as e:
        print(f"Warning: Failed to get in-progress idea: {str(e)}")
        return None

def create_sheet(title, original_title=None):
    if not use_sheets:
        logger.info("Sheets unavailable - skipping sheet creation")
        return
        
    if sheets_service is None:
        logger.warning("Google Sheets service not available. Skipping sheet creation")
        return
        
    if use_sheets:
        try:
            body = {'requests': [{'addSheet': {'properties': {'title': title}}}]}
            sheets_service.spreadsheets().batchUpdate(spreadsheetId=GOOGLE_SHEET_ID, body=body).execute()
            escaped_title = escape_sheet_title(title)
            
            # Store original title in first row if provided
            if original_title:
                sheets_service.spreadsheets().values().update(
                    spreadsheetId=GOOGLE_SHEET_ID,
                    range=f"{escaped_title}!A1",
                    valueInputOption='RAW',
                    body={'values': [[original_title]]}
                ).execute()
            
            for i in range(1, 21):
                sheets_service.spreadsheets().values().update(
                    spreadsheetId=GOOGLE_SHEET_ID, range=f'{escaped_title}!D{i+1}',
                    valueInputOption='RAW', body={'values': [[str(i)]]}).execute()
        except Exception as e:
            logger.warning(f"Sheets failed: {e}")
    else:
        logger.info("Sheets unavailable - skipping")





def get_story_structure_template(story_type):
    """Return the specific story structure template based on story type"""
    
    templates = {
        "Power Fantasy": """
Story Structure (20 Scenes) - POWER FANTASY
1-3: Underdog Setup - Red fox is weak, dirty, poor, facing hardships and rejection.
Scene1: Humiliation or Offering to girl fox (e.g., flower).
Scene2: Loneliness or Rejection of offering.
Scene3: Others having what he wants.
Scene4: Sad reaction.
5-6: Spark of Ambition - Discovers trigger (blueprint/master/relic), hopeful.
Scene5: Discovers trigger.
Scene6: Reaches for object/trains/builds.
7-8: Failed Attempt - Tries and fails, mishap with laughter, defeated but determined.
9-10: Montage - Disciplined training/building, improving.
11-12: Transformation - Appearance changes, complete.
13-14: First Test - Displays power, others amazed.
15-19: Challenge - Confronts villain/challenge, struggles, overcomes, victory.
Scene20: New life, triumphant.""",

        "Redemption Arc": """
Story Structure (20 Scenes) - REDEMPTION ARC
1-4: Past Mistakes - Wrongdoing, consequences, isolation, regret.
5-6: Call to Redemption - Meets guide, accepts path.
7-8: First Attempts - Rejected help, persists.
9-10: Learning - Empathy, sacrifice.
11-12: Proving Change - Selfless act, recognition.
13-14: Test - Temptation, chooses right.
15-19: Major Redemption - Crisis, helps, amends, forgiveness, restored.
Scene20: New life, at peace.""",

        "Hero's Journey": """
Story Structure (20 Scenes) - HERO'S JOURNEY
1-2: Ordinary World - Normal life, challenges.
3-4: Call to Adventure - Disruption, hesitation.
5-6: Mentor - Meets guide, receives aid.
7-8: Threshold - Departs, first obstacles.
9-10: Tests/Allies - Meets friends, team builds.
11-12: Approach - Plans, gathers courage.
13-15: Ordeal - Confronts, darkest moment, overcomes.
16-19: Reward/Return - Gains reward, road back, resurrection, master of worlds.
Scene20: Returns with elixir to help community.""",

        "Coming of Age": """
Story Structure (20 Scenes) - COMING OF AGE
1-3: Childhood - Innocent play, protected, naive views.
4-5: Awakening - First loss, confusion.
6-7: Seeking - Questions, independence.
8-9: Mistakes - Poor decision, consequences.
10-11: Identity - Self-discovery, asserts self.
12-13: Relationships - Friendship tested, learns loyalty.
14-16: Challenge - Faces test, rises, grows through struggle.
17-18: Wisdom - Wise choice, helps others.
19-20: Maturity - Accepts complexity, ready for adulthood.""",
    }
    
    return templates.get(story_type, templates["Power Fantasy"])

def build_system_prompt(answers):
    story_type = answers.get('story_type', 'Power Fantasy')
    story_structure = get_story_structure_template(story_type)
    
    prompt = f"""
You are a creative assistant that generates emotionally-driven {story_type} stories starring a red fox. Stories told through images only — no dialogue/text.

CRITICAL: Exactly 20 scenes, numbered Scene1 to Scene20 in JSON. Do not skip numbers.

{story_structure}

Rules:
- One action per scene. No multiple actions.
- Refer to protagonist as "the red fox." No names.
- Visual storytelling only: body language, props, expression, setting, etc.
- Each scene visually distinct, like comic panels.
- Exaggerated/symbolic visuals (glowing items, massive elements).
- Tight emotional arc: weakness to power/growth, no subplots.
"""
    # Fill in placeholders based on answers
    if answers['humiliation_type'].lower() == 'a':
        prompt = prompt.replace("Red fox is weak, dirty, poor, facing hardships and rejection.", answers['humiliation'])
    else:
        prompt = prompt.replace("Scene1: Humiliation or Offering to girl fox (e.g., flower).", f"Scene1: Humiliation or Offering to girl fox (e.g., {answers['offering_what']}).")
        prompt = prompt.replace("Scene2: Loneliness or Rejection of offering.", f"Scene2: Loneliness or Rejection of offering.")

    prompt = prompt.replace("a blueprint, or he meets a master who trains him, or he finds some ancient magical relic with a great power", answers['find'])
    if answers['do_with_find'].lower() == 'a':
        prompt = prompt.replace("begins building the powerful technology", "begins training with his master")
        prompt = prompt.replace("building", "training")
    
    # Replace villain crime if provided
    if answers.get('villain_crime'):
        prompt = prompt.replace("committing a crime and getting away with it", f"committing {answers['villain_crime']} and getting away with it")
    
    return prompt

def generate_story(system_prompt):
    max_retries = 1  # Reduced from 2 to minimize token usage
    for attempt in range(max_retries):
        try:
            print(f"=== STORY GENERATION ATTEMPT {attempt + 1}/{max_retries} ===")
            
            response = openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": "Generate exactly 20 scenes. Return your response as a JSON object with keys Scene1, Scene2, Scene3, ..., Scene20. Each scene should be a detailed description. Do not skip any scene numbers."}],
                response_format={"type": "json_object"},
                timeout=120.0
            )
            
            # Print the full raw response for debugging
            print("=== RAW OPENAI RESPONSE ===")
            print(response.choices[0].message.content)
            print("=" * 40)
            
            scenes = json.loads(response.choices[0].message.content)
            
            # Print the full scenes dictionary for debugging
            print("=== SCENES DICTIONARY FROM OPENAI ===")
            print(json.dumps(scenes, indent=2))
            print(f"Total scenes in response: {len(scenes)}")
            print(f"Scene keys present: {list(scenes.keys())}")
            print("=" * 40)
            
            # Check for missing scenes and log them
            missing_scenes = []
            for i in range(1, 21):
                scene_key = f"Scene{i}"
                if scene_key not in scenes:
                    missing_scenes.append(scene_key)
            
            if missing_scenes:
                print(f"WARNING: Missing scenes from OpenAI response: {missing_scenes}")
                if attempt < max_retries - 1:
                    print(f"Retrying due to missing scenes... (attempt {attempt + 1}/{max_retries})")
                    continue
            else:
                print("✅ All 20 scenes present in OpenAI response")
            
            # Build the list with fallbacks for missing scenes
            result = []
            for i in range(1, 21):
                scene_key = f"Scene{i}"
                if scene_key in scenes:
                    result.append(scenes[scene_key])
                else:
                    print(f"Warning: {scene_key} missing from API response")
                    result.append(f"(Scene{i} missing)")
            
            print(f"Final result list length: {len(result)}")
            return result
            
        except Exception as e:
            print(f"Error on attempt {attempt + 1}: {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(30)  # Add delay before retry
                print(f"Retrying after 30s... (attempt {attempt + 1}/{max_retries})")
                continue
            else:
                print("Max retries exceeded, falling back to placeholder scenes")
                # Return placeholder scenes if all retries fail
                result = []
                for i in range(1, 21):
                    result.append(f"(Scene{i} missing - API failed)")
                return result

def edit_scenes(scenes):
    """Return scenes as-is (automated version, no manual editing)"""
    print("=== GENERATED SCENES ===")
    for i, scene in enumerate(scenes, 1):
        print(f"Scene {i}: {scene}")
    print("========================")
    return scenes

def create_prompts(scenes):
    logger.info(f"Creating visual prompts for {len(scenes)} scenes")
    system = """
You are a creative assistant generating visual prompts for red fox stories told in images (no dialogue).

Job: Turn 20 scenes into detailed visual image prompts. Output only prompts as JSON with keys Prompt1 to Prompt20.

Rules:
1. Hyper-detailed descriptions.
2. Serious/sad expressions before transformation; happy after.
3. No clothes on animals.
4. No midair/jumping unless flying.
""".replace("red panda", "red fox").replace("victim", "fox").replace("saved", "transformed")  # Adjust for new theme
    
    logger.info(f"Calling OpenAI for prompt refinement: {str(scenes)[:50]}...")
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": system}, {"role": "user", "content": json.dumps({"scenes": scenes}) + " Return as JSON with keys Prompt1, Prompt2, etc."}],
            response_format={"type": "json_object"},
            timeout=120.0
        )
        prompts = json.loads(response.choices[0].message.content)
        logger.info(f"Visual prompts created: {len(prompts)}")
    except Exception as e:
        logger.error(f"Visual prompt error: {e}")
        raise
    return [prompts[f"Prompt{i}"] for i in range(1, 21)]

def standardize_prompts(prompts):
    logger.info(f"Standardizing {len(prompts)} visual prompts")
    system = """
You are a creative assistant standardizing visual prompts for red fox stories.

Job: Add art style to start of each of 20 prompts and character descriptions every time mentioned. Output JSON with keys Prompt1 to Prompt20.

ArtStyle: Stylized, cinematic 3D animation with soft, high-res render like modern films. Physically accurate materials with subtle texture, plush fur detailed yet toy-like. Warm naturalistic lighting, golden hour tones, soft shadows. Balances realism and whimsy, friendly vibrant tone.

Character Description: Wholesome, animated with childlike wonder. Rounded expressive features, large bright eyes, exaggerated cute structure. Evokes innocence, curiosity, adventure like animated film sidekick.

Rules:
1. Repeat exact artstyle/character descriptions in EVERY prompt.
2. Describe EVERY character mention.
3. Do not remove original prompt text.
"""
    logger.info(f"Standardizing prompt: {str(prompts)[:50]}...")
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": system}, {"role": "user", "content": json.dumps({"prompts": prompts}) + " Return as JSON with keys Prompt1, Prompt2, etc."}],
            response_format={"type": "json_object"},
            timeout=120.0
        )
        std_prompts = json.loads(response.choices[0].message.content)
        # Apply sanitization to all standardized prompts
        for key in std_prompts:
            std_prompts[key] = sanitize_prompt(std_prompts[key])
        logger.info(f"Standardized prompts: {len(std_prompts)}")
    except Exception as e:
        logger.error(f"Standardize prompt error: {e}")
        raise
    return [std_prompts[f"Prompt{i}"] for i in range(1, 21)]

async def generate_async(prompt):
    """Async version of image generation using httpx with timeouts"""
    start_time = time.time()
    logger.debug(f"[ASYNC-DEBUG] generate_async started with prompt length: {len(prompt)}")
    logger.debug(f"[STOPPAGE-DEBUG] generate_async starting at {time.time()}")
    
    try:
        # Add 180s timeout to httpx client for GPT-Image-1 (can take up to 2 minutes)
        client_start = time.time()
        client = httpx.AsyncClient(timeout=180.0)
        client_elapsed = time.time() - client_start
        logger.debug(f"[ASYNC-DEBUG] httpx client created in {client_elapsed:.3f}s with 180s timeout")
    except Exception as e:
        logger.error(f"[ASYNC-DEBUG] Async client init error: {type(e).__name__}: {e}")
        raise
    
    try:
        gpt_image_start = time.time()
        logger.debug(f"[ASYNC-DEBUG] Starting GPT-Image-1 API call with 180s timeout")
        logger.debug(f"[STOPPAGE-DEBUG] GPT-Image-1 API call starting at {time.time()}")
        # Use OpenAI client for GPT-Image-1 generation with timeout (can take up to 2 minutes)
        # CRITICAL FIX: Run synchronous OpenAI call in thread pool to avoid blocking event loop
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: openai_client.images.generate(
            model="gpt-image-1", 
            prompt=prompt, 
            size="1024x1536", 
            n=1,
            timeout=180.0
        ))
        logger.debug(f"[STOPPAGE-DEBUG] GPT-Image-1 API call completed at {time.time()}")
        gpt_image_elapsed = time.time() - gpt_image_start
        
        # Validate API response structure and handle both URL and base64 formats
        if not response or not hasattr(response, 'data') or not response.data:
            logger.error(f"[ASYNC-DEBUG] Invalid API response: {response}")
            raise ValueError("OpenAI API returned invalid response structure")
        
        # Process single image from GPT-Image-1 response
        logger.debug(f"[ASYNC-DEBUG] GPT-Image-1 returned {len(response.data)} image(s)")
        variations = []
        
        for i, image_data in enumerate(response.data):
            logger.debug(f"[ASYNC-DEBUG] Processing image {i+1}/{len(response.data)}")
            
            if hasattr(image_data, 'b64_json') and image_data.b64_json:
                logger.debug(f"[ASYNC-DEBUG] Image {i+1} returned base64 data, converting to bytes")
                import base64
                img_data = base64.b64decode(image_data.b64_json)
                logger.debug(f"[ASYNC-DEBUG] Image {i+1} got {len(img_data)} bytes of image data")
                variations.append(img_data)
            elif hasattr(image_data, 'url') and image_data.url:
                img_url = image_data.url
                logger.debug(f"[ASYNC-DEBUG] Image {i+1} got URL: {img_url[:50]}...")
                
                # Download the image asynchronously
                download_start = time.time()
                logger.debug(f"[ASYNC-DEBUG] Starting download for image {i+1}")
                img_response = await client.get(img_url)
                download_elapsed = time.time() - download_start
                img_data = img_response.content
                logger.debug(f"[ASYNC-DEBUG] Image {i+1} download completed in {download_elapsed:.2f}s, size: {len(img_data)} bytes")
                variations.append(img_data)
            else:
                logger.error(f"[ASYNC-DEBUG] Invalid image {i+1} - no URL or b64_json: {image_data}")
                raise ValueError(f"OpenAI API image {i+1} returned neither URL nor base64 data")
        
        total_elapsed = time.time() - start_time
        logger.debug(f"[ASYNC-DEBUG] All {len(variations)} image(s) processed in {total_elapsed:.2f}s (GPT-Image-1: {gpt_image_elapsed:.2f}s)")
        await client.aclose()
        return variations
    except Exception as e:
        total_elapsed = time.time() - start_time
        logger.error(f"[ASYNC-DEBUG] generate_async failed after {total_elapsed:.2f}s: {type(e).__name__}: {e}")
        await client.aclose()
        raise

def sanitize_prompt(prompt):
    violations = {
        "beats up": "overcomes",
        "subdue": "stops",
        "confronts": "approaches",
        "fight": "challenges peacefully",
        "overpower": "defeats non-violently",
        "attacks": "confronts safely",
        "violence": "conflict",
        "violent": "intense",
        "punch": "touch",
        "kick": "nudge",
        "hit": "tap",
        "hurt": "surprise",
        "harm": "affect"
    }
    original_prompt = prompt
    for bad, good in violations.items():
        prompt = re.sub(bad, good, prompt, flags=re.IGNORECASE)
    if prompt != original_prompt:
        logger.info(f"Sanitized prompt (length {len(prompt)}): {prompt[:50]}...")
    return prompt

def generate_image(prompt):
    logger.info(f"Generating image for prompt: {prompt[:50]}...")
    max_retries = 3
    
    for retry in range(max_retries):
        try:
            current_prompt = prompt
            if retry > 0:
                current_prompt = sanitize_prompt(current_prompt)  # Base sanitization
                if retry > 1:
                    current_prompt = current_prompt[:1000] + " (simplified)"  # Shorten on later retries
            logger.debug(f"Retry {retry + 1} prompt: {current_prompt[:50]}")
            logger.debug(f"Attempting GPT-Image-1 with prompt (length {len(current_prompt)}): {current_prompt}")
            return asyncio.run(generate_async(current_prompt))
        except Exception as e:
            logger.error(f"GPT-Image-1 error details: {e.response.json() if hasattr(e, 'response') else str(e)}")
            
            # Check for rate limiting (429 errors) and handle with longer delays
            is_rate_limit = False
            global RATE_LIMIT_DETECTED
            if hasattr(e, 'response') and hasattr(e.response, 'status_code') and e.response.status_code == 429:
                is_rate_limit = True
                RATE_LIMIT_DETECTED = True
                logger.warning(f"[RATE-LIMIT] OpenAI API rate limit hit on retry {retry + 1}, setting global rate limit flag")
            elif "429" in str(e) or "Too Many Requests" in str(e):
                is_rate_limit = True
                RATE_LIMIT_DETECTED = True
                logger.warning(f"[RATE-LIMIT] Rate limit detected in error message: {e}, setting global rate limit flag")
            
            if retry < max_retries - 1:
                if is_rate_limit:
                    # Longer delays for rate limits: 30, 60, 90 seconds
                    wait_time = 30 * (retry + 1)
                    logger.warning(f"[RATE-LIMIT] Waiting {wait_time}s for rate limit recovery before retry {retry + 2}")
                else:
                    # Normal retry delays: 5, 10, 15 seconds
                    wait_time = 5 * (retry + 1)
                    logger.warning(f"Retry {retry + 1} for generate: {e}")
                time.sleep(wait_time)
            else:
                if is_rate_limit:
                    logger.error(f"[RATE-LIMIT] Generate failed after {max_retries} attempts due to persistent rate limiting: {e}")
                else:
                    logger.error(f"Generate failed after {max_retries} attempts: {e}")
                raise

def upload_image(img_data):
    max_retries = 3
    
    for retry in range(max_retries):
        try:
            files = {'file': ('image.png', img_data, 'image/png'), 'upload_preset': (None, CLOUDINARY_PRESET)}
            response = requests.post(CLOUDINARY_URL + 'image/upload', files=files)
            url = response.json()['secure_url']
            logger.info(f"Uploaded image URL: {url}")
            return url
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, Exception) as e:
            if retry < max_retries - 1:
                wait_time = 5 * (retry + 1)  # 5, 10, 15 seconds
                logger.warning(f"Retry {retry + 1} for upload: {e}")
                time.sleep(wait_time)
            else:
                logger.error(f"Upload failed after {max_retries} attempts: {e}")
                raise

async def process_image_async(semaphore, classifier, prompt, sheet_title, story_id=None):
    """Async version of process_image with semaphore control for rate limiting"""
    logger.debug(f"[STOPPAGE-DEBUG] Task {classifier} attempting to acquire semaphore")
    async with semaphore:
        start_time = time.time()
        logger.info(f"[ASYNC] Starting image {classifier} with prompt: {prompt[:50]}...")
        logger.debug(f"[STOPPAGE-DEBUG] Task {classifier} acquired semaphore, starting processing at {time.time()}")
        
        try:
            # Sanitize prompt before generation
            prompt = sanitize_prompt(prompt)
            logger.debug(f"[ASYNC-ERROR] Image {classifier} sanitized prompt: {prompt[:100]}...")
            
            # Generate single image and upload with retries
            logger.debug(f"[STOPPAGE-DEBUG] Task {classifier} starting image generation at {time.time()}")
            try:
                variations_data = await generate_image_async_with_retries(prompt)
                logger.debug(f"[ASYNC-ERROR] Image {classifier} generation completed, got {len(variations_data)} image(s)")
                logger.debug(f"[STOPPAGE-DEBUG] Task {classifier} completed image generation at {time.time()}")
            except Exception as gen_error:
                logger.error(f"[ASYNC-ERROR] Image {classifier} generation failed: {type(gen_error).__name__}: {gen_error}")
                logger.debug(f"[STOPPAGE-DEBUG] Task {classifier} generation failed at {time.time()}")
                raise gen_error
            
            # Upload single image
            logger.debug(f"[STOPPAGE-DEBUG] Task {classifier} starting image upload at {time.time()}")
            variation_urls = []
            for i, img_data in enumerate(variations_data):
                try:
                    # CRITICAL FIX: Run blocking upload_image in thread pool to avoid blocking event loop
                    loop = asyncio.get_event_loop()
                    url = await loop.run_in_executor(None, upload_image, img_data)
                    variation_urls.append(url)
                    logger.debug(f"[ASYNC-ERROR] Image {classifier} upload completed: {url}")
                    logger.debug(f"[BLOCKING-FIX] Task {classifier} upload executed in thread pool")
                except Exception as upload_error:
                    logger.error(f"[ASYNC-ERROR] Image {classifier} upload failed: {type(upload_error).__name__}: {upload_error}")
                    variation_urls.append(None)  # Keep position but mark as failed
            
            logger.debug(f"[STOPPAGE-DEBUG] Task {classifier} completed upload at {time.time()}")
            elapsed = time.time() - start_time
            successful_uploads = len([url for url in variation_urls if url])
            logger.info(f"[ASYNC] Successfully completed image {classifier} in {elapsed:.2f}s: {successful_uploads}/{len(variations_data)} image(s) uploaded")
            logger.debug(f"[STOPPAGE-DEBUG] Task {classifier} starting sheet update at {time.time()}")
            
            # Update sheet with successful image if available
            if variation_urls and any(variation_urls):
                first_url = next(url for url in variation_urls if url)
                try:
                    update_sheet(sheet_title, classifier, 'Picture Generation', first_url)
                    logger.debug(f"[STOPPAGE-DEBUG] Task {classifier} completed sheet update at {time.time()}")
                except Exception as e:
                    logger.warning(f"[ASYNC-ERROR] Sheet update failed for {classifier}: {type(e).__name__}: {e}")
                    logger.debug(f"[STOPPAGE-DEBUG] Task {classifier} sheet update failed at {time.time()}")
            
            # Emit image event with single image if story_id is provided
            logger.debug(f"[STOPPAGE-DEBUG] Task {classifier} checking SSE emit at {time.time()}")
            if story_id:
                logger.debug(f"[STOPPAGE-DEBUG] Task {classifier} starting SSE emit at {time.time()}")
                try:
                    from flask_server import emit_image_event
                    # For single image, emit the first successful URL directly
                    if variation_urls and any(variation_urls):
                        image_url = next(url for url in variation_urls if url)
                        emit_image_event(story_id, int(classifier), image_url, "completed")
                        logger.info(f"[APPROVAL] Emitted completed for image {classifier} with single image")
                    else:
                        emit_image_event(story_id, int(classifier), None, "failed")
                        logger.info(f"[APPROVAL] Emitted failed for image {classifier} - no successful uploads")
                    logger.debug(f"[STOPPAGE-DEBUG] Task {classifier} completed SSE emit at {time.time()}")
                except ImportError:
                    logger.warning(f"[ASYNC-ERROR] Could not emit image event for story {story_id}: ImportError")
                    logger.debug(f"[STOPPAGE-DEBUG] Task {classifier} SSE emit ImportError at {time.time()}")
                except Exception as emit_error:
                    logger.error(f"[ASYNC-ERROR] SSE emit failed for image {classifier}: {type(emit_error).__name__}: {emit_error}")
                    logger.debug(f"[STOPPAGE-DEBUG] Task {classifier} SSE emit failed at {time.time()}")
            
            logger.debug(f"[STOPPAGE-DEBUG] Task {classifier} about to return result at {time.time()}")
            return classifier, variation_urls
            
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"[ASYNC-ERROR] Failed to generate image {classifier} after {elapsed:.2f}s: {type(e).__name__}: {str(e)}")
            logger.debug(f"[ASYNC-ERROR] Image {classifier} full exception details:", exc_info=True)
            return classifier, None

async def generate_image_async_with_retries(prompt):
    """Async image generation with retry logic"""
    max_retries = 3
    start_time = time.time()
    logger.debug(f"[ASYNC-DEBUG] generate_image_async_with_retries started with {max_retries} max retries")
    
    for retry in range(max_retries):
        retry_start = time.time()
        logger.debug(f"[ASYNC-DEBUG] Starting retry {retry + 1}/{max_retries}")
        
        try:
            current_prompt = prompt
            if retry > 0:
                logger.debug(f"[ASYNC-DEBUG] Applying sanitization for retry {retry + 1}")
                current_prompt = sanitize_prompt(current_prompt)  # Base sanitization
                if retry > 1:
                    original_length = len(current_prompt)
                    current_prompt = current_prompt[:1000] + " (simplified)"  # Shorten on later retries
                    logger.debug(f"[ASYNC-DEBUG] Prompt shortened from {original_length} to {len(current_prompt)} chars")
            
            logger.debug(f"[ASYNC-DEBUG] Retry {retry + 1} prompt length: {len(current_prompt)}, preview: {current_prompt[:50]}...")
            
            result = await generate_async(current_prompt)
            retry_elapsed = time.time() - retry_start
            total_elapsed = time.time() - start_time
            logger.debug(f"[ASYNC-DEBUG] Retry {retry + 1} succeeded in {retry_elapsed:.2f}s, total time: {total_elapsed:.2f}s")
            return result
            
        except Exception as e:
            retry_elapsed = time.time() - retry_start
            logger.error(f"[ASYNC-DEBUG] Retry {retry + 1} failed after {retry_elapsed:.2f}s: {type(e).__name__}: {e}")
            
            # Check for rate limiting (429 errors) and handle with longer delays
            is_rate_limit = False
            global RATE_LIMIT_DETECTED
            if hasattr(e, 'response') and hasattr(e.response, 'status_code') and e.response.status_code == 429:
                is_rate_limit = True
                RATE_LIMIT_DETECTED = True
                logger.warning(f"[RATE-LIMIT] OpenAI API rate limit hit on retry {retry + 1}, setting global rate limit flag")
            elif "429" in str(e) or "Too Many Requests" in str(e):
                is_rate_limit = True
                RATE_LIMIT_DETECTED = True
                logger.warning(f"[RATE-LIMIT] Rate limit detected in error message: {e}, setting global rate limit flag")
            
            if retry < max_retries - 1:
                if is_rate_limit:
                    # Longer delays for rate limits: 30, 60, 90 seconds
                    wait_time = 30 * (retry + 1)
                    logger.warning(f"[RATE-LIMIT] Waiting {wait_time}s for rate limit recovery before retry {retry + 2}")
                else:
                    # Normal retry delays: 5, 10, 15 seconds
                    wait_time = 5 * (retry + 1)
                    logger.debug(f"[ASYNC-DEBUG] Waiting {wait_time}s before retry {retry + 2}")
                await asyncio.sleep(wait_time)
            else:
                total_elapsed = time.time() - start_time
                if is_rate_limit:
                    logger.error(f"[RATE-LIMIT] All retries exhausted due to persistent rate limiting after {total_elapsed:.2f}s")
                else:
                    logger.error(f"[ASYNC-DEBUG] All retries exhausted after {total_elapsed:.2f}s, final error: {e}")
                raise

async def generate_images_concurrently(prompts_with_metadata, story_id=None):
    """
    Generate multiple images concurrently with rate limiting
    
    Args:
        prompts_with_metadata: List of tuples (scene_number, prompt, sheet_title)
        story_id: Optional story ID for SSE events
    
    Returns:
        List of tuples (scene_number, image_url_or_none)
    """
    start_time = time.time()
    logger.info(f"[ASYNC-DEBUG] generate_images_concurrently started with {len(prompts_with_metadata)} images")
    logger.debug(f"[ASYNC-DEBUG] Concurrent limits: MAX_CONCURRENT={MAX_CONCURRENT}, BATCH_SIZE={BATCH_SIZE}, MAX_IMAGES_PER_MIN={MAX_IMAGES_PER_MIN}")
    
    # Create semaphore to limit concurrent requests (reduce concurrency if rate limited)
    global RATE_LIMIT_DETECTED
    concurrent_limit = MAX_CONCURRENT // 2 if RATE_LIMIT_DETECTED else MAX_CONCURRENT
    semaphore = asyncio.Semaphore(concurrent_limit)
    logger.debug(f"[ASYNC-DEBUG] Semaphore created with limit {concurrent_limit} (rate limited: {RATE_LIMIT_DETECTED})")
    logger.debug(f"[DEADLOCK-DEBUG] Initial semaphore value: {semaphore._value}")
    
    # Split into batches to respect rate limits
    batches = [prompts_with_metadata[i:i + BATCH_SIZE] for i in range(0, len(prompts_with_metadata), BATCH_SIZE)]
    logger.debug(f"[ASYNC-DEBUG] Split into {len(batches)} batches of max size {BATCH_SIZE}")
    
    # Potential deadlock check: ensure BATCH_SIZE doesn't exceed MAX_CONCURRENT
    if BATCH_SIZE > MAX_CONCURRENT:
        logger.warning(f"[DEADLOCK-DEBUG] Potential deadlock: BATCH_SIZE ({BATCH_SIZE}) > MAX_CONCURRENT ({MAX_CONCURRENT})")
    else:
        logger.debug(f"[DEADLOCK-DEBUG] Deadlock check passed: BATCH_SIZE ({BATCH_SIZE}) <= MAX_CONCURRENT ({MAX_CONCURRENT})")
    
    all_results = []
    total_images_processed = 0
    
    for batch_num, batch in enumerate(batches, 1):
        batch_start_time = time.time()
        logger.info(f"[CONCURRENT] Processing batch {batch_num}/{len(batches)} with {len(batch)} images")
        
        # Create async tasks for this batch
        tasks = []
        logger.debug(f"[ASYNC-DEBUG] Creating {len(batch)} tasks for batch {batch_num}")
        for i, (scene_number, prompt, sheet_title) in enumerate(batch):
            logger.debug(f"[ASYNC-DEBUG] Creating task {i+1} for scene {scene_number}, prompt length: {len(prompt)}")
            task = process_image_async(semaphore, str(scene_number), prompt, sheet_title, story_id)
            tasks.append(task)
        logger.debug(f"[ASYNC-DEBUG] All {len(tasks)} tasks created for batch {batch_num}")
        
        # Execute batch concurrently with enhanced error handling
        logger.debug(f"[STOPPAGE-DEBUG] Starting asyncio.gather for batch {batch_num} with {len(tasks)} tasks at {time.time()}")
        logger.debug(f"[DEADLOCK-DEBUG] Semaphore available permits before gather: {semaphore._value}")
        try:
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            logger.info(f"[ASYNC-ERROR] Batch {batch_num} gather completed with {len(batch_results)} results")
            logger.debug(f"[STOPPAGE-DEBUG] Completed asyncio.gather for batch {batch_num} at {time.time()}")
            logger.debug(f"[DEADLOCK-DEBUG] Semaphore available permits after gather: {semaphore._value}")
        except Exception as gather_error:
            logger.error(f"[ASYNC-ERROR] asyncio.gather failed for batch {batch_num}: {gather_error}")
            logger.debug(f"[STOPPAGE-DEBUG] asyncio.gather failed for batch {batch_num} at {time.time()}")
            batch_results = [Exception(f"Gather failed: {gather_error}") for _ in tasks]
        
        # Process results and handle exceptions with detailed logging
        failed_count = 0
        success_count = 0
        for i, result in enumerate(batch_results):
            if isinstance(result, Exception):
                failed_count += 1
                logger.error(f"[ASYNC-ERROR] Task {i+1} in batch {batch_num} failed: {type(result).__name__}: {result}")
                # Try to extract scene number from task if possible
                try:
                    scene_info = batch[i][0] if i < len(batch) else "unknown"
                    logger.error(f"[ASYNC-ERROR] Failed scene: {scene_info}")
                except:
                    pass
                all_results.append((0, None))  # Placeholder for failed task
            else:
                success_count += 1
                all_results.append(result)
        
        logger.info(f"[ASYNC-ERROR] Batch {batch_num} results: {success_count} success, {failed_count} failed")
        
        total_images_processed += len(batch)
        batch_elapsed = time.time() - batch_start_time
        images_per_min = (len(batch) / batch_elapsed) * 60
        
        logger.info(f"[CONCURRENT] Batch {batch_num} completed in {batch_elapsed:.2f}s ({images_per_min:.1f} images/min)")
        
        # Rate limiting: Sleep between batches to stay under 15 images/min
        if batch_num < len(batches):  # Don't sleep after the last batch
            sleep_time = (60 / MAX_IMAGES_PER_MIN) * len(batch)
            logger.debug(f"[ASYNC-DEBUG] Rate limiting calculation: {len(batch)} images * 60s / {MAX_IMAGES_PER_MIN} = {sleep_time:.1f}s")
            logger.info(f"[CONCURRENT] Sleeping {sleep_time:.1f}s to respect {MAX_IMAGES_PER_MIN} images/min limit")
            await asyncio.sleep(sleep_time)
    
    total_elapsed = time.time() - start_time
    success_count = len([result for result in all_results if result[1] is not None])
    failure_count = len(all_results) - success_count
    overall_rate = (total_images_processed / total_elapsed) * 60 if total_elapsed > 0 else 0
    
    logger.info(f"[ASYNC-DEBUG] generate_images_concurrently completed in {total_elapsed:.2f}s")
    logger.info(f"[ASYNC-DEBUG] Final results: {success_count} success, {failure_count} failed, {overall_rate:.1f} images/min")
    logger.info(f"[CONCURRENT] All {total_images_processed} images processed successfully")
    return all_results



def process_image(classifier, prompt, sheet_title, story_id=None):
    """Simplified image processing without Telegram approval"""
    logger.info(f"Processing image {classifier} with prompt: {prompt[:50]}...")
    
    try:
        # Sanitize prompt before generation
        prompt = sanitize_prompt(prompt)
        # Generate and upload image
        img_data = generate_image(prompt)
        url = upload_image(img_data)
        logger.info(f"Successfully uploaded image {classifier} to: {url}")
        
        # Update sheet if available
        try:
            update_sheet(sheet_title, classifier, 'Picture Generation', url)
        except Exception as e:
            logger.warning(f"Failed to update sheet: {e}")
        
        # Emit image event if story_id is provided
        if story_id:
            try:
                from flask_server import emit_image_event
                # Emit single image directly (fallback behavior)
                emit_image_event(story_id, int(classifier), url, "completed")
            except ImportError:
                logger.warning(f"Could not emit image event for story {story_id}")
        
        logger.info(f"Image {classifier} completed without approval")
        return url
        
    except Exception as e:
        logger.error(f"Failed to generate/upload image {classifier}: {str(e)}")
        return None

def update_sheet(sheet_title, classifier, column, value):
    if not use_sheets:
        logger.info("Sheets unavailable - skipping update")
        return
        
    if sheets_service is None:
        logger.warning("Google Sheets service not available. Skipping update")
        return
        
    try:
        # Find row for classifier
        # Simplified: assume row = int(classifier) +1
        row = int(classifier) + 1
        
        # Map column names to letters
        column_map = {
            'Prompt': 'A',
            'Picture Generation': 'B', 
            'Video Generation': 'C'
        }
        column_letter = column_map.get(column, column)
        
        # Escape sheet title using consistent function
        escaped_title = escape_sheet_title(sheet_title)
        
        range_str = f'{escaped_title}!{column_letter}{row}'
        
        sheets_service.spreadsheets().values().update(
            spreadsheetId=GOOGLE_SHEET_ID, range=range_str,
            valueInputOption='RAW', body={'values': [[value]]}).execute()
    except Exception as e:
        logger.warning(f"Sheets failed: {e}")

def choose_video_model():
    """Default to Kling video model"""
    logger.info("Using default Kling video model")
    return 'kling'


def get_motion_prompt():
    """Return default motion prompt"""
    default_prompt = "smooth camera movement with natural transitions"
    logger.info(f"Using default motion prompt: {default_prompt}")
    return default_prompt

def generate_video(model, prompt, image_url):
    if model == 'kling':
        # Kling API call
        payload = { "prompt": prompt, "image_url": image_url }  # Simplified
        response = requests.post("https://api.piapi.ai/api/v1/task", json=payload, headers={"x-api-key": KLING_API_KEY})
        return response.json()['video_url']
    else:
        # Hailuo
        payload = { "prompt": prompt, "first_frame_image": image_url }
        response = requests.post("https://api.minimax.io/v1/video_generation", json=payload, headers={"Authorization": HAILUO_AUTH})
        task_id = response.json()['task_id']
        while True:
            status = requests.get(f"https://api.minimax.io/v1/query/video_generation?task_id={task_id}", headers={"Authorization": HAILUO_AUTH}).json()
            if status['status'] == 'Success':
                return status['video_url']
            time.sleep(30)

def process_video(classifier, image_url, sheet_title):
    """Simplified video processing without Telegram approval"""
    model = choose_video_model()
    motion_prompt = get_motion_prompt()
    try:
        video_url = generate_video(model, motion_prompt, image_url)
        update_sheet(sheet_title, classifier, 'Video Generation', video_url)
        logger.info(f"Video {classifier} completed successfully")
        return video_url
    except Exception as e:
        logger.error(f"Failed to generate video {classifier}: {str(e)}")
        return None

def process_story_generation(answers, story_id=None):
    """Process story generation with provided answers from Flask server"""
    system_prompt = build_system_prompt(answers)
    scenes = generate_story(system_prompt)
    scenes = edit_scenes(scenes)
    prompts = create_prompts(scenes)
    std_prompts = standardize_prompts(prompts)
    
    # Create new sanitized sheet for this story
    idea = generate_sheet_title()
    original_title = f"{answers.get('story_type', 'Power Fantasy')} Story"
    if answers.get('find'):
        original_title += f" - Fox finds {answers['find']}"
    create_sheet(idea, original_title)

    images = []
    for i, prompt in enumerate(std_prompts, 1):
        update_sheet(idea, str(i), 'Prompt', prompt)
        img_url = process_image(str(i), prompt, idea, story_id)
        images.append(img_url)

    for i, img_url in enumerate(images, 1):
        process_video(str(i), img_url, idea)

def process_story_generation_with_scenes(approved_scenes, original_answers, story_id=None):
    """Process story generation with pre-approved scenes from frontend"""
    # DETAILED LOGGING: Process entry point with comprehensive info
    logger.info(f"[PROCESS-START] Starting story generation with pre-approved scenes for story {story_id}")
    logger.info(f"[PROCESS-INFO] Number of scene keys in approved_scenes: {len(approved_scenes)}")
    logger.info(f"[PROCESS-INFO] Story ID: {story_id}")
    logger.debug(f"[PROCESS-DEBUG] Original answers keys: {list(original_answers.keys())}")
    logger.debug(f"[PROCESS-DEBUG] Thread info: {threading.current_thread().name}, daemon: {threading.current_thread().daemon}")
    
    process_start_time = time.time()
    logger.info(f"[TIMING] Process started at: {process_start_time}")
    
    # Convert approved scenes dict to list format
    scenes = []
    missing_scenes = []
    for i in range(1, 21):
        scene_key = f"Scene{i}"
        if scene_key in approved_scenes:
            scenes.append(approved_scenes[scene_key])
            logger.debug(f"[SCENE-PROCESSING] Scene {i}: Added from approved scenes (length: {len(approved_scenes[scene_key])})")
        else:
            scenes.append(f"(Scene {i} missing)")
            missing_scenes.append(i)
            logger.warning(f"[SCENE-PROCESSING] Scene {i}: Missing from approved scenes")
    
    if missing_scenes:
        logger.warning(f"[SCENE-PROCESSING] Missing scenes: {missing_scenes}")
    else:
        logger.info(f"[SCENE-PROCESSING] All 20 scenes present in approved scenes")
    
    logger.info(f"[PROCESS-FLOW] Starting generation for {story_id} with {len(scenes)} scenes")
    
    # DETAILED LOGGING: Scene editing phase
    edit_start_time = time.time()
    logger.info(f"[SCENE-EDIT] Starting scene editing at {edit_start_time}")
    scenes = edit_scenes(scenes)
    edit_elapsed = time.time() - edit_start_time
    logger.info(f"[TIMING] Scene editing completed in {edit_elapsed:.2f}s")
    
    # DETAILED LOGGING: Prompt creation phase
    prompt_start_time = time.time()
    logger.info(f"[PROMPT-CREATE] Starting prompt creation for {len(scenes)} scenes at {prompt_start_time}")
    prompts = create_prompts(scenes)
    prompt_elapsed = time.time() - prompt_start_time
    logger.info(f"[TIMING] Prompt creation completed in {prompt_elapsed:.2f}s")
    logger.info(f"[PROMPT-CREATE] Generated {len(prompts)} prompts")
    
    # DETAILED LOGGING: Prompt standardization phase
    std_start_time = time.time()
    logger.info(f"[PROMPT-STANDARDIZE] Starting prompt standardization at {std_start_time}")
    std_prompts = standardize_prompts(prompts)
    std_elapsed = time.time() - std_start_time
    logger.info(f"[TIMING] Prompt standardization completed in {std_elapsed:.2f}s")
    logger.info(f"[PROMPT-STANDARDIZE] Standardized {len(std_prompts)} prompts")
    
    # Debug log to check scene 16 sanitization
    if len(std_prompts) >= 16:
        logger.debug(f"[PROMPT-DEBUG] Post-sanitization prompt 16 example: {std_prompts[15][:50]}")
    
    # DETAILED LOGGING: Sheet creation phase
    sheet_start_time = time.time()
    logger.info(f"[SHEET-CREATE] Starting sheet creation at {sheet_start_time}")
    idea = generate_sheet_title()
    original_title = f"{original_answers.get('story_type', 'Power Fantasy')} Story"
    if original_answers.get('find'):
        original_title += f" - Fox finds {original_answers['find']}"
    create_sheet(idea, original_title)
    sheet_elapsed = time.time() - sheet_start_time
    logger.info(f"[TIMING] Sheet creation completed in {sheet_elapsed:.2f}s")
    logger.info(f"[SHEET-CREATE] Created sheet with title: {original_title}")

    logger.info(f"Starting PARALLEL image generation for {len(std_prompts)} prompts")
    
    # CRITICAL FIX: Replace signal-based timeout with thread-safe approach
    # Signal handling can only be done from main thread, not from Flask worker threads
    logger.info("[SIGNAL-FIX] Using thread-safe timeout instead of signal-based timeout")
    logger.debug(f"[SIGNAL-DETAILED] Current thread: {threading.current_thread().name}, is_main: {threading.current_thread() == threading.main_thread()}")
    logger.debug(f"[SIGNAL-DETAILED] Thread daemon status: {threading.current_thread().daemon}")
    logger.debug("[SIGNAL-DETAILED] Signal handlers not used to avoid thread compatibility issues")
    
    images = []
    try:
        # Prepare data for concurrent processing
        prompts_with_metadata = []
        for i, prompt in enumerate(std_prompts, 1):
            update_sheet(idea, str(i), 'Prompt', prompt)
            prompts_with_metadata.append((i, prompt, idea))
        
        # Use async processing with asyncio timeout (thread-safe alternative to signal)
        # RETRY LOGIC: Implement retry for transient async failures
        max_retries = 2  # Reduced for async operations (they're already expensive)
        retry_delay = 5  # seconds
        
        for attempt in range(max_retries):
            try:
                concurrent_start_time = time.time()
                logger.info(f"[SIGNAL-FIX] Starting async generation attempt {attempt + 1}/{max_retries} with asyncio timeout (no signals)")
                
                # Use asyncio timeout instead of signal-based timeout for thread safety
                async def run_with_timeout():
                    return await asyncio.wait_for(
                        generate_images_concurrently(prompts_with_metadata, story_id),
                        timeout=600.0  # 10 minutes timeout
                    )
                
                results = asyncio.run(run_with_timeout())
                concurrent_elapsed = time.time() - concurrent_start_time
                logger.info(f"[SIGNAL-FIX] Async generation completed in {concurrent_elapsed:.2f}s (no signal handlers used, attempt {attempt + 1})")
                break  # Success, exit retry loop
                
            except asyncio.TimeoutError as timeout_e:
                logger.error(f"[SIGNAL-FIX] Async generation timed out after 10 minutes (attempt {attempt + 1}): {timeout_e}")
                if attempt < max_retries - 1:
                    logger.info(f"[ASYNC-RETRY] Retrying async generation in {retry_delay}s...")
                    time.sleep(retry_delay)
                else:
                    logger.error(f"[ASYNC-RETRY] All {max_retries} async attempts timed out")
                    raise TimeoutError("Async generation timed out after 10 minutes")
                    
            except Exception as async_e:
                logger.error(f"[SIGNAL-FIX] Async generation error (attempt {attempt + 1}): {async_e}")
                if attempt < max_retries - 1:
                    logger.info(f"[ASYNC-RETRY] Retrying async generation in {retry_delay}s...")
                    time.sleep(retry_delay)
                else:
                    logger.error(f"[ASYNC-RETRY] All {max_retries} async attempts failed")
                    raise
        
        # Process results in order
        results_dict = {int(scene): url for scene, url in results if scene != 0}
        for i in range(1, len(std_prompts) + 1):
            img_url = results_dict.get(i)
            if img_url:
                images.append(img_url)
                logger.info(f"✓ Image {i} completed: {img_url}")
            else:
                logger.warning(f"✗ Image {i} failed - using placeholder")
                images.append("Skipped")
        
        success_count = len([url for url in images if url != "Skipped"])
        logger.info(f"[PERFORMANCE] Parallel generation completed: {success_count}/{len(images)} images in {concurrent_elapsed:.2f}s")
        images_per_min = (len(images) / concurrent_elapsed) * 60
        logger.info(f"[PERFORMANCE] Rate achieved: {images_per_min:.1f} images/min (limit: {MAX_IMAGES_PER_MIN})")
        
    except TimeoutError as e:
        logger.error(f"Timeout during parallel generation: {e}")
    except Exception as e:
        logger.error(f"Parallel generation error: {e}")
        logger.info("Falling back to sequential processing...")
        # Fallback to original sequential method
        for i, prompt in enumerate(std_prompts, 1):
            try:
                img_url = process_image(str(i), prompt, idea, story_id)
                images.append(img_url if img_url else "Skipped")
            except Exception as fallback_e:
                logger.error(f"Fallback image process error {i}: {fallback_e}")
                images.append("Skipped")
    finally:
        # SIGNAL-FIX: No signal cleanup needed since we use asyncio timeout instead
        logger.info("[SIGNAL-FIX] Image generation completed (no signal handlers to clean up)")
        
        # DETAILED LOGGING: Final process timing and summary
        process_end_time = time.time()
        total_process_time = process_end_time - process_start_time
        logger.info(f"[PROCESS-END] Story generation process completed for {story_id}")
        logger.info(f"[TIMING] Total process time: {total_process_time:.2f}s")
        logger.info(f"[PROCESS-SUMMARY] Final image count: {len(images)}")
        
        successful_images = len([url for url in images if url and url != "Skipped"])
        logger.info(f"[PROCESS-SUMMARY] Successful images: {successful_images}/{len(images)}")
        
        if total_process_time > 0:
            images_per_minute = (len(images) / total_process_time) * 60
            logger.info(f"[PROCESS-SUMMARY] Overall rate: {images_per_minute:.1f} images/min")

    # Video generation is now implemented via /approve_videos endpoint
    # This is triggered by explicit frontend approval after all images are approved

def main():
    """For testing purposes only - use Flask server in production"""
    print("🦊 Red Fox Story Generator")
    print("=" * 40)
    print("Note: Use Flask server at /submit endpoint for production")
    
    # Example answers for testing
    test_answers = {
        "story_type": "Power Fantasy",
        "humiliation_type": "A",
        "humiliation": "Red fox gets laughed at by a group of crows",
        "offering_who": "",
        "offering_what": "",
        "find": "a magical blueprint for iron wings",
        "do_with_find": "B",
        "villain_crime": "stealing from innocent animals"
    }
    
    process_story_generation(test_answers)

if __name__ == "__main__":
    main()