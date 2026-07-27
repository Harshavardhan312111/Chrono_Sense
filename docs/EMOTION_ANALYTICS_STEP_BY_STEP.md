# Emotion Analytics: Step-by-Step Implementation Guide

## Quick Start (2-3 hours to MVP)

This guide provides exact steps to improve emotion detection with minimal disruption.

### Step 1: Database Updates (15 minutes)

```bash
cd /private/tmp/ChronoSenseWeb-clean/backend

# Create migration script
cat > update_emotion_schema.py << 'EOF'
import sqlite3

conn = sqlite3.connect('profiles.db')
cursor = conn.cursor()

# Check if columns already exist
cursor.execute("PRAGMA table_info(attendance_log)")
columns = [col[1] for col in cursor.fetchall()]

if 'emotion_intensity' not in columns:
    cursor.execute('ALTER TABLE attendance_log ADD COLUMN emotion_intensity TEXT DEFAULT "low"')
    print("Added emotion_intensity column")

if 'emotion_method' not in columns:
    cursor.execute('ALTER TABLE attendance_log ADD COLUMN emotion_method TEXT DEFAULT "heuristics"')
    print("Added emotion_method column")

if 'face_quality_score' not in columns:
    cursor.execute('ALTER TABLE attendance_log ADD COLUMN face_quality_score REAL DEFAULT 0.0')
    print("Added face_quality_score column")

if 'is_emotion_stable' not in columns:
    cursor.execute('ALTER TABLE attendance_log ADD COLUMN is_emotion_stable INTEGER DEFAULT 0')
    print("Added is_emotion_stable column")

# Create indexes for analytics
try:
    cursor.execute('CREATE INDEX idx_emotion_timestamp ON attendance_log(timestamp, emotion)')
    print("Created emotion_timestamp index")
except sqlite3.OperationalError:
    print("emotion_timestamp index already exists")

try:
    cursor.execute('CREATE INDEX idx_emotion_location ON attendance_log(location, emotion)')
    print("Created emotion_location index")
except sqlite3.OperationalError:
    print("emotion_location index already exists")

conn.commit()
conn.close()
print("Database schema updated successfully!")
EOF

# Run the migration
python update_emotion_schema.py
```

### Step 2: Update emotion_detector.py (30 minutes)

**Location**: `backend/emotion_detector.py`

Add this improved confidence calculation function:

