#!/usr/bin/env python3
"""
Isolated test script for SSE emission functionality.
Tests if SSE events can be emitted without the full Flask server.
"""

import logging
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('test_sse_emit.log', mode='a')
    ]
)
logger = logging.getLogger(__name__)

def test_sse_emission():
    """Test SSE event emission functionality"""
    try:
        # Import emit_image_event from flask_server
        from flask_server import emit_image_event, active_stories
        
        # Mock story data
        test_story_id = "test_story_123"
        test_scene_number = 1
        test_image_url = "https://example.com/test_image.jpg"
        
        # Initialize mock story in active_stories
        active_stories[test_story_id] = {
            'images': {},
            'completed_scenes': 0,
            'total_scenes': 20
        }
        
        logger.info(f"Testing SSE emission for story: {test_story_id}")
        logger.info(f"Scene: {test_scene_number}, URL: {test_image_url}")
        
        # Test the emit function
        emit_image_event(test_story_id, test_scene_number, test_image_url, "completed")
        
        # Check if the story was updated
        if test_story_id in active_stories:
            story_data = active_stories[test_story_id]
            if test_scene_number in story_data['images']:
                image_data = story_data['images'][test_scene_number]
                logger.info(f"✅ Story updated successfully: {image_data}")
                logger.info(f"✅ Completed scenes: {story_data['completed_scenes']}")
            else:
                logger.warning("⚠️ Scene not found in story images")
        else:
            logger.warning("⚠️ Story not found in active_stories")
        
        # Clean up
        if test_story_id in active_stories:
            del active_stories[test_story_id]
        
        logger.info("✅ SSE emission test completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"❌ SSE emission test failed: {str(e)}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        return False

if __name__ == "__main__":
    logger.info("Starting isolated SSE emission test...")
    success = test_sse_emission()
    if success:
        logger.info("Test completed successfully")
    else:
        logger.error("Test failed")