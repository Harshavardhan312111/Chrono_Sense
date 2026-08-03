"""
Configurable emotion sensing pipeline with pluggable backends, face quality
assessment, temporal smoothing, and education-oriented state mapping.
"""

from __future__ import annotations

import logging
import math
import os
import sys
import threading
from abc import ABC, abstractmethod
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import timedelta
from typing import Deque, Dict, Optional

import cv2
import numpy as np

BACKEND_ROOT = os.path.dirname(__file__)
version_specific_vendor = os.path.join(
    BACKEND_ROOT,
    "vendor-py313" if sys.version_info[:2] == (3, 13) else "vendor-py",
)
fallback_vendor = os.path.join(BACKEND_ROOT, "vendor-py")
for candidate in (version_specific_vendor, fallback_vendor):
    if os.path.isdir(candidate) and candidate not in sys.path:
        sys.path.append(candidate)

try:
    from emotion_detector import FERPlusEmotionDetector, EMOTION_LABELS
except ImportError:
    from backend.emotion_detector import FERPlusEmotionDetector, EMOTION_LABELS

try:
    from emotiefflib.facial_analysis import EmotiEffLibRecognizer
except ImportError:
    EmotiEffLibRecognizer = None

try:
    from mma_dfer_runtime import MMADFERCheckpointRuntime
except ImportError:
    try:
        from backend.mma_dfer_runtime import MMADFERCheckpointRuntime
    except ImportError:
        MMADFERCheckpointRuntime = None

try:
    from time_utils import app_now
except ImportError:
    from backend.time_utils import app_now

logger = logging.getLogger(__name__)

DEFAULT_RAW_LABELS = ["Happy", "Neutral", "Sad", "Angry", "Fear", "Surprise", "Disgust", "Contempt"]
DERIVED_EMOTIONS = [
    "Interested",
    "Focused",
    "Curious",
    "Excited",
    "Calm",
    "Confident",
    "Confused",
    "Frustrated",
    "Distracted",
    "Bored",
    "Disengaged",
    "Tired",
    "Sleepy",
    "Stressed",
    "Overwhelmed",
    "Motivated",
    "Passive",
    "Active",
    "Relaxed",
    "Negative",
    "Positive",
]
EDUCATIONAL_STATES = [
    "Highly Engaged",
    "Engaged",
    "Focused",
    "Learning Well",
    "Curious",
    "Thinking Deeply",
    "Problem Solving",
    "Asking Questions",
    "Reflective",
    "Collaborative",
    "Confused",
    "Frustrated",
    "Distracted",
    "Passive",
    "Bored",
    "Disengaged",
    "Waiting",
    "Inactive",
    "Fatigued",
    "Overloaded",
]
CLASSROOM_STATES = [
    "Highly Engaged Classroom",
    "Active Learning",
    "Collaborative Classroom",
    "Positive Classroom",
    "Focused Classroom",
    "Curious Classroom",
    "Calm Classroom",
    "Energetic Classroom",
    "Distracted Classroom",
    "Confused Classroom",
    "Frustrated Classroom",
    "Low Energy Classroom",
    "Restless Classroom",
    "Stressful Classroom",
]
LOW_SIGNAL_EMOTION = "LowSignal"
PIPELINE_VERSION = "emotion-modernization-v1"
RAW_DIAGNOSTIC_CONFIDENCE_FLOOR = 0.18


@dataclass
class EmotionBackendResult:
    raw_emotion: str
    raw_confidence: float
    raw_scores: Dict[str, float]
    model_name: str
    model_version: str
    backend_name: str
    fallback_backend_used: bool = False
    error: Optional[str] = None


class EmotionBackend(ABC):
    name = "base"
    model_name = "base"
    model_version = "v1"

    def __init__(self):
        self.model_loaded = False
        self.last_error = None

    @abstractmethod
    def predict(self, face_roi, track_key=None, timestamp=None) -> EmotionBackendResult:
        raise NotImplementedError


class NullEmotionBackend(EmotionBackend):
    name = "disabled"
    model_name = "disabled"
    model_version = "v1"

    def predict(self, face_roi, track_key=None, timestamp=None) -> EmotionBackendResult:
        return EmotionBackendResult(
            raw_emotion=LOW_SIGNAL_EMOTION,
            raw_confidence=0.0,
            raw_scores={},
            model_name=self.model_name,
            model_version=self.model_version,
            backend_name=self.name,
            fallback_backend_used=False,
        )


