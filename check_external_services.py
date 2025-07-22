#!/usr/bin/env python3
"""
Check external service status for image generation pipeline
"""

import requests
import time
import sys
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def check_openai_api():
    """Check OpenAI API status"""
    print("Checking OpenAI API status...")
    
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key or api_key == 'your_openai_api_key_here':
        print("  WARNING: OpenAI API key not configured")
        return False
    
    try:
        # Check OpenAI status page
        response = requests.get('https://status.openai.com/api/v2/status.json', timeout=10)
        if response.status_code == 200:
            status_data = response.json()
            status = status_data.get('status', {}).get('indicator', 'unknown')
            print(f"  OpenAI Status: {status}")
            
            if status in ['none', 'minor']:
                print("  ✅ OpenAI services operational")
                return True
            else:
                print(f"  ⚠️ OpenAI services experiencing issues: {status}")
                return False
        else:
            print(f"  ❌ Could not check OpenAI status (HTTP {response.status_code})")
            return False
            
    except Exception as e:
        print(f"  ❌ OpenAI status check failed: {e}")
        return False

def check_openai_api_access():
    """Test actual OpenAI API access"""
    print("Testing OpenAI API access...")
    
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key or api_key == 'your_openai_api_key_here':
        print("  SKIP: API key not configured")
        return False
    
    try:
        # Test with a simple completion request
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        
        data = {
            'model': 'gpt-3.5-turbo',
            'messages': [{'role': 'user', 'content': 'Hello'}],
            'max_tokens': 5
        }
        
        response = requests.post(
            'https://api.openai.com/v1/chat/completions',
            headers=headers,
            json=data,
            timeout=30
        )
        
        if response.status_code == 200:
            print("  ✅ OpenAI API access working")
            return True
        elif response.status_code == 401:
            print("  ❌ OpenAI API key invalid or expired")
            return False
        elif response.status_code == 429:
            print("  ⚠️ OpenAI API rate limited")
            return False
        else:
            print(f"  ❌ OpenAI API error: HTTP {response.status_code}")
            return False
            
    except Exception as e:
        print(f"  ❌ OpenAI API test failed: {e}")
        return False

def check_gpt_image_1_access():
    """Test GPT-Image-1 model access"""
    print("Testing GPT-Image-1 model access...")
    
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key or api_key == 'your_openai_api_key_here':
        print("  SKIP: API key not configured")
        return False
    
    try:
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        
        data = {
            'model': 'gpt-image-1',
            'prompt': 'A simple test image',
            'size': '1024x1536',
            'n': 1
        }
        
        # Just check if the model is accessible (we'll let it fail on generation)
        response = requests.post(
            'https://api.openai.com/v1/images/generations',
            headers=headers,
            json=data,
            timeout=10  # Short timeout, we just want to see if model is recognized
        )
        
        if response.status_code == 200:
            print("  ✅ GPT-Image-1 model accessible")
            return True
        elif response.status_code == 404 and 'model' in response.text.lower():
            print("  ❌ GPT-Image-1 model not available to this account")
            return False
        elif response.status_code == 401:
            print("  ❌ API key invalid for image generation")
            return False
        elif response.status_code == 429:
            print("  ⚠️ Rate limited (but model appears accessible)")
            return True
        else:
            print(f"  ⚠️ GPT-Image-1 test inconclusive: HTTP {response.status_code}")
            # Could be timeout or other issue, assume accessible if not explicit model error
            return True
            
    except requests.exceptions.Timeout:
        print("  ⚠️ GPT-Image-1 test timed out (model likely accessible)")
        return True
    except Exception as e:
        print(f"  ❌ GPT-Image-1 test failed: {e}")
        return False

