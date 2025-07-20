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
from googleapiclient.discovery import build
from google.oauth2 import service_account
from openai import OpenAI
from dotenv import load_dotenv

# Rate limiting constants for DALL-E API compliance
MAX_CONCURRENT = 10  # Semaphore limit for concurrent requests
MAX_IMAGES_PER_MIN = 15  # OpenAI DALL-E rate limit
BATCH_SIZE = 10  # Process images in batches to respect rate limits

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





def build_system_prompt(answers):
    prompt = """
You are a creative assistant that generates emotionally-driven Power Fantasy stories starring a red fox. These stories are told entirely through images only — with no dialogue, narration, or text.
The red fox begins each story powerless or humiliated. Through grit, invention, or training, he transforms into something strong. His journey is emotional, exaggerated, and symbolic — like a mini cinematic redemption arc. 

CRITICAL REQUIREMENT: Each story must be exactly 20 scenes, with each scene being a self-contained visual moment. You must provide all 20 scenes numbered Scene1, Scene2, Scene3, ... Scene20 in your JSON response. Do not skip any scene numbers.

Story Structure (20 Scenes)
1. Underdog Setup (Scenes 1–3)
The red fox is weak, dirty and poor. Each scene shows a different hardship or form of rejection in a visually expressive environment.
Scene 1. Scene of Humiliation - The Red Fox is humiliated in some way he is either rejected by a pretty and wealthy girl fox, or he is laughed at by a group of another type of animal While he stands devastated. 
	-Optionally this could be the Scene of Offering, where he is making an offering to a girl fox. Ie. a flower, a ring, or simply his hand for a hand holding etc. (If this option is chosen the optional choice must also be made in scene 2)
Scene 2. Scene of Loneliness - A scene that displays his loneliness and poverty
	-Optional (required if you did the optional choice for scene 1) – Scene of Rejection- the girl fox rejects his offering. Ie laughs at him, destroys flower, or puts her hand in his face etc.
Scene 3. What others have - A scene of the fox girl he liked with another man or sees friends hanging out and having fun without him 
Scene 4. Reaction - A scene of the red fox crying or being sad/devestated in some way that he is left out
2. Spark of Ambition (Scenes 5-6)
The fox discovers a visual trigger — a blueprint, or he meets a master who trains him, or he finds some ancient magical relic with a great power— that inspires a desire for transformation. The fox is still weak dirty and poor but his demeanor is hopeful
Scene 5. Discover – The fox discovers a visual trigger that inspires a hope of a way out of his situation
Scene 6. The fox reaches for the magical object or begins training with his master or begins building the powerful technology
3. Failed Attempt (Scenes 7–8)
The fox tries to act or fight back — and fails. He may build something that doesn't work or attempt something too early.
Scene 7. The fox has some sort of mishap, he either electrecutes himself, uses the magic item on himself, or slips while trying to learn his new skills. While people in the background laugh at him
Scene 8. The fox lies defeated on the ground, bruised and embarrassed, looking up at the sky with determination growing in his eyes
4. Montage: Training / Building (Scenes 9–10)
He commits to change. These scenes show him building, lifting, planning, improving, or imagining.
Scene 9. More disciplined training or building - first session
Scene 10. More disciplined training or building - advanced session
5. Transformation (Scenes 11–12)
The fox undergoes a dramatic change, becoming stronger, more capable, and ready to face his challenges.
Scene 11. The fox undergoing transformation - becoming stronger, more confident, cleaner, and more powerful
Scene 12. The fox's transformation is complete - he stands tall, confident, and ready to face the world
6. Power Reveal (Scenes 13–14)
He unveils his transformation — mech, wings, elemental form, or super reflexes — and shocks the world around him.
Scene 13: His new power his finished or revealed
Scene 14: His power is displayed and others look in awe
7. Test or Consequence (Scenes 15–20)
The new power causes unexpected damage or a new challenge appears. These scenes increase the emotional complexity.
Scene 15: Whoever rejected the red fox from earlier, is committing a crime and getting away with it
Scene 16: The red fox beats up the criminal with his new power
Scene 17: The police takes The criminal rejector away as he is crying (No fox in shot)
Scene 18: Everyone cheers for the fox
Scene 19: The fox walks down a street with sunglasses on and a really sexy woman while everyone is flashing pictures at him
Scene 20: The fox stands on a mountaintop or high building, looking out over the city with confidence and satisfaction, having completed his transformation from underdog to hero 

Scene Rules
One single action per scene.
 Never show multiple actions in one scene. For example: if the red fox builds wings, that is one scene. If he tests them, that is a separate scene.


No names.
 Always refer to the protagonist only as “the red fox.” No other characters should be named either.


No dialogue or narration.
 All storytelling must be conveyed through visuals only — body language, props, expression, setting, light, color, etc.


Each scene must be visually distinct.
 Do not chain or transition between scenes. Each is its own visual beat, like a comic panel or animated shot.


Use exaggerated and symbolic visuals.
 Think glowing blueprints, spark-filled workshops, massive bullies, oversized tools, etc.


Keep the arc tight and emotional.
 Every story must follow one red fox, from weakness to power to growth — no B-stories, no diversions.

"""
    # Fill in placeholders based on answers
    if answers['humiliation_type'].lower() == 'a':
        prompt = prompt.replace("The Red Fox is humiliated in some way he is either rejected by a pretty and wealthy girl fox, or he is laughed at by a group of another type of animal While he stands devastated.", answers['humiliation'])
    else:
        prompt = prompt.replace("Scene 1. Scene of Humiliation - The Red Fox is humiliated in some way he is either rejected by a pretty and wealthy girl fox, or he is laughed at by a group of another type of animal While he stands devastated.", f"Scene 1. Scene of Offering - the red fox is making an offering to {answers['offering_who']}. Ie. {answers['offering_what']}")
        prompt = prompt.replace("Scene 2. Scene of Loneliness - A scene that displays his loneliness and poverty", f"Scene 2. Scene of Rejection - {answers['offering_who']} rejects his offering. Ie laughs at him, destroys {answers['offering_what']}, or puts her hand in his face etc.")

    prompt = prompt.replace("a blueprint, or he meets a master who trains him, or he finds some ancient magical relic with a great power", answers['find'])
    if answers['do_with_find'].lower() == 'a':
        prompt = prompt.replace("begins building the powerful technology", "begins training with his master")
        prompt = prompt.replace("building", "training")
    
    # Replace villain crime if provided
    if answers.get('villain_crime'):
        prompt = prompt.replace("committing a crime and getting away with it", f"committing {answers['villain_crime']} and getting away with it")
    
    return prompt

