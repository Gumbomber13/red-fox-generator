from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sse import sse
import json
import traceback
import uuid
import threading
import time
import os
import logging
# import multiprocessing  # Replaced with threading for SSE memory sharing
from Animalchannel import process_story_generation, process_story_generation_with_scenes, process_video

# Configure logging with proper formatting
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('flask_server.log', mode='a')
    ]
)

# Create logger instance
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Configure Flask-SSE with Redis (fallback to in-memory for development)
app.config["REDIS_URL"] = os.getenv("REDIS_URL")
try:
    app.register_blueprint(sse, url_prefix='/stream')
    print("Flask-SSE blueprint registered successfully")
except Exception as e:
    logger.error(f"Flask-SSE setup failed: {e}")
    logger.error(f"Exception type: {type(e).__name__}")
    logger.error(f"Exception details: {str(e)}")
    logger.error("SSE functionality will not be available")
    logger.exception("Flask-SSE initialization failed")

# Configure Redis client for shared story storage
redis_client = None
try:
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        import redis
        redis_client = redis.from_url(redis_url, decode_responses=True)
        # Test Redis connection
        redis_client.ping()
        logger.info(f"[REDIS] Redis connected successfully: {redis_url}")
    else:
        logger.warning("[REDIS] REDIS_URL not set, using in-memory storage (may cause multi-instance issues)")
except Exception as e:
    logger.error(f"[REDIS] Redis connection failed: {e}")
    redis_client = None

# Shared storage functions
def set_story_data(story_id, story_data):
    """Store story data in Redis or in-memory fallback"""
    if redis_client:
        try:
            import json
            # Create a copy of the data to avoid modifying the original
            serializable_data = {}
            for key, value in story_data.items():
                # Skip non-serializable objects like Thread
                if key == 'process':
                    continue
                serializable_data[key] = value
            
            redis_client.setex(f"story:{story_id}", 3600, json.dumps(serializable_data))  # 1 hour expiry
            logger.debug(f"[REDIS] Stored story {story_id} in Redis")
            return True
        except Exception as e:
            logger.error(f"[REDIS] Failed to store story {story_id}: {e}")
            logger.exception(f"[REDIS] Redis serialization error details")
    
    # Fallback to in-memory
    active_stories[story_id] = story_data
    logger.debug(f"[REDIS] Stored story {story_id} in memory (fallback)")
    return True

def get_story_data(story_id):
    """Get story data from Redis or in-memory fallback"""
    if redis_client:
        try:
            import json
            data = redis_client.get(f"story:{story_id}")
            if data:
                story_data = json.loads(data)
                logger.debug(f"[REDIS] Retrieved story {story_id} from Redis")
                return story_data
        except Exception as e:
            logger.error(f"[REDIS] Failed to get story {story_id}: {e}")
    
    # Fallback to in-memory
    story_data = active_stories.get(story_id)
    if story_data:
        logger.debug(f"[REDIS] Retrieved story {story_id} from memory (fallback)")
    return story_data

def update_story_data(story_id, updates):
    """Update specific fields in story data"""
    story_data = get_story_data(story_id)
    if story_data:
        story_data.update(updates)
        set_story_data(story_id, story_data)
        return True
    return False

def delete_story_data(story_id):
    """Delete story data from Redis or in-memory"""
    if redis_client:
        try:
            redis_client.delete(f"story:{story_id}")
            logger.debug(f"[REDIS] Deleted story {story_id} from Redis")
        except Exception as e:
            logger.error(f"[REDIS] Failed to delete story {story_id}: {e}")
    
    # Also remove from in-memory fallback
    if story_id in active_stories:
        del active_stories[story_id]
        logger.debug(f"[REDIS] Deleted story {story_id} from memory")

def get_all_story_ids():
    """Get all active story IDs"""
    story_ids = []
    if redis_client:
        try:
            story_ids = [key.replace("story:", "") for key in redis_client.keys("story:*")]
            logger.debug(f"[REDIS] Found {len(story_ids)} stories in Redis")
        except Exception as e:
            logger.error(f"[REDIS] Failed to get story IDs from Redis: {e}")
    
    # Also include in-memory stories
    memory_ids = list(active_stories.keys())
    all_ids = list(set(story_ids + memory_ids))  # Deduplicate
    logger.debug(f"[REDIS] Total unique story IDs: {len(all_ids)}")
    return all_ids

# Store active story sessions and heartbeat timers (heartbeat_timers stays in-memory since it's process-specific)
active_stories = {}  # Keep for fallback
heartbeat_timers = {}

