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
- REST API with `/submit` endpoint for story generation (returns story_id)
- `/health` endpoint for service monitoring
- `/story/<story_id>` endpoint for checking story status
- `/approve_scenes` endpoint for handling scene approval and starting image generation
- Server-Sent Events (SSE) via `/stream` endpoint for real-time image updates
- Handles form data from frontend and triggers async story pipeline

**Story Generation Pipeline (`Animalchannel.py`)**
- Multi-stage AI content generation pipeline
- Processes user answers through OpenAI GPT-4o for story creation
- Generates 20-scene visual stories with image and video content
- Integrates with multiple external services (Telegram, Google Sheets, Cloudinary)
- Emits real-time SSE events as images are generated (`emit_image_event` in flask_server)

**Frontend (`index.html`)**
- Interactive quiz interface for story customization
- Branching question flow based on user selections
- Real-time image display via EventSource SSE connection
- Image grid with loading states and progress tracking
- Scene editing interface with 20 editable text boxes for user modification

### Data Flow
1. User completes quiz in `index.html`
2. Form data sent to Flask `/submit` endpoint, returns generated scenes
3. Frontend displays scenes in editable text boxes
4. User modifies scenes and clicks "Approve Scenes" button
5. Approved scenes sent to `/approve_scenes` endpoint, returns unique `story_id`
6. Frontend opens EventSource connection to `/stream?channel={story_id}`
7. Backend starts async `process_story_generation_with_scenes()` with approved scenes and story_id
8. System prompt built using `build_system_prompt()`
9. Scenes converted to visual prompts via `create_prompts()`
10. Prompts standardized for consistent art style via `standardize_prompts()`
11. Google Sheet created for tracking story progress
12. For each scene: Images generated via DALL-E 3 and uploaded to Cloudinary
13. Real-time SSE events emitted to frontend as each image completes
14. Telegram approval workflow for each generated image
15. Video generation using Kling or Hailuo APIs
16. Final content stored in Google Sheets

### Key Integration Points
- **OpenAI**: Story generation, prompt creation, image generation
- **Google Sheets**: Story tracking and progress management
- **Telegram**: Manual approval workflow for generated content
- **Cloudinary**: Image hosting and management
- **Kling/Hailuo**: Video generation from static images
- **Redis**: Backend for Flask-SSE real-time event streaming
- **Flask-SSE**: Server-Sent Events for real-time image updates

### Error Handling
- Graceful degradation when services are unavailable
- Environment variable validation with warnings
- Google Sheets service availability checks
- Comprehensive exception handling in Flask endpoints
- SSE connection retry logic with exponential backoff
- Fallback to legacy behavior if real-time features fail

## Development Notes

### Real-time Image Display Architecture
The system uses Server-Sent Events (SSE) to provide real-time image updates:

**Backend Implementation:**
- `flask_server.py` generates unique story IDs and maintains active story sessions
- `emit_image_event()` function sends SSE events when images are ready
- `process_image()` in `Animalchannel.py` triggers events after image generation/approval
- Redis backend supports horizontal scaling of SSE connections

**Frontend Implementation:**
- `initializeImageGrid()` creates 20 image slots with loading states
- `startImageEventStream()` opens EventSource connection with automatic retry
- `displayImage()` updates slots as images arrive
- Progress bar shows real-time completion status

**Key Functions:**
- `flask_server.emit_image_event()` - Emits SSE events for image completion
- `Animalchannel.process_image()` - Modified to accept story_id and emit events
- `index.html:startImageEventStream()` - Handles SSE connection and events

### Story Structure
Stories follow a strict 20-scene "Power Fantasy" format:
- Scenes 1-4: Underdog setup (humiliation, loneliness, exclusion)
- Scenes 5-6: Spark of ambition (discovery of power source)
- Scenes 7-8: Failed attempt (initial failure and mockery)
- Scenes 9-10: Training/building montage
- Scenes 13-14: Power reveal and demonstration
- Scenes 15-19: Test, victory, and celebration
- Scene 20: Final triumph

### Content Generation Flow
The system uses multiple OpenAI calls:
1. Scene generation (structured JSON response)
2. Visual prompt creation (detailed image descriptions)
3. Prompt standardization (consistent art style and character descriptions)

### External Dependencies
- Python 3.10+ environment
- Active internet connection for API calls
- Service account credentials for Google Sheets
- Telegram bot setup for approval workflow
- Redis server for SSE functionality (optional, falls back to in-memory)

### Technical Implementation Notes

**Session Management:**
- Each story generation creates a unique UUID story_id
- `active_stories` dict tracks progress and images for each session
- Story sessions are memory-based (consider persistence for production scaling)

**Image Generation Flow:**
- `process_image()` handles generation, upload, and Telegram approval
- Images are uploaded to Cloudinary before approval workflow
- SSE events are emitted only after successful approval
- Retry logic exists for failed image generations

**Frontend Event Handling:**
- EventSource connects to `/stream?channel={story_id}`
- Event types: `image_ready`, `story_complete`, `story_error`
- Automatic reconnection with exponential backoff (max 3 retries)
- Graceful degradation if SSE connection fails

 Goals: insert (check) next to each goal when completed
Scene Editing UI
✓ Show 20 editable text boxes after quiz is submitted

✓ Pre-fill each box with a corresponding scene from OpenAI

✓ Allow user to modify any scene before submission

✓ Add "Approve Scenes" button to proceed
--
 Logs: (Write everything you do under here)
- Implemented Scene Editing UI feature
- Modified flask_server.py /submit endpoint to return generated scenes instead of starting image generation
- Added new /approve_scenes endpoint to handle scene approval and start image generation
- Created process_story_generation_with_scenes function in Animalchannel.py to handle pre-approved scenes
- Updated frontend to show scenes editor after quiz submission
- Added continueWithScenes() function to collect edited scenes and submit to /approve_scenes endpoint
- Changed button text from "Continue" to "Approve Scenes"
- All 4 goals for Scene Editing UI completed successfully