class FERPlusEmotionBackend(EmotionBackend):
    name = "ferplus"
    model_name = "emotion-ferplus-8.onnx"
    model_version = "ferplus-8"

    def __init__(self, allow_heuristic_fallback=False):
        super().__init__()
        self.detector = FERPlusEmotionDetector()
        self.allow_heuristic_fallback = allow_heuristic_fallback
        self.model_loaded = bool(getattr(self.detector, "model_loaded", False))
        self.last_error = getattr(self.detector, "last_error", None)
        if self.model_loaded:
            logger.info(
                "Emotion backend ready: FERPlus loaded "
                f"(backend={self.name}, model={self.model_name}, version={self.model_version})"
            )
        else:
            logger.warning(
                "Emotion backend not fully loaded: FERPlus unavailable "
                f"(backend={self.name}, model={self.model_name}, version={self.model_version}, "
                f"heuristic_fallback={'on' if self.allow_heuristic_fallback else 'off'}, error={self.last_error})"
            )

    def predict(self, face_roi, track_key=None, timestamp=None) -> EmotionBackendResult:
        h, w = face_roi.shape[:2]
        result = self.detector.detect_emotion(face_roi, (0, 0, w, h))
        using_fallback = not self.model_loaded
        if using_fallback and not self.allow_heuristic_fallback:
            return EmotionBackendResult(
                raw_emotion=LOW_SIGNAL_EMOTION,
                raw_confidence=0.0,
                raw_scores={},
                model_name=self.model_name,
                model_version=self.model_version,
                backend_name=self.name,
                fallback_backend_used=True,
                error=self.last_error or "ferplus_backend_unavailable",
            )
        return EmotionBackendResult(
            raw_emotion=result.get("emotion") or "Neutral",
            raw_confidence=float(result.get("confidence") or 0.0),
            raw_scores={k: float(v or 0.0) for k, v in (result.get("all_scores") or {}).items()},
            model_name=self.model_name,
            model_version=self.model_version,
            backend_name=self.name,
            fallback_backend_used=using_fallback,
            error=self.last_error if using_fallback else None,
        )


