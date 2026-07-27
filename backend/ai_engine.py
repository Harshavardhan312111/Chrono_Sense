"""
ChronoSense Enterprise Face Recognition Engine
Architecture: InsightFace ArcFace + Emotion Detection + Kalman Tracking
Supports: 4,400+ people with real-time emotion sensing and spatio-temporal analysis
"""

import cv2
import numpy as np
import insightface
import time
import os
import threading
from collections import defaultdict, deque
from filterpy.kalman import KalmanFilter
import logging
from emotion_detector import FERPlusEmotionDetector, EmotionAnalytics

logger = logging.getLogger(__name__)


def _required_gap_for_score(best_score):
    if best_score >= 0.34:
        return 0.04
    if best_score >= 0.30:
        return 0.03
    if best_score >= 0.28:
        return 0.02
    return 0.10


class InsightFaceRecognizer:
    """
    Production-grade face recognition using InsightFace ArcFace v2.
    Generates 512-dimensional embeddings for 4,400+ scale.
    Similarity threshold: 0.6 (cosine distance)
    """
    
    def __init__(self):
        """Initialize InsightFace model and GPU acceleration"""
        self._lock = threading.Lock()
        try:
            self.app = insightface.app.FaceAnalysis(
                name='buffalo_l',  # Lightweight model optimized for speed
                providers=['CPUExecutionProvider']  # Use CPU; change to ['CUDAExecutionProvider'] for GPU
            )
            self.app.prepare(ctx_id=-1, det_size=(1280, 1280))
            logger.info("✓ InsightFace model loaded (buffalo_l, det_size=1280x1280)")
        except Exception as e:
            logger.error(f"Failed to load InsightFace: {e}")
            raise

    def get_faces_safe(self, frame):
        """Thread-safe wrapper around app.get()."""
        with self._lock:
            return self.app.get(frame)

    @staticmethod
    def _select_best_face(faces, target_bbox=None):
        """Pick the face that best matches the requested bbox, else the largest face."""
        if not faces:
            return None

        if target_bbox is None:
            return max(faces, key=lambda face: (face.bbox[2] - face.bbox[0]) * (face.bbox[3] - face.bbox[1]))

        tx, ty, tw, th = target_bbox
        tcx = tx + tw / 2.0
        tcy = ty + th / 2.0

        def score(face):
            x1, y1, x2, y2 = face.bbox.astype(float)
            fw = max(1.0, x2 - x1)
            fh = max(1.0, y2 - y1)
            fcx = x1 + fw / 2.0
            fcy = y1 + fh / 2.0
            center_distance = ((fcx - tcx) ** 2 + (fcy - tcy) ** 2) ** 0.5
            area_delta = abs((fw * fh) - (tw * th))
            return (center_distance, area_delta)

        return min(faces, key=score)
    
    def get_embedding(self, frame, bbox):
        """
        Extract face embedding from frame ROI.
        Args:
            frame: BGR image
            bbox: (x, y, w, h) bounding box
        Returns:
            512-D numpy array (normalized)
        """
        x, y, w, h = bbox
        
        # First try: use full frame
        try:
            faces = self.get_faces_safe(frame)
            best_face = self._select_best_face(faces, bbox)
            if best_face is not None:
                emb = best_face.embedding.astype(np.float32)
                logger.debug(f"Extracted embedding from full frame: shape={emb.shape}, dtype={emb.dtype}, norm={np.linalg.norm(emb):.4f}")
                return emb
        except Exception as e:
            logger.debug(f"Direct frame detection failed: {e}")
        
        # Fallback: extract ROI with generous padding and try again
        pad = int(max(w, h) * 0.5)
        x1, y1 = max(0, x - pad), max(0, y - pad)
        x2, y2 = min(frame.shape[1], x + w + pad), min(frame.shape[0], y + h + pad)
        face_roi = frame[y1:y2, x1:x2]
        
        if face_roi.size == 0:
            logger.warning(f"Empty ROI for bbox {bbox}")
            return None
        
        try:
            faces = self.get_faces_safe(face_roi)
            best_face = self._select_best_face(faces)
            if best_face is not None:
                emb = best_face.embedding.astype(np.float32)
                logger.debug(f"Extracted embedding from ROI: shape={emb.shape}, dtype={emb.dtype}, norm={np.linalg.norm(emb):.4f}")
                return emb
        except Exception as e:
            logger.debug(f"ROI detection failed: {e}")
        
        # Last resort: upscale ROI so small faces become detectable
        try:
            rh, rw = face_roi.shape[:2]
            target = 500
            scale_up = max(target / rw, target / rh)
            if scale_up > 1.2:
                upscaled = cv2.resize(face_roi, None, fx=scale_up, fy=scale_up, interpolation=cv2.INTER_CUBIC)
                faces = self.get_faces_safe(upscaled)
                best_face = self._select_best_face(faces)
                if best_face is not None:
                    emb = best_face.embedding.astype(np.float32)
                    logger.info(f"Extracted embedding from upscaled ROI ({scale_up:.1f}x): shape={emb.shape}, norm={np.linalg.norm(emb):.4f}")
                    return emb
        except Exception as e:
            logger.debug(f"Upscaled ROI detection failed: {e}")

        # Final fallback: upscale the full frame so small faces become more detectable.
        try:
            fh, fw = frame.shape[:2]
            target = 1600
            scale_up = min(4.0, max(target / max(fw, 1), target / max(fh, 1)))
            if scale_up > 1.2:
                upscaled_frame = cv2.resize(frame, None, fx=scale_up, fy=scale_up, interpolation=cv2.INTER_CUBIC)
                scaled_bbox = (
                    int(x * scale_up),
                    int(y * scale_up),
                    int(w * scale_up),
                    int(h * scale_up)
                )
                faces = self.get_faces_safe(upscaled_frame)
                best_face = self._select_best_face(faces, scaled_bbox)
                if best_face is not None:
                    emb = best_face.embedding.astype(np.float32)
                    logger.info(f"Extracted embedding from upscaled full frame ({scale_up:.1f}x): shape={emb.shape}, norm={np.linalg.norm(emb):.4f}")
                    return emb
        except Exception as e:
            logger.debug(f"Upscaled full-frame detection failed: {e}")
        
        logger.warning(f"Failed to extract embedding for bbox {bbox}")
        return None
    
    @staticmethod
    def cosine_similarity(emb1, emb2):
        """Compute cosine similarity between two embeddings (0-1, higher=more similar)"""
        if emb1 is None or emb2 is None:
            return 0.0
        
        # Ensure proper shapes and types
        emb1 = np.array(emb1, dtype=np.float32).flatten()
        emb2 = np.array(emb2, dtype=np.float32).flatten()
        
        norm1 = np.linalg.norm(emb1)
        norm2 = np.linalg.norm(emb2)
        
        if norm1 == 0 or norm2 == 0:
            logger.warning(f"Zero norm detected: norm1={norm1}, norm2={norm2}")
            return 0.0
        
        similarity = float(np.dot(emb1, emb2) / (norm1 * norm2))
        return max(0.0, min(1.0, similarity))  # Clamp to [0, 1]
    
    @staticmethod
    def euclidean_distance(emb1, emb2):
        """Compute Euclidean distance between embeddings (lower=more similar, returns 0-1 score)"""
        if emb1 is None or emb2 is None:
            return 0.0
        
        emb1 = np.array(emb1, dtype=np.float32).flatten()
        emb2 = np.array(emb2, dtype=np.float32).flatten()
        
        distance = np.sqrt(np.sum((emb1 - emb2) ** 2))
        # Convert distance to similarity score (0-1, higher=more similar)
        # Using logistic curve: 1/(1+distance) - more lenient than exp(-distance)
        similarity = 1.0 / (1.0 + distance)
        return max(0.0, min(1.0, similarity))
    
    @staticmethod
    def manhattan_distance(emb1, emb2):
        """Compute Manhattan distance between embeddings (lower=more similar, returns 0-1 score)"""
        if emb1 is None or emb2 is None:
            return 0.0
        
        emb1 = np.array(emb1, dtype=np.float32).flatten()
        emb2 = np.array(emb2, dtype=np.float32).flatten()
        
        distance = np.sum(np.abs(emb1 - emb2))
        # Normalize by embedding dimension and convert to similarity
        dim = len(emb1)
        normalized_distance = distance / (dim * 2)  # Max possible value is ~dim*2 for normalized embeddings
        similarity = 1.0 - min(1.0, normalized_distance)
        return max(0.0, similarity)
    
    @staticmethod
    def hybrid_similarity(emb1, emb2, weights=None):
        """
        Compute hybrid similarity using multiple metrics.
        Combines cosine, euclidean, and manhattan distances for robustness across camera qualities.
        
        Args:
            emb1, emb2: Embeddings to compare
            weights: Dict with keys 'cosine', 'euclidean', 'manhattan', 'l2_norm' (default: balanced)
        
        Returns:
            Combined similarity score (0-1, higher=more similar)
        """
        if emb1 is None or emb2 is None:
            return 0.0
        
        # Default weights optimized for HD->CCTV matching
        if weights is None:
            weights = {
                'cosine': 0.4,          # Good for overall shape similarity
                'euclidean': 0.3,       # Robust to noise and camera differences
                'manhattan': 0.2,       # Sensitive to local distortions
                'l2_norm': 0.1          # L2 norm difference (accounts for brightness)
            }
        
        scores = {}
        
        # Cosine similarity
        scores['cosine'] = InsightFaceRecognizer.cosine_similarity(emb1, emb2)
        
        # Euclidean distance
        scores['euclidean'] = InsightFaceRecognizer.euclidean_distance(emb1, emb2)
        
        # Manhattan distance
        scores['manhattan'] = InsightFaceRecognizer.manhattan_distance(emb1, emb2)
        
        # L2 norm difference (brightness/intensity scale invariance)
        emb1 = np.array(emb1, dtype=np.float32).flatten()
        emb2 = np.array(emb2, dtype=np.float32).flatten()
        norm1 = np.linalg.norm(emb1)
        norm2 = np.linalg.norm(emb2)
        norm_diff = abs(norm1 - norm2) / max(norm1, norm2, 1e-6)
        scores['l2_norm'] = 1.0 - min(1.0, norm_diff)  # Invert so higher=better
        
        # Weighted average
        total_weight = sum(weights.values())
        hybrid_score = sum(scores.get(k, 0) * v for k, v in weights.items()) / total_weight
        
        return max(0.0, min(1.0, float(hybrid_score)))