```python
# Add these imports at the top
import numpy as np
from collections import deque

# Add this class after imports
class EmotionTracker:
    """Track emotion stability across frames for a person"""
    
    def __init__(self, person_id, window_size=5):
        self.person_id = person_id
        self.emotion_history = deque(maxlen=window_size)
        self.confidence_history = deque(maxlen=window_size)
    
    def add_detection(self, emotion, confidence):
        """Add new emotion detection"""
        self.emotion_history.append(emotion)
        self.confidence_history.append(confidence)
    
    def is_stable(self):
        """Check if emotion is stable (same emotion in 60%+ of frames)"""
        if len(self.emotion_history) < 2:
            return False
        
        emotion_counts = {}
        for emotion in self.emotion_history:
            emotion_counts[emotion] = emotion_counts.get(emotion, 0) + 1
        
        max_count = max(emotion_counts.values()) if emotion_counts else 0
        stability = max_count / len(self.emotion_history) if self.emotion_history else 0
        return stability > 0.6
    
    def get_stability_score(self):
        """Get stability score (0-1)"""
        if not self.emotion_history:
            return 0.0
        emotion_counts = {}
        for emotion in self.emotion_history:
            emotion_counts[emotion] = emotion_counts.get(emotion, 0) + 1
        max_count = max(emotion_counts.values())
        return max_count / len(self.emotion_history)


# Add this helper function
def calculate_face_quality(face_region):
    """
    Calculate face quality score (0-1) based on:
    - Face size
    - Image brightness
    - Contrast
    
    Returns: float (0-1)
    """
    try:
        import cv2
        gray = cv2.cvtColor(face_region, cv2.COLOR_BGR2GRAY)
        
        # Face size quality (larger is better)
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
        
        # Contrast quality
        contrast = np.std(gray)
        contrast_quality = min(1.0, contrast / 50)
        
        # Weighted combination
        quality = (face_size_quality * 0.3 + 
                  brightness_quality * 0.35 + 
                  contrast_quality * 0.35)
        
        return max(0.0, min(1.0, quality))
    except Exception as e:
        logger.debug(f"Face quality calculation failed: {e}")
        return 0.5


# Replace or enhance the detect_emotion_with_confidence function
def detect_emotion_with_confidence_improved(face_region, method='auto'):
    """
    Detect emotion with improved confidence calculation
    
    Returns: {
        'emotion': str,
        'confidence': float (0-1),
        'intensity': str ('low', 'medium', 'high'),
        'method': str ('deepface', 'keras', 'heuristics')
    }
    """
    emotion = 'Neutral'
    confidence = 0.0
    method_used = 'heuristics'
    
    try:
        import cv2
        
        # Calculate face quality score
        face_quality = calculate_face_quality(face_region)
        
        # Try DeepFace first
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
                raw_confidence = emotions_dict[emotion] / 100
                
                # Weight by face quality
                confidence = raw_confidence * (0.7 + 0.3 * face_quality)
                method_used = 'deepface'
                
            except Exception as e:
                logger.debug(f"DeepFace failed: {e}")
        
        # Try Keras if confidence low
        if confidence < 0.5 and method in ['auto', 'keras']:
            try:
                emotion_keras, raw_confidence = detect_emotion_keras(face_region)
                confidence = raw_confidence * (0.6 + 0.4 * face_quality)
                emotion = emotion_keras
                method_used = 'keras'
            except Exception as e:
                logger.debug(f"Keras failed: {e}")
        
        # Heuristics fallback
        if confidence < 0.4:
            try:
                import cv2
                gray = cv2.cvtColor(face_region, cv2.COLOR_BGR2GRAY)
                brightness = np.mean(gray)
                contrast = np.std(gray)
                
                if contrast > 40:
                    emotion = 'Angry' if brightness < 120 else 'Happy'
                    confidence = 0.35 * face_quality
                else:
                    emotion = 'Neutral'
                    confidence = (0.4 + 0.1 * face_quality)
                
                method_used = 'heuristics'
            except Exception as e:
                logger.debug(f"Heuristics failed: {e}")
                confidence = max(0.1, face_quality * 0.3)
    
    except Exception as e:
        logger.error(f"Emotion detection error: {e}")
        confidence = 0.1
    
    # Determine intensity
    intensity = 'low' if confidence < 0.33 else ('medium' if confidence < 0.66 else 'high')
    
    return {
        'emotion': emotion,
        'confidence': round(confidence, 3),
        'intensity': intensity,
        'method': method_used
    }
```

**Then update the log_emotion function** (find it in your code and update):

```python
def log_emotion(frame, face, name, location='Unknown', conn=None):
    """
    Log emotion to database with improved data
    """
    try:
        # Extract face region
        x, y, w, h = face['coordinates']
        face_region = frame[y:y+h, x:x+w]
        
        # Detect emotion with improved confidence
        emotion_data = detect_emotion_with_confidence_improved(face_region)
        
        # Ensure database connection
        if conn is None:
            conn = get_db()
        
        cursor = conn.cursor()
        
        # Insert with new columns
        cursor.execute('''
            INSERT INTO attendance_log (
                timestamp, name, emotion, emotion_confidence, 
                location, confidence, emotion_intensity, 
                emotion_method, face_quality_score
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            datetime.now().isoformat(),
            name,
            emotion_data['emotion'],
            emotion_data['confidence'],
            location,
            emotion_data['confidence'],  # Reuse improved confidence
            emotion_data['intensity'],
            emotion_data['method'],
            0.5  # TODO: add actual face quality calculation
        ))
        
        conn.commit()
        logger.info(f"Logged emotion: {name} - {emotion_data['emotion']} ({emotion_data['confidence']})")
        
    except Exception as e:
        logger.error(f"Error logging emotion: {e}")
```

### Step 3: Create Analytics API (45 minutes)

Create new file: `backend/emotion_analytics.py`

