# Emotion Analytics Technical Implementation Guide

## 1. Improved Emotion Confidence Calculation

### Current Problem
The emotion detector uses static 0.3 confidence for heuristics fallback. This doesn't reflect actual detection quality.

### Improved Implementation

```python
# In emotion_detector.py - Enhanced detect_emotion_with_confidence function

def detect_emotion_with_confidence(face_region, method='auto'):
    """
    Detect emotion with improved confidence calculation
    
    Returns:
        dict: {
            'emotion': str,
            'confidence': float (0-1),
            'intensity': str ('low', 'medium', 'high'),
            'is_stable': bool,
            'method': str,
            'face_quality': float
        }
    """
    
    emotion = 'Neutral'
    confidence = 0.0
    method_used = 'none'
    face_quality = 0.0
    
    try:
        # Calculate face quality score (0-1)
        face_quality = calculate_face_quality(face_region)
        
        # Try DeepFace first (most reliable)
        if method in ['auto', 'deepface']:
            try:
                result = DeepFace.analyze(
                    face_region,
                    actions=['emotion'],
                    enforce_detection=False,
                    silent=True
                )
                
                emotions_dict = result[0]['emotion']
                emotion = max(emotions_dict, key=emotions_dict.get)
                raw_confidence = emotions_dict[emotion] / 100  # Convert to 0-1
                
                # Weight confidence by face quality
                confidence = raw_confidence * (0.7 + 0.3 * face_quality)
                method_used = 'deepface'
                
            except Exception as e:
                logger.debug(f"DeepFace failed: {e}")
        
        # Try Keras if DeepFace unavailable
        if method in ['auto', 'keras'] and confidence < 0.5:
            try:
                emotion, raw_confidence = detect_emotion_keras(face_region)
                confidence = raw_confidence * (0.6 + 0.4 * face_quality)
                method_used = 'keras'
            except Exception as e:
                logger.debug(f"Keras failed: {e}")
        
        # Improved heuristics as fallback
        if confidence < 0.4:
            emotion, heuristic_conf = detect_emotion_heuristics(face_region)
            # Heuristics confidence based on face quality
            confidence = heuristic_conf * face_quality
            method_used = 'heuristics'
    
    except Exception as e:
        logger.error(f"Emotion detection failed: {e}")
        confidence = 0.1  # Very low confidence for failed detections
    
    # Determine intensity level
    intensity = 'low' if confidence < 0.33 else ('medium' if confidence < 0.66 else 'high')
    
    return {
        'emotion': emotion,
        'confidence': round(confidence, 3),
        'intensity': intensity,
        'method': method_used,
        'face_quality': round(face_quality, 3),
        'is_stable': False  # Will be set by stability checker
    }


def calculate_face_quality(face_region):
    """
    Calculate face quality score (0-1) based on:
    - Face size (larger = better detection)
    - Image brightness (not too dark/bright)
    - Contrast (affects feature clarity)
    
    Returns: float (0-1)
    """
    try:
        gray = cv2.cvtColor(face_region, cv2.COLOR_BGR2GRAY)
        
        # Face size quality
        height, width = face_region.shape[:2]
        face_size_quality = min(1.0, (height * width) / (256 * 256))
        
        # Brightness quality (optimal: 100-150)
        brightness = np.mean(gray)
        if brightness < 50 or brightness > 200:
            brightness_quality = 0.5
        elif brightness < 80 or brightness > 170:
            brightness_quality = 0.75
        else:
            brightness_quality = 1.0
        
        # Contrast quality (standard dev of pixel values)
        contrast = np.std(gray)
        contrast_quality = min(1.0, contrast / 50)  # Good contrast ~50
        
        # Weighted combination
        quality = (face_size_quality * 0.3 + 
                  brightness_quality * 0.35 + 
                  contrast_quality * 0.35)
        
        return quality
    except:
        return 0.5  # Default middle quality


def detect_emotion_heuristics(face_region):
    """
    Improved heuristics using brightness/contrast analysis
    Returns: (emotion, confidence)
    """
    try:
        gray = cv2.cvtColor(face_region, cv2.COLOR_BGR2GRAY)
        brightness = np.mean(gray)
        contrast = np.std(gray)
        
        # Emotion mapping based on visual features
        if contrast > 40:  # High contrast often indicates strong expression
            if brightness > 120:
                # Light + high contrast → possibly happy
                emotion = 'Happy'
                confidence = 0.4
            else:
                # Dark + high contrast → possibly angry/fearful
                emotion = random.choice(['Angry', 'Fearful'])
                confidence = 0.35
        else:
            # Low contrast, neutral lighting → likely neutral
            emotion = 'Neutral'
            confidence = 0.5 - abs(brightness - 127) / 254
        
        return emotion, confidence
    except:
        return 'Neutral', 0.3
```

