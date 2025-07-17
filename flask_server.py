from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sse import sse
import json
import traceback
import uuid
import threading
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
    print(f"⚠️ Warning: Flask-SSE setup failed: {e}")
    print("SSE functionality will not be available")

# Store active story sessions
active_stories = {}

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
        except Exception as e:
            print(f"⚠️ Warning: Could not emit SSE event: {e}")
            print(f"Scene {scene_number} image ready: {image_url}")

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
        
        # Start story generation in background thread with approved scenes
        def generate_story_async():
            try:
                process_story_generation_with_scenes(approved_scenes, original_answers, story_id)
                # Mark as completed
                if story_id in active_stories:
                    active_stories[story_id]['status'] = 'completed'
                    try:
                        sse.publish({"status": "completed"}, type='story_complete', channel=story_id)
                    except Exception as sse_error:
                        print(f"⚠️ Warning: Could not emit completion event: {sse_error}")
            except Exception as e:
                # Mark as failed
                if story_id in active_stories:
                    active_stories[story_id]['status'] = 'failed'
                    try:
                        sse.publish({"status": "failed", "error": str(e)}, type='story_error', channel=story_id)
                    except Exception as sse_error:
                        print(f"⚠️ Warning: Could not emit error event: {sse_error}")
                        print(f"Story generation failed: {e}")
        
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