class MMADFEREmotionBackend(EmotionBackend):
    name = "mma_dfer"
    model_name = "mma-dfer.onnx"
    model_version = "mma-dfer-v1"

    def __init__(self):
        super().__init__()
        self._lock = threading.Lock()
        self.net = None
        self.runtime = None
        self.runtime_mode = None
        self.input_size = int(os.getenv("CHRONOSENSE_MMA_DFER_INPUT_SIZE", "224"))
        self.labels = DEFAULT_RAW_LABELS
        self._load_model()

    def _load_model(self):
        model_path = os.getenv(
            "CHRONOSENSE_MMA_DFER_MODEL_PATH",
            os.path.join(os.path.dirname(__file__), "models", "mma-dfer.onnx"),
        )
        checkpoint_dir = os.path.join(os.path.dirname(__file__), "models", "mma-dfer")
        checkpoint_path = os.getenv(
            "CHRONOSENSE_MMA_DFER_CHECKPOINT_PATH",
            os.path.join(checkpoint_dir, "fold1_112.pth"),
        )
        try:
            if os.path.exists(model_path):
                if os.path.isdir(model_path):
                    checkpoint_candidates = sorted(
                        name for name in os.listdir(model_path)
                        if name.endswith((".pth", ".pt", ".ckpt"))
                    )
                    self.last_error = (
                        "MMA-DFER path points to a checkpoint directory, but the current runtime "
                        "expects an ONNX file."
                    )
                    self.model_loaded = False
                    logger.warning(
                        "Emotion backend not loaded: MMA-DFER checkpoint directory detected but unsupported by "
                        "the current ONNX runtime "
                        f"(backend={self.name}, model={self.model_name}, version={self.model_version}, "
                        f"path={model_path}, checkpoints={checkpoint_candidates})"
                    )
                    return
                self.net = cv2.dnn.readNetFromONNX(model_path)
                self.model_loaded = True
                self.runtime_mode = "onnx"
                self.last_error = None
                logger.info(
                    "Emotion backend ready: MMA-DFER loaded "
                    f"(backend={self.name}, model={self.model_name}, version={self.model_version}, path={model_path})"
                )
            elif os.path.exists(checkpoint_path):
                if MMADFERCheckpointRuntime is None:
                    self.last_error = "mma_dfer_runtime_unavailable"
                    self.model_loaded = False
                    logger.warning(
                        "Emotion backend not loaded: MMA-DFER checkpoint is installed but the PyTorch runtime "
                        "wrapper is unavailable "
                        f"(backend={self.name}, checkpoint={checkpoint_path})"
                    )
                    return
                self.runtime = MMADFERCheckpointRuntime(checkpoint_path=checkpoint_path, image_size=112, sequence_length=16)
                self.model_loaded = True
                self.runtime_mode = "checkpoint"
                self.model_name = os.path.basename(checkpoint_path)
                self.model_version = "mma-dfer-dfew-fold1-112"
                self.last_error = None
                logger.info(
                    "Emotion backend ready: MMA-DFER checkpoint loaded "
                    f"(backend={self.name}, model={self.model_name}, version={self.model_version}, path={checkpoint_path})"
                )
            else:
                checkpoint_candidates = []
                if os.path.isdir(checkpoint_dir):
                    checkpoint_candidates = sorted(
                        name for name in os.listdir(checkpoint_dir)
                        if name.endswith((".pth", ".pt", ".ckpt"))
                    )
                if checkpoint_candidates:
                    self.last_error = (
                        f"MMA-DFER checkpoint(s) found in {checkpoint_dir}, but no ONNX file was found at {model_path}"
                    )
                    self.model_loaded = False
                    logger.warning(
                        "Emotion backend not loaded: MMA-DFER checkpoints are installed but the current runtime "
                        "only supports ONNX loading "
                        f"(backend={self.name}, model={self.model_name}, version={self.model_version}, "
                        f"expected_onnx={model_path}, checkpoints={checkpoint_candidates})"
                    )
                    return
                self.last_error = f"MMA-DFER model not found at {model_path}"
                self.model_loaded = False
                logger.warning(
                    "Emotion backend not loaded: MMA-DFER missing "
                    f"(backend={self.name}, model={self.model_name}, version={self.model_version}, path={model_path})"
                )
        except Exception as exc:
            self.model_loaded = False
            self.last_error = str(exc)
            logger.warning(f"Could not load MMA-DFER model: {exc}")

    def predict(self, face_roi, track_key=None, timestamp=None) -> EmotionBackendResult:
        if not self.model_loaded:
            return EmotionBackendResult(
                raw_emotion=LOW_SIGNAL_EMOTION,
                raw_confidence=0.0,
                raw_scores={},
                model_name=self.model_name,
                model_version=self.model_version,
                backend_name=self.name,
                error=self.last_error or "mma_dfer_model_unavailable",
            )
        if self.runtime_mode == "checkpoint" and self.runtime is not None:
            result = self.runtime.infer(face_roi, track_key=track_key)
            return EmotionBackendResult(
                raw_emotion=result.get("emotion") or LOW_SIGNAL_EMOTION,
                raw_confidence=float(result.get("confidence") or 0.0),
                raw_scores={k: float(v or 0.0) for k, v in (result.get("all_scores") or {}).items()},
                model_name=self.model_name,
                model_version=self.model_version,
                backend_name=self.name,
            )
        if self.net is None:
            return EmotionBackendResult(
                raw_emotion=LOW_SIGNAL_EMOTION,
                raw_confidence=0.0,
                raw_scores={},
                model_name=self.model_name,
                model_version=self.model_version,
                backend_name=self.name,
                error=self.last_error or "mma_dfer_model_unavailable",
            )

        try:
            rgb = cv2.cvtColor(face_roi, cv2.COLOR_BGR2RGB)
            resized = cv2.resize(rgb, (self.input_size, self.input_size))
            blob = cv2.dnn.blobFromImage(
                resized,
                scalefactor=1.0 / 255.0,
                size=(self.input_size, self.input_size),
                mean=(0.485, 0.456, 0.406),
                swapRB=False,
                crop=False,
            )
            with self._lock:
                self.net.setInput(blob)
                output = self.net.forward()
            logits = output[0] if len(output.shape) > 1 else output
            scores = _softmax(logits)
            usable_scores = {
                label: float(round(scores[index], 4))
                for index, label in enumerate(self.labels[: len(scores)])
            }
            best_idx = int(np.argmax(scores))
            return EmotionBackendResult(
                raw_emotion=self.labels[best_idx],
                raw_confidence=float(scores[best_idx]),
                raw_scores=usable_scores,
                model_name=self.model_name,
                model_version=self.model_version,
                backend_name=self.name,
            )
        except Exception as exc:
            logger.debug(f"MMA-DFER inference failed: {exc}")
            return EmotionBackendResult(
                raw_emotion=LOW_SIGNAL_EMOTION,
                raw_confidence=0.0,
                raw_scores={},
                model_name=self.model_name,
                model_version=self.model_version,
                backend_name=self.name,
                error=str(exc),
            )


