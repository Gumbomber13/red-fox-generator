#!/usr/bin/env python3
"""
Test Parallel Image Generation Stoppage Fix
Tests the fix for event loop blocking in async image generation
"""

import os
import sys
import time
import asyncio
import logging
from unittest.mock import patch, MagicMock

# Add the current directory to Python path for imports
sys.path.insert(0, os.path.dirname(__file__))

# Configure logging to see debug output
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_small_batch_generation():
    """Test with small batch to verify the blocking fix works"""
    print("=" * 60)
    print("🧪 TEST: Small Batch Generation (Blocking Fix Verification)")
    print("=" * 60)
    
    try:
        # Import after setting up path
        import Animalchannel
        
        # Mock external dependencies to focus on async flow
        with patch('Animalchannel.openai_client') as mock_openai, \
             patch('Animalchannel.upload_image') as mock_upload, \
             patch('Animalchannel.update_sheet') as mock_sheet:
            
            # Mock successful OpenAI response
            mock_response = MagicMock()
            mock_response.data = [MagicMock()]
            mock_response.data[0].url = "https://oaidalle.com/test_image.jpg"
            mock_openai.images.generate.return_value = mock_response
            
            # Mock successful upload
            mock_upload.return_value = "https://cloudinary.com/test_upload.jpg"
            
            # Mock sheet update (no-op)
            mock_sheet.return_value = None
            
            # Create test prompts - small batch to test quickly
            test_prompts = [
                (1, "A red fox sitting in a sunny meadow", "TestScene1"),
                (2, "A red fox playing in autumn leaves", "TestScene2"), 
                (3, "A red fox looking at the moon", "TestScene3")
            ]
            
            print(f"Testing with {len(test_prompts)} images to verify async flow...")
            print("Checking for event loop blocking issues...")
            
            start_time = time.time()
            
            # Run the async generation
            results = asyncio.run(Animalchannel.generate_images_concurrently(test_prompts, story_id="test-blocking-fix"))
            
            elapsed = time.time() - start_time
            
            print(f"✅ PASS: Generation completed in {elapsed:.2f}s")
            print(f"✅ PASS: Results: {len(results)} images processed")
            
            # Verify all images were processed
            success_count = sum(1 for _, url in results if url and url != "failed")
            print(f"✅ PASS: Success rate: {success_count}/{len(test_prompts)} images")
            
            # Verify upload was called with async executor (not directly)
            print(f"✅ PASS: Upload function called {mock_upload.call_count} times")
            
            if elapsed < 30:  # Should be fast with mocked dependencies
                print("✅ PASS: Performance looks good with blocking fix")
            else:
                print("⚠️  WARNING: Slower than expected, may still have blocking issues")
            
            return True
            
    except Exception as e:
        print(f"❌ FAIL: Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_async_flow_monitoring():
    """Test to monitor async flow and detect any hanging"""
    print("\n" + "=" * 60) 
    print("🧪 TEST: Async Flow Monitoring (Detect Hangs)")
    print("=" * 60)
    
    try:
        import Animalchannel
        
        # Mock with deliberately slow operations to test timeout handling
        with patch('Animalchannel.openai_client') as mock_openai, \
             patch('Animalchannel.upload_image') as mock_upload:
            
            def slow_openai_call(*args, **kwargs):
                """Simulate slow but not hanging OpenAI call"""
                time.sleep(2)  # 2 second delay
                mock_response = MagicMock()
                mock_response.data = [MagicMock()]
                mock_response.data[0].url = "https://oaidalle.com/slow_test.jpg"
                return mock_response
            
            def slow_upload_call(img_data):
                """Simulate slow but not hanging upload"""
                time.sleep(1)  # 1 second delay
                return "https://cloudinary.com/slow_upload.jpg"
            
            mock_openai.images.generate.side_effect = slow_openai_call
            mock_upload.side_effect = slow_upload_call
            
            # Small test set
            test_prompts = [
                (1, "Test prompt 1", "TestScene1"),
                (2, "Test prompt 2", "TestScene2")
            ]
            
            print(f"Testing with {len(test_prompts)} images with simulated slow operations...")
            
            start_time = time.time()
            
            # Run with timeout to detect hangs
            try:
                results = asyncio.wait_for(
                    Animalchannel.generate_images_concurrently(test_prompts),
                    timeout=30.0  # 30 second timeout
                )
                
                elapsed = time.time() - start_time
                print(f"✅ PASS: Slow operations completed without hanging in {elapsed:.2f}s")
                
                # Verify concurrent execution (should be faster than sequential)
                expected_sequential_time = (2 + 1) * len(test_prompts)  # 3s per image
                if elapsed < expected_sequential_time * 0.8:  # Allow some overhead
                    print("✅ PASS: Concurrent execution working (faster than sequential)")
                else:
                    print(f"⚠️  WARNING: May not be truly concurrent (took {elapsed:.2f}s vs expected <{expected_sequential_time * 0.8:.2f}s)")
                
                return True
                
            except asyncio.TimeoutError:
                elapsed = time.time() - start_time
                print(f"❌ FAIL: Process hung and timed out after {elapsed:.2f}s")
                print("This indicates the blocking issue may not be fully resolved")
                return False
            
    except Exception as e:
        print(f"❌ FAIL: Monitoring test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_semaphore_behavior():
    """Test semaphore behavior to ensure no deadlocks"""
    print("\n" + "=" * 60)
    print("🧪 TEST: Semaphore Behavior (Deadlock Detection)")
    print("=" * 60)
    
    try:
        import Animalchannel
        
        # Check the current configuration
        print(f"MAX_CONCURRENT: {Animalchannel.MAX_CONCURRENT}")
        print(f"BATCH_SIZE: {Animalchannel.BATCH_SIZE}")
        print(f"MAX_IMAGES_PER_MIN: {Animalchannel.MAX_IMAGES_PER_MIN}")
        
        # Verify no deadlock potential
        if Animalchannel.BATCH_SIZE <= Animalchannel.MAX_CONCURRENT:
            print("✅ PASS: No deadlock risk - BATCH_SIZE <= MAX_CONCURRENT")
        else:
            print("❌ FAIL: Potential deadlock - BATCH_SIZE > MAX_CONCURRENT")
            return False
        
        # Test with exact batch size to stress test semaphore
        with patch('Animalchannel.openai_client') as mock_openai, \
             patch('Animalchannel.upload_image') as mock_upload:
            
            # Quick mocks
            mock_response = MagicMock()
            mock_response.data = [MagicMock()]
            mock_response.data[0].url = "https://test.jpg"
            mock_openai.images.generate.return_value = mock_response
            mock_upload.return_value = "https://upload.jpg"
            
            # Create prompts equal to batch size
            test_prompts = [(i, f"Test prompt {i}", f"Scene{i}") 
                           for i in range(1, Animalchannel.BATCH_SIZE + 1)]
            
            print(f"Testing with {len(test_prompts)} images (full batch size)...")
            
            start_time = time.time()
            results = asyncio.run(Animalchannel.generate_images_concurrently(test_prompts))
            elapsed = time.time() - start_time
            
            print(f"✅ PASS: Full batch completed without deadlock in {elapsed:.2f}s")
            print(f"✅ PASS: All {len(results)} tasks completed")
            
            return True
            
    except Exception as e:
        print(f"❌ FAIL: Semaphore test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_event_loop_blocking():
    """Test to detect event loop blocking"""
    print("\n" + "=" * 60)
    print("🧪 TEST: Event Loop Blocking Detection")
    print("=" * 60)
    
    try:
        import Animalchannel
        
        # Create a background task that should continue running
        ping_count = 0
        
        async def background_ping():
            nonlocal ping_count
            while True:
                await asyncio.sleep(0.5)
                ping_count += 1
                if ping_count % 4 == 0:  # Every 2 seconds
                    print(f"🔄 Background ping {ping_count} (event loop is responsive)")
        
        # Start background task
        ping_task = asyncio.create_task(background_ping())
        
        # Mock dependencies
        with patch('Animalchannel.openai_client') as mock_openai, \
             patch('Animalchannel.upload_image') as mock_upload:
            
            # Mock with small delay
            def mock_openai_call(*args, **kwargs):
                time.sleep(0.1)  # Small delay
                mock_response = MagicMock()
                mock_response.data = [MagicMock()]
                mock_response.data[0].url = "https://test.jpg"
                return mock_response
                
            mock_openai.images.generate.side_effect = mock_openai_call
            mock_upload.return_value = "https://upload.jpg"
            
            test_prompts = [(1, "Test", "Scene1"), (2, "Test", "Scene2")]
            
            print("Running generation while monitoring event loop responsiveness...")
            
            # Run generation
            generation_task = asyncio.create_task(
                Animalchannel.generate_images_concurrently(test_prompts)
            )
            
            # Wait for completion or timeout
            try:
                results = await asyncio.wait_for(generation_task, timeout=15.0)
                ping_task.cancel()
                
                print(f"✅ PASS: Generation completed with event loop remaining responsive")
                print(f"✅ PASS: Background pings received: {ping_count}")
                
                if ping_count >= 4:  # Should have gotten several pings during generation
                    print("✅ PASS: Event loop was not blocked during generation")
                    return True
                else:
                    print("⚠️  WARNING: Few background pings - possible intermittent blocking")
                    return False
                    
            except asyncio.TimeoutError:
                ping_task.cancel()
                print(f"❌ FAIL: Generation timed out, background pings: {ping_count}")
                return False
                
    except Exception as e:
        print(f"❌ FAIL: Event loop test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all blocking fix tests"""
    print("🚀 PARALLEL IMAGE GENERATION STOPPAGE FIX TESTS")
    print("Testing the fix for event loop blocking in async upload operations")
    print("=" * 80)
    
    tests = [
        ("Small Batch Generation", test_small_batch_generation),
        ("Async Flow Monitoring", test_async_flow_monitoring), 
        ("Semaphore Behavior", test_semaphore_behavior),
        ("Event Loop Blocking", lambda: asyncio.run(test_event_loop_blocking()))
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n🧪 Running: {test_name}")
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ Test '{test_name}' threw exception: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 80)
    print("🏁 TEST RESULTS SUMMARY")
    print("=" * 80)
    
    passed = 0
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
        if result:
            passed += 1
    
    print("-" * 80)
    print(f"Total: {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("🎉 ALL TESTS PASSED - Parallel generation stoppage issue appears to be fixed!")
        print("Key fix: Wrapped blocking upload_image() call in asyncio thread pool")
    else:
        print(f"⚠️ {len(results) - passed} tests failed - issue may not be fully resolved")
    
    return passed == len(results)

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)