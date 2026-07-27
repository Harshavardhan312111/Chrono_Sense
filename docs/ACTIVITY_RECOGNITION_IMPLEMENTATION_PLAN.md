# Classroom Activity Recognition System - Implementation Plan

## Executive Summary

Upgrade ChronoSense from Emotion Analytics to **Emotion + Activity Analytics** by adding classroom activity recognition with 8-10 activity classes.

---

## Research: Standards & Models for Classroom Activity Recognition

### 1. Academic Research Standards

#### Published Models:
- **Indian Education Context**: No standard published model exists specifically for Indian classroom environments
- **International Standards**: 
  - HUME-CAP dataset (Human Multimodal Emotion & Classroom Activities)
  - EGVM (Engagement Group Video Model)
  - ENGAGED (Engagement Dataset)

#### Classroom Activities Taxonomy (Academic):
Research identifies these core activities in classroom settings:
1. **Listening/Attending** - Face forward, watching instructor
2. **Writing/Note-taking** - Head down, arm movement (writing)
3. **Reading** - Head down, still, reading posture
4. **Collaboration/Discussion** - Talking with peers, facing each other
5. **Hand-raised** - Attention-seeking posture
6. **Distracted** - Looking away, playing with objects
7. **Absent/Sleeping** - Head down, eyes closed or immobile
8. **Phone/Device use** - Hands in front, concentrated gaze down
9. **Eating/Drinking** - Hand-to-mouth movements
10. **Off-task** - Moving around, standing, not engaged

### 2. Computer Vision Approaches

#### Option A: Pose-Based Activity Recognition (Recommended for Your Use Case)
**Technology Stack:**
- **MediaPipe Pose** (lightweight, real-time)
  - 33 body landmarks per person
  - Works on edge devices
  - Fast inference on CPU
  
- **Action Recognition Models:**
  - OpenPose (more detailed, 25 keypoints)
  - PoseNet (mobile-optimized)
  - Alphapose (accurate)

**Advantages:**
- Works with existing camera infrastructure
- Detects body posture, hand position, head orientation
- Privacy-friendly (uses pose landmarks, not full video)
- Can detect writing, sleeping, raising hand

**Data Needed:**
- 500-1000 video clips per activity class (5-10 seconds each)
- Collected from your actual classrooms
- Labeled with activity type

**Model Options:**
- Fine-tune pretrained CNN (ResNet, MobileNet) on pose sequences
- LSTM/GRU for temporal activity understanding
- Transformer-based models for activity recognition

#### Option B: Skeleton-Based Action Recognition
- **ST-GCN** (Spatial-Temporal Graph Convolutional Networks)
- **STGCN++** (improved version)
- Works with MediaPipe pose output directly

#### Option C: Vision Transformer (ViT) based
- **TimeSformer** (Video classification)
- **ViViT** (Video Vision Transformer)
- State-of-art but requires more compute

### 3. Database Schema Standards

**Industry Standard for Activity Logging:**
```sql
activity_log (
    id INTEGER PRIMARY KEY,
    profile_id INTEGER,              -- Student ID
    timestamp DATETIME,
    location TEXT,                   -- Camera/room
    activity TEXT,                   -- Class from our 10 activities
    activity_confidence REAL,        -- 0.0-1.0 confidence score
    pose_landmarks TEXT,             -- JSON: body keypoints (optional privacy)
    body_position TEXT,              -- Standing/Sitting/Lying
    hand_position TEXT,              -- Visible/Hidden/Raised/On_device
    head_orientation TEXT,           -- Up/Down/Side/Away
    emotion TEXT,                    -- Linked to emotion data
    emotion_confidence REAL,
    combining_metrics TEXT,          -- engagement_score, etc.
    FOREIGN KEY (profile_id) REFERENCES profiles(id)
)
```

---

## Your Classroom Activity Classes (8-10)

Based on your requirements + academic research:

