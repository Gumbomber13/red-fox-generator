# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Python Environment
- Install dependencies: `pip install -r requirements.txt`
- Run Flask server: `python flask_server.py`
- Direct pipeline test: `python Animalchannel.py` (requires environment setup)

### Testing
- Test image generation: `python test_image_gen.py`
- Test SSE functionality: `python test_sse_emit.py`
- Test full workflow: `python test_full_flow.py`
- Test frontend integration: `python test_frontend_integration.py`
- Test async hang bug fixes: `python test_async_hang_fix.py`
- Test specific story endpoint: `curl http://localhost:5000/test_emit/<story_id>`
- Interactive browser test: Open `test_browser_compatibility.html` in browser

### Environment Setup
Create a `.env` file with these variables:

**Required:**
- `OPENAI_API_KEY`: OpenAI API key for story generation and DALL-E image generation
- `CLOUDINARY_PRESET`: Cloudinary preset for image uploads
- `CLOUDINARY_URL`: Cloudinary URL for image hosting

**Optional (with graceful fallbacks):**
- `REDIS_URL`: Redis connection URL for Flask-SSE (falls back to in-memory)
- `GOOGLE_SHEET_ID`: Google Sheets ID for story tracking
- `USE_GOOGLE_AUTH`: Set to "true" to enable Google Sheets integration
- `HAILUO_AUTH`: Hailuo API authentication for video generation
- `KLING_API_KEY`: Kling API key for video generation

**Deprecated (disabled by default):**
- `ENABLE_TELEGRAM`: Set to "true" to enable Telegram integration (defaults to false)
- `TELEGRAM_TOKEN`: Telegram bot token for approval workflow
- `TELEGRAM_CHAT_ID`: Telegram chat ID for notifications

### Service Account
Place Google service account JSON at `/etc/secrets/service-account.json` for Google Sheets integration.

### Logging
- Flask server logs: `flask_server.log`
- Animal channel pipeline logs: `animalchannel.log`
- Enable DEBUG mode by setting `DEBUG=true` in environment

## Architecture Overview

### Core Components

**Flask Server (`flask_server.py`)**
- REST API endpoints:
  - `/submit`: Generates and returns 20 story scenes (no image generation)
  - `/approve_scenes`: Starts background image generation process
  - `/stream`: Server-Sent Events endpoint for real-time image updates
  - `/health`: Health check endpoint
  - `/story/<story_id>`: Polling endpoint for SSE fallback
- **CRITICAL**: Redis-backed shared storage for `active_stories` to support multi-instance deployments
- Uses threading for background story generation (memory sharing)
- Flask-SSE with Redis support or in-memory fallback

**Story Generation Pipeline (`Animalchannel.py`)**
- Main functions: `process_story_generation()` and `process_story_generation_with_scenes()`
- Flow: Quiz answers → System prompt → OpenAI 20-scene generation → Visual prompt creation → Prompt standardization → Async DALL-E image generation → Cloudinary upload
- Optional integrations: Google Sheets tracking, video generation (Kling/Hailuo), Telegram approval (deprecated)
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
7. Flask server launches threading `process_story_generation_with_scenes()`
8. Background process: Scenes → Visual prompts → Standardization → Async DALL-E generation → Cloudinary upload
9. SSE events emitted for each completed image with real-time updates
10. Frontend updates image grid in real-time or falls back to polling
11. Optional: Google Sheets tracking and Telegram approval (deprecated)
12. Optional: Final video generation via Kling/Hailuo APIs

### Key Integration Points
- **OpenAI**: Scene generation (GPT), visual prompt creation, image generation (GPT-Image-1)
- **Cloudinary**: Image hosting and URL generation for frontend display
- **Redis**: **CRITICAL** - Shared storage for story data across multiple Flask instances
- **Flask-SSE + Redis**: Real-time event streaming with fallback to in-memory
- **Telegram**: Optional approval workflow for generated images (deprecated, disabled by default)
- **Google Sheets**: Optional prompt storage and progress tracking
- **Kling/Hailuo**: Optional video generation from final image sets

### Multi-Instance Deployment Architecture (CRITICAL)

**Problem Solved**: Production deployments (Render, Heroku) run multiple Flask instances, causing in-memory `active_stories` data to be isolated per instance. This resulted in images generating successfully but never appearing in the frontend.