def generate_story(system_prompt):
    max_retries = 2
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
                print(f"Retrying... (attempt {attempt + 1}/{max_retries})")
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
# Overview 
You are a creative assistant that helps generate engaging content for a child series of a red panda that saves some sort of cute animal from some sort of predator or tragic situation. These are visual stories that are told in images and have no dialogue. Your job is to receive a series of 20 scenes  turn the scenes into a series of visual kling image prompts of the first frame of each scene. These prompts should be visual descriptions that describe each aspect of the image in a very detailed and precise way.Only output the prompts with no explanation or commentary. 

#Rules
1.Be hyper-detailed in your description
2.Make sure that all characters have serious or sad expressions before the victim gets saved.
3.Make sure the characters have happy expressions after they are saved.
3.Make sure the animals are not wearing any clothes
4.Do not prompt for midair or jumping characters unless they are flying characters
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
You are a creative assistant that helps generate engaging content for a child series of a red panda that saves some sort of cute animal from some sort of predator or tragic situation. These are visual stories that are told in images and have no dialogue. Your job is to receive a series of 20 prompts and add a starting description to the beginning of the prompt and a character description every time a character (person, animal) is mentioned

#ArtStyle
Make sure the art style for each prompt starts with this description: Stylized, cinematic 3D animation with a soft, high-resolution render similar to modern feature films. Materials are physically accurate with subtle texture — plush fur, are highly detailed yet slightly softened for a toy-like finish. Lighting is warm and naturalistic, with golden hour tones and soft shadows that enhance depth and realism. The overall composition balances realism and whimsy, avoiding harsh contrasts for a friendly, vibrant visual tone.

And make sure all of the characters are described in this style each time:
Wholesome and animated with childlike wonder and charm. Features are rounded and expressive, with large, bright eyes and an exaggerated facial structure that emphasizes cuteness and emotional connection. The character design evokes a sense of innocence, curiosity, and adventure — like a beloved sidekick from a heartfelt animated film.

