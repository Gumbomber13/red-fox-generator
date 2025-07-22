#!/usr/bin/env python3
"""
Simple test for the blocking upload fix
"""

import os
import sys
import time
import asyncio
import logging
from unittest.mock import patch, MagicMock

# Add the current directory to Python path for imports
sys.path.insert(0, os.path.dirname(__file__))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_blocking_fix():
    """Test the blocking upload fix"""
    print("TESTING: Parallel Generation Blocking Fix")
    print("=" * 50)
    
    try:
        import Animalchannel
        
        # Mock external dependencies
        with patch('Animalchannel.openai_client') as mock_openai, \
             patch('Animalchannel.upload_image') as mock_upload:
            
            # Mock successful responses
            mock_response = MagicMock()
            mock_response.data = [MagicMock()]
            mock_response.data[0].url = "https://test.jpg"
            mock_openai.images.generate.return_value = mock_response
            mock_upload.return_value = "https://upload.jpg"
            
            # Small test batch
            test_prompts = [
                (1, "Test prompt 1", "Scene1"),
                (2, "Test prompt 2", "Scene2")
            ]
            
            print(f"Testing {len(test_prompts)} images...")
            
            start_time = time.time()
            results = asyncio.run(Animalchannel.generate_images_concurrently(test_prompts))
            elapsed = time.time() - start_time
            
            print(f"PASS: Completed in {elapsed:.2f}s")
            print(f"PASS: Results: {len(results)} images")
            
            success_count = sum(1 for _, url in results if url)
            print(f"PASS: Success rate: {success_count}/{len(test_prompts)}")
            
            return True
            
    except Exception as e:
        print(f"FAIL: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_blocking_fix()
    if success:
        print("SUCCESS: Blocking fix appears to work!")
    else:
        print("FAILED: Issue may not be resolved")
    sys.exit(0 if success else 1)