**Solution**: Redis-backed shared storage system with automatic fallbacks:

**Storage Functions (`flask_server.py`):**
- `set_story_data(story_id, story_data)`: Store story data in Redis with 1-hour expiry
- `get_story_data(story_id)`: Retrieve story data from Redis or in-memory fallback  
- `update_story_data(story_id, updates)`: Update specific fields in story data
- `delete_story_data(story_id)`: Remove story data from Redis and memory
- `get_all_story_ids()`: Get all active story IDs across instances

**Key Benefits:**
- All Flask instances share the same story data via Redis
- Automatic fallback to in-memory storage if Redis unavailable
- Thread references stored separately (non-serializable objects)
- 1-hour TTL prevents data accumulation
- Cross-instance image tracking and progress updates

**Critical for Production**: Without Redis, images generate but aren't tracked because `emit_image_event()` calls from background threads can't access the `active_stories` data created in different Flask instances.

### Error Handling & Resilience
- Comprehensive logging throughout all pipeline stages
- Graceful fallback for optional services (Telegram, Google Sheets, Redis)
- SSE with exponential backoff retry and polling fallback
- Async image generation with proper error handling
- Environment variable validation with warnings
- Threading isolation with shared memory prevents crashes

## Development Notes

### ✅ All Core Goals Completed Successfully (2025-07-18)

**Actions Completed:**
1. **✅ Robust Scene Generation**: Enhanced `/submit` endpoint with 2-retry logic and fallback placeholders
   - Added `generate_story()` function with retry mechanism (lines 245-310 in `Animalchannel.py`)
   - Implemented placeholder fallbacks: `f"(Scene{i} missing - API failed)"` for complete failures
   - Added scene validation and logging for missing scenes
   
2. **✅ Enhanced Frontend Error Handling**: Improved user feedback and error display
   - Added comprehensive error parsing for both `/submit` and `/approve_scenes` endpoints
   - Implemented server error message extraction and display
   - Added validation for missing scenes and empty responses in frontend
   - Users now see specific error messages instead of generic alerts

3. **✅ Retry Logic Implementation**: Added robust retry mechanisms for OpenAI API calls
   - Implemented 2-retry system with proper logging and error handling
   - Added progressive retry delays and fallback mechanisms
   - Integrated retry logic into both scene generation and image generation pipelines

4. **✅ Quiz Validation**: Comprehensive validation of required quiz answers
   - Added required field validation in Flask server (lines 124-133 in `flask_server.py`)
   - Returns specific error messages for missing fields
   - Prevents OpenAI API calls with incomplete data

5. **✅ Enhanced Logging**: Comprehensive error logging with full tracebacks
   - Added DEBUG level logging throughout both backend files
   - Implemented full traceback logging for all endpoints
   - Added raw OpenAI response logging for debugging
   - Enhanced SSE error logging with detailed exception tracking

6. **✅ Full Flow Testing**: Created comprehensive test suite
   - Implemented `test_full_flow.py` for complete workflow testing
   - Tests: Quiz validation → Scene generation → Image generation start → Status polling → SSE endpoints
   - Validates all 20 scenes, checks for API failures, and confirms error handling

**Technical Implementation Summary:**
- **Backend**: Enhanced retry logic, fallback mechanisms, comprehensive logging, and error handling
- **Frontend**: Improved error parsing, user-friendly messages, and validation feedback
- **Testing**: Complete test suite covering all major functionality
- **Documentation**: Updated with comprehensive goal completion tracking

**Files Modified:**
- `Animalchannel.py`: Enhanced scene generation with retry logic and fallback placeholders
- `flask_server.py`: Added comprehensive error logging and quiz validation
- `index.html`: Improved frontend error handling and user feedback
- `test_full_flow.py`: New comprehensive test suite for full workflow validation
- `CLAUDE.md`: Updated with goal completion documentation

**Result**: All core development goals have been successfully completed. The application now provides robust error handling, comprehensive logging, and reliable scene generation with proper fallback mechanisms.

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
- `generate_images_concurrently()`: **NEW** Parallel image generation with rate limiting
- `process_image_async()`: **NEW** Async version with semaphore control
- `process_image()`: Legacy sequential processing (fallback only)

**Frontend Event System:**
- SSE connection with exponential backoff (1s, 3s, 5s delays, max 3 retries)
- Polling fallback when SSE fails (5-second intervals)
- Auto-resize textareas with scroll support for long content

