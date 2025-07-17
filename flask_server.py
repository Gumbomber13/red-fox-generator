from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sse import sse
import json
import traceback
import uuid
import threading
import time
import os
from Animalchannel import process_story_generation, process_story_generation_with_scenes

app = Flask(__name__)
CORS(app)

# Configure Flask-SSE with Redis (fallback to in-memory for development)
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
app.config["REDIS_URL"] = redis_url
try:
    app.register_blueprint(sse, url_prefix='/stream')
except Exception as e:
    print(f"Warning: Flask-SSE setup failed: {e}")
    print("SSE functionality will not be available")

# Store active story sessions and heartbeat timers
active_stories = {}
heartbeat_timers = {}

def emit_image_event(story_id, scene_number, image_url, status="completed"):
    """Emit image generation event via SSE"""
    if story_id in active_stories:
        active_stories[story_id]['images'][scene_number] = {
            'url': image_url,
            'status': status
        }
        if status == "completed":
            active_stories[story_id]['completed_scenes'] += 1
        
        # Emit the event to connected clients
        try:
            sse.publish({
                "scene_number": scene_number,
                "image_url": image_url,
                "status": status,
                "completed_scenes": active_stories[story_id]['completed_scenes'],
                "total_scenes": active_stories[story_id]['total_scenes']
            }, type='image_ready', channel=story_id)
            print(f"SSE Event emitted successfully: Scene {scene_number} for story {story_id}")
        except Exception as e:
            # Enhanced error logging for SSE connection issues
            print(f"ERROR: Failed to emit SSE event for story {story_id}, scene {scene_number}")
            print(f"Exception type: {type(e).__name__}")
            print(f"Exception message: {str(e)}")
            print(f"Fallback: Scene {scene_number} image ready: {image_url}")
            
            # Try to log to file if possible
            try:
                import datetime
                timestamp = datetime.datetime.now().isoformat()
                with open('sse_errors.log', 'a') as f:
                    f.write(f"{timestamp} - SSE Error: {story_id} - {type(e).__name__}: {str(e)}\n")
            except Exception as log_error:
                print(f"Warning: Could not log to file: {log_error}")

def send_heartbeat(story_id):
    """Send periodic heartbeat/ping events to keep SSE connection alive"""
    def heartbeat_loop():
        while story_id in active_stories and active_stories[story_id]['status'] == 'processing':
            try:
                sse.publish({"timestamp": time.time()}, type='ping', channel=story_id)
                print(f"Sent heartbeat for story {story_id}")
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
        # Print the full traceback to console for debugging
        print("=" * 80)
        print("ERROR IN /submit ENDPOINT:")
        print("=" * 80)
        print(f"Exception Type: {type(e).__name__}")
        print(f"Exception Message: {str(e)}")
        print("-" * 80)
        print("Full Traceback:")
        traceback.print_exc()
        print("=" * 80)
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
            'completed_scenes': 0
        }
        
        # Start heartbeat to keep SSE connection alive
        send_heartbeat(story_id)
        
        # Start story generation in background thread with approved scenes
        def generate_story_async():
            try:
                process_story_generation_with_scenes(approved_scenes, original_answers, story_id)
                # Mark as completed and stop heartbeat
                if story_id in active_stories:
                    active_stories[story_id]['status'] = 'completed'
                    stop_heartbeat(story_id)
                    try:
                        sse.publish({"status": "completed"}, type='story_complete', channel=story_id)
                        print(f"Story completion event emitted successfully for {story_id}")
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
                        sse.publish({"status": "failed", "error": str(e)}, type='story_error', channel=story_id)
                        print(f"Story error event emitted successfully for {story_id}")
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
        
        thread = threading.Thread(target=generate_story_async)
        thread.daemon = True
        thread.start()
        
        # Return story ID for client to connect to SSE stream
        return jsonify({
            "status": "ok", 
            "story_id": story_id,
            "message": "Story generation started successfully"
        })
        
    except Exception as e:
        # Print the full traceback to console for debugging
        print("=" * 80)
        print("ERROR IN /approve_scenes ENDPOINT:")
        print("=" * 80)
        print(f"Exception Type: {type(e).__name__}")
        print(f"Exception Message: {str(e)}")
        print("-" * 80)
        print("Full Traceback:")
        traceback.print_exc()
        print("=" * 80)
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/story/<story_id>', methods=['GET'])
def get_story_status(story_id):
    """Get current status of a story generation"""
    if story_id not in active_stories:
        return jsonify({'error': 'Story not found'}), 404
    
    story = active_stories[story_id]
    return jsonify({
        'status': story['status'],
        'completed_scenes': story['completed_scenes'],
        'total_scenes': story['total_scenes'],
        'images': story['images']
    })

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({"status": "online"})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)