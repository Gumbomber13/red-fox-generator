# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Python Environment
- Install dependencies: `pip install -r requirements.txt`
- Run Flask server: `python flask_server.py`
- Direct pipeline test: `python Animalchannel.py` (requires environment setup)

### Environment Setup
Create a `.env` file with these required variables:
- `OPENAI_API_KEY`: OpenAI API key for story generation and DALL-E image generation
- `TELEGRAM_TOKEN`: Telegram bot token for approval workflow
- `TELEGRAM_CHAT_ID`: Telegram chat ID for notifications
- `GOOGLE_SHEET_ID`: Google Sheets ID for story tracking
- `CLOUDINARY_PRESET`: Cloudinary preset for image uploads
- `CLOUDINARY_URL`: Cloudinary URL for image hosting
- `HAILUO_AUTH`: Hailuo API authentication for video generation
- `KLING_API_KEY`: Kling API key for video generation
- `USE_GOOGLE_AUTH`: Set to "true" to enable Google Sheets integration
- `REDIS_URL`: Redis connection URL for Flask-SSE (optional, falls back to in-memory)

### Service Account
Place Google service account JSON at `/etc/secrets/service-account.json` for Google Sheets integration.

## Architecture Overview

### Core Components

**Flask Server (`flask_server.py`)**
- REST API endpoints:
  - `/submit`: Generates and returns 20 story scenes (no image generation)
  - `/approve_scenes`: Starts background image generation process
  - `/stream`: Server-Sent Events endpoint for real-time image updates
  - `/health`: Health check endpoint
  - `/story/<story_id>`: Polling endpoint for SSE fallback
- Session management via in-memory `active_stories` dict
- Uses multiprocessing for background story generation
- Flask-SSE with Redis support or in-memory fallback

**Story Generation Pipeline (`Animalchannel.py`)**
- Main functions: `process_story_generation()` and `process_story_generation_with_scenes()`
- Flow: Quiz answers → System prompt → OpenAI 20-scene generation → Visual prompt creation → Prompt standardization → Async DALL-E image generation → Cloudinary upload
- Optional integrations: Telegram approval, Google Sheets tracking, video generation (Kling/Hailuo)
- Comprehensive logging throughout pipeline for debugging
- Async image generation using httpx for improved performance

**Frontend (`index.html`)**
- Single-page application with branching quiz logic
- Real-time image display with SSE connections and polling fallback
- 20 editable scene text boxes with auto-resize functionality
- Event handling for `image_ready`, `story_complete`, and `story_error`
- Exponential backoff retry mechanism for connection resilience

### Data Flow
1. User completes quiz in `index.html`
2. Form data sent to Flask `/submit` endpoint, returns generated scenes
3. Frontend displays scenes in editable text boxes with auto-resize
4. User modifies scenes and clicks "Approve Scenes" button
5. Approved scenes sent to `/approve_scenes`, returns `story_id`
6. Frontend opens SSE connection to `/stream?channel={story_id}`
7. Flask server launches multiprocessing `process_story_generation_with_scenes()`
8. Background process: Scenes → Visual prompts → Standardization → Async DALL-E generation → Cloudinary upload
9. SSE events emitted for each completed image with real-time updates
10. Frontend updates image grid in real-time or falls back to polling
11. Optional: Telegram approval and Google Sheets tracking
12. Optional: Final video generation via Kling/Hailuo APIs

### Key Integration Points
- **OpenAI**: Scene generation (GPT), visual prompt creation, image generation (DALL-E 3)
- **Cloudinary**: Image hosting and URL generation for frontend display
- **Flask-SSE + Redis**: Real-time event streaming with fallback to in-memory
- **Telegram**: Optional approval workflow for generated images
- **Google Sheets**: Optional prompt storage and progress tracking
- **Kling/Hailuo**: Optional video generation from final image sets

### Error Handling & Resilience
- Comprehensive logging throughout all pipeline stages
- Graceful fallback for optional services (Telegram, Google Sheets)
- SSE with exponential backoff retry and polling fallback
- Async image generation with proper error handling
- Environment variable validation with warnings
- Multiprocessing isolation prevents main server crashes

## Development Notes

### Story Structure Format
Stories follow a strict 20-scene "Power Fantasy" narrative:
- Scenes 1–4: Underdog setup (rejection, sadness)
- Scenes 5–6: Discovery of something powerful
- Scenes 7–8: First failure or obstacle
- Scenes 9–10: Training/building montage
- Scenes 11–12: Transformation
- Scenes 13–14: Power display
- Scenes 15–19: Challenge, justice, redemption
- Scene 20: Closing triumph and symbolism

### Critical Functions

**Flask Server (`flask_server.py`):**
- `emit_image_event()`: Publishes SSE events for real-time updates
- `send_heartbeat()`: Maintains SSE connection with periodic pings
- Session tracking via `active_stories` dict with `story_id` keys

**Story Pipeline (`Animalchannel.py`):**
- `generate_story()`: Creates 20 scenes from quiz answers via OpenAI
- `create_prompts()`: Converts scenes to detailed visual prompts
- `standardize_prompts()`: Ensures visual consistency across prompts
- `generate_async()`: Async DALL-E image generation using httpx
- `process_image()`: Orchestrates generation → upload → approval flow

**Frontend Event System:**
- SSE connection with exponential backoff (1s, 3s, 5s delays, max 3 retries)
- Polling fallback when SSE fails (5-second intervals)
- Auto-resize textareas with scroll support for long content

---

## Implementation Status

All major features have been implemented and tested:
- ✅ Scene editing UI with auto-resize textareas
- ✅ Real-time SSE image updates with polling fallback
- ✅ Async image generation with multiprocessing
- ✅ Comprehensive logging throughout pipeline
- ✅ Redis SSE configuration with in-memory fallback
- ✅ Frontend robustness and error handling

### Recent Major Enhancements (2025-07-18)
- **Async Image Generation**: Replaced synchronous DALL-E calls with async httpx implementation
- **Multiprocessing**: Moved story generation to background processes for better performance
- **Enhanced Logging**: Added comprehensive logging throughout the entire pipeline
- **SSE Resilience**: Implemented exponential backoff retry with polling fallback
- **Frontend Improvements**: Auto-resize textareas, robust scene handling, real-time updates
- **Redis Integration**: Proper Flask-SSE Redis configuration with in-memory fallback

## Logs

### Actions Taken - 2025-07-18
- **Added Logs section**: Created this section to track all actions and modifications made to the codebase
- **Todo tracking**: Implemented systematic task tracking using TodoWrite tool
- **Verified implementation status**: Confirmed all checkmarked features are actually implemented:
  - ✅ Auto-resize textareas found in index.html
  - ✅ Async image generation with httpx confirmed in Animalchannel.py
  - ✅ Multiprocessing implementation verified in flask_server.py
  - ✅ Redis SSE configuration with fallback confirmed
  - ✅ Exponential backoff retry mechanism verified in frontend
- **Code quality verification**: Checked Python syntax compilation, imports usage, and error handling - all optimal