---

## Image Variation Popup Implementation - COMPLETED ✅ (2025-07-22)

### Objective
Enhance the frontend (index.html) to allow users to select an image variation and view it in a full-screen popup. The popup will display the selected image enlarged in the center, with the other three variations as small thumbnails below. Users can click thumbnails to swap the enlarged image, use approve/reject buttons in the popup, and close it via an 'X' button to return to the normal view.

### ✅ All 9 Goals Successfully Completed

**Phase 1: UI Preparation and Structure**
1. **✅ Goal 1**: In index.html, add a 'Full Screen' button next to the 'Reject All & Regenerate' button for each scene's image variations. Ensure it appears only when variations are available.
2. **✅ Goal 2**: Create the popup HTML structure as a hidden div (e.g., id='image-popup') including: an enlarged image container, a thumbnails container for the 3 other variations, approve and reject buttons at the bottom, and an 'X' close button at the top left.

**Phase 2: JavaScript Logic and Event Handling**
3. **✅ Goal 3**: Add event listeners to the 'Full Screen' buttons. When clicked, show the popup, set the selected image as enlarged, and populate the thumbnails with the other variations' URLs.
4. **✅ Goal 4**: Implement click handlers for the thumbnails to swap the enlarged image with the clicked thumbnail's image, updating the display dynamically without closing the popup.
5. **✅ Goal 5**: Integrate the approve and reject buttons in the popup to trigger the existing approval/rejection logic for the currently enlarged image, then refresh the scene display or close the popup as appropriate.
6. **✅ Goal 6**: Add functionality for the 'X' button to close the popup and return to the normal image generation screen, preserving any changes.

**Phase 3: Styling, Testing, and Documentation**
7. **✅ Goal 7**: Add CSS styles for the popup (e.g., fixed position overlay, centered enlarged image, thumbnail grid below, button styling) to ensure it's responsive and visually appealing.
8. **✅ Goal 8**: Test the full flow: Generate images with variations, open popup, swap variations, approve/reject from popup, and close without errors. Verify compatibility with existing SSE/polling updates.
9. **✅ Goal 9**: Update CLAUDE.md with completion status, technical summary, files modified, and expected results once all goals are done.

### Technical Implementation Summary

**Frontend Components Implemented**:
- **Full Screen Button**: Added blue "Full Screen" button next to existing approve/reject buttons for each scene with image variations
- **Popup HTML Structure**: Complete modal overlay with enlarged image container, thumbnail grid, and action buttons
- **Event Handling**: Comprehensive JavaScript functions for popup lifecycle management and user interactions
- **CSS Styling**: Responsive design with dark overlay, centered content, hover effects, and mobile optimization

**Key Features Implemented**:
- **Modal Popup**: Semi-transparent dark overlay with centered content and z-index 1000 for proper layering
- **Image Enlargement**: Main image displayed at max 60vh height with object-fit contain for optimal viewing
- **Thumbnail Navigation**: 4 thumbnail grid with visual selection indicators and click-to-swap functionality  
- **Keyboard Support**: ESC key closes popup, improving accessibility
- **Click-Outside-to-Close**: Clicking overlay background closes popup
- **Action Integration**: Approve/reject buttons use existing approval logic with selected variation
- **Mobile Responsive**: Optimized layout and sizing for mobile devices

**JavaScript Functions Added**:
- `openImagePopup(sceneNumber)`: Extracts variations from DOM and opens popup
- `populatePopup()`: Updates enlarged image and thumbnail grid based on selection
- `selectPopupVariation(index)`: Handles thumbnail clicks to swap enlarged image
- `closeImagePopup()`: Closes popup and cleans up event listeners
- `approveFromPopup()`: Integrates with existing `approveSelectedVariation()` logic
- `rejectFromPopup()`: Integrates with existing `rejectAllVariations()` logic
- `handlePopupKeydown(event)`: Handles ESC key for popup closure

**CSS Classes Added**:
- `.popup-overlay`: Fixed position modal background with rgba transparency
- `.popup-content`: Centered white container with rounded corners and scrolling
- `.popup-header`: Header area with close button positioned at top-right
- `.popup-body`: Main content area with padding and center alignment
- `.enlarged-image-container`: Container for main enlarged image with shadow
- `.thumbnails-container`: Flex grid for thumbnail navigation
- `.popup-thumbnail`: Individual thumbnail with hover and selection states
- `.fullscreen-btn`: Blue styled button for triggering popup

