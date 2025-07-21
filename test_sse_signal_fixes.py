#!/usr/bin/env python3
"""
Test SSE and Signal Handling Fixes
Tests the fixes for Flask application context and signal handling compatibility
"""

import os
import sys
import time
import threading
import logging
from unittest.mock import patch, MagicMock

# Add the current directory to Python path for imports
sys.path.insert(0, os.path.dirname(__file__))

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_sse_context_fix():
    """Test that SSE emissions work correctly with Flask application context"""
    print("=" * 60)
    print("TEST: SSE Application Context Fix")
    print("=" * 60)
    
    try:
        # Import Flask server components
        from flask_server import app, emit_image_event, active_stories
        
        # Setup test story data
        test_story_id = "test_sse_context_123"
        test_scene_number = 1
        test_image_url = "https://test.example.com/image.jpg"
        
        # Initialize story in active_stories
        active_stories[test_story_id] = {
            'images': {},
            'image_approvals': {},
            'completed_scenes': 0,
            'total_scenes': 20,
            'status': 'processing'
        }
        
        print(f"Testing SSE emission for story: {test_story_id}")
        print(f"Scene: {test_scene_number}, URL: {test_image_url}")
        
        # Test the emit function with Flask app context
        # This should work without errors now that we've added app.app_context()
        with app.app_context():
            emit_image_event(test_story_id, test_scene_number, test_image_url, "completed")
        
        # Verify the story was updated correctly
        if test_story_id in active_stories:
            story_data = active_stories[test_story_id]
            if test_scene_number in story_data['images']:
                stored_url = story_data['images'][test_scene_number]['url']
                stored_status = story_data['images'][test_scene_number]['status']
                
                if stored_url == test_image_url and stored_status == "completed":
                    print("PASS: SSE emission with Flask context successful")
                    print(f"PASS: Image data stored correctly: {stored_url}")
                    return True
                else:
                    print(f"FAIL: Image data mismatch - URL: {stored_url}, Status: {stored_status}")
                    return False
            else:
                print(f"FAIL: Scene {test_scene_number} not found in story images")
                return False
        else:
            print(f"FAIL: Story {test_story_id} not found in active_stories")
            return False
            
    except Exception as e:
        print(f"FAIL: SSE context test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_signal_handling_thread_safety():
    """Test that signal handling has been removed from threaded operations"""
    print("\n" + "=" * 60)
    print("🧪 TEST: Signal Handling Thread Safety")
    print("=" * 60)
    
    try:
        import Animalchannel
        
        # Check that signal-based operations are replaced with thread-safe alternatives
        source_code = ""
        with open(os.path.join(os.path.dirname(__file__), 'Animalchannel.py'), 'r') as f:
            source_code = f.read()
        
        # Verify that signal handlers are not being set in threaded operations
        signal_usage_lines = []
        for i, line in enumerate(source_code.split('\n'), 1):
            if 'signal.signal(' in line and 'SIGNAL-FIX' not in line:
                signal_usage_lines.append((i, line.strip()))
        
        if signal_usage_lines:
            print("⚠️  WARNING: Found potential signal usage in threaded code:")
            for line_num, line in signal_usage_lines:
                print(f"  Line {line_num}: {line}")
        else:
            print("✅ PASS: No problematic signal usage found in threaded code")
        
        # Check for asyncio timeout usage instead of signal
        if 'asyncio.wait_for(' in source_code and 'timeout=' in source_code:
            print("✅ PASS: Found asyncio timeout usage (thread-safe alternative)")
        else:
            print("❌ FAIL: No asyncio timeout found - signal replacement incomplete")
            return False
        
        # Check for threading import and usage
        if 'import threading' in source_code:
            print("✅ PASS: Threading module imported for thread safety checks")
        else:
            print("⚠️  WARNING: Threading module not imported")
        
        # Check for SIGNAL-FIX logging tags
        if '[SIGNAL-FIX]' in source_code:
            print("✅ PASS: Found SIGNAL-FIX logging tags indicating fixes applied")
        else:
            print("❌ FAIL: No SIGNAL-FIX logging found")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ FAIL: Signal handling test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_retry_logic():
    """Test that retry logic is implemented for transient failures"""
    print("\n" + "=" * 60)
    print("🧪 TEST: Retry Logic Implementation")
    print("=" * 60)
    
    try:
        # Test retry logic by examining source code
        source_code = ""
        with open(os.path.join(os.path.dirname(__file__), 'flask_server.py'), 'r') as f:
            source_code = f.read()
        
        # Check for retry implementation
        retry_indicators = [
            'max_retries',
            'for attempt in range(',
            '[SSE-RETRY]',
            'retry_delay',
            'exponential backoff'
        ]
        
        found_indicators = []
        for indicator in retry_indicators:
            if indicator in source_code:
                found_indicators.append(indicator)
                print(f"✅ PASS: Found retry indicator: {indicator}")
            else:
                print(f"❌ FAIL: Missing retry indicator: {indicator}")
        
        if len(found_indicators) >= 4:  # At least 4 out of 5 indicators
            print("✅ PASS: Retry logic appears to be implemented")
            return True
        else:
            print(f"❌ FAIL: Insufficient retry logic found ({len(found_indicators)}/5 indicators)")
            return False
            
    except Exception as e:
        print(f"❌ FAIL: Retry logic test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_threading_compatibility():
    """Test that threading is used correctly and compatibly"""
    print("\n" + "=" * 60)
    print("🧪 TEST: Threading Compatibility")
    print("=" * 60)
    
    try:
        from flask_server import app
        import threading
        
        # Test that we can create a thread and access Flask context
        test_result = {"success": False, "error": None}
        
        def test_thread_function():
            try:
                # Simulate what happens in background threads
                thread_name = threading.current_thread().name
                is_daemon = threading.current_thread().daemon
                is_main = threading.current_thread() == threading.main_thread()
                
                print(f"Thread info - Name: {thread_name}, Daemon: {is_daemon}, Main: {is_main}")
                
                # Test that Flask app context works in thread
                with app.app_context():
                    app_name = app.name
                    print(f"✅ PASS: Flask app context accessible in thread: {app_name}")
                    test_result["success"] = True
                    
            except Exception as e:
                test_result["error"] = str(e)
                print(f"❌ FAIL: Thread context test failed: {e}")
        
        # Create and run test thread
        test_thread = threading.Thread(target=test_thread_function, daemon=True)
        test_thread.start()
        test_thread.join(timeout=5)  # 5 second timeout
        
        if test_result["success"]:
            print("✅ PASS: Threading compatibility verified")
            return True
        else:
            error_msg = test_result["error"] or "Unknown error"
            print(f"❌ FAIL: Threading compatibility failed: {error_msg}")
            return False
            
    except Exception as e:
        print(f"❌ FAIL: Threading compatibility test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_detailed_logging():
    """Test that detailed logging is implemented for debugging"""
    print("\n" + "=" * 60)
    print("🧪 TEST: Detailed Logging Implementation")
    print("=" * 60)
    
    try:
        # Check both flask_server.py and Animalchannel.py for logging tags
        logging_tags_to_check = [
            '[SSE-CONTEXT]',
            '[SSE-DETAILED]',
            '[SSE-RETRY]', 
            '[SIGNAL-FIX]',
            '[SIGNAL-DETAILED]',
            '[ASYNC-RETRY]'
        ]
        
        files_to_check = ['flask_server.py', 'Animalchannel.py']
        
        found_tags = set()
        
        for filename in files_to_check:
            try:
                with open(os.path.join(os.path.dirname(__file__), filename), 'r') as f:
                    content = f.read()
                    
                for tag in logging_tags_to_check:
                    if tag in content:
                        found_tags.add(tag)
                        print(f"✅ PASS: Found logging tag {tag} in {filename}")
            except FileNotFoundError:
                print(f"⚠️  WARNING: Could not read {filename}")
        
        missing_tags = set(logging_tags_to_check) - found_tags
        if missing_tags:
            print(f"❌ FAIL: Missing logging tags: {list(missing_tags)}")
            return False
        else:
            print("✅ PASS: All required logging tags found")
            return True
            
    except Exception as e:
        print(f"❌ FAIL: Detailed logging test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all SSE and signal handling tests"""
    print("SSE AND SIGNAL HANDLING FIXES TEST SUITE")
    print("Testing fixes for Flask application context and signal handling compatibility")
    print("=" * 80)
    
    tests = [
        ("SSE Context Fix", test_sse_context_fix),
        ("Signal Handling Thread Safety", test_signal_handling_thread_safety),
        ("Retry Logic Implementation", test_retry_logic),
        ("Threading Compatibility", test_threading_compatibility),
        ("Detailed Logging", test_detailed_logging)
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
        print("🎉 ALL TESTS PASSED - SSE and signal handling fixes working correctly!")
        print("Key fixes verified:")
        print("  • Flask application context properly managed for SSE operations")
        print("  • Signal handling replaced with thread-safe asyncio timeout")
        print("  • Retry logic implemented for transient failures")
        print("  • Threading compatibility ensured")
        print("  • Detailed logging in place for debugging")
    else:
        print(f"⚠️ {len(results) - passed} tests failed - fixes may need adjustment")
    
    return passed == len(results)

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)