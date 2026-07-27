# Petals 306 F Camera - Emotion Detection Issue & Solution

## Problem Summary

**Issue**: Emotions from Petals 306 F camera are not showing on the emotion analytics dashboard.

**Root Cause**: The Petals camera IS running and detecting faces, but the faces are **too small** (~34x37 pixels) to be recognized. Without successful face recognition, no emotion data is logged.

## Current Status

### What's Working ✅
- Petals 306 F camera is **ENABLED**
- Camera stream is **OPENING** successfully  
- Recognition thread **IS RUNNING**
- Face detection **IS WORKING**

### What's NOT Working ❌
- **Face recognition FAILING** - embedding extraction errors
- Faces detected are only 34x37 pixels (too small for good recognition)
- **NO emotions logged** from Petals camera (0 records)
- Faces not matching against known profiles

### Comparison with Camera 4
- Camera 4 (CP IP Camera - Chronosphere): **2,462 emotion records** ✅
- Petals 306 F: **0 emotion records** ❌

## Why This Happens

**Face Recognition Requirements**:
- Minimum face size: 80x80 pixels (acceptable)
- Optimal face size: 150x250 pixels (ideal)
- Current face size: **34x37 pixels** ❌ (TOO SMALL)

**Why faces are too small**:
- Camera is **too far** from the subjects
- Camera is positioned too **high or at wrong angle**
- Camera **zoom level** is not optimal
- Camera **field of view** is capturing too wide an area

## Solution

### Step 1: Reposition the Petals 306 F Camera

**Action Items**:

1. **Reduce Distance**:
   - Move camera **closer** to where people's faces will be
   - Ideal distance: 1-2 meters for indoor spaces
   - Test: Faces should occupy at least 150 pixels height in the frame

2. **Adjust Angle**:
   - Mount camera at **eye level** or slightly above
   - Point at people's faces directly (not at floor, not at ceiling)
   - Avoid extreme angles (>45 degrees)

3. **Optimal Positioning**:
   - **Height**: Eye level or 10-20cm above (for 150 faces/height/pixels)
   - **Distance**: 1-2 meters from subject
   - **Angle**: 0-30 degrees tilt (centered on faces)
   - **Lighting**: Well-lit, facing camera → no backlighting

4. **Test the Camera**:
   ```bash
   # After repositioning, check camera feed
   # Use the test streaming endpoint to verify face size
   # Faces should be at least 100 pixels wide minimum
   ```

### Step 2: Verify the Fix (After Camera Repositioning)

**Check 1: Server logs for successful recognition**:
```bash
grep "Logged: " server.log | grep Petals | head -10
```

**Expected Output** (after fixing):
```
Logged: [person_name] (..., emotion=Happy, ...)
```

**Check 2: Query database for Petals emotions**:
```bash
sqlite3 backend/profiles.db \
  "SELECT COUNT(*), emotion FROM attendance_log WHERE location='Petals 306 F' GROUP BY emotion;"
```

**Expected Output** (after fixing):
```
200|Happy
150|Neutral
100|Sad
...
```

**Check 3: Dashboard will auto-update**:
- Petals 306 F will appear in the location-based emotion chart
- You'll see emotion distribution for that camera

### Step 3: Monitor and Optimize

**Metrics to Watch**:

1. **Recognition Accuracy**: Faces successfully matched to profiles
2. **Emotion Confidence**: Should see values > 0.5 (not stuck at 0.3)
3. **Daily Detections**: Should have ~100+ per day with proper positioning

**If Recognition Still Fails After Repositioning**:

```bash
# Check frame processing logs for embedding errors
grep "Failed to extract embedding" server.log | wc -l

# If still > 100 errors/minute, faces are still too small
```

### Step 4: Advanced Troubleshooting

**If camera positioning doesn't help:**

1. **Check Camera Specs**:
   - Verify Petals camera IP/RTSP URL is correct
   - Check camera resolution capability
   - Ensure camera isn't artificially zoomed out

2. **Test Camera Directly**:
   ```bash
   # Connect directly to camera feed to see image quality
   ffplay rtsp://admin:123456@192.168.3.92:554
   ```

3. **Check CCTV Config**:
   ```bash
   sqlite3 backend/profiles.db \
     "SELECT id, name, source, camera_type FROM cctv_cameras WHERE name='Petals 306 F';"
   ```

4. **Enable Debug Logging**:
   - Increase logging verbosity for cctv_recognition.py
   - Monitor embedding extraction success rate

## Location Fix (ALREADY APPLIED ✅)

**Fixed:**
- server.py now passes location parameter when logging events
- Previously: `log_stream_detections(detections)` ← No location!
- Now: `log_stream_detections(detections, location="Local Webcam")` ← Has location!

**Impact**:
- Future emotions will be logged with proper location
- Old NULL location emotions won't be affected (historical data)
- Clean data going forward

## Expected Timeline

- **Immediately After Fix**: 
  - Dashboard will show Petals 306 F in location dropdown
  - New emotions logged WITH location="Petals 306 F"

- **After 1 Day**: 
  - ~100+ emotion records from Petals camera
  - Visible trends in charts

- **After 1 Week**: 
  - Sufficient data for analytics
  - Clear emotional patterns by time of day

## Verification Checklist

After repositioning camera:

- [ ] Faces in camera feed are visibly larger (150+ pixels)
- [ ] Server logs show "Logged: " messages for Petals camera
- [ ] Database contains emotion records with location="Petals 306 F"
- [ ] Dashboard location dropdown includes "Petals 306 F"
- [ ] Emotion distribution chart shows Petals data
- [ ] Emotion confidence values vary (not stuck at 0.3)

## Implementation Steps

1. **Physically reposition Petals 306 F camera** (5-10 minutes)
   - Move closer to subjects
   - Adjust angle to eye level
   - Verify in camera feed

2. **Restart server** (1 minute):
   ```bash
   pkill -f "backend/server.py"
   sleep 2
   cd /private/tmp/ChronoSenseWeb-clean
   ./.venv/bin/python backend/server.py > server.log 2>&1 &
   ```

3. **Monitor logs** (2-3 minutes):
   ```bash
   tail -f server.log | grep -E "Logged:|Petals"
   ```

4. **Check database** (1 minute):
   ```bash
   sqlite3 backend/profiles.db \
     "SELECT COUNT(*) FROM attendance_log WHERE location='Petals 306 F';" 
   ```

5. **Verify dashboard** (1 minute):
   - Open emotion-analytics.html
   - Check location dropdown for "Petals 306 F"
   - Verify data appears

## FAQ

**Q: How long before emotions show up?**
A: Immediately after successful face recognition. Give it 5-10 minutes for volume to be visible on dashboard.

**Q: Will old NULL location emotions be affected?**
A: No, this only affects new emotions going forward.

**Q: What if I can't move the camera closer?**
A: Consider using a camera with better zoom/optical capabilities, or use a wider-angle view and crop the region of interest.

**Q: Why was this not detected earlier?**
A: Petals camera was enabled but faces are consistently too small to recognize. The system correctly skips unrecognizable faces, so no false positives are logged.

## Support

If issues persist:
1. Check camera source URL: `rtsp://admin:123456@192.168.3.92:554`
2. Verify camera credentials are correct
3. Check network connectivity to camera
4. Review detailed logs: `grep -i "petals\|error" server.log`

---

**Status**: Ready to implement
**Expected Outcome**: Petals 306 F emotions will appear on dashboard within 5-10 minutes of successful camera repositioning