### Files Modified
- `index.html`: Added popup HTML structure, CSS styles, and JavaScript functions for complete popup functionality
- `CLAUDE.md`: Updated with completion status and comprehensive technical documentation

### Expected User Experience
1. User sees "Full Screen" button appear next to approve/reject buttons for scenes with generated image variations
2. Clicking "Full Screen" opens modal popup with first variation enlarged and other variations as clickable thumbnails
3. User can click thumbnails to swap which variation is displayed enlarged
4. User can approve or reject the currently selected variation directly from popup
5. User can close popup via X button, ESC key, or clicking outside popup area
6. All actions integrate seamlessly with existing approval workflow and scene management

**Status**: ✅ **PRODUCTION READY** - Complete image variation popup system implemented with enhanced user experience for detailed image review and selection."

## Image Variation Edit & Regenerate Feature - COMPLETED ✅ (2025-07-22)

### Objective
Enhance the image variation popup to allow users to edit and regenerate images. Users can click 'Edit & Regenerate' to replace the reject button, then choose to edit an existing variation or create a new image with a custom prompt. This integrates with the backend to generate new variations based on user input.

### ✅ All 7 Goals Successfully Completed

**Phase 1: UI and Button Setup**
1. **✅ Goal 1**: Change the 'Reject' button to 'Edit & Regenerate' in the popup. When clicked, replace approve/reject buttons with 'Edit' and 'New Image' buttons.
2. **✅ Goal 2**: Implement 'Edit' button functionality to show a text box for user input on desired edits to the selected variation.
3. **✅ Goal 3**: Implement 'New Image' button functionality to show a text box for user input on a new custom prompt.

**Phase 2: Backend Integration and Logic**
4. **✅ Goal 4**: Integrate with the backend to send edit requests and generate 4 new variations based on user edits.
5. **✅ Goal 5**: Integrate with the backend to process new custom prompts through existing prompt agents, standardization, and sanitization, then generate 4 new variations.

**Phase 3: Testing and Documentation**
6. **✅ Goal 6**: Test the full flow: Edit a variation, submit a new prompt, verify new variations are generated and displayed correctly.
7. **✅ Goal 7**: Update CLAUDE.md with completion status, technical summary, files modified, and expected results once all goals are done.

### Technical Implementation Summary

**Frontend Components Enhanced**:
- **UI Transformation**: Replaced "Reject" button with orange "Edit & Regenerate" button in image variation popup
- **Multi-Stage Interface**: Dynamic button transitions from Approve/Edit&Regenerate → Edit/New Image/Cancel → Input textarea with Submit/Cancel
- **Input Validation**: Client-side validation for empty inputs and proper error handling
- **User Experience**: Clear placeholders and focused text areas for optimal user interaction

**Backend Integration Implemented**:
- **New Endpoint**: `/edit_image/<story_id>` POST endpoint for handling edit requests
- **Dual Mode Support**: 
  - **Edit Mode**: Combines original scene text with user edit instructions
  - **New Image Mode**: Uses custom user prompt as base for generation
- **Pipeline Integration**: Routes requests through existing prompt agents, standardization, and sanitization
- **Concurrent Generation**: Generates 4 new variations using existing async image generation system

**JavaScript Functions Added**:
- `showEditOptions()`: Transitions from main buttons to edit/new image options
- `showEditInput()`: Displays text input for editing existing variation
- `showNewImageInput()`: Displays text input for custom prompt creation
- `cancelEdit()`: Resets popup state to main button view
- `submitEdit()`: Validates input and sends request to backend with loading states
- Enhanced `closeImagePopup()`: Resets edit state when popup closes

**CSS Styling Added**:
- `.edit-regenerate-btn`: Orange button styling for main edit trigger
- `.popup-edit-buttons`: Flex layout for Edit/New Image/Cancel button group
- `.popup-input-section`: Input area with background styling and proper spacing
- `.submit-btn`: Primary blue button for generation trigger
- Responsive design maintains mobile compatibility

