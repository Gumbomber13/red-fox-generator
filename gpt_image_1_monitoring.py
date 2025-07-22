#!/usr/bin/env python3
"""
GPT-Image-1 Monitoring and Metrics Collection
Tracks performance and quality metrics for the GPT-Image-1 migration
"""

import os
import time
import json
import logging
from datetime import datetime, timedelta
from collections import defaultdict, deque
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class ImageGenerationMetrics:
    """Metrics for a single image generation"""
    timestamp: datetime
    scene_number: int
    prompt_length: int
    generation_time: float
    success: bool
    model_used: str
    error_type: Optional[str] = None
    retry_count: int = 0
    user_approved: Optional[bool] = None
    quality_score: Optional[float] = None

@dataclass
class StoryMetrics:
    """Metrics for a complete story generation"""
    story_id: str
    timestamp: datetime
    total_images: int
    successful_images: int
    total_time: float
    average_time_per_image: float
    user_completed: bool
    user_satisfaction: Optional[float] = None

class GPTImage1Monitor:
    """Monitor and collect metrics for GPT-Image-1 performance"""
    
    def __init__(self, metrics_file: str = "gpt_image_1_metrics.json"):
        self.metrics_file = metrics_file
        self.image_metrics: List[ImageGenerationMetrics] = []
        self.story_metrics: List[StoryMetrics] = []
        self.current_story_images: Dict[str, List[ImageGenerationMetrics]] = defaultdict(list)
        
        # Performance tracking
        self.recent_generation_times = deque(maxlen=100)  # Last 100 generations
        self.success_rate_tracker = deque(maxlen=100)
        self.timeout_tracker = deque(maxlen=100)
        
        # Load existing metrics
        self.load_metrics()
        
        logger.info("GPT-Image-1 Monitor initialized")

    def load_metrics(self):
        """Load existing metrics from file"""
        try:
            if os.path.exists(self.metrics_file):
                with open(self.metrics_file, 'r') as f:
                    data = json.load(f)
                    
                # Load image metrics
                for item in data.get('image_metrics', []):
                    item['timestamp'] = datetime.fromisoformat(item['timestamp'])
                    self.image_metrics.append(ImageGenerationMetrics(**item))
                
                # Load story metrics  
                for item in data.get('story_metrics', []):
                    item['timestamp'] = datetime.fromisoformat(item['timestamp'])
                    self.story_metrics.append(StoryMetrics(**item))
                    
                logger.info(f"Loaded {len(self.image_metrics)} image metrics and {len(self.story_metrics)} story metrics")
        except Exception as e:
            logger.warning(f"Could not load existing metrics: {e}")

    def save_metrics(self):
        """Save metrics to file"""
        try:
            data = {
                'image_metrics': [asdict(m) for m in self.image_metrics],
                'story_metrics': [asdict(m) for m in self.story_metrics]
            }
            
            # Convert datetime objects to ISO strings
            for item in data['image_metrics']:
                item['timestamp'] = item['timestamp'].isoformat()
            for item in data['story_metrics']:
                item['timestamp'] = item['timestamp'].isoformat()
            
            with open(self.metrics_file, 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            logger.error(f"Could not save metrics: {e}")

    def record_image_generation(self, scene_number: int, prompt: str, generation_time: float, 
                              success: bool, story_id: str, model_used: str = "gpt-image-1",
                              error_type: str = None, retry_count: int = 0):
        """Record metrics for a single image generation"""
        
        metrics = ImageGenerationMetrics(
            timestamp=datetime.now(),
            scene_number=scene_number,
            prompt_length=len(prompt),
            generation_time=generation_time,
            success=success,
            model_used=model_used,
            error_type=error_type,
            retry_count=retry_count
        )
        
        self.image_metrics.append(metrics)
        self.current_story_images[story_id].append(metrics)
        
        # Update performance trackers
        self.recent_generation_times.append(generation_time)
        self.success_rate_tracker.append(success)
        self.timeout_tracker.append(generation_time > 150.0)  # Consider >150s as timeout risk
        
        # Log performance alerts
        self._check_performance_alerts(metrics)
        
        logger.info(f"[METRICS] Image {scene_number} - {generation_time:.1f}s - {'SUCCESS' if success else 'FAILED'}")

    def record_story_completion(self, story_id: str, user_completed: bool, 
                              user_satisfaction: float = None):
        """Record metrics for a completed story"""
        
        images = self.current_story_images.get(story_id, [])
        if not images:
            logger.warning(f"No image metrics found for story {story_id}")
            return
        
        successful_images = sum(1 for img in images if img.success)
        total_time = sum(img.generation_time for img in images)
        average_time = total_time / len(images) if images else 0
        
        story_metrics = StoryMetrics(
            story_id=story_id,
            timestamp=datetime.now(),
            total_images=len(images),
            successful_images=successful_images,
            total_time=total_time,
            average_time_per_image=average_time,
            user_completed=user_completed,
            user_satisfaction=user_satisfaction
        )
        
        self.story_metrics.append(story_metrics)
        
        # Clean up current story tracking
        if story_id in self.current_story_images:
            del self.current_story_images[story_id]
        
        logger.info(f"[METRICS] Story {story_id} - {successful_images}/{len(images)} images - {total_time:.1f}s total")

    def record_user_approval(self, story_id: str, scene_number: int, approved: bool, 
                           quality_score: float = None):
        """Record user approval/rejection for an image"""
        
        # Find the corresponding image metric
        for metrics in self.current_story_images.get(story_id, []):
            if metrics.scene_number == scene_number:
                metrics.user_approved = approved
                metrics.quality_score = quality_score
                break
        
        logger.info(f"[METRICS] User {'approved' if approved else 'rejected'} image {scene_number} for story {story_id}")

    def _check_performance_alerts(self, metrics: ImageGenerationMetrics):
        """Check for performance issues and log alerts"""
        
        # Check for timeouts
        if metrics.generation_time > 150.0:
            logger.warning(f"[ALERT] Slow generation: {metrics.generation_time:.1f}s for scene {metrics.scene_number}")
        
        # Check success rate over last 20 generations
        if len(self.success_rate_tracker) >= 20:
            recent_success_rate = sum(self.success_rate_tracker) / len(self.success_rate_tracker)
            if recent_success_rate < 0.90:
                logger.warning(f"[ALERT] Low success rate: {recent_success_rate:.1%} over last {len(self.success_rate_tracker)} generations")
        
        # Check for repeated failures
        if not metrics.success and metrics.retry_count >= 2:
            logger.error(f"[ALERT] Multiple retries failed for scene {metrics.scene_number}: {metrics.error_type}")

    def get_performance_summary(self, hours: int = 24) -> Dict:
        """Get performance summary for the last N hours"""
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        recent_images = [m for m in self.image_metrics if m.timestamp > cutoff_time]
        recent_stories = [m for m in self.story_metrics if m.timestamp > cutoff_time]
        
        if not recent_images:
            return {"error": "No data available for specified time period"}
        
        # Calculate metrics
        total_images = len(recent_images)
        successful_images = sum(1 for m in recent_images if m.success)
        success_rate = successful_images / total_images if total_images > 0 else 0
        
        generation_times = [m.generation_time for m in recent_images if m.success]
        avg_generation_time = sum(generation_times) / len(generation_times) if generation_times else 0
        
        timeout_count = sum(1 for m in recent_images if m.generation_time > 150.0)
        timeout_rate = timeout_count / total_images if total_images > 0 else 0
        
        # User metrics
        completed_stories = sum(1 for s in recent_stories if s.user_completed)
        total_stories = len(recent_stories)
        completion_rate = completed_stories / total_stories if total_stories > 0 else 0
        
        approved_images = [m for m in recent_images if m.user_approved is True]
        rejected_images = [m for m in recent_images if m.user_approved is False]
        approval_rate = len(approved_images) / (len(approved_images) + len(rejected_images)) if (approved_images or rejected_images) else None
        
        return {
            "time_period": f"Last {hours} hours",
            "timestamp": datetime.now().isoformat(),
            "performance": {
                "total_images": total_images,
                "success_rate": f"{success_rate:.1%}",
                "average_generation_time": f"{avg_generation_time:.1f}s",
                "timeout_rate": f"{timeout_rate:.1%}",
                "model_performance": "GPT-Image-1"
            },
            "user_experience": {
                "stories_started": total_stories,
                "stories_completed": completed_stories,
                "completion_rate": f"{completion_rate:.1%}",
                "approval_rate": f"{approval_rate:.1%}" if approval_rate is not None else "No data"
            },
            "quality": {
                "retry_rate": f"{sum(1 for m in recent_images if m.retry_count > 0) / total_images:.1%}",
                "error_types": self._get_error_breakdown(recent_images)
            }
        }

    def _get_error_breakdown(self, images: List[ImageGenerationMetrics]) -> Dict[str, int]:
        """Get breakdown of error types"""
        error_counts = defaultdict(int)
        for img in images:
            if not img.success and img.error_type:
                error_counts[img.error_type] += 1
        return dict(error_counts)

    def generate_daily_report(self) -> str:
        """Generate a daily performance report"""
        
        summary = self.get_performance_summary(24)
        
        report = f"""
GPT-Image-1 Daily Performance Report
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Performance Metrics (Last 24 Hours):
- Images Generated: {summary['performance']['total_images']}
- Success Rate: {summary['performance']['success_rate']}
- Average Generation Time: {summary['performance']['average_generation_time']}
- Timeout Rate: {summary['performance']['timeout_rate']}

User Experience:
- Stories Started: {summary['user_experience']['stories_started']}
- Stories Completed: {summary['user_experience']['stories_completed']}  
- Completion Rate: {summary['user_experience']['completion_rate']}
- Image Approval Rate: {summary['user_experience']['approval_rate']}

Quality Metrics:
- Retry Rate: {summary['quality']['retry_rate']}
- Error Types: {summary['quality']['error_types']}

Status: {'🟢 HEALTHY' if float(summary['performance']['success_rate'].strip('%')) > 95 else '🟡 ATTENTION NEEDED' if float(summary['performance']['success_rate'].strip('%')) > 90 else '🔴 CRITICAL'}
"""
        
        return report

    def export_metrics_csv(self, filename: str = None):
        """Export metrics to CSV for analysis"""
        if filename is None:
            filename = f"gpt_image_1_metrics_{datetime.now().strftime('%Y%m%d')}.csv"
        
        import csv
        
        with open(filename, 'w', newline='') as csvfile:
            fieldnames = ['timestamp', 'scene_number', 'prompt_length', 'generation_time', 
                         'success', 'model_used', 'error_type', 'retry_count', 'user_approved']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            for metrics in self.image_metrics:
                row = asdict(metrics)
                row['timestamp'] = row['timestamp'].isoformat()
                writer.writerow(row)
        
        logger.info(f"Metrics exported to {filename}")

# Global monitor instance
monitor = GPTImage1Monitor()

def record_generation_start(story_id: str, scene_number: int, prompt: str):
    """Record the start of image generation (for timing)"""
    # Store start time for this generation
    start_time = time.time()
    return start_time

def record_generation_complete(story_id: str, scene_number: int, prompt: str, 
                             start_time: float, success: bool, error_type: str = None, 
                             retry_count: int = 0):
    """Record completion of image generation"""
    generation_time = time.time() - start_time
    monitor.record_image_generation(
        scene_number=scene_number,
        prompt=prompt,
        generation_time=generation_time,
        success=success,
        story_id=story_id,
        error_type=error_type,
        retry_count=retry_count
    )
    monitor.save_metrics()

def record_user_feedback(story_id: str, scene_number: int, approved: bool, quality_score: float = None):
    """Record user approval/rejection"""
    monitor.record_user_approval(story_id, scene_number, approved, quality_score)
    monitor.save_metrics()

def record_story_complete(story_id: str, user_completed: bool, satisfaction: float = None):
    """Record story completion"""
    monitor.record_story_completion(story_id, user_completed, satisfaction)
    monitor.save_metrics()

def get_current_performance():
    """Get current performance summary"""
    return monitor.get_performance_summary()

def generate_report():
    """Generate and return daily report"""
    return monitor.generate_daily_report()

if __name__ == "__main__":
    # Example usage and testing
    print("GPT-Image-1 Monitoring System")
    print("=" * 40)
    
    # Simulate some metrics
    import random
    
    for i in range(10):
        story_id = f"test-story-{i}"
        for scene in range(1, 4):  # 3 scenes per story
            success = random.choice([True, True, True, False])  # 75% success rate
            gen_time = random.uniform(45, 120) if success else random.uniform(150, 180)
            error_type = None if success else random.choice(["timeout", "api_error", "policy_violation"])
            
            monitor.record_image_generation(
                scene_number=scene,
                prompt=f"Test prompt for scene {scene}",
                generation_time=gen_time,
                success=success,
                story_id=story_id,
                error_type=error_type
            )
        
        # Record story completion
        monitor.record_story_completion(story_id, random.choice([True, False]))
    
    # Generate report
    print(monitor.generate_daily_report())
    
    # Export metrics
    monitor.export_metrics_csv()
    print("Sample metrics generated and exported!")