import os
import json
import time
import requests
import asyncio
import datetime
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from openai import OpenAI
import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Load API keys and configs from environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID", "0"))  # Default to 0 if not set
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
CLOUDINARY_PRESET = os.getenv("CLOUDINARY_PRESET")
CLOUDINARY_URL = os.getenv("CLOUDINARY_URL")
HAILUO_AUTH = os.getenv("HAILUO_AUTH")
KLING_API_KEY = os.getenv("KLING_API_KEY")

# Validate required environment variables
required_vars = {
    "OPENAI_API_KEY": OPENAI_API_KEY,
    "TELEGRAM_TOKEN": TELEGRAM_TOKEN,
    "GOOGLE_SHEET_ID": GOOGLE_SHEET_ID,
    "CLOUDINARY_PRESET": CLOUDINARY_PRESET,
    "CLOUDINARY_URL": CLOUDINARY_URL,
    "HAILUO_AUTH": HAILUO_AUTH,
    "KLING_API_KEY": KLING_API_KEY
}

for var_name, var_value in required_vars.items():
    if not var_value:
        print(f"⚠️ Warning: {var_name} environment variable is not set")

# Initialize clients only if API keys are available
if OPENAI_API_KEY:
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
else:
    openai_client = None
    print("⚠️ OpenAI client not initialized - OPENAI_API_KEY missing")

if TELEGRAM_TOKEN:
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
else:
    bot = None
    print("⚠️ Telegram bot not initialized - TELEGRAM_TOKEN missing")

# Google Sheets setup
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
creds = None
sheets_service = None

if os.getenv("USE_GOOGLE_AUTH") == "true":
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('/etc/secrets/credentials.json', SCOPES)
            creds = flow.run_console()
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    sheets_service = build('sheets', 'v4', credentials=creds)

def generate_sheet_title():
    return "Story_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

def escape_sheet_title(title):
    return "'" + title.replace("'", "''") + "'"

def get_in_progress_idea():
    result = sheets_service.spreadsheets().values().get(
        spreadsheetId=GOOGLE_SHEET_ID, range='Sheet1!A:C').execute()
    values = result.get('values', [])
    for row in values[1:]:
        if len(row) > 2 and row[2] == 'In Progress':
            return row[0]
    return None

def create_sheet(title, original_title=None):
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





