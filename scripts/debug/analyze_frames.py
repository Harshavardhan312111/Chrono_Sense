#!/usr/bin/env python3
import numpy as np
import cv2

def analyze_frame(frame, name):
    """Analyze frame metrics"""
    if len(frame.shape) == 3:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    else:
        gray = frame
    
    brightness = np.mean(gray)
    brightness_std = np.std(gray)
    
    edges = cv2.Canny(gray, 50, 150)
    edge_density = np.count_nonzero(edges) / (gray.shape[0] * gray.shape[1])
    
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contour_count = len(contours)
    large_contours = sum(1 for c in contours if cv2.contourArea(c) > 100)
    
    print(f"\n{name}:")
    print(f"  Brightness: {brightness:.1f}, Std: {brightness_std:.1f}")
    print(f"  Edge density: {edge_density:.4f}")
    print(f"  Contours: {contour_count} (large: {large_contours})")
    
    # Check conditions
    if brightness < 70:
        print(f"  ✓ Dark enough for sleeping (brightness < 70)")
    else:
        print(f"  ✗ Too bright for sleeping (brightness {brightness:.1f})")

# Dark frame
dark = np.full((480, 640, 3), (30, 30, 30), dtype=np.uint8)
analyze_frame(dark, "Sleeping (dark)")

# Playing frame
playing = np.full((480, 640, 3), (110, 110, 110), dtype=np.uint8)
for j in range(6):
    cv2.circle(playing, (100 + j * 100, 200), 20, (150, 200, 100), -1)
analyze_frame(playing, "Playing (circles)")

# Threshold check
print("\n\nCondition check for Sleeping:")
print("  Motion < 3 AND brightness < 70: SLEEPING (0.75)")
print("\nCondition check for Reading:")
print("  Motion < 5 AND edge_density > 0.04: READING (0.70)")
