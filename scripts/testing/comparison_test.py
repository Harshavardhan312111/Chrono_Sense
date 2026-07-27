"""
Activity Detection Comparison Test
Compares Option 1 (Enhanced Heuristic) vs Option 2 (Lite Pose)
on real video frames
"""

import os
import sys
import cv2
import numpy as np
import time
from datetime import datetime

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from activity_detector import ActivityDetector
from lite_pose_detector import LitePoseDetector

class ComparisonTest:
    """Test and compare activity detection methods"""
    
    def __init__(self):
        self.heuristic_detector = ActivityDetector()  # Uses enhanced heuristic
        self.lite_pose_detector = LitePoseDetector()  # Uses lite pose
        
        self.results = []
        
    def test_on_webcam(self, duration_seconds=30):
        """
        Test both detectors on live webcam feed
        
        Args:
            duration_seconds: How long to test (default 30 seconds)
        """
        cap = cv2.VideoCapture(0)
        
        if not cap.isOpened():
            print("❌ Could not open webcam")
            return False
        
        print(f"\n{'='*70}")
        print(f"Testing Activity Detection Methods (Duration: {duration_seconds}s)")
        print(f"{'='*70}")
        print(f"Press 'q' to quit early, 'a' to annotate as activity\n")
        
        start_time = time.time()
        frame_count = 0
        
        # FPS tracking
        fps_start = time.time()
        fps_count = 0
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            elapsed = time.time() - start_time
            if elapsed > duration_seconds:
                break
            
            # Resize for faster processing
            frame = cv2.resize(frame, (640, 480))
            h, w = frame.shape[:2]
            
            # Run both detectors
            start_heur = time.time()
            activity_h, conf_h = self.heuristic_detector.detect_activity(frame, None)
            time_h = (time.time() - start_heur) * 1000
            
            start_lite = time.time()
            activity_l, conf_l = self.lite_pose_detector.detect_activity(frame, None)
            time_l = (time.time() - start_lite) * 1000
            
            # Store result
            self.results.append({
                'frame': frame_count,
                'heuristic': (activity_h, conf_h, time_h),
                'lite_pose': (activity_l, conf_l, time_l),
                'timestamp': elapsed
            })
            
            # Draw results on frame
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB) if len(frame.shape) == 3 else frame
            frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            
            # Left side - Heuristic
            cv2.putText(frame, "Option 1: Enhanced Heuristic", (10, 30), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 100, 100), 2)
            cv2.putText(frame, f"{activity_h} ({conf_h:.2f})", (10, 70),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 255), 2)
            cv2.putText(frame, f"Time: {time_h:.1f}ms", (10, 100),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
            
            # Right side - Lite Pose
            cv2.putText(frame, "Option 2: Lite Pose (OpenCV)", (w - 300, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (100, 255, 100), 2)
            cv2.putText(frame, f"{activity_l} ({conf_l:.2f})", (w - 300, 70),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 255, 200), 2)
            cv2.putText(frame, f"Time: {time_l:.1f}ms", (w - 300, 100),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
            
            # Bottom - Progress
            progress = int(50 * elapsed / duration_seconds)
            cv2.putText(frame, f"Progress: [{elapsed:.1f}s/{duration_seconds}s] - Frame {frame_count}", 
                       (10, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 150, 255), 1)
            
            cv2.imshow("Activity Detection Comparison", frame)
            
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            
            frame_count += 1
            fps_count += 1
            
            if time.time() - fps_start > 1.0:
                fps = fps_count / (time.time() - fps_start)
                print(f"FPS: {fps:.1f} | Frame {frame_count} | {activity_h} vs {activity_l}")
                fps_start = time.time()
                fps_count = 0
        
        cap.release()
        cv2.destroyAllWindows()
        
        print(f"\n✓ Tested {frame_count} frames in {elapsed:.1f}s")
        return True
    
    def test_on_file(self, video_path):
        """
        Test on a video file
        
        Args:
            video_path: Path to video file
        """
        if not os.path.exists(video_path):
            print(f"❌ Video file not found: {video_path}")
            return False
        
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            print(f"❌ Could not open video: {video_path}")
            return False
        
        print(f"\n{'='*70}")
        print(f"Testing on: {os.path.basename(video_path)}")
        print(f"{'='*70}")
        
        frame_count = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            # Resize
            frame = cv2.resize(frame, (640, 480))
            
            # Test both
            activity_h, conf_h = self.heuristic_detector.detect_activity(frame, None)
            activity_l, conf_l = self.lite_pose_detector.detect_activity(frame, None)
            
            self.results.append({
                'frame': frame_count,
                'heuristic': (activity_h, conf_h, 0),
                'lite_pose': (activity_l, conf_l, 0),
                'timestamp': frame_count / (cap.get(cv2.CAP_PROP_FPS) or 30)
            })
            
            frame_count += 1
            if frame_count % 30 == 0:
                print(f"Processed {frame_count} frames...")
        
        cap.release()
        print(f"✓ Tested {frame_count} frames")
        return True
    
    def generate_report(self):
        """Generate comparison report"""
        if not self.results:
            print("❌ No results to report")
            return
        
        print(f"\n{'='*70}")
        print(f"COMPARISON REPORT")
        print(f"{'='*70}\n")
        
        # Count activities
        heur_activities = {}
        lite_activities = {}
        heur_times = []
        lite_times = []
        agreement = 0
        
        for r in self.results:
            heur_act, heur_conf, heur_time = r['heuristic']
            lite_act, lite_conf, lite_time = r['lite_pose']
            
            heur_activities[heur_act] = heur_activities.get(heur_act, 0) + 1
            lite_activities[lite_act] = lite_activities.get(lite_act, 0) + 1
            
            if heur_time > 0:
                heur_times.append(heur_time)
            if lite_time > 0:
                lite_times.append(lite_time)
            
            if heur_act == lite_act:
                agreement += 1
        
        total_frames = len(self.results)
        agreement_rate = (agreement / total_frames * 100) if total_frames > 0 else 0
        
        print("DETECTION AGREEMENT:")
        print(f"  Match rate: {agreement}/{total_frames} frames ({agreement_rate:.1f}%)\n")
        
        print("OPTION 1 - Enhanced Heuristic:")
        print(f"  Activities detected:")
        for activity, count in sorted(heur_activities.items(), key=lambda x: -x[1]):
            print(f"    - {activity}: {count} frames ({count/total_frames*100:.1f}%)")
        if heur_times:
            print(f"  Performance: avg {np.mean(heur_times):.2f}ms, max {np.max(heur_times):.2f}ms")
        
        print("\nOPTION 2 - Lite Pose (OpenCV):")
        print(f"  Activities detected:")
        for activity, count in sorted(lite_activities.items(), key=lambda x: -x[1]):
            print(f"    - {activity}: {count} frames ({count/total_frames*100:.1f}%)")
        if lite_times:
            print(f"  Performance: avg {np.mean(lite_times):.2f}ms, max {np.max(lite_times):.2f}ms")
        
        print(f"\n{'='*70}")
        print("ANALYSIS:")
        if agreement_rate > 80:
            print("✓ Both methods show high agreement")
            print("  Recommendation: Use Option 1 (Heuristic) - simpler and equally reliable")
        elif agreement_rate > 60:
            print("⚠️  Moderate agreement between methods")
            print("  Recommendation: Test more samples, consider ensemble approach")
        else:
            print("❌ Low agreement - methods detect differently")
            print("  Recommendation: Need more investigation on ground truth")
        
        print(f"{'='*70}\n")

def main():
    """Main test function"""
    tester = ComparisonTest()
    
    print("\nActivity Detection Method Comparison")
    print("=====================================")
    print("Option 1: Enhanced Heuristic (current)")
    print("Option 2: Lite Pose (OpenCV-based)\n")
    
    # Test on webcam (30 seconds)
    if tester.test_on_webcam(duration_seconds=30):
        tester.generate_report()
    else:
        print("❌ Webcam test failed")
        sys.exit(1)

if __name__ == '__main__':
    main()