```python
"""
Emotion Analytics API Endpoints
"""
from flask import Blueprint, jsonify, request
from database import get_db
import logging

logger = logging.getLogger(__name__)

analytics_bp = Blueprint('analytics', __name__, url_prefix='/api/analytics')


@analytics_bp.route('/emotions/distribution', methods=['GET'])
def emotion_distribution():
    """Get emotion distribution for specified period"""
    try:
        hours = request.args.get('hours', 24, type=int)
        location = request.args.get('location', None)
        
        conn = get_db()
        cursor = conn.cursor()
        
        where_clause = f"WHERE timestamp > datetime('now', '-{hours} hours') AND emotion IS NOT NULL"
        if location:
            where_clause += f" AND location = '{location}'"
        
        query = f"""
            SELECT emotion, COUNT(*) as count, AVG(emotion_confidence) as avg_confidence
            FROM attendance_log
            {where_clause}
            GROUP BY emotion
            ORDER BY count DESC
        """
        
        cursor.execute(query)
        results = cursor.fetchall()
        
        total = sum(r[1] for r in results)
        data = {
            'period_hours': hours,
            'location': location or 'all',
            'total_records': total,
            'emotions': []
        }
        
        for emotion, count, avg_conf in results:
            data['emotions'].append({
                'emotion': emotion,
                'count': count,
                'percentage': round(count / total * 100, 1) if total > 0 else 0,
                'avg_confidence': round(avg_conf, 3)
            })
        
        conn.close()
        return jsonify(data), 200
    
    except Exception as e:
        logger.error(f"Error in emotion_distribution: {e}")
        return jsonify({'error': str(e)}), 500


@analytics_bp.route('/emotions/timeline', methods=['GET'])
def emotion_timeline():
    """Get emotion changes over time"""
    try:
        hours = request.args.get('hours', 24, type=int)
        
        conn = get_db()
        cursor = conn.cursor()
        
        query = f"""
            SELECT 
                strftime('%Y-%m-%d %H:00:00', timestamp) as hour,
                emotion,
                COUNT(*) as count,
                AVG(emotion_confidence) as avg_confidence
            FROM attendance_log
            WHERE timestamp > datetime('now', '-{hours} hours')
            AND emotion IS NOT NULL
            GROUP BY hour, emotion
            ORDER BY hour DESC
        """
        
        cursor.execute(query)
        results = cursor.fetchall()
        
        timeline = {}
        for hour, emotion, count, avg_conf in results:
            if hour not in timeline:
                timeline[hour] = {}
            timeline[hour][emotion] = {
                'count': count,
                'avg_confidence': round(avg_conf, 3)
            }
        
        conn.close()
        return jsonify({'timeline': timeline}), 200
    
    except Exception as e:
        logger.error(f"Error in emotion_timeline: {e}")
        return jsonify({'error': str(e)}), 500


@analytics_bp.route('/emotions/by-person', methods=['GET'])
def emotions_by_person():
    """Get emotion preferences for each person"""
    try:
        hours = request.args.get('hours', 24, type=int)
        
        conn = get_db()
        cursor = conn.cursor()
        
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
            GROUP BY name, emotion
            ORDER BY name, count DESC
        """
        
        cursor.execute(query)
        results = cursor.fetchall()
        
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
        return jsonify({'by_person': by_person}), 200
    
    except Exception as e:
        logger.error(f"Error in emotions_by_person: {e}")
        return jsonify({'error': str(e)}), 500


@analytics_bp.route('/emotions/summary', methods=['GET'])
def emotion_summary():
    """Get overall emotion summary"""
    try:
        hours = request.args.get('hours', 24, type=int)
        
        conn = get_db()
        cursor = conn.cursor()
        
        query = f"""
            SELECT emotion, COUNT(*) as count, AVG(emotion_confidence) as avg_confidence
            FROM attendance_log
            WHERE timestamp > datetime('now', '-{hours} hours')
            AND emotion IS NOT NULL
            GROUP BY emotion
        """
        
        cursor.execute(query)
        results = cursor.fetchall()
        
        total_records = sum(r[1] for r in results)
        avg_confidence = sum(r[1] * r[2] for r in results) / total_records if total_records > 0 else 0
        
        positive_emotions = ['Happy', 'Surprised']
        negative_emotions = ['Angry', 'Sad', 'Fearful', 'Disgusted']
        
        positive_count = sum(r[1] for r in results if r[0] in positive_emotions)
        negative_count = sum(r[1] for r in results if r[0] in negative_emotions)
        
        summary = {
            'period_hours': hours,
            'total_detections': total_records,
            'average_confidence': round(avg_confidence, 3),
            'positive_percentage': round(positive_count / total_records * 100, 1) if total_records > 0 else 0,
            'negative_percentage': round(negative_count / total_records * 100, 1) if total_records > 0 else 0,
            'emotions': []
        }
        
        for emotion, count, avg_conf in results:
            summary['emotions'].append({
                'emotion': emotion,
                'count': count,
                'percentage': round(count / total_records * 100, 1) if total_records > 0 else 0,
                'avg_confidence': round(avg_conf, 3)
            })
        
        conn.close()
        return jsonify(summary), 200
    
    except Exception as e:
        logger.error(f"Error in emotion_summary: {e}")
        return jsonify({'error': str(e)}), 500
```

### Step 4: Register Analytics Blueprint (5 minutes)

In `backend/server.py`, find the section with app initialization and add:

```python
# Add near the top with other imports
from emotion_analytics import analytics_bp

# Add after other blueprint registrations
app.register_blueprint(analytics_bp)
```

