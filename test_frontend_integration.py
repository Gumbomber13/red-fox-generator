#!/usr/bin/env python3
"""
Test script to verify frontend integration endpoints work correctly
"""
import os
import sys
import json
import uuid
from flask import Flask
from flask_cors import CORS

# Add current directory to path
sys.path.insert(0, os.getcwd())

# Import the Flask app
from flask_server import app, active_stories

def test_frontend_integration():
    """Test frontend integration endpoints"""
    print("=== Testing Frontend Integration ===")
    
    # Create test story data
    test_story_id = str(uuid.uuid4())
    active_stories[test_story_id] = {
        'status': 'processing',
        'completed_scenes': 3,
        'total_scenes': 20,
        'images': {
            '1': {'url': 'https://res.cloudinary.com/demo/image/upload/v1234/sample1.jpg', 'status': 'completed'},
            '2': {'url': 'https://res.cloudinary.com/demo/image/upload/v1234/sample2.jpg', 'status': 'completed'},
            '3': {'url': 'https://res.cloudinary.com/demo/image/upload/v1234/sample3.jpg', 'status': 'completed'}
        }
    }
    
    print(f"Created test story with ID: {test_story_id}")
    
    with app.test_client() as client:
        # Test 1: Health endpoint
        print("\n1. Testing health endpoint...")
        response = client.get('/health')
        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'online'
        print("OK Health endpoint working")
        
        # Test 2: Story status endpoint
        print("\n2. Testing story status endpoint...")
        response = client.get(f'/story/{test_story_id}')
        assert response.status_code == 200
        data = response.get_json()
        
        # Verify response structure
        assert 'status' in data
        assert 'completed_scenes' in data
        assert 'total_scenes' in data
        assert 'images' in data
        
        # Verify data values
        assert data['status'] == 'processing'
        assert data['completed_scenes'] == 3
        assert data['total_scenes'] == 20
        assert len(data['images']) == 3
        
        # Verify image structure
        for scene_num in ['1', '2', '3']:
            assert scene_num in data['images']
            assert 'url' in data['images'][scene_num]
            assert 'status' in data['images'][scene_num]
            assert data['images'][scene_num]['status'] == 'completed'
            assert data['images'][scene_num]['url'].startswith('https://res.cloudinary.com/')
        
        print("OK Story status endpoint working")
        print(f"  - Status: {data['status']}")
        print(f"  - Progress: {data['completed_scenes']}/{data['total_scenes']}")
        print(f"  - Images: {len(data['images'])} available")
        
        # Test 3: Test emit endpoint
        print("\n3. Testing SSE test emit endpoint...")
        response = client.get(f'/test_emit/{test_story_id}')
        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'Test emitted successfully'
        print("OK SSE test emit endpoint working")
        
        # Test 4: Invalid story ID
        print("\n4. Testing invalid story ID...")
        response = client.get('/story/invalid-story-id')
        assert response.status_code == 404
        data = response.get_json()
        assert 'error' in data
        assert data['error'] == 'Story not found'
        print("OK Invalid story ID handled correctly")
        
        # Test 5: CORS headers
        print("\n5. Testing CORS headers...")
        response = client.get('/health')
        assert 'Access-Control-Allow-Origin' in response.headers
        print("OK CORS headers present")
        
    print("\n=== All Frontend Integration Tests Passed! ===")
    print(f"Test story ID: {test_story_id}")
    print("Frontend can now:")
    print("- Fetch story status via GET /story/<id>")
    print("- Receive JSON with image URLs")
    print("- Handle missing stories gracefully")
    print("- Access all endpoints with CORS support")
    
    # Clean up
    del active_stories[test_story_id]
    print("\nTest story cleaned up.")

if __name__ == "__main__":
    test_frontend_integration()