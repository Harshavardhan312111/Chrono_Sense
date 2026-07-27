#!/usr/bin/env python3
import sys, os
sys.path.insert(0, 'backend')
import numpy as np
import cv2

# Create synthetic frames
gray_static = np.full((480, 640), 100, dtype=np.uint8)

# High motion frame with lines
gray_motion = np.full((480, 640), 120, dtype=np.uint8)
for i in range(0, 640, 10):
    cv2.line(gray_motion, (i, 0), (i + 50, 480), (200,), 2)

# Calculate motion
motion = cv2.absdiff(gray_static, gray_motion).mean()
print(f"Motion score: {motion:.2f}")

# Edge analysis
edges = cv2.Canny(gray_motion, 50, 150)
edge_density = np.count_nonzero(edges) / (480 * 640)
print(f"Edge density: {edge_density:.4f}")
print(f"\nWriting threshold: motion > 15, edges > 0.05")
print(f"Result: motion={motion:.2f}, edges={edge_density:.4f}")

if motion > 15 and edge_density > 0.05:
    print("✓ Should detect as WRITING")
elif edge_density > 0.05:
    print("✓ Should detect as READING (high edges, low motion)")
else:
    print("? Other activity")
