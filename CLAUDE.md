# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Python Environment
- Install dependencies: `pip install -r requirements.txt`
- Run Flask server: `python flask_server.py`
- Test main pipeline: `python Animalchannel.py`

### Environment Setup
Create a `.env` file with these required variables:
- `OPENAI_API_KEY`: OpenAI API key for story generation
- `TELEGRAM_TOKEN`: Telegram bot token for approval workflow
- `TELEGRAM_CHAT_ID`: Telegram chat ID for notifications
- `GOOGLE_SHEET_ID`: Google Sheets ID for story tracking
- `CLOUDINARY_PRESET`: Cloudinary preset for image uploads
- `CLOUDINARY_URL`: Cloudinary URL for image hosting
- `HAILUO_AUTH`: Hailuo API authentication for video generation
- `KLING_API_KEY`: Kling API key for video generation
- `USE_GOOGLE_AUTH`: Set to "true" to enable Google Sheets integration
- `REDIS_URL`: Redis connection URL for real-time SSE functionality (optional, defaults to localhost)

### Service Account
Place Google service account JSON at `/etc/secrets/service-account.json` for Google Sheets integration.

## Architecture Overview

### Core Components

**Flask Server (`flask_server.py`)**
- REST API with:
  - `/submit`: Generates and returns initial story scenes (no image generation yet)
  - `/approve_scenes`: Starts image generation using user-edited scenes
  - `/stream`: Server-Sent Events (SSE) endpoint for real-time image updates
  - `/health`: Status check endpoint
  - `/story/<story_id>`: Optional status polling endpoint for future extensions
- Maintains in-memory `active_stories` dict for session tracking
- Emits SSE updates using `flask_sse` backed by Redis or in-memory

**Story Generation Pipeline (`Animalchannel.py`)**
- Accepts quiz answers → Builds system prompt → Generates 20 scenes (JSON)
- Generates prompts from scenes and refines for visual consistency
- Triggers image generation, uploads to Cloudinary, sends approval message via Telegram
- Emits SSE event after each image is approved
- Uses Google Sheets to track prompt and progress (optional if `USE_GOOGLE_AUTH` is false)

**Frontend (`index.html`)**
- Hosted on Vercel (connected GitHub repo must point to latest project)
- Quiz form with branching logic based on "Offering" vs "Humiliation"
- Shows 20 editable scene boxes after form submission
- Sends approved scenes to `/approve_scenes` on "Approve Scenes"
- Opens EventSource connection to `/stream?channel={story_id}`
- Displays 20 image slots with real-time loading states

### Data Flow
1. User completes quiz in `index.html`
2. Form data sent to Flask `/submit` endpoint, returns generated scenes
3. Frontend displays scenes in editable text boxes
4. User modifies scenes and clicks "Approve Scenes" button
5. Approved scenes sent to `/approve_scenes`, returns `story_id`
6. Frontend opens SSE connection to `/stream?channel={story_id}`
7. Flask server launches async `process_story_generation_with_scenes()`
8. Scenes → Prompts → Refined → DALL·E image generation
9. Image URLs uploaded to Cloudinary
10. SSE events emitted for each completed image
11. Telegram bot sends image for manual approval (optional)
12. Final video generation via Kling/Hailuo (optional)
13. Google Sheet updated with prompt + tracking info

### Key Integration Points
- **OpenAI**: Scene generation, visual prompt creation, image generation (via DALL·E)
- **Google Sheets**: Prompt storage, scene tracking
- **Telegram**: Approval system for generated images (optional)
- **Cloudinary**: Hosts image URLs accessible to frontend
- **Kling / Hailuo**: Generates videos from final image sets
- **Redis**: Used by Flask-SSE to manage persistent event channels
- **Vercel**: Frontend hosting platform (must match correct repo and deployment branch)

### Error Handling
- Graceful fallback if Google Sheets or Telegram is unavailable
- Flask returns detailed errors for debugging
- SSE client uses exponential backoff on reconnect
- Skipped images log warnings but do not crash pipeline
- Google Sheets writes wrapped in `try/except` with guard for `sheets_service is None`

## Development Notes

### Real-time Image Display Architecture

**Backend Implementation:**
- `flask_server.py` tracks each story_id in `active_stories`
- Each image completion triggers `emit_image_event()` with `{ story_id, image_url }`
- SSE uses Redis if `REDIS_URL` is provided, else falls back to in-memory queue

**Frontend Implementation:**
- `startImageEventStream()` opens an EventSource to `/stream?channel={story_id}`
- Listens for `image_ready` and `story_complete` events
- `displayImage()` updates image grid in-place as URLs arrive
- Connection retry logic uses up to 3 reconnect attempts

### Story Structure
Stories follow a strict 20-scene "Power Fantasy" format:
- Scenes 1–4: Underdog setup (rejection, sadness)
- Scenes 5–6: Discovery of something powerful
- Scenes 7–8: First failure or obstacle
- Scenes 9–10: Training/building montage
- Scenes 11–12: Transformation
- Scenes 13–14: Power display
- Scenes 15–19: Challenge, justice, redemption
- Scene 20: Closing triumph and symbolism

