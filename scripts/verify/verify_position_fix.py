#!/usr/bin/env python3
"""
Verify position-based face matching is working correctly.
Simulates 7 people detected across multiple frames with position-based matching.
"""

from collections import defaultdict

class PositionMatcher:
    def __init__(self):
        self.face_position_cache = defaultdict(lambda: defaultdict(list))
        self.unknown_face_counter = defaultdict(int)
        self.position_match_threshold = 500
        self.size_match_threshold = 0.5
    
    def match(self, face_bbox, camera_id):
        """Match face by position - returns (id, is_new)"""
        x, y, w, h = face_bbox
        center_x, center_y = x + w // 2, y + h // 2
        face_area = w * h
        
        recent_faces = self.face_position_cache[camera_id]
        best_match_id = None
        best_distance = float('inf')
        
        # Check last 30 frames
        for frame_id, faces_in_frame in list(recent_faces.items())[-30:]:
            for dx, dy, x2, y2, last_id in faces_in_frame:
                detected_center_x = dx + (x2 - dx) // 2
                detected_center_y = dy + (y2 - dy) // 2
                detected_area = (x2 - dx) * (y2 - dy)
                
                distance = ((center_x - detected_center_x)**2 + (center_y - detected_center_y)**2)**0.5
                size_ratio = max(face_area, detected_area) / min(face_area, detected_area) if min(face_area, detected_area) > 0 else 2.0
                
                if distance < self.position_match_threshold and size_ratio < (1 + self.size_match_threshold):
                    if distance < best_distance:
                        best_distance = distance
                        best_match_id = last_id
        
        # Found match
        if best_match_id is not None:
            current_frame_id = len(recent_faces)
            self.face_position_cache[camera_id][current_frame_id].append((x, y, x + w, y + h, best_match_id))
            return best_match_id, False
        
        # New person
        self.unknown_face_counter[camera_id] += 1
        new_id = self.unknown_face_counter[camera_id]
        current_frame_id = len(recent_faces)
        self.face_position_cache[camera_id][current_frame_id].append((x, y, x + w, y + h, new_id))
        return new_id, True

# Test with 7 people
matcher = PositionMatcher()
cam = "camera_1"

# Define 7 positions
positions = [
    (10, 50, 100, 120),
    (250, 50, 100, 120),
    (490, 50, 100, 120),
    (10, 300, 100, 120),
    (250, 300, 100, 120),
    (490, 300, 100, 120),
    (250, 150, 100, 120),
]

print("=" * 60)
print("POSITION-BASED FACE MATCHING VERIFICATION")
print("=" * 60)

# Frame 1
print("\nFrame 1 (Initial Detection):")
ids_f1 = []
for i, pos in enumerate(positions):
    fid, is_new = matcher.match(pos, cam)
    ids_f1.append(fid)
    print(f"  Person {i+1}: ID {fid:2d} ({'NEW' if is_new else 'matched'})")

unique_f1 = len(set(ids_f1))
print(f"  Total unique IDs: {unique_f1}")

# Frame 2 - slight movement
print("\nFrame 2 (Slight Movement):")
positions2 = [
    (15, 55, 100, 120),
    (255, 52, 100, 120),
    (495, 58, 100, 120),
    (12, 305, 100, 120),
    (252, 302, 100, 120),
    (492, 308, 100, 120),
    (255, 155, 100, 120),
]
ids_f2 = []
for i, pos in enumerate(positions2):
    fid, is_new = matcher.match(pos, cam)
    ids_f2.append(fid)
    print(f"  Person {i+1}: ID {fid:2d} ({'NEW' if is_new else 'matched'})")

unique_f2 = len(set(ids_f2))
print(f"  Total unique IDs: {unique_f2}")

# Results
print("\n" + "=" * 60)
print("RESULTS:")
print("=" * 60)
print(f"Frame 1 unique IDs: {unique_f1}")
print(f"Frame 2 unique IDs: {unique_f2}")
print(f"IDs consistent across frames: {ids_f1 == ids_f2}")
print(f"\n✅ PASS: Position matching keeps 7 people as 7 IDs" if unique_f1 == 7 and unique_f2 == 7 and ids_f1 == ids_f2 else "\n❌ FAIL")
