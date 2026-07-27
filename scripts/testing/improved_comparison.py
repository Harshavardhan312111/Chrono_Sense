#!/usr/bin/env python3
"""
Improved Activity Detection Comparison
Tests with sequential frames to properly capture motion
"""

import sys, os
sys.path.insert(0, 'backend')

import numpy as np
import cv2
from activity_detector import ActivityDetector
from lite_pose_detector import LitePoseDetector

def create_frame_sequence(activity_type, num_frames=5):
    """Create a sequence of frames simulating an activity"""
    frames = []
    
    if activity_type == "writing":
        # Sequence: static -> motion -> motion -> motion -> static
        for i in range(num_frames):
            f = np.full((480, 640, 3), (120, 120, 120), dtype=np.uint8)
            if i > 0 and i < num_frames - 1:
                # Add moving lines
                offset = (i * 10) % 50
                for j in range(0, 640, 15):
                    cv2.line(f, (j + offset, 0), (j + offset + 40, 480), (200, 150, 100), 2)
            frames.append(f)
    
    elif activity_type == "reading":
        # Sequence: static with many horizontal lines (text-like)
        for _ in range(num_frames):
            f = np.full((480, 640, 3), (140, 140, 140), dtype=np.uint8)
            for i in range(100, 400, 20):
                cv2.line(f, (150, i), (500, i), (100, 100, 100), 1)
            frames.append(f)
    
    elif activity_type == "sleeping":
        # Very dark, very static
        for _ in range(num_frames):
            f = np.full((480, 640, 3), (30, 30, 30), dtype=np.uint8)
            frames.append(f)
    
    elif activity_type == "playing":
        # High motion with many objects
        for i in range(num_frames):
            f = np.full((480, 640, 3), (110, 110, 110), dtype=np.uint8)
            for j in range(6):
                y = (200 + j * 50 + i * 10) % 480
                cv2.circle(f, (100 + j * 100, y), 20, (150, 200, 100), -1)
            frames.append(f)
    
    return frames

def test_activity(detectors, activity_type, num_frames=5):
    """Test both detectors on an activity sequence"""
    frames = create_frame_sequence(activity_type, num_frames)
    
    heur_detector, lite_detector = detectors
    
    h_results = []
    l_results = []
    
    for frame in frames:
        h_act, h_conf = heur_detector.detect_activity(frame, None)
        l_act, l_conf = lite_detector.detect_activity(frame, None)
        
        h_results.append((h_act, h_conf))
        l_results.append((l_act, l_conf))
    
    # Get final results (majority vote from sequence)
    h_activities = [r[0] for r in h_results]
    l_activities = [r[0] for r in l_results]
    
    h_final = max(set(h_activities), key=h_activities.count)
    l_final = max(set(l_activities), key=l_activities.count)
    
    h_avg_conf = np.mean([r[1] for r in h_results])
    l_avg_conf = np.mean([r[1] for r in l_results])
    
    return h_final, h_avg_conf, l_final, l_avg_conf

def main():
    print("\n" + "="*75)
    print("ACTIVITY DETECTION COMPARISON - Sequential Frame Test")
    print("="*75)
    
    # Initialize detectors
    heur = ActivityDetector()
    lite = LitePoseDetector()
    detectors = (heur, lite)
    
    activities = ["writing", "reading", "sleeping", "playing"]
    
    print("\nTesting each activity with 5-frame sequences:\n")
    print(f"{'Activity':<15} | {'Heuristic':<20} | {'Lite Pose':<20} | Match")
    print("-" * 75)
    
    matches = 0
    for activity in activities:
        h_act, h_conf, l_act, l_conf = test_activity(detectors, activity, num_frames=5)
        
        h_str = f"{h_act} ({h_conf:.2f})"
        l_str = f"{l_act} ({l_conf:.2f})"
        
        match = "✓" if h_act == l_act else "✗"
        if h_act == l_act:
            matches += 1
        
        print(f"{activity:<15} | {h_str:<20} | {l_str:<20} | {match}")
    
    print("-" * 75)
    agreement = (matches / len(activities)) * 100
    print(f"\nAgreement: {matches}/{len(activities)} ({agreement:.0f}%)\n")
    
    if agreement >= 75:
        print("✅ RECOMMENDATION: Use Option 1 (Enhanced Heuristic)")
        print("   - Both methods agree well")
        print("   - Heuristic is simpler with fewer dependencies")
        print("   - No threading issues on macOS")
        return 1
    elif agreement >= 50:
        print("⚠️  RECOMMENDATION: Use ENSEMBLE (both methods with voting)")
        print("   - Moderate agreement suggests voting helps")
        print("   - Better robustness")
        return 2
    else:
        print("❌ RECOMMENDATION: Need further investigation with real video")
        return 3

if __name__ == '__main__':
    result = main()
    sys.exit(result)
