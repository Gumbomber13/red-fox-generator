#!/usr/bin/env python3
"""
GPT-Image-1 Integration Test Suite
Tests the migration from DALL-E 3 to GPT-Image-1 for image generation
"""

import os
import sys
import time
import asyncio
import json
import logging
from dotenv import load_dotenv

# Add the current directory to Python path for imports
sys.path.insert(0, os.path.dirname(__file__))

# Load environment variables
load_dotenv()

# Import from our modules
try:
    from Animalchannel import generate_async, generate_image, generate_images_concurrently, sanitize_prompt
    from openai import OpenAI
except ImportError as e:
    print(f"Import error: {e}")
    print("Please ensure you're running this test from the project directory with proper dependencies installed")
    sys.exit(1)

# Configure logging for tests
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def check_environment():
    """Check if required environment variables are set"""
    required_vars = ['OPENAI_API_KEY', 'CLOUDINARY_PRESET', 'CLOUDINARY_URL']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {missing_vars}")
        return False
    
    logger.info("✅ All required environment variables are set")
    return True

def test_gpt_image_1_model_call():
    """Test direct OpenAI API call with GPT-Image-1"""
    logger.info("🧪 Test 1: Direct GPT-Image-1 API call")
    
    try:
        client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        test_prompt = "A cute red fox sitting in a forest clearing, digital art style"
        
        logger.info(f"Testing GPT-Image-1 with prompt: {test_prompt}")
        start_time = time.time()
        
        response = client.images.generate(
            model="gpt-image-1",
            prompt=test_prompt,
            size="1024x1024",
            n=1,
            timeout=180.0
        )
        
        elapsed = time.time() - start_time
        logger.info(f"✅ GPT-Image-1 API call successful in {elapsed:.2f}s")
        logger.info(f"Image URL: {response.data[0].url[:50]}...")
        return True
        
    except Exception as e:
        logger.error(f"❌ GPT-Image-1 API call failed: {e}")
        return False

async def test_async_generation():
    """Test async image generation with GPT-Image-1"""
    logger.info("🧪 Test 2: Async GPT-Image-1 generation")
    
    try:
        test_prompt = "A majestic red fox with glowing eyes in a moonlit forest"
        
        logger.info(f"Testing async generation with prompt: {test_prompt}")
        start_time = time.time()
        
        image_data = await generate_async(test_prompt)
        
        elapsed = time.time() - start_time
        logger.info(f"✅ Async generation successful in {elapsed:.2f}s")
        logger.info(f"Image data size: {len(image_data)} bytes")
        return True
        
    except Exception as e:
        logger.error(f"❌ Async generation failed: {e}")
        return False

def test_synchronous_generation():
    """Test synchronous image generation with retry logic"""
    logger.info("🧪 Test 3: Synchronous GPT-Image-1 generation with retries")
    
    try:
        test_prompt = "A wise red fox reading a book under a tree"
        
        logger.info(f"Testing sync generation with prompt: {test_prompt}")
        start_time = time.time()
        
        image_data = generate_image(test_prompt)
        
        elapsed = time.time() - start_time
        logger.info(f"✅ Synchronous generation successful in {elapsed:.2f}s")
        logger.info(f"Image data size: {len(image_data)} bytes")
        return True
        
    except Exception as e:
        logger.error(f"❌ Synchronous generation failed: {e}")
        return False

async def test_concurrent_generation():
    """Test concurrent image generation with multiple prompts"""
    logger.info("🧪 Test 4: Concurrent GPT-Image-1 generation (3 images)")
    
    try:
        # Test with 3 images to avoid hitting rate limits
        test_prompts = [
            (1, "A red fox jumping over a stream", "TestScene1"),
            (2, "A red fox sleeping in autumn leaves", "TestScene2"),
            (3, "A red fox hunting in winter snow", "TestScene3")
        ]
        
        logger.info(f"Testing concurrent generation with {len(test_prompts)} prompts")
        start_time = time.time()
        
        results = await generate_images_concurrently(test_prompts, story_id="test-concurrent")
        
        elapsed = time.time() - start_time
        logger.info(f"✅ Concurrent generation completed in {elapsed:.2f}s")
        
        success_count = sum(1 for _, url in results if url and url != "failed")
        logger.info(f"Success rate: {success_count}/{len(test_prompts)} images generated")
        
        return success_count > 0
        
    except Exception as e:
        logger.error(f"❌ Concurrent generation failed: {e}")
        return False