class EmotionDetector:
    """
    Wrapper for FERPlus-based emotion detection.
    Uses real deep learning models for facial expression recognition.
    """
    
    def __init__(self):
        """Initialize FERPlus emotion detector"""
        self.detector = FERPlusEmotionDetector()
        logger.info("✓ Emotion detector initialized (FERPlus-based)")
    
    def detect_emotion(self, frame, bbox):
        """
        Detect emotion from face ROI.
        
        Args:
            frame: BGR image
            bbox: (x, y, w, h) bounding box
        
        Returns:
            {
                'emotion': str,
                'confidence': float,
                'all_scores': dict,
                'intensity': str
            }
        """
        return self.detector.detect_emotion(frame, bbox)


class KalmanBBoxTracker:
    """
    Kalman filter based bounding box tracker.
    Tracks position (x, y) and scale (w, h) + velocity estimates.
    Handles occlusions and temporal smoothing.
    """
    
    def __init__(self, bbox, track_id):
        """
        Initialize tracker with initial bounding box.
        Args:
            bbox: (x, y, w, h)
            track_id: unique identifier
        """
        self.track_id = track_id
        self.hits = 0
        self.age = 0
        self.last_seen = 0  # Frames since last detection (for timeout)
        self.history = deque(maxlen=30)  # Store last 30 positions for trajectory
        
        # Kalman filter state: [x, y, w, h, vx, vy]
        self.kf = KalmanFilter(dim_x=6, dim_z=4)
        x, y, w, h = bbox
        
        self.kf.x = np.array([[x + w/2], [y + h/2], [w], [h], [0], [0]], dtype=np.float32)
        self.kf.F = np.eye(6)
        self.kf.F[0, 4] = 1  # vx contribution to x
        self.kf.F[1, 5] = 1  # vy contribution to y
        
        self.kf.H = np.zeros((4, 6))
        self.kf.H[0, 0] = 1  # measure x
        self.kf.H[1, 1] = 1  # measure y
        self.kf.H[2, 2] = 1  # measure w
        self.kf.H[3, 3] = 1  # measure h
        
        self.kf.P *= 100
        self.kf.R = np.eye(4) * 10
        self.kf.Q = np.eye(6) * 0.1
        
        self.history.append((x, y, w, h))
    
    def predict(self):
        """Predict next position using Kalman filter"""
        try:
            self.kf.predict()
            state = self.kf.x
            x, y, w, h = state[0, 0], state[1, 0], state[2, 0], state[3, 0]
            return (int(x - w/2), int(y - h/2), int(max(1, w)), int(max(1, h)))
        except:
            if self.history:
                return self.history[-1]
            return None
    
    def update(self, bbox):
        """Update tracker with new measurement"""
        x, y, w, h = bbox
        z = np.array([[x + w/2], [y + h/2], [w], [h]], dtype=np.float32)
        try:
            self.kf.update(z)
            self.hits += 1
            self.last_seen = 0  # Reset timeout counter
        except:
            pass
        
        self.history.append((x, y, w, h))
    
    def get_trajectory(self):
        """Return movement trajectory for spatio-temporal analysis"""
        return list(self.history)


