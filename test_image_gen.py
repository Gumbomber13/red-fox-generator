#!/usr/bin/env python3
"""
Isolated test script for image generation without the full app pipeline.
Tests image generation and upload functionality with different prompt lengths.
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
        logging.FileHandler('test_image_gen.log', mode='a')
    ]
)
logger = logging.getLogger(__name__)

def test_image_generation():
    """Test image generation with different prompt lengths"""
    try:
        # Import functions from Animalchannel
        from Animalchannel import generate_image, upload_image
        
        # Test with short prompt
        logger.info("Testing with short prompt...")
        short_prompt = "red fox"
        logger.info(f"Short prompt: {short_prompt}")
        
        img_data_short = generate_image(short_prompt)
        logger.info(f"Short prompt image data: {len(img_data_short)} bytes")
        
        url_short = upload_image(img_data_short)
        logger.info(f"Short prompt image URL: {url_short}")
        
        # Test with long prompt (>1024 chars)
        logger.info("Testing with long prompt...")
        long_prompt = "A majestic red fox with vibrant orange-red fur and distinctive white markings on its chest and tail tip, standing proudly in a mystical forest clearing during the golden hour. The fox has intelligent amber eyes that seem to glow with ancient wisdom, pointed ears that are alert and attentive, and a magnificent bushy tail with a white tip. The setting is an enchanted woodland with towering ancient oak trees whose gnarled branches create intricate patterns against the soft golden sunlight filtering through the canopy. Dappled light creates magical spots of illumination on the forest floor, which is carpeted with vibrant green moss, fallen autumn leaves in shades of gold, amber, and deep red, and delicate wildflowers including bluebells and white wood anemones. In the background, ethereal mist swirls between the tree trunks, and particles of light dance in the air like fairy dust. The atmosphere is serene and mystical, with a sense of ancient magic permeating the scene. The fox appears confident and regal, as if it is the guardian spirit of this enchanted realm, with every detail of its fur texture clearly visible and meticulously rendered."
        logger.info(f"Long prompt length: {len(long_prompt)} characters")
        
        img_data_long = generate_image(long_prompt)
        logger.info(f"Long prompt image data: {len(img_data_long)} bytes")
        
        url_long = upload_image(img_data_long)
        logger.info(f"Long prompt image URL: {url_long}")
        
        logger.info("✅ All image generation tests passed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Image generation test failed: {str(e)}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        return False

if __name__ == "__main__":
    logger.info("Starting isolated image generation test...")
    success = test_image_generation()
    if success:
        logger.info("Test completed successfully")
    else:
        logger.error("Test failed")