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
from Animalchannel import process_story_generation, process_story_generation_with_scenes

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

# Store active story sessions and heartbeat timers
active_stories = {}
heartbeat_timers = {}

def emit_image_event(story_id, scene_number, image_url, status="completed"):
    """Emit image generation event via SSE"""
    logger.info(f"[SSE-FIX] emit_image_event called: story={story_id}, scene={scene_number}, status={status}")
    logger.debug(f"[SSE-DETAILED] Thread info: current={threading.current_thread().name}, daemon={threading.current_thread().daemon}")
    logger.debug(f"[SSE-DETAILED] Flask app context available: {bool(app.app_context)}")
    if story_id in active_stories:
        active_stories[story_id]['images'][scene_number] = {
            'url': image_url,
            'status': status
        }
        
        # Initialize approval status for pending_approval images
        if status == "pending_approval":
            active_stories[story_id]['image_approvals'][scene_number] = 'pending'
            active_stories[story_id]['completed_scenes'] += 1  # Count pending_approval as completed for progress tracking
            logger.info(f"[APPROVAL] Image {scene_number} set to pending approval")
        elif status == "completed":
            active_stories[story_id]['completed_scenes'] += 1
        
        # Debug logging: Print full active_stories state after update
        story_state = active_stories[story_id]
        logger.info(f"[DEBUG-DATA] Story {story_id} state after scene {scene_number} update:")
        logger.info(f"[DEBUG-DATA] Status: {story_state['status']}, Completed: {story_state['completed_scenes']}/{story_state['total_scenes']}")
        logger.info(f"[DEBUG-DATA] Images dict: {len(story_state['images'])} scenes - {list(story_state['images'].keys())}")
        logger.info(f"[DEBUG-DATA] Full story state: {story_state}")
        
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
                        "completed_scenes": active_stories[story_id]['completed_scenes'],
                        "total_scenes": active_stories[story_id]['total_scenes']
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
        
        # Store story session
        active_stories[story_id] = {
            'status': 'processing',
            'answers': original_answers,
            'scenes': approved_scenes,
            'images': {},
            'total_scenes': 20,
            'completed_scenes': 0,
            'image_approvals': {}  # Track approval status: {scene_number: 'pending' | 'approved' | 'rejected'}
        }
        
        # Start heartbeat to keep SSE connection alive
        send_heartbeat(story_id)
        
        # Start story generation in background process with approved scenes
        def generate_story_async():
            try:
                process_story_generation_with_scenes(approved_scenes, original_answers, story_id)
                # Mark as completed and stop heartbeat
                if story_id in active_stories:
                    active_stories[story_id]['status'] = 'completed'
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
                if story_id in active_stories:
                    active_stories[story_id]['status'] = 'failed'
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
        
        # Store thread reference for potential monitoring (shared memory with main process)
        active_stories[story_id]['process'] = thread
        
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
    
    if story_id not in active_stories:
        logger.warning(f"Story not found: {story_id}")
        return jsonify({'error': 'Story not found'}), 404
    
    story = active_stories[story_id]
    
    # Log the current state for debugging
    logger.debug(f"Story {story_id} status: {story['status']}, completed: {story['completed_scenes']}/{story['total_scenes']}")
    logger.debug(f"Story {story_id} images: {len(story['images'])} images available")
    
    return jsonify({
        'status': story['status'],
        'completed_scenes': story['completed_scenes'],
        'total_scenes': story['total_scenes'],
        'images': story['images']
    })

@app.route('/debug_story/<story_id>', methods=['GET'])
def debug_story_full(story_id):
    """Debug endpoint to return full active_stories state for manual checking"""
    logger.info(f"[DEBUG-ENDPOINT] Full debug request for story ID: {story_id}")
    
    if story_id not in active_stories:
        logger.warning(f"[DEBUG-ENDPOINT] Story not found: {story_id}")
        return jsonify({'error': 'Story not found'}), 404
    
    story = active_stories[story_id]
    
    # Log the full state
    logger.info(f"[DEBUG-ENDPOINT] Full story state for {story_id}: {story}")
    
    # Return complete story state for debugging
    return jsonify({
        'story_id': story_id,
        'full_state': story,
        'timestamp': time.time(),
        'total_active_stories': len(active_stories),
        'active_story_ids': list(active_stories.keys())
    })

@app.route('/approve_image/<story_id>/<int:scene_number>', methods=['POST'])
def approve_image(story_id, scene_number):
    """Handle image approval/rejection"""
    try:
        data = request.get_json()
        action = data.get('action')  # 'approve' or 'reject'
        
        if story_id not in active_stories:
            logger.warning(f"Story not found for approval: {story_id}")
            return jsonify({'error': 'Story not found'}), 404
        
        if action not in ['approve', 'reject']:
            logger.warning(f"Invalid action: {action}")
            return jsonify({'error': 'Invalid action'}), 400
        
        # Update approval status
        active_stories[story_id]['image_approvals'][scene_number] = action + 'd'  # 'approved' or 'rejected'
        logger.info(f"[APPROVAL] Image {scene_number} {action}d for story {story_id}")
        
        # Handle rejection - trigger regeneration
        if action == 'reject':
            logger.info(f"[APPROVAL] Triggering regeneration for rejected image {scene_number}")
            # Get the current prompt for regeneration
            try:
                # Import here to avoid circular imports
                from Animalchannel import process_image
                
                # Get scene text and regenerate
                scenes = active_stories[story_id]['scenes']
                scene_key = f'Scene{scene_number}'
                
                if scene_key in scenes:
                    scene_text = scenes[scene_key]
                    
                    # Create a simple prompt from scene text for regeneration
                    regeneration_prompt = f"Digital art of: {scene_text}"
                    
                    # Start regeneration in background thread
                    def regenerate_image():
                        try:
                            new_url = process_image(str(scene_number), regeneration_prompt, 
                                                 f"Regen_{story_id}", story_id)
                            if new_url:
                                logger.info(f"[APPROVAL] Successfully regenerated image {scene_number}")
                            else:
                                logger.error(f"[APPROVAL] Failed to regenerate image {scene_number}")
                        except Exception as e:
                            logger.error(f"[APPROVAL] Regeneration error for image {scene_number}: {e}")
                    
                    # Start regeneration in background
                    thread = threading.Thread(target=regenerate_image)
                    thread.daemon = True
                    thread.start()
                else:
                    logger.warning(f"[APPROVAL] Scene text not found for regeneration: {scene_key}")
                    
            except Exception as e:
                logger.error(f"[APPROVAL] Error setting up regeneration: {e}")
        
        # Check if all images are approved
        approvals = active_stories[story_id]['image_approvals']
        total_images = active_stories[story_id]['total_scenes']
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
            'total_images': total_images
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