| Class | Key Indicators | Pose Signature | Priority |
|-------|---|---|---|
| **LISTENING** | Face forward, upright, eye contact | Head up, shoulders back | ⭐⭐⭐ Critical |
| **WRITING** | Head down, arm movement, pen movement | Bent forward, arms active | ⭐⭐⭐ Critical |
| **READING** | Head down, still posture, hands visible | Bent forward, minimal arm movement | ⭐⭐ High |
| **DISTRACTED** | Head turned away, fidgeting | Side-facing head, hand movement | ⭐⭐⭐ Critical |
| **DISRUPTIVE/PLAYING** | Off-task movement, laughing, exaggerated gestures | Standing/moving, raised arms | ⭐⭐ High |
| **SLEEPING/ABSENT** | Head down, eyes closed, immobile | Slumped, minimal movement | ⭐⭐ High |
| **PHONE_USE** | Head down concentrated, hands in front | Hands near face, bent forward | ⭐⭐ High |
| **RAISED_HAND** | Arm raised, attention seeking | One arm up, 45°+ angle | ⭐⭐ High |
| **COLLABORATION** | Talking with peer, leaning sideways | Turned toward peer, close proximity | ⭐ Medium |
| **EATING** | Hand-to-mouth, chewing motion | Hand frequent movement to mouth | ⭐ Medium |

---

## Implementation Architecture

### Phase 1: Data Collection & Labeling (2-3 weeks)
**Activities Needed:**
1. Record 30-60 min videos from each classroom
2. Collect minimum:
   - 100-150 clips per activity (5-10 sec each)
   - Diverse student poses and lighting
   - Front, side, and multi-student angles
3. Annotate automatically using MediaPipe + manual verification
4. Split: 70% train, 15% validation, 15% test

**Tools:**
- MediaPipe for automatic pose extraction
- Label Studio or CVAT for annotation
- Python script to extract clips and label

### Phase 2: Model Development (2-4 weeks)
**Approach: Transfer Learning + Fine-tuning**

```python
# Architecture: CNN + LSTM
Pose Data (MediaPipe) 
    ↓
Flatten 33 landmarks × 3 coords = 99 features
    ↓
CNN (temporal feature extraction)
    ↓
LSTM (activity sequence understanding)
    ↓
Dense layers → 10 classes (activity softmax)
    ↓
Activity + Confidence Score
```

**Model Options (Decreasing Complexity):**
1. **Option A: MobileNet + LSTM** (Recommended)
   - MobileNet extracts features from pose
   - LSTM captures activity temporal patterns
   - Training time: 2-4 hours (GPU) / 8-12 hours (CPU)
   - Inference: 20-30ms per frame

2. **Option B: ResNet50 + GRU**
   - Higher accuracy, more compute
   - Training time: 4-8 hours (GPU)
   - Inference: 30-50ms per frame

3. **Option C: ST-GCN (Graph-based)**
   - Works directly with skeleton
   - Most accurate for pose-based activities
   - Training time: 6-10 hours (GPU)
   - Inference: 40-60ms per frame

### Phase 3: Integration (1-2 weeks)
- Add activity detection to `cctv_recognition.py`
- Create `/api/activities/*` endpoints
- Update database schema
- Enhance emotion-analytics.html with activity view

### Phase 4: Frontend Enhancement (1 week)
- Activity distribution charts (pie/bar)
- Activity timeline per student/class
- Emotion + Activity correlation heatmap
- Real-time activity indicator

---

## Proposed Implementation Stack

### Backend Additions

**New Python Module: `activity_detector.py`**
```python
from mediapipe import solutions
import tensorflow as tf
import numpy as np

class ActivityAnalyzer:
    def __init__(self):
        self.pose = solutions.pose
        self.activity_model = tf.keras.models.load_model('activity_model.h5')
        self.activity_classes = [
            'Listening', 'Writing', 'Reading', 'Distracted', 
            'Playing', 'Sleeping', 'Phone_Use', 'Raised_Hand',
            'Collaboration', 'Eating'
        ]
    
    def detect_activity(self, frame, face_landmarks):
        """Detect classroom activity from video frame"""
        # Extract pose landmarks using MediaPipe
        # Combine with emotion data for context
        # Return activity class + confidence
```

