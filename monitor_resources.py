#!/usr/bin/env python3
"""
Resource monitoring for parallel image generation
Monitors CPU and memory usage during generation process
"""

import psutil
import time
import threading
import sys
import os

class ResourceMonitor:
    """Monitor system resources during image generation"""
    
    def __init__(self):
        self.monitoring = False
        self.samples = []
        self.start_time = None
        
    def start_monitoring(self):
        """Start monitoring system resources"""
        self.monitoring = True
        self.start_time = time.time()
        self.samples = []
        
        # Start monitoring thread
        monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        monitor_thread.start()
        
        print("Resource monitoring started...")
        
    def stop_monitoring(self):
        """Stop monitoring and return summary"""
        self.monitoring = False
        
        if not self.samples:
            return {"error": "No samples collected"}
        
        # Calculate statistics
        cpu_values = [s['cpu_percent'] for s in self.samples]
        memory_values = [s['memory_percent'] for s in self.samples]
        memory_mb = [s['memory_mb'] for s in self.samples]
        
        summary = {
            "duration": time.time() - self.start_time,
            "samples_collected": len(self.samples),
            "cpu_usage": {
                "average": sum(cpu_values) / len(cpu_values),
                "max": max(cpu_values),
                "min": min(cpu_values)
            },
            "memory_usage": {
                "average_percent": sum(memory_values) / len(memory_values),
                "max_percent": max(memory_values),
                "min_percent": min(memory_values),
                "average_mb": sum(memory_mb) / len(memory_mb),
                "max_mb": max(memory_mb),
                "min_mb": min(memory_mb)
            }
        }
        
        print("Resource monitoring stopped")
        return summary
        
    def _monitor_loop(self):
        """Background monitoring loop"""
        while self.monitoring:
            try:
                # Get current process info
                process = psutil.Process()
                
                # Get system-wide CPU usage
                cpu_percent = psutil.cpu_percent(interval=None)
                
                # Get current process memory info
                memory_info = process.memory_info()
                memory_percent = process.memory_percent()
                
                # Store sample
                sample = {
                    "timestamp": time.time() - self.start_time,
                    "cpu_percent": cpu_percent,
                    "memory_percent": memory_percent,
                    "memory_mb": memory_info.rss / 1024 / 1024,  # MB
                    "memory_vms_mb": memory_info.vms / 1024 / 1024  # Virtual memory MB
                }
                
                self.samples.append(sample)
                
                # Print periodic updates
                if len(self.samples) % 10 == 0:  # Every 10 samples (5 seconds)
                    print(f"Resource usage: CPU {cpu_percent:.1f}%, Memory {memory_percent:.1f}% ({memory_info.rss/1024/1024:.1f} MB)")
                
            except Exception as e:
                print(f"Monitoring error: {e}")
                
            time.sleep(0.5)  # Sample every 500ms

def print_resource_summary(summary):
    """Print formatted resource usage summary"""
    if "error" in summary:
        print(f"Resource monitoring error: {summary['error']}")
        return
        
    print("\n" + "=" * 60)
    print("RESOURCE USAGE SUMMARY")
    print("=" * 60)
    
    print(f"Monitoring Duration: {summary['duration']:.1f} seconds")
    print(f"Samples Collected: {summary['samples_collected']}")
    
    print(f"\nCPU Usage:")
    print(f"  Average: {summary['cpu_usage']['average']:.1f}%")
    print(f"  Peak: {summary['cpu_usage']['max']:.1f}%")
    print(f"  Minimum: {summary['cpu_usage']['min']:.1f}%")
    
    print(f"\nMemory Usage:")
    print(f"  Average: {summary['memory_usage']['average_percent']:.1f}% ({summary['memory_usage']['average_mb']:.1f} MB)")
    print(f"  Peak: {summary['memory_usage']['max_percent']:.1f}% ({summary['memory_usage']['max_mb']:.1f} MB)")
    print(f"  Minimum: {summary['memory_usage']['min_percent']:.1f}% ({summary['memory_usage']['min_mb']:.1f} MB)")
    
    # Performance assessment
    print(f"\nPerformance Assessment:")
    
    if summary['cpu_usage']['average'] > 80:
        print("  CPU: HIGH usage - may indicate performance bottleneck")
    elif summary['cpu_usage']['average'] > 50:
        print("  CPU: MODERATE usage - acceptable for image generation")
    else:
        print("  CPU: LOW usage - good performance")
    
    if summary['memory_usage']['max_mb'] > 1000:
        print("  Memory: HIGH usage (>1GB) - monitor for memory leaks")
    elif summary['memory_usage']['max_mb'] > 500:
        print("  Memory: MODERATE usage (>500MB) - acceptable")
    else:
        print("  Memory: LOW usage - efficient")

def test_with_monitoring():
    """Test image generation with resource monitoring"""
    print("TESTING: Resource monitoring during image generation")
    print("=" * 60)
    
    try:
        # Import after adding to path
        sys.path.insert(0, os.path.dirname(__file__))
        
        from unittest.mock import patch, MagicMock
        import asyncio
        import Animalchannel
        
        # Create monitor
        monitor = ResourceMonitor()
        
        # Mock external dependencies for faster test
        with patch('Animalchannel.openai_client') as mock_openai, \
             patch('Animalchannel.upload_image') as mock_upload:
            
            # Mock with small delay to simulate work
            def mock_openai_call(*args, **kwargs):
                time.sleep(0.5)  # Small delay to simulate API call
                mock_response = MagicMock()
                mock_response.data = [MagicMock()]
                mock_response.data[0].url = "https://test.jpg"
                return mock_response
                
            def mock_upload_call(img_data):
                time.sleep(0.2)  # Small delay to simulate upload
                return "https://upload.jpg"
            
            mock_openai.images.generate.side_effect = mock_openai_call
            mock_upload.side_effect = mock_upload_call
            
            # Test with multiple images to see resource usage
            test_prompts = [
                (i, f"Test prompt {i}", f"Scene{i}") 
                for i in range(1, 6)  # 5 images
            ]
            
            print(f"Testing with {len(test_prompts)} images...")
            print("Starting resource monitoring...")
            
            # Start monitoring
            monitor.start_monitoring()
            
            # Run generation
            start_time = time.time()
            results = asyncio.run(Animalchannel.generate_images_concurrently(test_prompts))
            elapsed = time.time() - start_time
            
            # Stop monitoring
            summary = monitor.stop_monitoring()
            
            print(f"\nGeneration completed in {elapsed:.2f}s")
            print(f"Results: {len(results)} images processed")
            
            # Print resource summary
            print_resource_summary(summary)
            
            return True
            
    except Exception as e:
        print(f"Resource monitoring test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_with_monitoring()
    
    if success:
        print("\nSUCCESS: Resource monitoring completed")
    else:
        print("\nFAILED: Resource monitoring test failed")
        
    sys.exit(0 if success else 1)