### Content Generation Flow
1. OpenAI generates story scenes (JSON)
2. Claude turns them into detailed visual prompts
3. Prompts refined with consistent tone/character style
4. Each scene passed to DALL·E 3 to generate image
5. Images uploaded to Cloudinary
6. SSE image update sent to frontend
7. Final scenes submitted to Kling or Hailuo for video generation

### External Dependencies
- Python 3.10+ runtime
- Vercel account (for frontend)
- Redis server (for live SSE updates; optional)
- Cloudinary account
- Google service account (Sheets)
- OpenAI + Telegram + Kling/Hailuo API access

### Technical Implementation Notes

**Session Management:**
- `uuid4()` used to generate unique story_id per user submission
- In-memory tracking only — not persisted across restarts (optional future: Redis or DB)

**Image Generation Flow:**
- `process_image()` handles prompt → image → upload → approve → emit
- SSE only fires after Telegram approval or immediate pass-through

**Frontend Event Handling:**
- Event types: `image_ready`, `story_complete`, `story_error`
- Retry mechanism reconnects EventSource if closed (max 3 retries)
- Display updates with real-time image population per scene index

---

## Goals: insert (check) next to each goal when completed

### Scene Missing Analysis & Fixes
✓ Verify frontend behavior when scenes are missing
✓ Confirm how missing scenes are displayed in index.html
✓ Check if placeholders like (SceneX missing) are coming directly from the backend or created by the frontend
✓ Trace backend response from /submit
✓ Inspect flask_server.py to see what the /submit endpoint returns
✓ Confirm whether the response includes all 20 scenes
✓ Log the full scene payload in the response
✓ Audit generate_story() return values
✓ Check how generate_story() constructs the final scene list
✓ Identify any fallback or placeholder logic like (SceneX missing)
✓ Ensure it always returns a list of 20 strings
✓ Log and validate OpenAI API response
✓ Print the full response.choices[0].message.content from OpenAI
✓ Ensure the JSON returned includes all 20 scene keys (Scene1 to Scene20)
✓ Add debug output if scenes are missing from the raw JSON
✓ Ensure build_system_prompt() provides proper instructions
✓ Review how the system prompt instructs OpenAI to return scenes
✓ Make sure the prompt clearly asks for exactly 20 scenes in JSON format
✓ Evaluate retry logic (if any)
✓ Determine if the code currently retries scene generation when results are incomplete
✓ If not, suggest adding one retry if scene count is < 20
✓ Confirm scene keys and indexing
✓ Ensure no off-by-one or naming issues (e.g., scene20 vs Scene20)
✓ Confirm the frontend loop displays all 20 inputs even if some scene data is missing
✓ Propose fixes after analysis
✓ Based on findings, propose targeted fixes (e.g., prompt tweaks, fallback improvements, frontend guards)



---

## Logs: (Write everything you do under here)
- Implemented Scene Editing UI feature  
- Modified flask_server.py `/submit` endpoint to return generated scenes instead of starting image generation  
- Added new `/approve_scenes` endpoint to handle scene approval and start image generation  
- Created `process_story_generation_with_scenes` function in Animalchannel.py to handle pre-approved scenes  
- Updated frontend to show scenes editor after quiz submission  
- Added `continueWithScenes()` function to collect edited scenes and submit to `/approve_scenes` endpoint  
- Changed button text from "Continue" to "Approve Scenes"  
- All 4 goals for Scene Editing UI completed successfully  

### Scene Missing Analysis & Fixes Completed:
- **Frontend Analysis**: Verified that missing scenes display as "(Scene X missing)" placeholder text in index.html:413
- **Backend Tracing**: Confirmed flask_server.py `/submit` endpoint converts scenes list to dict and returns JSON response
- **Payload Logging**: Added comprehensive logging to flask_server.py to track scene generation and responses
- **OpenAI Response Validation**: Enhanced generate_story() function with detailed logging of raw OpenAI responses
- **Fallback Logic**: Identified existing fallback logic that creates "(SceneX missing)" for missing scenes
- **System Prompt Enhancement**: Updated build_system_prompt() to include explicit "CRITICAL REQUIREMENT" for exactly 20 scenes
- **Retry Logic Implementation**: Added retry mechanism (2 attempts) for scene generation when scenes are missing
- **Debug Output**: Added comprehensive debug logging for missing scene detection and validation
- **Scene Key Validation**: Confirmed proper Scene1-Scene20 indexing with no off-by-one errors
- **Frontend Robustness**: Verified frontend displays all 20 input boxes even with missing scene data
- **Improved Error Handling**: Enhanced error handling with fallback to placeholder scenes if OpenAI API fails
- **Enhanced User Prompt**: Updated OpenAI user prompt to explicitly request "exactly 20 scenes" and "do not skip any scene numbers"
- All 26 goals for Scene Missing Analysis & Fixes completed successfully  