class EmotiEffLibEmotionBackend(EmotionBackend):
    name = "emotiefflib"
    model_version = "emotiefflib-1.1.1"

    def __init__(self):
        super().__init__()
        self._lock = threading.Lock()
        self.engine = (os.getenv("CHRONOSENSE_EMOTIEFFLIB_ENGINE", "onnx") or "onnx").strip().lower()
        self.requested_model_name = (
            os.getenv("CHRONOSENSE_EMOTIEFFLIB_MODEL_NAME", "enet_b2_8")
            or "enet_b2_8"
        ).strip()
        self.device = (os.getenv("CHRONOSENSE_EMOTIEFFLIB_DEVICE", "cpu") or "cpu").strip().lower()
        self.recognizer = None
        self.model_name = self.requested_model_name
        self._label_map = {
            "Anger": "Angry",
            "Disgust": "Disgust",
            "Fear": "Fear",
            "Happiness": "Happy",
            "Neutral": "Neutral",
            "Sadness": "Sad",
            "Surprise": "Surprise",
            "Contempt": "Contempt",
        }
        self._load_model()

    def _load_model(self):
        if EmotiEffLibRecognizer is None:
            self.model_loaded = False
            self.last_error = "emotiefflib_not_installed"
            logger.warning(
                "Emotion backend not loaded: EmotiEffLib package missing "
                f"(backend={self.name}, model={self.model_name}, version={self.model_version})"
            )
            return
        try:
            self.recognizer = EmotiEffLibRecognizer(
                engine=self.engine,
                model_name=self.requested_model_name,
                device=self.device,
            )
            self.model_loaded = True
            self.last_error = None
            logger.info(
                "Emotion backend ready: EmotiEffLib loaded "
                f"(backend={self.name}, model={self.model_name}, version={self.model_version}, "
                f"engine={self.engine}, device={self.device})"
            )
        except Exception as exc:
            self.recognizer = None
            self.model_loaded = False
            self.last_error = str(exc)
            logger.warning(f"Could not load EmotiEffLib model: {exc}")

    def predict(self, face_roi, track_key=None, timestamp=None) -> EmotionBackendResult:
        if not self.model_loaded or self.recognizer is None:
            return EmotionBackendResult(
                raw_emotion=LOW_SIGNAL_EMOTION,
                raw_confidence=0.0,
                raw_scores={},
                model_name=self.model_name,
                model_version=self.model_version,
                backend_name=self.name,
                error=self.last_error or "emotiefflib_model_unavailable",
            )

        try:
            rgb_face = cv2.cvtColor(face_roi, cv2.COLOR_BGR2RGB)
            with self._lock:
                predicted_labels, score_batches = self.recognizer.predict_emotions(rgb_face, logits=False)

            if not predicted_labels:
                raise RuntimeError("emotiefflib_empty_prediction")

            labels = list(predicted_labels)
            scores = np.asarray(score_batches[0] if len(score_batches) else [], dtype=np.float32)
            emotion_keys = [
                self._label_map.get(self.recognizer.idx_to_emotion_class[idx], self.recognizer.idx_to_emotion_class[idx])
                for idx in sorted(self.recognizer.idx_to_emotion_class.keys())
            ]
            raw_scores = {
                emotion_keys[idx]: float(round(scores[idx], 4))
                for idx in range(min(len(emotion_keys), len(scores)))
            }
            predicted_label = self._label_map.get(labels[0], labels[0])
            confidence = raw_scores.get(predicted_label, float(scores.max()) if scores.size else 0.0)
            return EmotionBackendResult(
                raw_emotion=predicted_label or LOW_SIGNAL_EMOTION,
                raw_confidence=float(confidence or 0.0),
                raw_scores=raw_scores,
                model_name=self.model_name,
                model_version=self.model_version,
                backend_name=self.name,
            )
        except Exception as exc:
            logger.debug(f"EmotiEffLib inference failed: {exc}")
            return EmotionBackendResult(
                raw_emotion=LOW_SIGNAL_EMOTION,
                raw_confidence=0.0,
                raw_scores={},
                model_name=self.model_name,
                model_version=self.model_version,
                backend_name=self.name,
                error=str(exc),
            )


def _softmax(values):
    exp_values = np.exp(values - np.max(values))
    return exp_values / np.sum(exp_values)