### Database Schema Updates

```sql
-- Add new columns to attendance_log for enhanced emotion data
ALTER TABLE attendance_log ADD COLUMN emotion_intensity TEXT DEFAULT 'low';
ALTER TABLE attendance_log ADD COLUMN emotion_method TEXT DEFAULT 'heuristics';
ALTER TABLE attendance_log ADD COLUMN face_quality_score REAL DEFAULT 0.0;
ALTER TABLE attendance_log ADD COLUMN is_emotion_stable INTEGER DEFAULT 0;

-- Create index for analytics queries
CREATE INDEX idx_emotion_timestamp ON attendance_log(timestamp, emotion);
CREATE INDEX idx_emotion_location ON attendance_log(location, emotion);
```

## 2. Emotion Stability Detection

### Track Consistent Emotions Across Frames

```python
class EmotionTracker:
    """Track emotion stability across frames"""
    
    def __init__(self, person_id, window_size=5):
        self.person_id = person_id
        self.emotion_history = deque(maxlen=window_size)
        self.confidence_history = deque(maxlen=window_size)
        self.window_size = window_size
    
    def add_detection(self, emotion, confidence):
        """Add new emotion detection"""
        self.emotion_history.append(emotion)
        self.confidence_history.append(confidence)
    
    def is_stable(self):
        """Check if emotion is stable across frames"""
        if len(self.emotion_history) < 3:
            return False
        
        # Count occurrences of most common emotion
        emotion_counts = {}
        for emotion in self.emotion_history:
            emotion_counts[emotion] = emotion_counts.get(emotion, 0) + 1
        
        max_count = max(emotion_counts.values())
        stability_score = max_count / len(self.emotion_history)
        
        return stability_score > 0.6  # Stable if 60%+ same emotion
    
    def get_stability_score(self):
        """Get stability score (0-1)"""
        if len(self.emotion_history) < 2:
            return 0.0
        
        emotion_counts = {}
        for emotion in self.emotion_history:
            emotion_counts[emotion] = emotion_counts.get(emotion, 0) + 1
        
        max_count = max(emotion_counts.values())
        return max_count / len(self.emotion_history)
    
    def get_average_confidence(self):
        """Get average confidence across recent frames"""
        if not self.confidence_history:
            return 0.0
        return np.mean(list(self.confidence_history))
```

## 3. Analytics API Endpoints

### Create analytic_endpoints.py