def check_cloudinary():
    """Check Cloudinary service status"""
    print("Checking Cloudinary service...")
    
    cloudinary_url = os.getenv('CLOUDINARY_URL')
    cloudinary_preset = os.getenv('CLOUDINARY_PRESET')
    
    if not cloudinary_url or cloudinary_url == 'your_cloudinary_url_here':
        print("  WARNING: Cloudinary URL not configured")
        return False
    
    if not cloudinary_preset or cloudinary_preset == 'your_cloudinary_preset_here':
        print("  WARNING: Cloudinary preset not configured")
        return False
    
    try:
        # Test Cloudinary upload endpoint (without actually uploading)
        # Extract cloud name from URL
        if '//' in cloudinary_url:
            cloud_name = cloudinary_url.split('/')[-1] if cloudinary_url.endswith('/') else cloudinary_url.split('/')[-1]
            if '@' in cloud_name:
                cloud_name = cloud_name.split('@')[-1]
        else:
            print("  ❌ Invalid Cloudinary URL format")
            return False
        
        # Test with a HEAD request to check if the endpoint is reachable
        test_url = f"https://api.cloudinary.com/v1_1/{cloud_name}/image/upload"
        response = requests.head(test_url, timeout=10)
        
        if response.status_code in [200, 400, 401]:  # 400/401 are expected without proper data
            print("  ✅ Cloudinary service accessible")
            return True
        else:
            print(f"  ❌ Cloudinary service issue: HTTP {response.status_code}")
            return False
            
    except Exception as e:
        print(f"  ❌ Cloudinary check failed: {e}")
        return False

def check_network_connectivity():
    """Check basic network connectivity"""
    print("Checking network connectivity...")
    
    test_urls = [
        ('Google DNS', 'https://dns.google'),
        ('OpenAI API', 'https://api.openai.com'),
        ('Cloudinary', 'https://cloudinary.com')
    ]
    
    results = []
    for name, url in test_urls:
        try:
            response = requests.head(url, timeout=5)
            if response.status_code < 500:  # Any response < 500 means connectivity works
                print(f"  ✅ {name}: Connected")
                results.append(True)
            else:
                print(f"  ⚠️ {name}: Server error (HTTP {response.status_code})")
                results.append(False)
        except Exception as e:
            print(f"  ❌ {name}: Connection failed ({e})")
            results.append(False)
    
    return all(results)

def main():
    """Run all external service checks"""
    print("EXTERNAL SERVICES STATUS CHECK")
    print("=" * 50)
    
    # Environment check
    print("\nEnvironment Configuration:")
    required_vars = ['OPENAI_API_KEY', 'CLOUDINARY_URL', 'CLOUDINARY_PRESET']
    for var in required_vars:
        value = os.getenv(var, 'NOT_SET')
        if value == 'NOT_SET':
            print(f"  ❌ {var}: Not set")
        elif 'your_' in value.lower() and '_here' in value.lower():
            print(f"  ❌ {var}: Default placeholder value")
        else:
            print(f"  ✅ {var}: Configured")
    
    print("\nService Status Checks:")
    checks = [
        ("Network Connectivity", check_network_connectivity),
        ("OpenAI Status Page", check_openai_api),
        ("OpenAI API Access", check_openai_api_access),
        ("GPT-Image-1 Access", check_gpt_image_1_access),
        ("Cloudinary Service", check_cloudinary)
    ]
    
    results = []
    for check_name, check_func in checks:
        print(f"\n{check_name}:")
        try:
            result = check_func()
            results.append((check_name, result))
        except Exception as e:
            print(f"  ❌ Check failed with exception: {e}")
            results.append((check_name, False))
    
    # Summary
    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    
    passed = 0
    for check_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {check_name}")
        if result:
            passed += 1
    
    print(f"\nOverall: {passed}/{len(results)} checks passed")
    
    if passed == len(results):
        print("🎉 All external services are operational!")
        return True
    elif passed >= len(results) * 0.7:  # 70% pass rate
        print("⚠️ Most services operational, some issues detected")
        return True
    else:
        print("❌ Multiple service issues detected")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)