#Rules
1.Make sure the artstyle and description of the characters and setting are explained in the same way repeatedly for every prompt
2.Make sure every prompt has a description for each character
3.Use the art style descriptions above in every single prompt
4.Dont say “same art style and character description. Actually describe it for every single prompt
5. Do not remove anything from prompt given to you, output the same text with only the picture and character descriptions added
""".replace("red panda", "red fox").replace("20", "20")  # Adjust
    
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
    
    try:
        # Add 120s timeout to httpx client
        client_start = time.time()
        client = httpx.AsyncClient(timeout=120.0)
        client_elapsed = time.time() - client_start
        logger.debug(f"[ASYNC-DEBUG] httpx client created in {client_elapsed:.3f}s with 120s timeout")
    except Exception as e:
        logger.error(f"[ASYNC-DEBUG] Async client init error: {type(e).__name__}: {e}")
        raise
    
    try:
        dalle_start = time.time()
        logger.debug(f"[ASYNC-DEBUG] Starting DALL-E API call with 120s timeout")
        # Use OpenAI client for DALL-E generation with timeout
        response = openai_client.images.generate(
            model="dall-e-3", 
            prompt=prompt, 
            size="1024x1024", 
            n=1,
            timeout=120.0
        )
        dalle_elapsed = time.time() - dalle_start
        img_url = response.data[0].url
        logger.debug(f"[ASYNC-DEBUG] DALL-E API completed in {dalle_elapsed:.2f}s, got URL: {img_url[:50]}...")
        
        # Use httpx to download the image asynchronously (inherits client timeout)
        download_start = time.time()
        logger.debug(f"[ASYNC-DEBUG] Starting image download from: {img_url}")
        img_response = await client.get(img_url)
        download_elapsed = time.time() - download_start
        img_data = img_response.content
        total_elapsed = time.time() - start_time
        logger.debug(f"[ASYNC-DEBUG] Image download completed in {download_elapsed:.2f}s, data size: {len(img_data)} bytes")
        logger.debug(f"[ASYNC-DEBUG] Total generate_async time: {total_elapsed:.2f}s (DALL-E: {dalle_elapsed:.2f}s, Download: {download_elapsed:.2f}s)")
        await client.aclose()
        return img_data
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
            logger.debug(f"Attempting DALL-E with prompt (length {len(current_prompt)}): {current_prompt}")
            return asyncio.run(generate_async(current_prompt))
        except Exception as e:
            logger.error(f"DALL-E error details: {e.response.json() if hasattr(e, 'response') else str(e)}")
            if retry < max_retries - 1:
                wait_time = 5 * (retry + 1)  # 5, 10, 15 seconds
                logger.warning(f"Retry {retry + 1} for generate: {e}")
                time.sleep(wait_time)
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
    async with semaphore:
        start_time = time.time()
        logger.info(f"[ASYNC] Starting image {classifier} with prompt: {prompt[:50]}...")
        
        try:
            # Sanitize prompt before generation
            prompt = sanitize_prompt(prompt)
            logger.debug(f"[ASYNC-ERROR] Image {classifier} sanitized prompt: {prompt[:100]}...")
            
            # Generate and upload image with retries
            try:
                img_data = await generate_image_async_with_retries(prompt)
                logger.debug(f"[ASYNC-ERROR] Image {classifier} generation completed, data size: {len(img_data) if img_data else 0}")
            except Exception as gen_error:
                logger.error(f"[ASYNC-ERROR] Image {classifier} generation failed: {type(gen_error).__name__}: {gen_error}")
                raise gen_error
            
            try:
                url = upload_image(img_data)
                logger.debug(f"[ASYNC-ERROR] Image {classifier} upload completed: {url}")
            except Exception as upload_error:
                logger.error(f"[ASYNC-ERROR] Image {classifier} upload failed: {type(upload_error).__name__}: {upload_error}")
                raise upload_error
            
            elapsed = time.time() - start_time
            logger.info(f"[ASYNC] Successfully completed image {classifier} in {elapsed:.2f}s: {url}")
            
            # Update sheet if available
            try:
                update_sheet(sheet_title, classifier, 'Picture Generation', url)
            except Exception as e:
                logger.warning(f"[ASYNC-ERROR] Sheet update failed for {classifier}: {type(e).__name__}: {e}")
            
            # Emit image event if story_id is provided
            if story_id:
                try:
                    from flask_server import emit_image_event
                    emit_image_event(story_id, int(classifier), url, "pending_approval")
                    logger.info(f"[APPROVAL] Emitted pending_approval for image {classifier}")
                except ImportError:
                    logger.warning(f"[ASYNC-ERROR] Could not emit image event for story {story_id}: ImportError")
                except Exception as emit_error:
                    logger.error(f"[ASYNC-ERROR] SSE emit failed for image {classifier}: {type(emit_error).__name__}: {emit_error}")
            
            return classifier, url
            
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
            
            if retry < max_retries - 1:
                wait_time = 5 * (retry + 1)  # 5, 10, 15 seconds
                logger.debug(f"[ASYNC-DEBUG] Waiting {wait_time}s before retry {retry + 2}")
                await asyncio.sleep(wait_time)
            else:
                total_elapsed = time.time() - start_time
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
    
    # Create semaphore to limit concurrent requests
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    logger.debug(f"[ASYNC-DEBUG] Semaphore created with limit {MAX_CONCURRENT}")
    
    # Split into batches to respect rate limits
    batches = [prompts_with_metadata[i:i + BATCH_SIZE] for i in range(0, len(prompts_with_metadata), BATCH_SIZE)]
    logger.debug(f"[ASYNC-DEBUG] Split into {len(batches)} batches of max size {BATCH_SIZE}")
    
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
        try:
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            logger.info(f"[ASYNC-ERROR] Batch {batch_num} gather completed with {len(batch_results)} results")
        except Exception as gather_error:
            logger.error(f"[ASYNC-ERROR] asyncio.gather failed for batch {batch_num}: {gather_error}")
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
    # Convert approved scenes dict to list format
    scenes = []
    for i in range(1, 21):
        scene_key = f"Scene{i}"
        if scene_key in approved_scenes:
            scenes.append(approved_scenes[scene_key])
        else:
            scenes.append(f"(Scene {i} missing)")
    
    logger.info(f"Starting generation for {story_id} with {len(scenes)} scenes")
    
    scenes = edit_scenes(scenes)
    prompts = create_prompts(scenes)
    std_prompts = standardize_prompts(prompts)
    
    # Debug log to check scene 16 sanitization
    if len(std_prompts) >= 16:
        logger.debug(f"Post-sanitization prompt 16 example: {std_prompts[15][:50]}")
    
    # Create new sanitized sheet for this story
    idea = generate_sheet_title()
    original_title = f"{original_answers.get('story_type', 'Power Fantasy')} Story"
    if original_answers.get('find'):
        original_title += f" - Fox finds {original_answers['find']}"
    create_sheet(idea, original_title)

    logger.info(f"Starting PARALLEL image generation for {len(std_prompts)} prompts")
    
    def timeout_handler(signum, frame):
        raise TimeoutError("Generation timed out")
    
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(3600)  # 1hr max
    
    images = []
    try:
        # Prepare data for concurrent processing
        prompts_with_metadata = []
        for i, prompt in enumerate(std_prompts, 1):
            update_sheet(idea, str(i), 'Prompt', prompt)
            prompts_with_metadata.append((i, prompt, idea))
        
        # Use async processing for parallel image generation with 10-min timeout
        def async_timeout_handler(signum, frame):
            raise TimeoutError("Async generation timed out after 10 minutes")
        
        # Set 10-minute timeout for async generation
        old_handler = signal.signal(signal.SIGALRM, async_timeout_handler)
        signal.alarm(600)  # 10 minutes
        
        try:
            concurrent_start_time = time.time()
            logger.info("[ASYNC-TIMEOUT] Starting async generation with 10-min timeout")
            results = asyncio.run(generate_images_concurrently(prompts_with_metadata, story_id))
            concurrent_elapsed = time.time() - concurrent_start_time
            logger.info(f"[ASYNC-TIMEOUT] Async generation completed in {concurrent_elapsed:.2f}s")
        except TimeoutError as timeout_e:
            logger.error(f"[ASYNC-TIMEOUT] Async generation timed out: {timeout_e}")
            raise
        finally:
            # Restore original signal handler and cancel alarm
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
        
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
        signal.alarm(0)

    # TODO: Video generation should only start after explicit frontend approval
    # Will be triggered via new /approve_videos endpoint once all images are approved
    # for i, img_url in enumerate(images, 1):
    #     if img_url and img_url != "Skipped":
    #         process_video(str(i), img_url, idea)
    #     else:
    #         logger.info(f"Skipping video generation for image {i} (no valid image URL)")

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