def build_system_prompt(answers):
    prompt = """
You are a creative assistant that generates emotionally-driven Power Fantasy stories starring a red fox. These stories are told entirely through images only — with no dialogue, narration, or text.
The red fox begins each story powerless or humiliated. Through grit, invention, or training, he transforms into something strong. His journey is emotional, exaggerated, and symbolic — like a mini cinematic redemption arc. Each story is exactly 20 scenes, with each scene being a self-contained visual moment.

🧱 Story Structure (20 Scenes)
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
4. Montage: Training / Building (Scenes 9–10)
He commits to change. These scenes show him building, lifting, planning, improving, or imagining.
Scenes 9 & 10: More disciplined training or building. 
5. Power Reveal (Scenes 13–14)
He unveils his transformation — mech, wings, elemental form, or super reflexes — and shocks the world around him.
Scene 13: His new power his finished or revealed
Scene 14: His power is displayed and others look in awe
6. Test or Consequence (Scenes 15–17)
The new power causes unexpected damage or a new challenge appears. These scenes increase the emotional complexity.
Scene 15: Whoever rejected the red fox from earlier, is committing a crime and getting away with it
Scene 16: The red fox beats up the criminal with his new power
Scene 17: The police takes The criminal rejector away as he is crying (No fox in shot)
Scene 18: Everyone cheers for the fox
Scene 19: The fox walks down a street with sunglasses on and a really sexy woman while everyone is flashing pictures at him 

📏 Scene Rules
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
    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": "Generate the 20 scenes. Return your response as a JSON object with keys Scene1, Scene2, etc."}],
        response_format={"type": "json_object"}
    )
    scenes = json.loads(response.choices[0].message.content)
    return [scenes[f"Scene{i}"] for i in range(1, 21)]

def edit_scenes(scenes):
    """Return scenes as-is (automated version, no manual editing)"""
    print("=== GENERATED SCENES ===")
    for i, scene in enumerate(scenes, 1):
        print(f"Scene {i}: {scene}")
    print("========================")
    return scenes

def create_prompts(scenes):
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
    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": system}, {"role": "user", "content": json.dumps({"scenes": scenes}) + " Return as JSON with keys Prompt1, Prompt2, etc."}],
        response_format={"type": "json_object"}
    )
    prompts = json.loads(response.choices[0].message.content)
    return [prompts[f"Prompt{i}"] for i in range(1, 21)]

def standardize_prompts(prompts):
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
    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": system}, {"role": "user", "content": json.dumps({"prompts": prompts}) + " Return as JSON with keys Prompt1, Prompt2, etc."}],
        response_format={"type": "json_object"}
    )
    std_prompts = json.loads(response.choices[0].message.content)
    return [std_prompts[f"Prompt{i}"] for i in range(1, 21)]

def generate_image(prompt):
    response = openai_client.images.generate(model="dall-e-3", prompt=prompt, size="1024x1024", n=1)
    img_url = response.data[0].url
    img_data = requests.get(img_url).content
    return img_data

def upload_image(img_data):
    files = {'file': ('image.png', img_data, 'image/png'), 'upload_preset': (None, CLOUDINARY_PRESET)}
    response = requests.post(CLOUDINARY_URL + 'image/upload', files=files)
    return response.json()['secure_url']

async def telegram_approve_async(url, prompt, classifier):
    keyboard = [[InlineKeyboardButton("Approve", callback_data='approve'), InlineKeyboardButton("Reject", callback_data='reject')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await bot.send_photo(chat_id=TELEGRAM_CHAT_ID, photo=url, caption=f"Prompt {classifier}: {prompt}", reply_markup=reply_markup)
    # Wait for callback (simplified; in full bot, use updater)
    await asyncio.sleep(60)  # Placeholder; implement proper handler
    return True  # Assume approve for script; replace with actual logic

def telegram_approve(url, prompt, classifier):
    return asyncio.run(telegram_approve_async(url, prompt, classifier))

def reject_fix(prompt):
    """Auto-retry with original prompt (no manual intervention)"""
    print(f"Retrying with original prompt: {prompt}")
    return prompt

def process_image(classifier, prompt, sheet_title):
    while True:
        img_data = generate_image(prompt)
        url = upload_image(img_data)
        if telegram_approve(url, prompt, classifier):
            update_sheet(sheet_title, classifier, 'Picture Generation', url)
            return url
        else:
            prompt = reject_fix(prompt)
            update_sheet(sheet_title, classifier, 'Prompt', prompt)

def update_sheet(sheet_title, classifier, column, value):
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

async def choose_video_model_async():
    keyboard = [[InlineKeyboardButton("Kling", callback_data='kling'), InlineKeyboardButton("Hailuo", callback_data='hailuo')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="Choose model:", reply_markup=reply_markup)
    await asyncio.sleep(60)  # Placeholder
    return 'kling'  # Assume

def choose_video_model():
    return asyncio.run(choose_video_model_async())


def get_motion_prompt():
    # msg = bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="Motion prompt:")
    time.sleep(60)  # Wait for response
    return "user motion prompt"  # Placeholder

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
    model = choose_video_model()
    while True:
        motion_prompt = get_motion_prompt()
        video_url = generate_video(model, motion_prompt, image_url)
        if telegram_approve(video_url, motion_prompt, f"Video {classifier}"):
            update_sheet(sheet_title, classifier, 'Video Generation', video_url)
            return
        else:
            # Reject, loop for new prompt
            pass

def process_story_generation(answers):
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
        img_url = process_image(str(i), prompt, idea)
        images.append(img_url)

    for i, img_url in enumerate(images, 1):
        process_video(str(i), img_url, idea)

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