class ChronoEngine:
    """
    Main recognition pipeline: Detection → Emotion → Recognition → Tracking
    Enterprise architecture supporting:
    - Real-time processing (30+ FPS)
    - 4,400+ person database
    - Concurrent emotion + recognition streams
    - Trajectory analysis for behavior patterns
    """
    
    def __init__(self, recognition_threshold=0.50, matching_metric='hybrid', camera_thresholds=None, enable_emotion_detection=False):
        """
        Initialize engine components.
        Args:
            recognition_threshold: Default similarity threshold (0.50 = lower for CCTV, 0.60 = HD camera)
            matching_metric: Method for face matching ('cosine', 'euclidean', 'manhattan', 'hybrid')
            camera_thresholds: Dict mapping camera names to specific thresholds
                             e.g. {'Local Webcam': 0.30, 'Chronosphere Lab': 0.40}
        """
        self.recognizer = InsightFaceRecognizer()
        self.enable_emotion_detection = enable_emotion_detection
        self.emotion_detector = EmotionDetector() if enable_emotion_detection else None
        # Serialize native model inference across camera threads. InsightFace and
        # OpenCV-backed emotion paths can segfault on macOS when invoked in
        # parallel from multiple stream workers.
        self.runtime_lock = threading.RLock()
        # Note: Face detection is now handled by InsightFace (via self.recognizer.app.get())
        # Removed Haar Cascade due to OpenCV assertion failures with certain frame inputs
        
        self.recognition_threshold = recognition_threshold
        self.matching_metric = matching_metric
        
        # Camera-specific thresholds for handling different image qualities
        # Local Webcam captures at different angle/lighting than IP cameras
        self.camera_thresholds = camera_thresholds or {
            'Local Webcam': 0.30,  # Lower threshold for webcam (lower image quality)
            'local_webcam': 0.30,  # Also accept lowercase variant
        }
        
        self.profiles = {}  # {profile_id: {'name': str, 'embedding': ndarray, ...}}
        self.trackers = {}  # {track_id: KalmanBBoxTracker}
        self.next_track_id = 1
        self.detect_count = 0    
        self.dynamic_gap_enabled = str(os.getenv("CHRONOSENSE_DYNAMIC_GAP_ENABLED", "true")).lower() == "true"
        
        # Multi-face classroom optimization
        self.max_simultaneous_faces = 60  # Support up to 60 faces
        self.iou_threshold = 0.15  # Stricter for classroom (avoid merging nearby faces)
        self.distance_threshold_ratio = 0.3  # Max percentage of bbox size for auto-match
        
        logger.info(
            f"✓ ChronoEngine initialized (threshold={recognition_threshold}, metric={matching_metric}, "
            f"camera_thresholds={list(self.camera_thresholds.keys())}, classroom_mode=60_faces, "
            f"emotion_detection={'on' if self.enable_emotion_detection else 'off'}, "
            f"dynamic_gap={'on' if self.dynamic_gap_enabled else 'off'})"
        )
    
    def detect_faces(self, frame):
        """
        Face detection using InsightFace with Haar cascade fallback.
        Haar cascade runs when InsightFace returns 0 faces (e.g. thread
        contention, small faces, low resolution webcam).
        Returns:
            List of (x, y, w, h) bounding boxes
        """
        try:
            # Use InsightFace's built-in detector (thread-safe)
            detected_faces = self.recognizer.get_faces_safe(frame)
            
            if detected_faces:
                bboxes = []
                fh, fw = frame.shape[:2]
                MIN_FACE_SIZE = 23  # Slightly relaxed: catches classroom faces at distance
                
                for face in detected_faces:
                    bbox = face.bbox.astype(int)
                    x1, y1, x2, y2 = bbox
                    x, y, w, h = x1, y1, (x2 - x1), (y2 - y1)
                    
                    # Filter out very tiny faces (likely false positives)
                    if w < MIN_FACE_SIZE or h < MIN_FACE_SIZE:
                        logger.debug(f"Filtered tiny face: {w}x{h}")
                        continue
                    
                    bboxes.append((x, y, w, h))
                
                if bboxes:
                    logger.debug(f"Detected {len(bboxes)} valid faces using InsightFace (filtered from {len(detected_faces)})")
                    return bboxes
            
            # Fallback: Haar cascade for smaller/harder-to-detect faces
            # Upscale frame to improve small-face detection
            fh, fw = frame.shape[:2]
            scale = max(1, 1280 // max(fw, fh))
            if scale > 1:
                detect_frame = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR)
            else:
                detect_frame = frame
            gray = cv2.cvtColor(detect_frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.equalizeHist(gray)
            cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            )
            haar_faces = cascade.detectMultiScale(
                gray, scaleFactor=1.05, minNeighbors=4, minSize=(40, 40)  # Moderately relaxed to catch classroom faces
            )
            if len(haar_faces) > 0:
                # Scale bboxes back to original frame coordinates
                bboxes = [
                    (int(x / scale), int(y / scale), int(w / scale), int(h / scale))
                    for (x, y, w, h) in haar_faces
                ]
                logger.info(f"Detected {len(bboxes)} faces using Haar fallback (scale={scale}x)")
                return bboxes
            
            return []
        
        except Exception as e:
            logger.warning(f"Face detection failed: {e}")
            return []
    
    def detect_faces_with_landmarks(self, frame):
        """
        Face detection with landmarks using InsightFace.
        
        Returns:
            List of dicts: [{'bbox': (x, y, w, h), 'landmarks': landmarks_array}, ...]
        """
        try:
            # Use InsightFace's built-in detector (thread-safe)
            detected_faces = self.recognizer.get_faces_safe(frame)
            
            if not detected_faces:
                return []
            
            # Convert InsightFace format and extract landmarks
            faces_with_landmarks = []
            for face in detected_faces:
                # InsightFace bbox is [x1, y1, x2, y2]
                bbox = face.bbox.astype(int)
                x1, y1, x2, y2 = bbox
                x, y, w, h = x1, y1, (x2 - x1), (y2 - y1)
                
                # Extract landmarks (106-point face landmarks)
                landmarks = face.landmark  # (106, 2) array of landmark coordinates
                
                faces_with_landmarks.append({
                    'bbox': (x, y, w, h),
                    'landmark': landmarks,
                    'face_obj': face  # Keep reference to full face object
                })
            
            logger.debug(f"Detected {len(faces_with_landmarks)} faces with landmarks")
            return faces_with_landmarks
        
        except Exception as e:
            logger.warning(f"InsightFace detection with landmarks failed: {e}")
            return []
    
    def recognize_face(self, frame, bbox, profile_embedding=None, face_obj=None, camera_id=None):
        """
        Recognize face by computing embedding and matching against profiles.
        
        Args:
            frame: Image containing the face (can be full frame or crop)
            bbox: Bounding box (x, y, w, h)
            profile_embedding: Optional pre-computed embedding (for testing)
            face_obj: Optional InsightFace face object with pre-computed embedding
            camera_id: Optional camera name/identifier for camera-specific thresholds
            
        Returns:
            (profile_id, name, confidence) or (None, 'Unknown', 0.0)
        """
        # Critical check: Do we have profiles loaded?
        if not self.profiles:
            logger.error("❌ NO PROFILES LOADED - Recognition cannot work without profiles!")
            return None, 'Unknown', 0.0, {
                "best_score": 0.0,
                "second_best_score": 0.0,
                "score_gap": 0.0,
                "applied_threshold": self.recognition_threshold,
                "applied_min_gap": 0.10,
                "matched_view": None,
                "recognition_rejection_reason": "no_profiles_loaded",
            }
        
        # Use pre-computed embedding from face_obj if available (already computed by InsightFace detector)
        if face_obj is not None:
            try:
                embedding = face_obj.embedding.astype(np.float32)
                logger.info(f"Using pre-computed embedding from face_obj: shape={embedding.shape}, norm={np.linalg.norm(embedding):.4f}")
            except Exception as e:
                logger.warning(f"Failed to extract embedding from face_obj: {e}")
                embedding = None
        else:
            embedding = self.recognizer.get_embedding(frame, bbox)
        
        if embedding is None:
            logger.info(f"Failed to extract embedding for bbox {bbox}")
            return None, 'Unknown', 0.0, {
                "best_score": 0.0,
                "second_best_score": 0.0,
                "score_gap": 0.0,
                "applied_threshold": self.recognition_threshold,
                "applied_min_gap": 0.10,
                "matched_view": None,
                "recognition_rejection_reason": "embedding_extraction_failed",
            }
        
        best_match = None
        best_score = 0.0
        second_best_score = 0.0
        all_scores = {}
        
        for profile_id, profile in self.profiles.items():
            profile_best_score = 0.0
            matched_view = "legacy"
            candidate_embeddings = []

            for view_name, view_payload in (profile.get("view_embeddings") or {}).items():
                candidate_embedding = view_payload.get("embedding")
                if candidate_embedding is None:
                    continue
                candidate_embeddings.append((view_name, candidate_embedding))

            if not candidate_embeddings and profile.get("embedding") is not None:
                candidate_embeddings.append(("legacy", profile["embedding"]))

            for view_name, candidate_embedding in candidate_embeddings:
                if self.matching_metric == 'cosine':
                    score = self.recognizer.cosine_similarity(embedding, candidate_embedding)
                elif self.matching_metric == 'euclidean':
                    score = self.recognizer.euclidean_distance(embedding, candidate_embedding)
                elif self.matching_metric == 'manhattan':
                    score = self.recognizer.manhattan_distance(embedding, candidate_embedding)
                else:  # 'hybrid' (default)
                    score = self.recognizer.hybrid_similarity(embedding, candidate_embedding)

                if score > profile_best_score:
                    profile_best_score = score
                    matched_view = view_name

            if not candidate_embeddings:
                continue

            all_scores[profile['name']] = {
                "score": profile_best_score,
                "matched_view": matched_view,
            }
            if profile_best_score > best_score:
                second_best_score = best_score
                best_score = profile_best_score
                best_match = profile_id
            elif profile_best_score > second_best_score:
                second_best_score = profile_best_score
        
        # Log all scores for debugging
        logger.info(f"=== FACE RECOGNITION SCORES === Profiles: {all_scores}")
        
        # Use camera-specific threshold if available, otherwise use default
        # This allows lower thresholds for lower-quality cameras (e.g., webcam)
        if camera_id and camera_id in self.camera_thresholds:
            threshold = self.camera_thresholds[camera_id]
            logger.info(f"🎥 Using camera-specific threshold: {threshold:.3f} for '{camera_id}'")
        else:
            threshold = self.recognition_threshold
        
        score_gap = best_score - second_best_score
        
        # DUAL THRESHOLD: Both absolute score AND gap requirement to prevent false positives
        min_gap = _required_gap_for_score(best_score) if self.dynamic_gap_enabled else 0.10
        
        best_name = self.profiles[best_match]['name'] if best_match else 'None'
        matched_view = self.profiles[best_match].get("matched_view") if best_match else None
        if best_match:
            matched_view = all_scores.get(best_name, {}).get("matched_view")
        recognition_debug = {
            "best_score": round(float(best_score or 0.0), 4),
            "second_best_score": round(float(second_best_score or 0.0), 4),
            "score_gap": round(float(score_gap or 0.0), 4),
            "applied_threshold": round(float(threshold or 0.0), 4),
            "applied_min_gap": round(float(min_gap or 0.0), 4),
            "matched_view": matched_view,
            "recognition_rejection_reason": None,
        }
        logger.info(f"Best: {best_name}={best_score:.4f}, 2nd={second_best_score:.4f}, gap={score_gap:.4f}, threshold={threshold:.4f}, min_gap={min_gap:.4f}")
        
        # Match only if BOTH conditions are met:
        # 1. Score >= threshold (absolute quality check)
        # 2. Gap >= min_gap (relative distinctiveness check - not confused with another person)
        if best_score >= threshold and score_gap >= min_gap and best_match is not None:
            logger.info(f"✓ RECOGNIZED: {best_name} (score={best_score:.4f}, gap={score_gap:.4f}, matched_view={matched_view})")
            return best_match, self.profiles[best_match]['name'], best_score, recognition_debug
        
        if best_score < threshold:
            logger.warning(f"✗ NOT RECOGNIZED: Best score {best_score:.4f} < threshold {threshold:.4f}")
            recognition_debug["recognition_rejection_reason"] = "threshold"
        elif score_gap < min_gap:
            logger.warning(f"✗ NOT RECOGNIZED: Score gap {score_gap:.4f} < min_gap {min_gap:.4f} (ambiguous: {best_name}={best_score:.4f} vs 2nd={second_best_score:.4f})")
            recognition_debug["recognition_rejection_reason"] = "gap"
        else:
            recognition_debug["recognition_rejection_reason"] = "unknown"
        
        return None, 'Unknown', best_score, recognition_debug
    
    def match_detections_to_tracks(self, detections, frame):
        """
        Assign detections to existing tracks using spatial proximity + Kalman predictions.
        Optimized for 40-50 simultaneous faces in classroom setting.
        Implements strict one-to-one matching to prevent face merging.
        Returns:
            List of (track_id, detection_bbox, recognition_result)
        """
        matches = []
        unmatched_detections = set(range(len(detections)))
        unmatched_tracks = set(self.trackers.keys())
        
        # Step 1: Build cost matrix for all possible assignments
        # Lower cost = better match
        track_ids = list(unmatched_tracks)
        
        assignment_costs = {}  # (track_id, det_idx) -> cost
        
        for track_id in track_ids:
            tracker = self.trackers[track_id]
            predicted_bbox = tracker.predict()
            if predicted_bbox is None:
                continue
            
            px1, py1, pw, ph = predicted_bbox
            px2, py2 = px1 + pw, py1 + ph
            pcx, pcy = px1 + pw/2, py1 + ph/2
            
            for det_idx in unmatched_detections:
                x, y, w, h = detections[det_idx]
                dx2, dy2 = x + w, y + h
                dcx, dcy = x + w/2, y + h/2
                
                # Compute IoU
                ix1, iy1 = max(px1, x), max(py1, y)
                ix2, iy2 = min(px2, dx2), min(py2, dy2)
                
                iou = 0
                if ix2 > ix1 and iy2 > iy1:
                    inter = (ix2 - ix1) * (iy2 - iy1)
                    area1 = pw * ph
                    area2 = w * h
                    union = area1 + area2 - inter
                    iou = inter / union if union > 0 else 0
                
                # Compute normalized center distance
                dist = np.sqrt((pcx - dcx)**2 + (pcy - dcy)**2)
                max_dist = max(pw, ph) * self.distance_threshold_ratio
                dist_norm = dist / max_dist if max_dist > 0 else 999
                
                # Cost: penalize low IoU heavily, then use distance
                # Only consider if either IoU is good OR distance is very small
                if iou > self.iou_threshold or dist_norm < 0.5:
                    cost = (1.0 - iou) * 10 + dist_norm
                    assignment_costs[(track_id, det_idx)] = cost
        
        # Step 2: Greedy one-to-one assignment (best match first)
        while assignment_costs and unmatched_detections and unmatched_tracks:
            # Find best assignment
            best_assignment = min(assignment_costs.items(), key=lambda x: x[1])
            (track_id, det_idx), cost = best_assignment
            
            # Only accept if cost is reasonable
            if cost < 20:  # Threshold for acceptance
                tracker = self.trackers[track_id]
                tracker.update(detections[det_idx])
                matches.append((
                    track_id, detections[det_idx],
                    self.recognize_face(frame, detections[det_idx])[:3]
                ))
                
                # Remove this assignment and all conflicts
                unmatched_detections.discard(det_idx)
                unmatched_tracks.discard(track_id)
                
                # Remove all assignments involving this track or detection
                keys_to_remove = [
                    key for key in assignment_costs.keys()
                    if key[0] == track_id or key[1] == det_idx
                ]
                for key in keys_to_remove:
                    del assignment_costs[key]
            else:
                # Cost too high, remove this assignment
                del assignment_costs[best_assignment[0]]
        
        # Step 3: Mark unmatched tracks as missing (for timeout)
        for track_id in unmatched_tracks:
            self.trackers[track_id].last_seen += 1
        
        # Step 4: Create new tracks for unmatched detections
        for det_idx in unmatched_detections:
            bbox = detections[det_idx]
            track_id = self.next_track_id
            self.next_track_id += 1
            self.trackers[track_id] = KalmanBBoxTracker(bbox, track_id)
            matches.append((
                track_id, bbox,
                self.recognize_face(frame, bbox)[:3]
            ))
        
        # Step 5: Clean up old tracks (not seen in 30 frames)
        tracks_to_remove = [
            tid for tid, tracker in self.trackers.items()
            if tracker.last_seen > 30
        ]
        for tid in tracks_to_remove:
            del self.trackers[tid]
        
        return matches
    
    def process_frame(self, frame):
        """
        Main processing pipeline: Detection → Tracking → Recognition → Emotion
        Returns:
            {
                'detections': [{'track_id', 'bbox', 'name', 'confidence', 'emotion', 'trajectory'}],
                'timestamp': float,
                'frame_count': int
            }
        """
        with self.runtime_lock:
            self.detect_count += 1
            frame_h, frame_w = frame.shape[:2]
            
            detections = self.detect_faces(frame)
            if not detections:
                return {
                    'detections': [],
                    'timestamp': time.time(),
                    'frame_count': self.detect_count
                }
            
            matches = self.match_detections_to_tracks(detections, frame)
            
            results = []
            for track_id, bbox, (profile_id, name, confidence) in matches:
                if self.emotion_detector is not None:
                    emotion_data = self.emotion_detector.detect_emotion(frame, bbox)
                else:
                    emotion_data = {
                        'emotion': 'Neutral',
                        'confidence': 0.0,
                        'intensity': 'low',
                        'all_scores': {}
                    }
                trajectory = self.trackers[track_id].get_trajectory()
                
                results.append({
                    'track_id': track_id,
                    'bbox': bbox,
                    'name': name,
                    'confidence': float(confidence),
                    'profile_id': profile_id,
                    'emotion': emotion_data.get('emotion', 'Neutral'),
                    'emotion_confidence': emotion_data.get('confidence', 0.0),
                    'emotion_intensity': emotion_data.get('intensity', 'low'),
                    'all_emotions': emotion_data.get('all_scores', {}),
                    'trajectory': trajectory[-10:]  # Last 10 positions
                })
            
            return {
                'detections': results,
                'timestamp': time.time(),
                'frame_count': self.detect_count
            }
    
    def register_face_from_detection(self, profile_id, name, frame, bbox, face_obj=None):
        """
        Register face for new profile by extracting and storing embedding.
        Args:
            profile_id: Unique identifier
            name: Person's name
            frame: BGR image
            bbox: (x, y, w, h) bounding box
            face_obj: Optional InsightFace face object with precomputed embedding
        Returns:
            bool: Success status
        """
        embedding = None

        if face_obj is not None:
            try:
                embedding = face_obj.embedding.astype(np.float32)
                logger.info(f"Using pre-computed registration embedding for {name}: norm={np.linalg.norm(embedding):.4f}")
            except Exception as e:
                logger.warning(f"Failed to use pre-computed registration embedding for {name}: {e}")

        if embedding is None:
            embedding = self.recognizer.get_embedding(frame, bbox)

        if embedding is None:
            logger.warning(f"Failed to extract embedding for {name}")
            return False
        
        self.profiles[profile_id] = {
            'name': name,
            'embedding': embedding,
            'registered_at': time.time()
        }
        
        logger.info(f"✓ Registered {name} (profile_id={profile_id})")
        return True
    
    def register_face_from_array(self, profile_id, name, embedding):
        """
        Register face using pre-computed embedding (batch import).
        Useful for importing embeddings from external sources.
        """
        if not isinstance(embedding, np.ndarray) or embedding.shape != (512,):
            logger.error(f"Invalid embedding shape: {embedding.shape}")
            return False
        
        self.profiles[profile_id] = {
            'name': name,
            'embedding': embedding.astype(np.float32),
            'view_embeddings': {},
            'registered_at': time.time()
        }
        
        logger.info(f"✓ Registered {name} via import (profile_id={profile_id})")
        return True

    def register_face_views_from_arrays(self, profile_id, name, view_embeddings, primary_embedding):
        if not isinstance(primary_embedding, np.ndarray) or primary_embedding.shape != (512,):
            logger.error(f"Invalid primary embedding shape: {getattr(primary_embedding, 'shape', None)}")
            return False

        normalized_views = {}
        for view_name, payload in (view_embeddings or {}).items():
            embedding = payload.get("embedding")
            if not isinstance(embedding, np.ndarray) or embedding.shape != (512,):
                logger.error(f"Invalid {view_name} embedding shape: {getattr(embedding, 'shape', None)}")
                return False
            normalized_views[view_name] = {
                "embedding": embedding.astype(np.float32),
                "captured_at": payload.get("captured_at"),
                "image_path": payload.get("image_path"),
            }

        self.profiles[profile_id] = {
            'name': name,
            'embedding': primary_embedding.astype(np.float32),
            'view_embeddings': normalized_views,
            'registered_at': time.time()
        }
        logger.info(f"✓ Registered {name} with {len(normalized_views)} view embeddings (profile_id={profile_id})")
        return True
    
    def get_profiles_summary(self):
        """Return summary of all registered profiles"""
        return {
            'count': len(self.profiles),
            'profiles': [
                {
                    'profile_id': pid,
                    'name': p['name'],
                    'registered_at': p.get('registered_at')
                }
                for pid, p in self.profiles.items()
            ]
        }