def emit_image_event(story_id, scene_number, image_url, status="completed"):
    """Emit image generation event via SSE"""
    logger.info(f"[SSE-FIX] emit_image_event called: story={story_id}, scene={scene_number}, status={status}")
    logger.debug(f"[SSE-DETAILED] Thread info: current={threading.current_thread().name}, daemon={threading.current_thread().daemon}")
    logger.debug(f"[SSE-DETAILED] Flask app context available: {bool(app.app_context)}")
    
    # Get story data using Redis-backed storage
    story_data = get_story_data(story_id)
    all_story_ids = get_all_story_ids()
    
    logger.info(f"[REDIS] Total active stories: {len(all_story_ids)}")
    logger.info(f"[REDIS] Active story IDs: {all_story_ids}")
    logger.info(f"[REDIS] Story {story_id} exists in storage: {story_data is not None}")
    
    if story_data:
        # Update image data
        if 'images' not in story_data:
            story_data['images'] = {}
        story_data['images'][scene_number] = {
            'url': image_url,
            'status': status
        }
        
        # Initialize approval status for pending_approval images
        if status == "pending_approval":
            if 'image_approvals' not in story_data:
                story_data['image_approvals'] = {}
            story_data['image_approvals'][scene_number] = 'pending'
            story_data['completed_scenes'] += 1  # Count pending_approval as completed for progress tracking
            logger.info(f"[APPROVAL] Image {scene_number} set to pending approval")
        elif status == "completed":
            story_data['completed_scenes'] += 1
        
        # Save updated story data back to Redis
        set_story_data(story_id, story_data)
        
        # Debug logging: Print full story state after update
        logger.info(f"[DEBUG-DATA] Story {story_id} state after scene {scene_number} update:")
        logger.info(f"[DEBUG-DATA] Status: {story_data['status']}, Completed: {story_data['completed_scenes']}/{story_data['total_scenes']}")
        logger.info(f"[DEBUG-DATA] Images dict: {len(story_data['images'])} scenes - {list(story_data['images'].keys())}")
        logger.info(f"[DEBUG-DATA] Updated story saved to Redis")
        
        # Emit the event to connected clients
        logger.debug(f"Attempting SSE emit for story {story_id}, scene {scene_number}, URL length {len(image_url)}")
        # RETRY LOGIC: Implement retry for transient SSE failures
        max_retries = 3
        retry_delay = 1  # seconds
        
        for attempt in range(max_retries):
            try:
                # CRITICAL FIX: Ensure Flask application context for SSE operations
                logger.debug(f"[SSE-DETAILED] Attempt {attempt + 1}/{max_retries}: Thread={threading.current_thread().name}")
                with app.app_context():
                    logger.debug(f"[SSE-CONTEXT] Inside Flask app context for SSE emission (attempt {attempt + 1})")
                    logger.debug(f"[SSE-DETAILED] App context: name={app.name}, config_keys={list(app.config.keys())[:5]}")
                    
                    sse_data = {
                        "scene_number": scene_number,
                        "image_url": image_url,
                        "status": status,
                        "completed_scenes": story_data['completed_scenes'],
                        "total_scenes": story_data['total_scenes']
                    }
                    logger.debug(f"[SSE-DETAILED] Publishing SSE data: {sse_data}")
                    
                    sse.publish(sse_data, type='image_ready', channel=story_id)
                    logger.info(f"[SSE-CONTEXT] SSE emit success for {scene_number} with app context (attempt {attempt + 1})")
                    logger.debug(f"[SSE-DETAILED] SSE publish completed without errors")
                    print(f"SSE Event emitted successfully: Scene {scene_number} for story {story_id}")
                    return  # Success, exit function
                    
            except Exception as e:
                logger.warning(f"[SSE-RETRY] Attempt {attempt + 1}/{max_retries} failed: {type(e).__name__}: {str(e)}")
                
                if attempt < max_retries - 1:  # Not the last attempt
                    logger.info(f"[SSE-RETRY] Retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    # Final attempt failed, log error and continue
                    logger.error(f"[SSE-RETRY] All {max_retries} attempts failed for scene {scene_number}")
                    # Enhanced error logging for SSE connection issues (final failure)
                    logger.exception(f"[SSE-CONTEXT] All retries failed to emit SSE event for story {story_id}, scene {scene_number}")
                    print(f"ERROR: Failed to emit SSE event for story {story_id}, scene {scene_number} after {max_retries} attempts")
                    print(f"Exception type: {type(e).__name__}")
                    print(f"Exception message: {str(e)}")
                    print(f"Fallback: Scene {scene_number} image ready: {image_url}")
    else:
        logger.warning(f"[REDIS] Story {story_id} NOT found in Redis storage - cannot update image data")
        logger.warning(f"[REDIS] Available stories: {all_story_ids}")
        logger.warning(f"[REDIS] This means images are generating but story was not created properly")

def emit_image_variations_event(story_id, scene_number, variation_urls, status="pending_approval"):
    """Emit image variations event via SSE with all 4 variations"""
    logger.info(f"[SSE-FIX] emit_image_variations_event called: story={story_id}, scene={scene_number}, status={status}")
    logger.info(f"[VARIATIONS] Got {len(variation_urls)} variations for scene {scene_number}")
    
    # Get story data using Redis-backed storage
    story_data = get_story_data(story_id)
    all_story_ids = get_all_story_ids()
    
    logger.info(f"[REDIS] Total active stories: {len(all_story_ids)}")
    logger.info(f"[REDIS] Story {story_id} exists in storage: {story_data is not None}")
    
    if story_data:
        # Update image data with variations
        if 'images' not in story_data:
            story_data['images'] = {}
        story_data['images'][scene_number] = {
            'variations': variation_urls,  # Array of 4 URLs
            'status': status,
            'selected_variation': None  # Will be set when user approves a variation
        }
        
        # Initialize approval status for pending_approval images
        if status == "pending_approval":
            if 'image_approvals' not in story_data:
                story_data['image_approvals'] = {}
            story_data['image_approvals'][scene_number] = 'pending'
            story_data['completed_scenes'] += 1  # Count pending_approval as completed for progress tracking
            logger.info(f"[APPROVAL] Image {scene_number} variations set to pending approval")
        elif status == "completed":
            story_data['completed_scenes'] += 1
        
        # Save updated story data back to Redis
        set_story_data(story_id, story_data)
        
        # Debug logging
        successful_variations = len([url for url in variation_urls if url])
        logger.info(f"[DEBUG-DATA] Story {story_id} scene {scene_number}: {successful_variations}/4 variations uploaded")
        
        # Emit the event to connected clients with variations
        max_retries = 3
        retry_delay = 1
        
        for attempt in range(max_retries):
            try:
                with app.app_context():
                    logger.debug(f"[SSE-CONTEXT] Inside Flask app context for variations SSE emission (attempt {attempt + 1})")
                    
                    sse_data = {
                        "scene_number": scene_number,
                        "variations": variation_urls,  # Send all 4 variations
                        "status": status,
                        "completed_scenes": story_data['completed_scenes'],
                        "total_scenes": story_data['total_scenes']
                    }
                    logger.debug(f"[SSE-DETAILED] Publishing variations SSE data: scene={scene_number}, variations={len(variation_urls)}")
                    
                    sse.publish(sse_data, type='image_variations_ready', channel=story_id)
                    logger.info(f"[SSE-CONTEXT] SSE variations emit success for scene {scene_number} (attempt {attempt + 1})")
                    return  # Success, exit function
                    
            except Exception as e:
                logger.warning(f"[SSE-RETRY] Variations attempt {attempt + 1}/{max_retries} failed: {type(e).__name__}: {str(e)}")
                if attempt < max_retries - 1:
                    logger.info(f"[SSE-RETRY] Retrying variations in {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    logger.error(f"[SSE-RETRY] All {max_retries} attempts failed for variations scene {scene_number}")
    else:
        logger.warning(f"[REDIS] Story {story_id} NOT found in Redis storage - cannot update variations data")

def send_heartbeat(story_id):
    """Send periodic heartbeat/ping events to keep SSE connection alive"""
    def heartbeat_loop():
        while story_id in active_stories and active_stories[story_id]['status'] == 'processing':
            try:
                # CRITICAL FIX: Ensure Flask application context for SSE heartbeat
                with app.app_context():
                    sse.publish({"timestamp": time.time()}, type='ping', channel=story_id)
                    print(f"[SSE-CONTEXT] Sent heartbeat for story {story_id} with app context")
            except Exception as e:
                # Enhanced error logging for heartbeat failures
                print(f"ERROR: Failed to send heartbeat for story {story_id}")
                print(f"Exception type: {type(e).__name__}")
                print(f"Exception message: {str(e)}")
                
                # Log to file
                try:
                    import datetime
                    timestamp = datetime.datetime.now().isoformat()
                    with open('sse_errors.log', 'a') as f:
                        f.write(f"{timestamp} - Heartbeat Error: {story_id} - {type(e).__name__}: {str(e)}\n")
                except Exception as log_error:
                    print(f"Warning: Could not log heartbeat error to file: {log_error}")
                break
            
            time.sleep(30)  # Send heartbeat every 30 seconds
        
        print(f"Heartbeat stopped for story {story_id}")
    
    # Start heartbeat in a separate thread
    heartbeat_thread = threading.Thread(target=heartbeat_loop)
    heartbeat_thread.daemon = True
    heartbeat_thread.start()
    heartbeat_timers[story_id] = heartbeat_thread

def stop_heartbeat(story_id):
    """Stop heartbeat for a story"""
    if story_id in heartbeat_timers:
        print(f"Stopping heartbeat for story {story_id}")
        # The heartbeat loop will stop automatically when status changes
        del heartbeat_timers[story_id]

@app.route('/submit', methods=['POST'])
def submit():
    """Handle POST requests with quiz answers from frontend"""
    try:
        # Get JSON data from request
        answers = request.get_json()
        
        # Validate required fields
        required_fields = [
            'story_type', 'humiliation_type', 'offering_who', 
            'offering_what', 'humiliation', 'find', 
            'do_with_find', 'villain_crime'
        ]
        
        # Check if all required fields are present
        for field in required_fields:
            if field not in answers:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        # Generate scenes only (no image generation yet)
        from Animalchannel import build_system_prompt, generate_story
        system_prompt = build_system_prompt(answers)
        scenes = generate_story(system_prompt)
        
        # Convert scenes list to dictionary format expected by frontend
        scenes_dict = {}
        for i, scene in enumerate(scenes, 1):
            scenes_dict[f"Scene{i}"] = scene
        
        # Log the full scene payload for debugging
        print("=== FLASK SERVER: SCENES PAYLOAD ===")
        print(f"Total scenes generated: {len(scenes)}")
        print(f"Scenes dict keys: {list(scenes_dict.keys())}")
        print("Full scenes payload:")
        import json
        print(json.dumps(scenes_dict, indent=2))
        print("=" * 40)
        
        # Return scenes for editing
        return jsonify(scenes_dict)
        
    except Exception as e:
        # Log the full traceback for debugging
        logger.error("=" * 80)
        logger.error("ERROR IN /submit ENDPOINT:")
        logger.error("=" * 80)
        logger.error(f"Exception Type: {type(e).__name__}")
        logger.error(f"Exception Message: {str(e)}")
        logger.error("-" * 80)
        logger.error("Full Traceback:")
        logger.exception("Submit endpoint error")
        logger.error("=" * 80)
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/approve_scenes', methods=['POST'])
def approve_scenes():
    """Handle approved scenes and start image generation"""
    try:
        # Get JSON data from request
        data = request.get_json()
        approved_scenes = data.get('scenes', {})
        original_answers = data.get('answers', {})
        
        # Generate unique story ID
        story_id = str(uuid.uuid4())
        
        # Store story session using Redis-backed storage
        story_data = {
            'status': 'processing',
            'answers': original_answers,
            'scenes': approved_scenes,
            'images': {},
            'total_scenes': 20,
            'completed_scenes': 0,
            'image_approvals': {}  # Track approval status: {scene_number: 'pending' | 'approved' | 'rejected'}
        }
        set_story_data(story_id, story_data)
        
        # Debug logging for story creation
        all_story_ids = get_all_story_ids()
        logger.info(f"[STORY-CREATE] Created story {story_id} using Redis storage")
        logger.info(f"[STORY-CREATE] Total active stories after creation: {len(all_story_ids)}")
        logger.info(f"[STORY-CREATE] Active story IDs: {all_story_ids}")
        
        # Start heartbeat to keep SSE connection alive
        send_heartbeat(story_id)
        
        # Start story generation in background process with approved scenes
        def generate_story_async():
            try:
                # Debug: Check if story still exists when background thread starts
                logger.info(f"[STORY-CREATE] Background thread starting for story {story_id}")
                logger.info(f"[STORY-CREATE] Story exists at thread start: {story_id in active_stories}")
                logger.info(f"[STORY-CREATE] Total stories at thread start: {len(active_stories)}")
                process_story_generation_with_scenes(approved_scenes, original_answers, story_id)
                # Mark as completed and stop heartbeat
                update_story_data(story_id, {'status': 'completed'})
                stop_heartbeat(story_id)
                try:
                    # CRITICAL FIX: Ensure Flask application context for SSE story completion
                    with app.app_context():
                        sse.publish({"status": "completed"}, type='story_complete', channel=story_id)
                        print(f"[SSE-CONTEXT] Story completion event emitted successfully for {story_id} with app context")
                except Exception as sse_error:
                        print(f"ERROR: Failed to emit story completion event for {story_id}")
                        print(f"Exception type: {type(sse_error).__name__}")
                        print(f"Exception message: {str(sse_error)}")
                        
                        # Log to file
                        try:
                            import datetime
                            timestamp = datetime.datetime.now().isoformat()
                            with open('sse_errors.log', 'a') as f:
                                f.write(f"{timestamp} - Completion Event Error: {story_id} - {type(sse_error).__name__}: {str(sse_error)}\n")
                        except Exception as log_error:
                            print(f"Warning: Could not log completion error to file: {log_error}")
            except Exception as e:
                # Mark as failed and stop heartbeat
                update_story_data(story_id, {'status': 'failed'})
                stop_heartbeat(story_id)
                try:
                    # CRITICAL FIX: Ensure Flask application context for SSE story error
                    with app.app_context():
                        sse.publish({"status": "failed", "error": str(e)}, type='story_error', channel=story_id)
                        print(f"[SSE-CONTEXT] Story error event emitted successfully for {story_id} with app context")
                except Exception as sse_error:
                        print(f"ERROR: Failed to emit story error event for {story_id}")
                        print(f"SSE Exception type: {type(sse_error).__name__}")
                        print(f"SSE Exception message: {str(sse_error)}")
                        print(f"Original story generation error: {e}")
                        
                        # Log to file
                        try:
                            import datetime
                            timestamp = datetime.datetime.now().isoformat()
                            with open('sse_errors.log', 'a') as f:
                                f.write(f"{timestamp} - Error Event Error: {story_id} - SSE: {type(sse_error).__name__}: {str(sse_error)}, Original: {str(e)}\n")
                        except Exception as log_error:
                            print(f"Warning: Could not log error event error to file: {log_error}")
        
        logger.info(f"Approved scenes for {story_id}, starting background thread")
        thread = threading.Thread(target=generate_story_async)
        thread.daemon = True
        thread.start()
        
        # Store thread reference in in-memory dict only (Thread objects can't be serialized to Redis)
        active_stories[story_id] = {'process': thread}
        
        # Return story ID for client to connect to SSE stream
        return jsonify({
            "status": "ok", 
            "story_id": story_id,
            "message": "Story generation started successfully"
        })
        
    except Exception as e:
        # Log the full traceback for debugging
        logger.error("=" * 80)
        logger.error("ERROR IN /approve_scenes ENDPOINT:")
        logger.error("=" * 80)
        logger.error(f"Exception Type: {type(e).__name__}")
        logger.error(f"Exception Message: {str(e)}")
        logger.error("-" * 80)
        logger.error("Full Traceback:")
        logger.exception("Approve scenes endpoint error")
        logger.error("=" * 80)
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/story/<story_id>', methods=['GET'])
def get_story_status(story_id):
    """Get current status of a story generation"""
    logger.info(f"Getting story status for ID: {story_id}")
    
    # Get story data using Redis-backed storage
    story_data = get_story_data(story_id)
    if not story_data:
        logger.warning(f"Story not found: {story_id}")
        return jsonify({'error': 'Story not found'}), 404
    
    # Log the current state for debugging
    logger.debug(f"Story {story_id} status: {story_data['status']}, completed: {story_data['completed_scenes']}/{story_data['total_scenes']}")
    logger.debug(f"Story {story_id} images: {len(story_data['images'])} images available")
    
    return jsonify({
        'status': story_data['status'],
        'completed_scenes': story_data['completed_scenes'],
        'total_scenes': story_data['total_scenes'],
        'images': story_data['images']
    })

@app.route('/debug_story/<story_id>', methods=['GET'])
def debug_story_full(story_id):
    """Debug endpoint to return full active_stories state for manual checking"""
    try:
        logger.info(f"[DEBUG-ENDPOINT] Full debug request for story ID: {story_id}")
        logger.info(f"[DEBUG-ENDPOINT] Total active stories: {len(active_stories)}")
        logger.info(f"[DEBUG-ENDPOINT] Active story IDs: {list(active_stories.keys())}")
        
        if story_id not in active_stories:
            logger.warning(f"[DEBUG-ENDPOINT] Story not found: {story_id}")
            # Return available info even if story not found
            return jsonify({
                'error': 'Story not found',
                'story_id': story_id,
                'timestamp': time.time(),
                'total_active_stories': len(active_stories),
                'active_story_ids': list(active_stories.keys())
            }), 404
        
        story = active_stories[story_id]
        
        # Log the full state
        logger.info(f"[DEBUG-ENDPOINT] Full story state for {story_id}: {story}")
        
        # Create a JSON-serializable copy of the story (exclude Thread object)
        story_debug = {}
        for key, value in story.items():
            if key == 'process':
                story_debug[key] = f"Thread: {value.name if hasattr(value, 'name') else str(type(value))}"
            else:
                story_debug[key] = value
        
        # Return complete story state for debugging
        return jsonify({
            'story_id': story_id,
            'full_state': story_debug,
            'timestamp': time.time(),
            'total_active_stories': len(active_stories),
            'active_story_ids': list(active_stories.keys())
        })
    except Exception as e:
        logger.error(f"[DEBUG-ENDPOINT] Error in debug endpoint: {e}")
        logger.exception("Debug endpoint error")
        return jsonify({'error': f'Debug endpoint error: {str(e)}'}), 500

@app.route('/approve_image/<story_id>/<int:scene_number>', methods=['POST'])
def approve_image(story_id, scene_number):
    """Handle image variation approval/rejection"""
    try:
        data = request.get_json()
        action = data.get('action')  # 'approve' or 'reject'
        selected_url = data.get('selected_url')  # URL of selected variation (for approve)
        
        # Get story data using Redis-backed storage
        story_data = get_story_data(story_id)
        if not story_data:
            logger.warning(f"Story not found for approval: {story_id}")
            return jsonify({'error': 'Story not found'}), 404
        
        if action not in ['approve', 'reject']:
            logger.warning(f"Invalid action: {action}")
            return jsonify({'error': 'Invalid action'}), 400
        
        # Handle approval - save selected variation
        if action == 'approve':
            if not selected_url:
                logger.warning(f"No selected URL provided for approval: {scene_number}")
                return jsonify({'error': 'No variation selected'}), 400
                
            # Update image data with selected variation
            if 'images' not in story_data:
                story_data['images'] = {}
            
            story_data['images'][scene_number]['selected_variation'] = selected_url
            story_data['images'][scene_number]['status'] = 'approved'
            
            # Update approval status
            if 'image_approvals' not in story_data:
                story_data['image_approvals'] = {}
            story_data['image_approvals'][scene_number] = 'approved'
            
            logger.info(f"[APPROVAL] Variation approved for image {scene_number} in story {story_id}")
            logger.info(f"[APPROVAL] Selected URL: {selected_url[:50]}...")
        
        # Handle rejection - trigger regeneration
        elif action == 'reject':
            logger.info(f"[APPROVAL] Triggering regeneration for rejected variations {scene_number}")
            
            # Update approval status to rejected
            if 'image_approvals' not in story_data:
                story_data['image_approvals'] = {}
            story_data['image_approvals'][scene_number] = 'rejected'
            
            # Get the current prompt for regeneration
            try:
                # Import here to avoid circular imports
                from Animalchannel import process_image_async
                import asyncio
                
                # Get scene text and regenerate
                scenes = story_data['scenes']
                scene_key = f'Scene{scene_number}'
                
                if scene_key in scenes:
                    scene_text = scenes[scene_key]
                    
                    # Create a simple prompt from scene text for regeneration
                    regeneration_prompt = f"Digital art of: {scene_text}"
                    
                    # Start regeneration in background thread with async support
                    def regenerate_variations():
                        try:
                            import asyncio
                            # Create new event loop for this thread
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            
                            # Create semaphore for single regeneration
                            semaphore = asyncio.Semaphore(1)
                            
                            # Run the async regeneration
                            result = loop.run_until_complete(
                                process_image_async(semaphore, str(scene_number), 
                                                  regeneration_prompt, f"Regen_{story_id}", story_id)
                            )
                            
                            if result and result[1]:  # result = (classifier, variation_urls)
                                logger.info(f"[APPROVAL] Successfully regenerated variations for {scene_number}")
                            else:
                                logger.error(f"[APPROVAL] Failed to regenerate variations for {scene_number}")
                        except Exception as e:
                            logger.error(f"[APPROVAL] Regeneration error for variations {scene_number}: {e}")
                        finally:
                            loop.close()
                    
                    # Start regeneration in background
                    thread = threading.Thread(target=regenerate_variations)
                    thread.daemon = True
                    thread.start()
                else:
                    logger.warning(f"[APPROVAL] Scene text not found for regeneration: {scene_key}")
                    
            except Exception as e:
                logger.error(f"[APPROVAL] Error setting up variations regeneration: {e}")
        
        # Save updated story data back to Redis
        set_story_data(story_id, story_data)
        
        # Check if all images are approved
        approvals = story_data.get('image_approvals', {})
        total_images = story_data['total_scenes']
        approved_count = sum(1 for status in approvals.values() if status == 'approved')
        
        logger.info(f"[APPROVAL] Status: {approved_count}/{total_images} images approved")
        
        # If all approved, emit 'all_approved' event
        if approved_count == total_images:
            logger.info(f"[APPROVAL] All images approved for story {story_id}")
            try:
                # CRITICAL FIX: Ensure Flask application context for SSE all_approved event
                with app.app_context():
                    sse.publish({
                        "message": "all_approved",
                        "story_id": story_id,
                        "approved_count": approved_count,
                        "total_images": total_images
                    }, type='all_approved', channel=story_id)
                    logger.info(f"[SSE-CONTEXT] [APPROVAL] Emitted all_approved event for story {story_id} with app context")
            except Exception as e:
                logger.error(f"[APPROVAL] Failed to emit all_approved event: {e}")
        
        return jsonify({
            'success': True,
            'action': action,
            'scene_number': scene_number,
            'approved_count': approved_count,
            'total_images': total_images,
            'selected_url': selected_url if action == 'approve' else None
        })
        
    except Exception as e:
        logger.error(f"[APPROVAL] Error in approve_image endpoint: {e}")
        logger.exception("Approve image error")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/test_emit/<story_id>', methods=['GET'])
def test_emit(story_id):
    """Test endpoint for SSE emission"""
    logger.info(f"Testing SSE emission for story: {story_id}")
    
    # Initialize mock story if it doesn't exist
    if story_id not in active_stories:
        active_stories[story_id] = {
            'images': {},
            'completed_scenes': 0,
            'total_scenes': 20
        }
    
    # Test emit with fake data
    fake_scene = 1
    fake_url = "https://example.com/test_image.jpg"
    
    try:
        emit_image_event(story_id, fake_scene, fake_url, "test")
        return jsonify({"status": "Test emitted successfully", "story_id": story_id})
    except Exception as e:
        logger.error(f"Test emit failed: {e}")
        return jsonify({"status": "Test emit failed", "error": str(e)}), 500

@app.route('/approve_videos/<story_id>', methods=['POST'])
def approve_videos(story_id):
    """Handle video generation approval after all images are approved"""
    try:
        # Get story data using Redis-backed storage
        story_data = get_story_data(story_id)
        if not story_data:
            logger.warning(f"[VIDEO-GEN] Story not found: {story_id}")
            return jsonify({"error": "Story not found"}), 404
        
        # Verify all images are approved
        image_approvals = story_data.get('image_approvals', {})
        approved_count = sum(1 for status in image_approvals.values() if status == 'approved')
        
        if approved_count < 20:
            logger.warning(f"[VIDEO-GEN] Not all images approved: {approved_count}/20 for story {story_id}")
            return jsonify({"error": f"Only {approved_count}/20 images approved. All images must be approved before video generation."}), 400
        
        logger.info(f"[VIDEO-GEN] Starting video generation for story {story_id} with {approved_count}/20 approved images")
        
        # Update story status to video processing
        update_story_data(story_id, {'status': 'generating_videos'})
        
        # Start video generation in background thread
        def generate_videos_async():
            try:
                logger.info(f"[VIDEO-GEN] Background video generation starting for story {story_id}")
                
                # Get approved images from story data
                images = story_data.get('images', {})
                answers = story_data.get('answers', {})
                sheet_title = answers.get('idea', 'NoSheet_DefaultIdea')
                
                video_urls = {}
                successful_videos = 0
                
                # Emit video generation start event
                try:
                    with app.app_context():
                        sse.publish({
                            "status": "started",
                            "total_videos": 20,
                            "completed_videos": 0
                        }, type='video_generation_started', channel=story_id)
                        logger.info(f"[VIDEO-GEN] Emitted video generation start event for story {story_id}")
                except Exception as sse_error:
                    logger.error(f"[VIDEO-GEN] Failed to emit start event: {sse_error}")
                
                # Process each image for video generation
                for scene_number in range(1, 21):
                    try:
                        scene_str = str(scene_number)
                        scene_images = images.get(scene_str, [])
                        
                        if not scene_images:
                            logger.warning(f"[VIDEO-GEN] No images found for scene {scene_number}")
                            continue
                            
                        # Use the first approved image for video generation
                        image_url = scene_images[0] if isinstance(scene_images, list) else scene_images
                        
                        if image_url and image_url != "Skipped":
                            logger.info(f"[VIDEO-GEN] Generating video for scene {scene_number}")
                            
                            # Generate video using existing process_video function
                            video_url = process_video(scene_str, image_url, sheet_title)
                            
                            if video_url:
                                video_urls[scene_str] = video_url
                                successful_videos += 1
                                
                                logger.info(f"[VIDEO-GEN] Video {scene_number} completed: {video_url}")
                                
                                # Emit progress event
                                try:
                                    with app.app_context():
                                        sse.publish({
                                            "scene_number": scene_number,
                                            "video_url": video_url,
                                            "completed_videos": successful_videos,
                                            "total_videos": 20
                                        }, type='video_ready', channel=story_id)
                                except Exception as sse_error:
                                    logger.error(f"[VIDEO-GEN] Failed to emit video ready event: {sse_error}")
                            else:
                                logger.error(f"[VIDEO-GEN] Failed to generate video for scene {scene_number}")
                        else:
                            logger.warning(f"[VIDEO-GEN] Skipping video generation for scene {scene_number} (no valid image URL)")
                            
                    except Exception as scene_error:
                        logger.error(f"[VIDEO-GEN] Error processing scene {scene_number}: {scene_error}")
                        logger.error(f"[VIDEO-GEN] Scene error traceback: {traceback.format_exc()}")
                
                # Update story data with video URLs
                update_story_data(story_id, {
                    'status': 'videos_completed',
                    'videos': video_urls
                })
                
                # Emit completion event
                try:
                    with app.app_context():
                        sse.publish({
                            "status": "completed",
                            "successful_videos": successful_videos,
                            "total_videos": 20,
                            "video_urls": video_urls
                        }, type='video_generation_complete', channel=story_id)
                        logger.info(f"[VIDEO-GEN] Video generation completed for story {story_id}: {successful_videos}/20 videos")
                except Exception as sse_error:
                    logger.error(f"[VIDEO-GEN] Failed to emit completion event: {sse_error}")
                    
            except Exception as e:
                logger.error(f"[VIDEO-GEN] Background video generation failed for story {story_id}: {e}")
                logger.error(f"[VIDEO-GEN] Error traceback: {traceback.format_exc()}")
                
                # Update status to error
                update_story_data(story_id, {'status': 'video_generation_failed'})
                
                try:
                    with app.app_context():
                        sse.publish({
                            "status": "error",
                            "error": str(e)
                        }, type='video_generation_error', channel=story_id)
                except Exception as sse_error:
                    logger.error(f"[VIDEO-GEN] Failed to emit error event: {sse_error}")
        
        # Start background thread for video generation
        video_thread = threading.Thread(target=generate_videos_async)
        video_thread.daemon = True
        video_thread.start()
        
        # Store thread reference (non-serializable, stored in memory only)
        active_stories[story_id]['video_thread'] = video_thread
        
        logger.info(f"[VIDEO-GEN] Video generation started for story {story_id}")
        return jsonify({
            "message": "Video generation started",
            "story_id": story_id,
            "status": "generating_videos"
        })
        
    except Exception as e:
        logger.error(f"[VIDEO-GEN] Error in approve_videos endpoint: {e}")
        logger.error(f"[VIDEO-GEN] Error traceback: {traceback.format_exc()}")
        return jsonify({"error": "Failed to start video generation"}), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({"status": "online"})

def start_keep_alive_thread():
    """Start background thread to keep app awake on Render free tier"""
    def keep_alive():
        while True:
            try:
                time.sleep(600)  # Sleep for 10 minutes
                logger.info("[KEEP-ALIVE] Internal ping to prevent Render app sleep")
                # Make internal health check to keep app awake
                import requests
                try:
                    response = requests.get("http://localhost:5000/health", timeout=30)
                    logger.info(f"[KEEP-ALIVE] Health check response: {response.status_code}")
                except Exception as ping_error:
                    logger.warning(f"[KEEP-ALIVE] Health check failed: {ping_error}")
            except Exception as e:
                logger.error(f"[KEEP-ALIVE] Keep-alive thread error: {e}")
    
    # Start keep-alive thread for Render deployments
    if os.getenv("RENDER"):  # Render sets this environment variable
        keep_alive_thread = threading.Thread(target=keep_alive)
        keep_alive_thread.daemon = True
        keep_alive_thread.start()
        logger.info("[KEEP-ALIVE] Started keep-alive thread for Render deployment")
    else:
        logger.info("[KEEP-ALIVE] Skipping keep-alive thread (not on Render)")

if __name__ == '__main__':
    # Start keep-alive thread for Render deployments
    start_keep_alive_thread()
    
    # Set debug mode via environment variable for production control
    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(debug=debug_mode, host='0.0.0.0', port=5000)