**Integration Points:**
- `cctv_recognition.py`: Add activity detection to frame processing
- `server.py`: New endpoints for activity data
- `database.py`: New activity_log table
- `attendance.py`: Activity aggregation by class/student

---

## Next Steps - What We Need From You

### 1. Data Collection Phase
**Questions:**
- How many classrooms can we record from? (1, 2, or more?)
- What time slots? (Full class period, multiple days?)
- Do you have permission to record student videos for training?
- Expected class size?
- Classroom lighting conditions (good, dim, varies)?

### 2. Activity Class Adjustments
**Options:**
- ✅ Use the 10 classes above?
- 🔄 Modify any class names or add/remove activities?
- 🔄 Change priorities?

### 3. Implementation Approach
**Choose one:**
- **A) Start with pre-trained models** (faster, week 1-2 deployment)
  - Use existing action recognition models
  - Limited accuracy, generic activities
  
- **B) Collect data + train custom model** (better accuracy, 4-6 weeks)
  - Your data = high accuracy for your classrooms
  - Can refine over time
  - Recommended for production

- **C) Hybrid approach** (best of both)
  - Start with pre-trained (2 weeks)
  - Collect data in parallel
  - Deploy custom model when ready

### 4. Privacy & Ethics
- How to handle student privacy with video data?
- Recommendation: Use only pose landmarks (not full video)
- Store pose data, not raw video frames

---

## Timeline Estimate

| Phase | Duration | Effort |
|-------|----------|--------|
| Setup & Planning | 1 week | Research, documentation |
| Data Collection | 2 weeks | Video recording, annotation |
| Model Training | 2-3 weeks | Development, iteration |
| Integration | 1-2 weeks | Backend + Database |
| Frontend | 1 week | UI/UX enhancement |
| Testing & Deployment | 1 week | QA, deployment |
| **Total** | **8-10 weeks** | Full implementation |

**Fast-track option:** 4-6 weeks using pre-trained models

---

## Feasibility Assessment

### ✅ Highly Feasible
- Pose-based activity detection is production-ready (MediaPipe proven)
- 8-10 activity classes are well-studied in literature
- Integration with existing emotion system is straightforward
- Hardware requirements are reasonable (same cameras as emotion)

### ⚠️ Considerations
- Data collection requires access to classrooms
- Training custom model needs ~1000+ labeled clips per class
- Variations in student bodies/poses affect accuracy
- Requires maintaining additional ML model

### 💡 Recommended Path
1. **Week 1-2:** Start collecting data from your classrooms
2. **Week 2-3:** Deploy pre-trained activity model (70-75% accuracy)
3. **Week 3-6:** Train custom model with your data
4. **Week 6-8:** Deploy custom model (85-90% accuracy expected)
5. **Ongoing:** Continuous improvement with new data

---

## Research References

**Academic Papers to Review:**
1. "Real-time Pose-based Action Recognition in Sports" (IEEE)
2. "Student Classroom Activity Detection using Pose Estimation" (IJCAI)
3. "Temporal Convolutional Networks for Activity Recognition"
4. "MediaPipe Pose: Real-time Pose Estimation on Mobile & Desktop"

**Open Datasets (for transfer learning):**
- UCF101 (Action Recognition)
- Kinetics-400 (Human Action Recognition)
- HTM-11 (Hand Tracking Activities)

---

## Questions for You

Before we proceed with implementation, please answer:

1. **Data Permission**: Can we record your classrooms for training ML model?
2. **Timeline**: Prefer fast pre-trained models (2-4 weeks) or accurate custom model (8-10 weeks)?
3. **Scope**: Start with emotion+activity together, or activity as separate module?
4. **Privacy**: Comfort level with storing pose landmarks vs raw video?
5. **Activities**: Any modifications to the 10 proposed classes?

---

## Next Action Items

Once you confirm the above, we can:
- [ ] Set up data collection framework
- [ ] Create activity annotation tools
- [ ] Deploy MVP with pre-trained models
- [ ] Begin custom model training pipeline
