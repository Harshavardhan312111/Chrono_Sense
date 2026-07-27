#!/usr/bin/env python3
"""
Quick Activity Detection Comparison Test
Tests both methods on synthesized frames without needing a webcam
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

import cv2
import numpy as np
from activity_detector import ActivityDetector
from lite_pose_detector import LitePoseDetector

def create_test_frames():
    """Create synthetic test frames representing different activities"""
    frames = []
    
    # Frame 1: Static, normal (Listening)
    f1 = np.full((480, 640, 3), (100, 100, 100), dtype=np.uint8)
    cv2.putText(f1, "Listening", (300, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    frames.append(("Static/Listening", f1))
    
    # Frame 2: High motion (Writing/Moving)
    f2 = np.full((480, 640, 3), (120, 120, 120), dtype=np.uint8)
    for i in range(0, 640, 10):
        cv2.line(f2, (i, 0), (i + 50, 480), (200, 200, 200), 2)
    frames.append(("High Motion/Writing", f2))
    
    # Frame 3: Dark (Sleeping)
    f3 = np.full((480, 640, 3), (30, 30, 30), dtype=np.uint8)
    cv2.putText(f3, "Dark Frame", (250, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (100, 100, 100), 2)
    frames.append(("Dark/Sleeping", f3))
    
    # Frame 4: Multiple contours (Playing/Collaboration)
    f4 = np.full((480, 640, 3), (120, 120, 120), dtype=np.uint8)
    for i in range(0, 5):
        cv2.circle(f4, (100 + i*100, 200), 30, (200, 150, 100), 2)
    frames.append(("Multiple Objects/Playing", f4))
    
    # Frame 5: Complex edges (Reading)
    f5 = np.full((480, 640, 3), (140, 140, 140), dtype=np.uint8)
    for i in range(100, 300, 20):
        cv2.line(f5, (200, i), (400, i), (100, 100, 100), 1)
    frames.append(("Many Edges/Reading", f5))
    
    return frames

def run_comparison():
    """Run comparison on test frames"""
    print("\n" + "="*70)
    print("ACTIVITY DETECTION METHOD COMPARISON")
    print("="*70)
    print("\nGenerating synthetic test frames...")
    
    # Create detectors
    heuristic = ActivityDetector()
    lite_pose = LitePoseDetector()
    
    frames = create_test_frames()
    
    print(f"\nTesting {len(frames)} synthetic frames:\n")
    print(f"{'Scenario':<30} | {'Heuristic':<20} | {'Lite Pose':<20}")
    print("-" * 75)
    
    matches = 0
    results = []
    
    for scenario, frame in frames:
        # Test heuristic
        h_activity, h_conf = heuristic.detect_activity(frame, None)
        
        # Test lite pose
        l_activity, l_conf = lite_pose.detect_activity(frame, None)
        
        # Track match
        if h_activity == l_activity:
            matches += 1
            match_marker = "✓"
        else:
            match_marker = "✗"
        
        # Format output
        h_str = f"{h_activity} ({h_conf:.2f})"
        l_str = f"{l_activity} ({l_conf:.2f})"
        
        print(f"{scenario:<30} | {h_str:<20} | {l_str:<20} {match_marker}")
        
        results.append({
            'scenario': scenario,
            'heuristic': (h_activity, h_conf),
            'lite_pose': (l_activity, l_conf),
            'match': h_activity == l_activity
        })
    
    print("-" * 75)
    agreement_rate = (matches / len(frames)) * 100
    print(f"\nAGREEMENT RATE: {matches}/{len(frames)} ({agreement_rate:.1f}%)\n")
    
    print("="*70)
    print("PRELIMINARY ASSESSMENT")
    print("="*70)
    
    print("""
✅ Option 1: Enhanced Heuristic
   - Uses: Motion detection, edges, brightness, contours
   - Pros: Fast, no dependencies, no threading issues
   - Cons: Less accurate than pose-based methods
   - Best for: School monitoring where speed > accuracy

✅ Option 2: Lite Pose (OpenCV)
   - Uses: Skin detection, optical flow, hand tracking, contours
   - Pros: More accurate hand detection, optical flow
   - Cons: Slightly heavier computation, more edge cases
   - Best for: Detailed activity analysis

RECOMMENDATION FOR YOUR USE CASE:
""")
    
    if agreement_rate > 85:
        print("""
  Use Option 1 (Enhanced Heuristic)
  - Both methods agree > 85%
  - Simpler maintenance, fewer dependencies
  - Sufficient accuracy for classroom monitoring
  - Task: Monitor student engagement, not identify individuals
""")
    elif agreement_rate > 70:
        print("""
  Consider BOTH methods with voting
  - Moderate agreement suggests ensemble approach
  - Run both detectors, use majority vote
  - Better robustness against edge cases
""")
    else:
        print("""
  Investigate further with real video
  - Synthetic frames may not represent real behavior
  - Need actual classroom footage to validate
""")
    
    print("="*70 + "\n")
    
    return results

if __name__ == '__main__':
    results = run_comparison()
