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
                response_format={"type": "json_object"}
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
            timeout=120
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
            timeout=120
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
    """Async version of image generation using httpx"""
    try:
        client = httpx.AsyncClient()
        logger.info("Async client created")
    except Exception as e:
        logger.error(f"Async client init error: {e}")
        raise
    
    try:
        logger.info("Posting to DALL-E API")
        # Use OpenAI client for DALL-E generation (synchronous)
        response = openai_client.images.generate(model="dall-e-3", prompt=prompt, size="1024x1024", n=1)
        img_url = response.data[0].url
        logger.info("DALL-E post complete")
        
        # Use httpx to download the image asynchronously
        img_response = await client.get(img_url)
        img_data = img_response.content
        logger.info(f"Image data received: {len(img_data)} bytes")
        await client.aclose()
        return img_data
    except Exception as e:
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

    logger.info(f"Starting image generation loop for {len(std_prompts)} prompts")
    
    def timeout_handler(signum, frame):
        raise TimeoutError("Generation timed out")
    
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(3600)  # 1hr max
    
    images = []
    try:
        for i, prompt in enumerate(std_prompts, 1):
            logger.info(f"Processing image {i+1}: {prompt[:50]}...")
            update_sheet(idea, str(i), 'Prompt', prompt)
            try:
                img_url = process_image(str(i), prompt, idea, story_id)
                if img_url:
                    images.append(img_url)
                else:
                    logger.warning(f"Skipping image {i} due to generation failure")
                    images.append("Skipped")
            except Exception as e:
                logger.error(f"Image process error {i+1}: {e}")
                images.append("Skipped")
                continue
    except TimeoutError as e:
        logger.error(f"Timeout: {e}")
    finally:
        signal.alarm(0)

    for i, img_url in enumerate(images, 1):
        if img_url and img_url != "Skipped":
            process_video(str(i), img_url, idea)
        else:
            logger.info(f"Skipping video generation for image {i} (no valid image URL)")

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