**Backend Processing Flow**:
1. **Request Validation**: Validates scene_number, user_input, edit_mode, and story existence
2. **Mode Processing**: 
   - Edit mode: Appends "USER REQUESTED EDITS: {input}" to original scene
   - New image mode: Uses user input directly as prompt
3. **Pipeline Processing**: Runs through create_prompts() → standardize_prompts() → sanitization
4. **Image Generation**: Uses generate_images_concurrently() to create 4 new variations
5. **SSE Emission**: New variations appear in real-time via existing SSE system

### Files Modified
- `index.html`: Added edit UI components, CSS styles, and JavaScript functionality (300+ lines added)
- `flask_server.py`: Added `/edit_image/<story_id>` endpoint with comprehensive processing (120+ lines added)
- `CLAUDE.md`: Updated with completion status and technical documentation

### Expected User Experience
1. **Trigger Edit**: User clicks "Edit & Regenerate" in image variation popup
2. **Choose Mode**: User selects "Edit" (modify existing) or "New Image" (custom prompt)
3. **Input Content**: User enters edit instructions or custom prompt in focused textarea
4. **Submit Request**: User clicks "Generate New Variations" with loading feedback
5. **Receive Results**: 4 new variations appear via SSE events, replacing previous variations
6. **Continue Workflow**: User can approve new variations or repeat edit process

### Key Features
- **Seamless Integration**: Works with existing approval workflow and SSE system
- **Input Validation**: Comprehensive client and server-side validation
- **Error Handling**: Graceful error messages and recovery mechanisms  
- **Loading States**: Visual feedback during generation process
- **Mobile Support**: Responsive design maintains functionality on all devices
- **Pipeline Consistency**: Uses existing prompt processing for quality and safety

**Status**: ✅ **PRODUCTION READY** - Complete edit and regenerate system implemented with seamless integration to existing image variation workflow.

## Main Page Edit & Regenerate Feature - COMPLETED ✅ (2025-07-22)

### ✅ All 5 Goals Successfully Completed

**Objective**: Extend the edit & regenerate functionality from the fullscreen popup to the main image generation page for consistent user experience.

**Actions Completed**:
1. **✅ Replace Reject Button**: Updated `displayImage` function to use "Edit & Regenerate" instead of "Reject" for single images
2. **✅ UI Implementation**: Added main page edit interface with Edit/New Image button options
3. **✅ JavaScript Functions**: Implemented dedicated main page functions to avoid conflicts with popup functions:
   - `showMainEditOptions()` - Initial edit options display
   - `showMainEditInput()` - Edit existing image interface  
   - `showMainNewImageInput()` - New custom prompt interface
   - `submitMainEdit()` - Backend integration with loading states
   - `cancelMainEdit()` - Restore original state functionality
4. **✅ CSS Styling**: Added responsive styles for main page edit interface (`.main-edit-buttons`, `.main-input-section`, `.main-edit-actions`)
5. **✅ Backend Integration**: Connected to existing `/edit_image` endpoint with proper error handling and loading states

### Technical Implementation Summary

**Frontend Changes**:
- Updated single image display to use consistent edit workflow
- Separate function namespace for main page vs popup to prevent conflicts
- Loading states and error recovery with original HTML restoration
- Responsive CSS design maintaining mobile compatibility

**Integration Points**:
- Uses existing `/edit_image/<story_id>` backend endpoint
- Same prompt processing pipeline (standardization, sanitization)
- Transitions single images to variation display after edit
- Maintains SSE event system compatibility

**User Experience**:
- Consistent edit workflow across single images and image variations
- Clear visual feedback during edit processing
- Intuitive button progression: Edit & Regenerate → Edit/New Image → Submit/Cancel
- Seamless integration with existing approval workflow

### Files Modified
- `index.html`: Updated `displayImage()`, added main page edit functions and CSS styles
- Commit: `88b5d17` - Complete main page edit functionality implementation

### Expected User Flow
1. User sees single image with "Approve" and "Edit & Regenerate" buttons
2. User clicks "Edit & Regenerate" → Shows Edit/New Image/Cancel options  
3. User clicks "Edit" → Text area for describing changes
4. User clicks "New Image" → Text area for custom prompt
5. User submits → Loading state → New variations display
6. User proceeds with normal variation approval workflow

**Status**: ✅ **PRODUCTION READY** - Main page and popup now have identical edit & regenerate functionality with consistent user experience across all image types."