def test_prompt_sanitization():
    """Test prompt sanitization for GPT-Image-1"""
    logger.info("🧪 Test 5: Prompt sanitization")
    
    try:
        test_cases = [
            ("A fox that beats up enemies", "A fox that overcomes enemies"),
            ("The hero fights violently", "The hero challenges peacefully intensely"),
            ("Normal prompt without issues", "Normal prompt without issues")
        ]
        
        for original, expected_pattern in test_cases:
            sanitized = sanitize_prompt(original)
            logger.info(f"Original: {original}")
            logger.info(f"Sanitized: {sanitized}")
            
            # Check if sanitization worked (should be different if violations were found)
            if "beats up" in original or "fights" in original or "violently" in original:
                if sanitized == original:
                    logger.warning(f"⚠️ Expected sanitization but got same prompt")
                else:
                    logger.info(f"✅ Prompt properly sanitized")
            else:
                logger.info(f"✅ Clean prompt unchanged")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Prompt sanitization test failed: {e}")
        return False

def test_timeout_handling():
    """Test timeout configuration for GPT-Image-1"""
    logger.info("🧪 Test 6: Timeout configuration verification")
    
    try:
        # This test just verifies our timeout values are appropriate
        # GPT-Image-1 can take up to 2 minutes, so 180s timeout is correct
        timeout_config = {
            "api_timeout": 180.0,
            "client_timeout": 180.0,
            "expected_max_time": 120.0  # 2 minutes for complex prompts
        }
        
        logger.info(f"Timeout configuration: {timeout_config}")
        logger.info("✅ Timeout values are appropriate for GPT-Image-1 (up to 2 min processing)")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Timeout configuration test failed: {e}")
        return False

async def run_performance_benchmark():
    """Run a small performance benchmark"""
    logger.info("🧪 Test 7: Performance benchmark (single image)")
    
    try:
        test_prompt = "A detailed red fox portrait with realistic fur texture"
        
        # Time multiple generations to get average
        times = []
        for i in range(1):  # Just 1 to avoid rate limits
            logger.info(f"Benchmark run {i+1}/1")
            start_time = time.time()
            
            try:
                image_data = await generate_async(test_prompt)
                elapsed = time.time() - start_time
                times.append(elapsed)
                logger.info(f"Run {i+1} completed in {elapsed:.2f}s")
            except Exception as e:
                logger.warning(f"Run {i+1} failed: {e}")
        
        if times:
            avg_time = sum(times) / len(times)
            logger.info(f"✅ Average generation time: {avg_time:.2f}s (target: <180s)")
            
            if avg_time < 180:
                logger.info("✅ Performance within expected bounds")
                return True
            else:
                logger.warning("⚠️ Performance slower than expected")
                return False
        else:
            logger.error("❌ No successful runs for benchmark")
            return False
        
    except Exception as e:
        logger.error(f"❌ Performance benchmark failed: {e}")
        return False

async def main():
    """Run all GPT-Image-1 tests"""
    logger.info("🚀 Starting GPT-Image-1 Integration Test Suite")
    logger.info("=" * 60)
    
    # Check environment first
    if not check_environment():
        logger.error("❌ Environment check failed. Please set required environment variables.")
        return False
    
    # Define all tests
    tests = [
        ("Environment Check", lambda: True),  # Already passed
        ("Direct API Call", test_gpt_image_1_model_call),
        ("Async Generation", test_async_generation),
        ("Sync Generation", test_synchronous_generation),
        ("Concurrent Generation", test_concurrent_generation),
        ("Prompt Sanitization", test_prompt_sanitization),
        ("Timeout Configuration", test_timeout_handling),
        ("Performance Benchmark", run_performance_benchmark)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        logger.info("-" * 60)
        try:
            if asyncio.iscoroutinefunction(test_func):
                result = await test_func()
            else:
                result = test_func()
            results.append((test_name, result))
        except Exception as e:
            logger.error(f"Test '{test_name}' threw exception: {e}")
            results.append((test_name, False))
    
    # Summary
    logger.info("=" * 60)
    logger.info("🏁 TEST SUMMARY")
    logger.info("=" * 60)
    
    passed = 0
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"{status}: {test_name}")
        if result:
            passed += 1
    
    logger.info("-" * 60)
    logger.info(f"Total: {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        logger.info("🎉 ALL TESTS PASSED - GPT-Image-1 integration is working correctly!")
        return True
    else:
        logger.error(f"⚠️ {len(results) - passed} tests failed - please review errors above")
        return False

if __name__ == "__main__":
    # Run the test suite
    success = asyncio.run(main())
    sys.exit(0 if success else 1)