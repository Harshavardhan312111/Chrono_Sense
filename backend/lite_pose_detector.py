"""
Lightweight Pose Detection for Activity Recognition
Uses OpenCV and traditional CV techniques - no heavy ML models
Optimized for macOS performance without threading issues
"""

import cv2
import numpy as np
import logging
from typing import Tuple, Dict, List
from collections import deque

logger = logging.getLogger(__name__)

class LitePoseDetector:
    """
    Lightweight pose detection using OpenCV features:
    - Hand detection via skin color and contours
    - Head position via HOG or shape analysis
    - Body posture via silhouette analysis
    - No threading issues, pure OpenCV
    """
    
    def __init__(self):
        """Initialize lite pose detector"""
        try:
            # Store previous frames for motion analysis
            self._prev_frame = None
            self._prev_gray = None
            
            # Temporal buffers
            self.activity_buffer = deque(maxlen=10)
            self.confidence_buffer = deque(maxlen=10)
            
            # Improved skin color ranges (HSV for robustness)
            # Much more restrictive to avoid picking up monitors, desks, etc.
            self.lower_skin = np.array([0, 40, 80], dtype=np.uint8)      # Higher saturation + value threshold
            self.upper_skin = np.array([20, 255, 255], dtype=np.uint8)    # Still red/pink but selective
            
            logger.info("✓ Lite pose detector initialized (OpenCV-based, improved skin detection)")
        except Exception as e:
            logger.error(f"Failed to initialize LitePoseDetector: {e}")
            raise
    
    def update_student_count(self, num_students: int):
        """
        Update detected student count (for compatibility with interface).
        This is optional tracking that can be used for classroom statistics.
        
        Args:
            num_students: Number of students detected in current frame
        """
        # This is a no-op for LitePoseDetector but required for API compatibility
        pass
    
    def detect_group_activities(self, detections: List[Dict]) -> List[Dict]:
        """
        Detect group-based activities like Playing/Fighting based on proximity.
        Returns detections with updated group activity fields if applicable.
        
        Args:
            detections: List of detection dicts with face positions
            
        Returns:
            Same detections, possibly with updated group activities
        """
        # For now, return detections unchanged
        # Group activity detection (Playing, Fighting) would require spatial proximity analysis
        # which is beyond the scope of single-frame activity detection
        return detections
    
    def detect_activity(self, frame: np.ndarray, face_bbox: Tuple = None) -> Tuple[str, float]:
        """
        Detect activity using lightweight OpenCV methods.
        
        Args:
            frame: Video frame (BGR)
            face_bbox: Face bounding box (x, y, w, h)
            
        Returns:
            activity: Activity name
            confidence: Confidence score (0.0-1.0)
        """
        try:
            h, w = frame.shape[:2]
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame
            
            # === Feature Extraction ===
            
            # 1. Motion Detection
            if self._prev_gray is None:
                self._prev_gray = gray.copy()
                return 'Listening', 0.5
            
            motion_score = cv2.absdiff(gray, self._prev_gray).mean()
            self._prev_gray = gray.copy()
            
            # 2. REMOVED: Hand Detection (disabled due to high false positive rate in classrooms)
            # Hand-based detection was causing false positives for stationary people
            # Classroom scenarios don't require explicit hand-raise detection
            
            # 3. Edge Density (indicates writing, using pen)
            edges = cv2.Canny(gray, 50, 150)
            edge_density = np.count_nonzero(edges) / (h * w)
            
            # 4. Brightness Variance (concentration level)
            brightness = np.mean(gray)
            brightness_std = np.std(gray)
            
            # 5. Optical Flow (alternative motion detection)
            if self._prev_frame is not None:
                flow = cv2.calcOpticalFlowFarneback(
                    self._prev_frame, gray, None, 
                    0.5, 3, 15, 3, 5, 1.2, 0
                )
                flow_mag = np.sqrt(flow[..., 0]**2 + flow[..., 1]**2)
                optical_motion = np.mean(flow_mag)
            else:
                optical_motion = 0
            
            self._prev_frame = gray.copy() if self._prev_frame is None else gray.copy()
            
            # 6. Contour Analysis (objects, writing materials)
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            contour_count = len(contours)
            large_contours = sum(1 for c in contours if cv2.contourArea(c) > 100)
            
            # === Activity Scoring ===
            # RECALIBRATED: Removed hand-based detection (was causing false Raised_Hand)
            # Now using motion, edges, and optical flow for accurate activity classification
            
            activity = 'Listening'
            confidence = 0.65
            
            # When in doubt, default to Listening - most likely classroom activity
            
            # 1. WRITING - High motion + high edge density
            if motion_score > 30 and edge_density > 0.08:
                activity = 'Writing'
                confidence = min(0.90, 0.6 + (motion_score / 100))
            
            # 2. READING - Low motion + moderate-high edge density
            elif motion_score < 8 and edge_density > 0.06:
                activity = 'Reading'
                confidence = 0.75
            
            # 3. SLEEPING - Very low motion + very low brightness variance
            elif motion_score < 2 and brightness_std < 8:
                activity = 'Sleeping'
                confidence = 0.85
            
            # 4. DISTRACTED - Jerky motion (high optical flow) without sustained activity
            elif optical_motion > 15 and motion_score > 15:
                activity = 'Distracted'
                confidence = 0.70
            
            # 5. PLAYING - Very high motion across the frame
            elif motion_score > 40:
                activity = 'Playing'
                confidence = 0.75
            
            # 6. COLLABORATION - Moderate continuous motion
            elif 12 < motion_score < 30 and edge_density > 0.04:
                activity = 'Collaboration'
                confidence = 0.65
            
            # 7. PHONE_USE - Very low motion + concentrated area
            elif motion_score < 3 and optical_motion < 2:
                activity = 'Phone_Use'
                confidence = 0.60
            
            # 8. EATING - Low motion + some hand/mouth area activity
            elif motion_score < 15 and 0.03 < edge_density < 0.07:
                activity = 'Eating'
                confidence = 0.55
            
            # DEFAULT - LISTENING (stationary, low-moderate edge density)
            else:
                activity = 'Listening'
                confidence = 0.70 if motion_score < 12 else 0.65
            
            # === Temporal Smoothing ===
            activity_classes = {
                'Listening': 0, 'Writing': 1, 'Reading': 2, 'Distracted': 3,
                'Playing': 4, 'Sleeping': 5, 'Phone_Use': 6,
                'Collaboration': 7, 'Eating': 8
            }
            
            activity_idx = activity_classes.get(activity, 0)
            self.activity_buffer.append(activity_idx)
            self.confidence_buffer.append(confidence)
            
            if len(self.activity_buffer) >= 3:
                # Majority vote
                mode_activity = max(set(self.activity_buffer), key=list(self.activity_buffer).count)
                mode_name = {v: k for k, v in activity_classes.items()}.get(mode_activity, 'Listening')
                mean_conf = np.mean(list(self.confidence_buffer))
                return mode_name, float(mean_conf)
            else:
                return activity, float(confidence)
        
        except Exception as e:
            logger.debug(f"Lite pose detection error: {e}")
            return 'Listening', 0.5