### Step 5: Test the Implementation (15 minutes)

```bash
cd /private/tmp/ChronoSenseWeb-clean/backend

# Test database
python << 'EOF'
from database import get_db
conn = get_db()
cursor = conn.cursor()
cursor.execute("PRAGMA table_info(attendance_log)")
columns = [col[1] for col in cursor.fetchall()]
print(f"Columns in attendance_log: {columns}")
assert 'emotion_intensity' in columns
assert 'emotion_method' in columns
print("✓ Database schema updated correctly!")
EOF

# Test emotion detection
python << 'EOF'
from emotion_detector import detect_emotion_with_confidence_improved
print("✓ Emotion detector imports successfully!")
EOF

# Test API endpoints with server running
curl http://localhost:5000/api/analytics/emotions/summary?hours=24
curl http://localhost:5000/api/analytics/emotions/distribution?hours=24
curl http://localhost:5000/api/analytics/emotions/by-person?hours=24
```

### Step 6: Create Simple Analytics Dashboard (1-2 hours optional)

Create `frontend/emotion-analytics.html`:

```html
<!DOCTYPE html>
<html>
<head>
    <title>Emotion Analytics Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { font-family: Arial; margin: 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
        .metric { display: inline-block; width: 22%; margin: 1%; padding: 20px; 
                  background: #f0f0f0; border-radius: 5px; }
        .chart-container { width: 45%; display: inline-block; margin: 2%; 
                          position: relative; height: 300px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Emotion Analytics Dashboard</h1>
        
        <div id="metrics"></div>
        
        <div class="chart-container">
            <canvas id="distributionChart"></canvas>
        </div>
        <div class="chart-container">
            <canvas id="confidenceChart"></canvas>
        </div>
    </div>
    
    <script>
        // Fetch emotion summary
        fetch('/api/analytics/emotions/summary?hours=24')
            .then(r => r.json())
            .then(data => {
                // Show metrics
                let html = `
                    <div class="metric">
                        <h3>Total Detections</h3>
                        <p>${data.total_detections}</p>
                    </div>
                    <div class="metric">
                        <h3>Positive %</h3>
                        <p>${data.positive_percentage}%</p>
                    </div>
                    <div class="metric">
                        <h3>Negative %</h3>
                        <p>${data.negative_percentage}%</p>
                    </div>
                    <div class="metric">
                        <h3>Confidence</h3>
                        <p>${data.average_confidence}</p>
                    </div>
                `;
                
                document.getElementById('metrics').innerHTML = html;
                
                // Draw distribution chart
                const labels = data.emotions.map(e => e.emotion);
                const counts = data.emotions.map(e => e.count);
                
                new Chart(document.getElementById('distributionChart'), {
                    type: 'doughnut',
                    data: {
                        labels: labels,
                        datasets: [{
                            data: counts,
                            backgroundColor: ['#4CAF50', '#FFC107', '#F44336', '#2196F3']
                        }]
                    },
                    options: { title: { text: 'Emotion Distribution' } }
                });
                
                // Draw confidence chart
                const confs = data.emotions.map(e => e.avg_confidence);
                new Chart(document.getElementById('confidenceChart'), {
                    type: 'bar',
                    data: {
                        labels: labels,
                        datasets: [{
                            label: 'Avg Confidence',
                            data: confs,
                            backgroundColor: '#2196F3'
                        }]
                    },
                    options: {
                        scales: {
                            y: { beginAtZero: true, max: 1 }
                        }
                    }
                });
            });
    </script>
</body>
</html>
```

## Verification Checklist

After implementation, verify:

- [ ] Database has new columns (emotion_intensity, emotion_method, face_quality_score)
- [ ] Emotion confidence values show variance (not stuck at 0.3)
- [ ] API endpoints respond with data:
  - `GET /api/analytics/emotions/distribution`
  - `GET /api/analytics/emotions/timeline`
  - `GET /api/analytics/emotions/by-person`
  - `GET /api/analytics/emotions/summary`
- [ ] Dashboard loads emotion data correctly
- [ ] Data shows meaningful patterns (different emotions, varying confidence)

## Performance Notes

- Analytics queries should complete in <500ms with indexes
- For >100k records, consider archiving old data
- Dashboard caches data for 5 minutes to reduce database load

## Next Steps

1. ✅ Implement the above changes
2. ☐ Collect 1-2 weeks of data with improved detection
3. ☐ Add machine learning recommendations
4. ☐ Build team-level emotion analytics
5. ☐ Integrate with wellness programs

---
