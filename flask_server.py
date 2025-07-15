from flask import Flask, request, jsonify
from flask_cors import CORS
import json
from Animalchannel import process_story_generation

app = Flask(__name__)
CORS(app)

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
        
        # Process the complete story generation pipeline
        process_story_generation(answers)
        
        # Return success response
        return jsonify({"status": "ok", "message": "Story generation started successfully"})
        
    except Exception as e:
        print(f"Error processing request: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({"status": "online"})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)