```python
from flask import Blueprint, jsonify, request
from datetime import datetime, timedelta
import json
from database import get_db

analytics_bp = Blueprint('analytics', __name__, url_prefix='/api/analytics')


@analytics_bp.route('/emotions/distribution', methods=['GET'])
def emotion_distribution():
    """Get emotion distribution for specified period"""
    hours = request.args.get('hours', 24, type=int)
    location = request.args.get('location', None)
    
    conn = get_db()
    cursor = conn.cursor()
    
    time_filter = f"WHERE timestamp > datetime('now', '-{hours} hours')"
    location_filter = f"AND location = '{location}'" if location else ""
    
    query = f"""
    SELECT emotion, COUNT(*) as count, AVG(emotion_confidence) as avg_confidence
    FROM attendance_log
    {time_filter} {location_filter}
    AND emotion IS NOT NULL
    GROUP BY emotion
    ORDER BY count DESC
    """
    
    cursor.execute(query)
    results = cursor.fetchall()
    
    data = {
        'period_hours': hours,
        'location': location or 'all',
        'emotions': []
    }
    
    total = sum(r[1] for r in results)
    for emotion, count, avg_conf in results:
        data['emotions'].append({
            'emotion': emotion,
            'count': count,
            'percentage': round(count / total * 100, 1) if total > 0 else 0,
            'avg_confidence': round(avg_conf, 3)
        })
    
    conn.close()
    return jsonify(data)


@analytics_bp.route('/emotions/timeline', methods=['GET'])
def emotion_timeline():
    """Get emotion distribution over time"""
    hours = request.args.get('hours', 24, type=int)
    interval = request.args.get('interval', 'hourly')  # hourly, daily
    location = request.args.get('location', None)
    
    conn = get_db()
    cursor = conn.cursor()
    
    if interval == 'hourly':
        time_format = "%Y-%m-%d %H:00:00"
        group_by = "strftime('%Y-%m-%d %H:00:00', timestamp)"
    else:
        time_format = "%Y-%m-%d"
        group_by = "date(timestamp)"
    
    location_filter = f"AND location = '{location}'" if location else ""
    
    query = f"""
    SELECT 
        {group_by} as time_bucket,
        emotion,
        COUNT(*) as count,
        AVG(emotion_confidence) as avg_confidence,
        MAX(emotion_confidence) as max_confidence
    FROM attendance_log
    WHERE timestamp > datetime('now', '-{hours} hours')
    AND emotion IS NOT NULL
    {location_filter}
    GROUP BY time_bucket, emotion
    ORDER BY time_bucket DESC, count DESC
    """
    
    cursor.execute(query)
    results = cursor.fetchall()
    
    # Organize by time bucket
    timeline = {}
    for time_bucket, emotion, count, avg_conf, max_conf in results:
        if time_bucket not in timeline:
            timeline[time_bucket] = []
        timeline[time_bucket].append({
            'emotion': emotion,
            'count': count,
            'avg_confidence': round(avg_conf, 3),
            'max_confidence': round(max_conf, 3)
        })
    
    conn.close()
    return jsonify({'timeline': timeline, 'interval': interval})


@analytics_bp.route('/emotions/by-person', methods=['GET'])
def emotion_by_person():
    """Get emotion distribution per person"""
    hours = request.args.get('hours', 24, type=int)
    location = request.args.get('location', None)
    
    conn = get_db()
    cursor = conn.cursor()
    
    location_filter = f"AND location = '{location}'" if location else ""
    
    query = f"""
    SELECT 
        name,
        emotion,
        COUNT(*) as count,
        AVG(emotion_confidence) as avg_confidence,
        MAX(emotion_confidence) as max_confidence
    FROM attendance_log
    WHERE timestamp > datetime('now', '-{hours} hours')
    AND emotion IS NOT NULL
    {location_filter}
    GROUP BY name, emotion
    ORDER BY name, count DESC
    """
    
    cursor.execute(query)
    results = cursor.fetchall()
    
    # Organize by person
    by_person = {}
    for name, emotion, count, avg_conf, max_conf in results:
        if name not in by_person:
            by_person[name] = []
        by_person[name].append({
            'emotion': emotion,
            'count': count,
            'avg_confidence': round(avg_conf, 3),
            'max_confidence': round(max_conf, 3)
        })
    
    conn.close()
    return jsonify({'by_person': by_person})


@analytics_bp.route('/emotions/by-location', methods=['GET'])
def emotion_by_location():
    """Get emotion distribution per location/camera"""
    hours = request.args.get('hours', 24, type=int)
    
    conn = get_db()
    cursor = conn.cursor()
    
    query = f"""
    SELECT 
        location,
        emotion,
        COUNT(*) as count,
        AVG(emotion_confidence) as avg_confidence,
        COUNT(DISTINCT name) as unique_people
    FROM attendance_log
    WHERE timestamp > datetime('now', '-{hours} hours')
    AND emotion IS NOT NULL
    GROUP BY location, emotion
    ORDER BY location, count DESC
    """
    
    cursor.execute(query)
    results = cursor.fetchall()
    
    # Organize by location
    by_location = {}
    for location, emotion, count, avg_conf, unique_people in results:
        if location not in by_location:
            by_location[location] = {'emotions': [], 'total_people': set()}
        by_location[location]['emotions'].append({
            'emotion': emotion,
            'count': count,
            'avg_confidence': round(avg_conf, 3)
        })
    
    # Convert sets to counts
    for location in by_location:
        by_location[location]['unique_people_count'] = len(by_location[location]['total_people'])
        del by_location[location]['total_people']
    
    conn.close()
    return jsonify({'by_location': by_location})


@analytics_bp.route('/emotions/summary', methods=['GET'])
def emotion_summary():
    """Get overall emotion summary with recommendations"""
    hours = request.args.get('hours', 24, type=int)
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get distribution
    query = f"""
    SELECT emotion, COUNT(*) as count, AVG(emotion_confidence) as avg_confidence
    FROM attendance_log
    WHERE timestamp > datetime('now', '-{hours} hours')
    AND emotion IS NOT NULL
    GROUP BY emotion
    ORDER BY count DESC
    """
    
    cursor.execute(query)
    emotions = cursor.fetchall()
    
    total_records = sum(e[1] for e in emotions)
    
    # Calculate metrics
    summary = {
        'period_hours': hours,
        'total_detections': total_records,
        'average_confidence': 0.0,
        'positive_emotions': {},  # Happy, Surprised
        'negative_emotions': {},  # Angry, Sad, Fearful, Disgusted
        'neutral_emotions': {},
        'recommendations': []
    }
    
    positive_emotes = ['Happy', 'Surprised']
    negative_emotes = ['Angry', 'Sad', 'Fearful', 'Disgusted']
    
    total_conf = 0
    positive_count = 0
    negative_count = 0
    
    for emotion, count, avg_conf in emotions:
        if emotion in positive_emotes:
            summary['positive_emotions'][emotion] = {'count': count, 'percentage': 0}
            positive_count += count
        elif emotion in negative_emotes:
            summary['negative_emotions'][emotion] = {'count': count, 'percentage': 0}
            negative_count += count
        else:
            summary['neutral_emotions'][emotion] = {'count': count, 'percentage': 0}
        
        total_conf += avg_conf * count
    
    # Calculate percentages
    for category in [summary['positive_emotions'], summary['negative_emotions'], summary['neutral_emotions']]:
        for emotion in category:
            category[emotion]['percentage'] = round(category[emotion]['count'] / total_records * 100, 1)
    
    summary['average_confidence'] = round(total_conf / total_records, 3) if total_records > 0 else 0
    
    # Generate recommendations
    positive_pct = (positive_count / total_records * 100) if total_records > 0 else 0
    negative_pct = (negative_count / total_records * 100) if total_records > 0 else 0
    
    if positive_pct > 70:
        summary['recommendations'].append("✓ Great! Overall positive mood detected. Team appears engaged and happy.")
    elif positive_pct > 50:
        summary['recommendations'].append("→ Moderate positivity. Consider team building activities to boost mood.")
    else:
        summary['recommendations'].append("⚠ Low positive emotions detected. Consider checking in with team, assess work environment.")
    
    if negative_pct > 30:
        summary['recommendations'].append("⚠ Significant negative emotions detected. Recommend wellness check-in or break opportunities.")
    
    if summary['average_confidence'] < 0.4:
        summary['recommendations'].append("⚠ Low detection confidence. Consider improving lighting or camera placement for better accuracy.")
    
    conn.close()
    return jsonify(summary)
```

## 4. Integration with server.py

```python
# Add to server.py imports
from analytic_endpoints import analytics_bp

# Register blueprint
app.register_blueprint(analytics_bp)
```

## Implementation Checklist

- [ ] Add new columns to attendance_log table
- [ ] Create new analytics_endpoints.py file
- [ ] Update emotion_detector.py with improved confidence calculation
- [ ] Implement EmotionTracker class in emotion_detector.py
- [ ] Register analytics blueprint in server.py
- [ ] Test all API endpoints
- [ ] Create frontend dashboard to visualize analytics
- [ ] Add data validation and error handling
- [ ] Performance test with high volume data

## Expected Outcomes

After implementation:
1. ✅ Emotion confidence values show meaningful variance (0.3-0.9 instead of stuck at 0.3)
2. ✅ Emotion stability detection helps identify genuine emotional states
3. ✅ Analytics API provides rich, queryable emotion data
4. ✅ Recommendations help guide action based on patterns
5. ✅ Location-based and person-based analytics enable targeted interventions

---