class FaceQualityAssessor:
    def __init__(self):
        self.min_face_size = max(32, int(os.getenv("CHRONOSENSE_MIN_EMOTION_FACE_SIZE", "64")))

    def assess(self, face_roi, landmarks=None, detection_confidence=1.0):
        height, width = face_roi.shape[:2]
        gray = cv2.cvtColor(face_roi, cv2.COLOR_BGR2GRAY) if len(face_roi.shape) == 3 else face_roi
        face_size = int(min(height, width))
        blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        brightness = float(np.mean(gray) / 255.0)
        pose = self._estimate_pose(landmarks, width, height)
        occlusion_score = self._estimate_occlusion(gray)
        size_score = min(1.0, face_size / float(max(self.min_face_size * 2, 1)))
        blur_norm = min(1.0, blur_score / 180.0)
        brightness_score = max(0.0, 1.0 - abs(brightness - 0.55) / 0.55)
        pose_penalty = min(1.0, (abs(pose["yaw"]) + abs(pose["pitch"]) + abs(pose["roll"])) / 120.0)
        quality_score = (
            (size_score * 0.26)
            + (blur_norm * 0.22)
            + (brightness_score * 0.16)
            + (max(0.0, 1.0 - occlusion_score) * 0.18)
            + (max(0.0, 1.0 - pose_penalty) * 0.12)
            + (max(0.0, min(1.0, float(detection_confidence or 0.0))) * 0.06)
        )
        quality_score = round(max(0.0, min(1.0, quality_score)), 4)
        return {
            "face_size": face_size,
            "blur_score": round(blur_score, 4),
            "brightness": round(brightness, 4),
            "yaw": round(pose["yaw"], 4),
            "pitch": round(pose["pitch"], 4),
            "roll": round(pose["roll"], 4),
            "occlusion_score": round(occlusion_score, 4),
            "detection_confidence": round(float(detection_confidence or 0.0), 4),
            "quality_score": quality_score,
            "low_quality": quality_score < float(os.getenv("CHRONOSENSE_EMOTION_QUALITY_THRESHOLD", "0.40")),
        }

    def _estimate_pose(self, landmarks, width, height):
        if landmarks is None or len(landmarks) < 68:
            return {"yaw": 0.0, "pitch": 0.0, "roll": 0.0}
        try:
            points = np.asarray(landmarks)
            left_eye = np.mean(points[36:42], axis=0)
            right_eye = np.mean(points[42:48], axis=0)
            nose = points[30]
            mouth_left = points[48]
            mouth_right = points[54]
            eye_dx = max(1e-6, right_eye[0] - left_eye[0])
            eye_dy = right_eye[1] - left_eye[1]
            eye_center_x = (left_eye[0] + right_eye[0]) / 2.0
            yaw = ((nose[0] - eye_center_x) / max(width, 1)) * 90.0
            pitch = (((mouth_left[1] + mouth_right[1]) / 2.0) - nose[1]) / max(height, 1) * 90.0
            roll = math.degrees(math.atan2(eye_dy, eye_dx))
            return {"yaw": yaw, "pitch": pitch, "roll": roll}
        except Exception:
            return {"yaw": 0.0, "pitch": 0.0, "roll": 0.0}

    @staticmethod
    def _estimate_occlusion(gray_face):
        height, width = gray_face.shape[:2]
        center_patch = gray_face[height // 4 : (3 * height) // 4, width // 4 : (3 * width) // 4]
        if center_patch.size == 0:
            return 1.0
        contrast = np.std(center_patch) / 64.0
        shadow_penalty = 1.0 - min(1.0, np.mean(center_patch) / 255.0)
        return max(0.0, min(1.0, (shadow_penalty * 0.6) + (max(0.0, 1.0 - contrast) * 0.4)))


class TemporalEmotionSmoother:
    def __init__(self):
        self.max_frames = max(5, int(os.getenv("CHRONOSENSE_EMOTION_WINDOW_FRAMES", "15")))
        self.window_seconds = max(1.0, float(os.getenv("CHRONOSENSE_EMOTION_WINDOW_SECONDS", "2.5")))
        self.alpha = max(0.05, min(0.95, float(os.getenv("CHRONOSENSE_EMOTION_SMOOTHING_ALPHA", "0.35"))))
        self.histories: Dict[str, Deque[Dict]] = defaultdict(lambda: deque(maxlen=self.max_frames))

    def update(self, track_key, observation, timestamp=None):
        timestamp = timestamp or app_now()
        history = self.histories[track_key]
        history.append({"timestamp": timestamp, **observation})
        cutoff = timestamp - timedelta(seconds=self.window_seconds)
        while history and history[0]["timestamp"] < cutoff:
            history.popleft()
        return self._summarize(history)

    def _summarize(self, history):
        if not history:
            return {
                "smoothed_emotion": LOW_SIGNAL_EMOTION,
                "smoothed_confidence": 0.0,
                "smoothed_scores": {},
                "temporal_consensus": 0.0,
                "history_size": 0,
                "low_signal_state": True,
            }

        weighted_scores = Counter()
        label_weights = Counter()
        history_size = len(history)
        decay = 1.0
        for item in reversed(history):
            quality = float(item.get("quality_score") or 0.0)
            confidence = float(item.get("raw_confidence") or 0.0)
            weight = max(0.02, ((confidence * 0.65) + (quality * 0.35)) * decay)
            label = item.get("raw_emotion") or LOW_SIGNAL_EMOTION
            if label != LOW_SIGNAL_EMOTION:
                label_weights[label] += weight
            for emotion_name, score in (item.get("raw_scores") or {}).items():
                weighted_scores[emotion_name] += float(score or 0.0) * weight
            decay *= (1.0 - self.alpha)

        if not label_weights:
            return {
                "smoothed_emotion": LOW_SIGNAL_EMOTION,
                "smoothed_confidence": 0.0,
                "smoothed_scores": dict(weighted_scores),
                "temporal_consensus": 0.0,
                "history_size": history_size,
                "low_signal_state": True,
            }

        total_weight = sum(label_weights.values()) or 1.0
        leading_emotion, leading_weight = label_weights.most_common(1)[0]
        temporal_consensus = leading_weight / total_weight
        smoothed_scores = {
            key: round(value / total_weight, 4)
            for key, value in weighted_scores.items()
        }
        smoothed_confidence = smoothed_scores.get(
            leading_emotion,
            round(sum(float(item.get("raw_confidence") or 0.0) for item in history) / history_size, 4),
        )

        low_signal = temporal_consensus < float(os.getenv("CHRONOSENSE_EMOTION_CONSENSUS_THRESHOLD", "0.25"))
        if leading_emotion == "Neutral":
            low_quality_floor = float(os.getenv("CHRONOSENSE_EMOTION_QUALITY_THRESHOLD", "0.40"))
            low_quality_count = sum(
                1 for item in history if float(item.get("quality_score") or 0.0) < low_quality_floor
            )
            if low_quality_count >= max(2, history_size // 2):
                smoothed_confidence = smoothed_confidence * 0.65
            if history_size < 3 and smoothed_confidence < 0.35:
                low_signal = True

        return {
            "smoothed_emotion": LOW_SIGNAL_EMOTION if low_signal else leading_emotion,
            "smoothed_confidence": round(max(0.0, min(1.0, smoothed_confidence)), 4),
            "smoothed_scores": smoothed_scores,
            "temporal_consensus": round(temporal_consensus, 4),
            "history_size": history_size,
            "low_signal_state": low_signal,
        }


class EmotionStateMapper:
    def map_states(self, raw_emotion, smoothed_emotion, smoothed_confidence, quality, attention=None, activity=None):
        quality_score = float((quality or {}).get("quality_score") or 0.0)
        attention_score = self._derive_attention(smoothed_emotion, quality_score, activity)
        engagement_score = self._derive_engagement(smoothed_emotion, smoothed_confidence, quality_score, attention_score)
        derived = self._derive_emotion(raw_emotion, smoothed_emotion, quality_score, attention_score, activity)
        educational = self._educational_state(derived, smoothed_emotion, engagement_score, attention_score)
        classroom = self._classroom_state(derived, educational, engagement_score)
        return {
            "derived_emotion": derived,
            "educational_state": educational,
            "classroom_state": classroom,
            "attention": round(attention_score, 4),
            "engagement": round(engagement_score, 4),
        }

    @staticmethod
    def _derive_attention(smoothed_emotion, quality_score, activity):
        if smoothed_emotion in {"Focused", "Curious"}:
            base = 0.75
        elif smoothed_emotion in {"Happy", "Surprise"}:
            base = 0.68
        elif smoothed_emotion in {"Sad", "Disgust"}:
            base = 0.4
        elif smoothed_emotion == LOW_SIGNAL_EMOTION:
            base = 0.3
        else:
            base = 0.58
        if activity in {"Talking", "Playing", "Fighting"}:
            base -= 0.15
        return max(0.0, min(1.0, (base * 0.7) + (quality_score * 0.3)))

    @staticmethod
    def _derive_engagement(smoothed_emotion, smoothed_confidence, quality_score, attention_score):
        emotion_weight = {
            "Happy": 0.82,
            "Surprise": 0.74,
            "Neutral": 0.62,
            "Sad": 0.34,
            "Angry": 0.28,
            "Fear": 0.32,
            "Disgust": 0.3,
            LOW_SIGNAL_EMOTION: 0.2,
        }.get(smoothed_emotion, 0.55)
        return max(
            0.0,
            min(
                1.0,
                (emotion_weight * 0.4)
                + (float(smoothed_confidence or 0.0) * 0.2)
                + (quality_score * 0.15)
                + (attention_score * 0.25),
            ),
        )

    @staticmethod
    def _derive_emotion(raw_emotion, smoothed_emotion, quality_score, attention_score, activity):
        if smoothed_emotion == LOW_SIGNAL_EMOTION:
            return "Passive" if quality_score < 0.35 else "Distracted"
        if smoothed_emotion == "Happy":
            return "Interested" if attention_score > 0.7 else "Positive"
        if smoothed_emotion == "Surprise":
            return "Curious"
        if smoothed_emotion == "Neutral":
            if activity in {"Writing", "Reading", "Listening"}:
                return "Focused"
            return "Calm" if quality_score > 0.6 else "Passive"
        if smoothed_emotion == "Sad":
            return "Bored" if attention_score < 0.45 else "Tired"
        if smoothed_emotion == "Angry":
            return "Frustrated"
        if smoothed_emotion == "Fear":
            return "Stressed"
        if smoothed_emotion == "Disgust":
            return "Negative"
        if raw_emotion == "Contempt":
            return "Disengaged"
        return "Focused"

    @staticmethod
    def _educational_state(derived, smoothed_emotion, engagement_score, attention_score):
        if derived in {"Interested", "Curious"} and engagement_score > 0.72:
            return "Highly Engaged"
        if derived in {"Focused", "Calm"} and attention_score > 0.62:
            return "Focused"
        if derived in {"Positive", "Motivated"} and engagement_score > 0.6:
            return "Learning Well"
        if derived == "Frustrated":
            return "Frustrated"
        if derived in {"Bored", "Passive"}:
            return "Bored" if smoothed_emotion == "Sad" else "Passive"
        if derived in {"Distracted", "Negative"}:
            return "Distracted"
        if derived in {"Tired", "Sleepy"}:
            return "Fatigued"
        if smoothed_emotion == LOW_SIGNAL_EMOTION:
            return "Waiting"
        return "Engaged" if engagement_score >= 0.5 else "Inactive"

    @staticmethod
    def _classroom_state(derived, educational_state, engagement_score):
        if educational_state == "Highly Engaged":
            return "Highly Engaged Classroom"
        if educational_state in {"Focused", "Learning Well"}:
            return "Focused Classroom"
        if educational_state == "Frustrated":
            return "Frustrated Classroom"
        if educational_state in {"Distracted", "Passive"}:
            return "Distracted Classroom"
        if educational_state in {"Fatigued", "Inactive"}:
            return "Low Energy Classroom"
        if derived in {"Curious", "Interested"}:
            return "Curious Classroom"
        return "Positive Classroom" if engagement_score >= 0.55 else "Calm Classroom"


class EmotionPipeline:
    def __init__(self):
        self.allow_heuristic_fallback = str(os.getenv("CHRONOSENSE_EMERGENCY_HEURISTIC_EMOTION", "false")).lower() == "true"
        preferred_backend = (os.getenv("CHRONOSENSE_EMOTION_BACKEND", "auto") or "auto").strip().lower()
        self.quality_assessor = FaceQualityAssessor()
        self.smoother = TemporalEmotionSmoother()
        self.mapper = EmotionStateMapper()
        self.backend = self._build_backend(preferred_backend)
        self.analytics_quality_threshold = float(os.getenv("CHRONOSENSE_EMOTION_ANALYTICS_QUALITY_THRESHOLD", "0.32"))
        logger.info(
            "Emotion pipeline selected backend: "
            f"{self.describe_backend()} "
            f"(preferred={preferred_backend}, analytics_quality_threshold={self.analytics_quality_threshold}, "
            f"heuristic_fallback={'on' if self.allow_heuristic_fallback else 'off'})"
        )

    def _build_backend(self, preferred_backend):
        if preferred_backend == "disabled":
            return NullEmotionBackend()

        ordered = []
        if preferred_backend in {"auto", "emotiefflib", "emotieff"}:
            ordered.append(EmotiEffLibEmotionBackend())
        if preferred_backend in {"auto", "mma_dfer", "mmadfer"}:
            ordered.append(MMADFEREmotionBackend())
        if preferred_backend in {"auto", "ferplus"}:
            ordered.append(FERPlusEmotionBackend(allow_heuristic_fallback=self.allow_heuristic_fallback))

        for backend in ordered:
            if backend.model_loaded or isinstance(backend, FERPlusEmotionBackend) and self.allow_heuristic_fallback:
                return backend
        return ordered[-1] if ordered else NullEmotionBackend()

    def describe_backend(self):
        backend = self.backend
        loaded_state = "loaded" if getattr(backend, "model_loaded", False) else "not_loaded"
        return (
            f"backend={getattr(backend, 'name', 'unknown')}, "
            f"model={getattr(backend, 'model_name', 'unknown')}, "
            f"version={getattr(backend, 'model_version', 'unknown')}, "
            f"state={loaded_state}"
        )

    def analyze_face(
        self,
        face_roi,
        landmarks=None,
        detection_confidence=1.0,
        track_key=None,
        timestamp=None,
        activity=None,
        activity_confidence=0.0,
    ):
        timestamp = timestamp or app_now()
        quality = self.quality_assessor.assess(face_roi, landmarks=landmarks, detection_confidence=detection_confidence)
        backend_result = self.backend.predict(face_roi, track_key=track_key, timestamp=timestamp)
        observation = {
            "raw_emotion": backend_result.raw_emotion,
            "raw_confidence": backend_result.raw_confidence,
            "raw_scores": backend_result.raw_scores,
            "quality_score": quality["quality_score"],
        }
        smoothed = self.smoother.update(track_key or f"anonymous:{id(face_roi)}", observation, timestamp=timestamp)
        states = self.mapper.map_states(
            raw_emotion=backend_result.raw_emotion,
            smoothed_emotion=smoothed["smoothed_emotion"],
            smoothed_confidence=smoothed["smoothed_confidence"],
            quality=quality,
            activity=activity,
        )

        raw_diagnostic_floor = float(
            os.getenv("CHRONOSENSE_EMOTION_RAW_DIAGNOSTIC_FLOOR", str(RAW_DIAGNOSTIC_CONFIDENCE_FLOOR))
        )
        if smoothed["smoothed_emotion"] != LOW_SIGNAL_EMOTION:
            legacy_emotion = smoothed["smoothed_emotion"]
            legacy_confidence = smoothed["smoothed_confidence"]
            legacy_emotion_source = "smoothed"
        elif backend_result.raw_confidence >= raw_diagnostic_floor:
            legacy_emotion = backend_result.raw_emotion
            legacy_confidence = backend_result.raw_confidence
            legacy_emotion_source = "raw_diagnostic"
        else:
            legacy_emotion = LOW_SIGNAL_EMOTION
            legacy_confidence = smoothed["smoothed_confidence"]
            legacy_emotion_source = "low_signal"
        all_scores = backend_result.raw_scores or smoothed.get("smoothed_scores") or {}
        intensity = self._confidence_to_intensity(legacy_confidence)
        fallback_active = bool(backend_result.fallback_backend_used or not getattr(self.backend, "model_loaded", False))

        return {
            "emotion": legacy_emotion or LOW_SIGNAL_EMOTION,
            "emotion_confidence": round(float(legacy_confidence or 0.0), 4),
            "emotion_intensity": intensity,
            "all_emotions": all_scores,
            "raw_emotion": backend_result.raw_emotion,
            "raw_confidence": round(float(backend_result.raw_confidence or 0.0), 4),
            "raw_scores": all_scores,
            "smoothed_emotion": smoothed["smoothed_emotion"],
            "smoothed_confidence": round(float(smoothed["smoothed_confidence"] or 0.0), 4),
            "smoothed_scores": smoothed.get("smoothed_scores") or {},
            "temporal_consensus": smoothed.get("temporal_consensus", 0.0),
            "history_size": smoothed.get("history_size", 0),
            "low_signal_state": bool(smoothed.get("low_signal_state")),
            "derived_emotion": states["derived_emotion"],
            "educational_state": states["educational_state"],
            "classroom_state": states["classroom_state"],
            "attention": states["attention"],
            "engagement": states["engagement"],
            "emotion_model": backend_result.model_name,
            "emotion_model_version": backend_result.model_version,
            "emotion_provider": backend_result.backend_name,
            "legacy_emotion_source": legacy_emotion_source,
            "reasoning_model": None,
            "reasoning": None,
            "pipeline_version": PIPELINE_VERSION,
            "below_analytics_threshold": quality["quality_score"] < self.analytics_quality_threshold,
            "fallback_backend_used": fallback_active,
            "emotion_available": backend_result.raw_emotion != LOW_SIGNAL_EMOTION or backend_result.raw_confidence > 0.0,
            "emotion_unavailable_reason": backend_result.error,
            "activity": activity,
            "activity_confidence": round(float(activity_confidence or 0.0), 4),
            **quality,
        }

    @staticmethod
    def _confidence_to_intensity(confidence):
        if confidence >= 0.7:
            return "high"
        if confidence >= 0.4:
            return "medium"
        return "low"
