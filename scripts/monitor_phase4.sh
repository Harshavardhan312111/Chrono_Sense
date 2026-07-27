#!/bin/bash
# Phase 4 Quick Monitoring Guide
# Run these commands to verify system is working correctly

echo "===================================================================="
echo "PHASE 4 MONITORING DASHBOARD"
echo "ChronoSense Face Recognition - Verification Testing"
echo "===================================================================="
echo ""

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get directory
cd /private/tmp/ChronoSenseWeb-clean

echo -e "${GREEN}1. SERVER STATUS${NC}"
echo "---"
if curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Server is ONLINE${NC}"
    curl -s http://localhost:8000/api/health | python -m json.tool 2>/dev/null || echo "API responding"
else
    echo -e "${RED}❌ Server is OFFLINE${NC}"
    echo "   Start with: ./.venv/bin/python backend/server.py > server.log 2>&1 &"
fi
echo ""

echo -e "${GREEN}2. DATABASE STATISTICS${NC}"
echo "---"
sqlite3 backend/profiles.db << 'SQL'
.headers on
.mode column
SELECT 'TOTAL RECORDS' as metric, COUNT(*) as count FROM attendance_log
UNION ALL
SELECT 'Recent (04-04+)', COUNT(*) FROM attendance_log WHERE DATE(timestamp) >= '2026-04-04'
UNION ALL
SELECT 'Borderline (0.32-0.36)', COUNT(*) FROM attendance_log WHERE confidence BETWEEN 0.32 AND 0.36
UNION ALL
SELECT 'Missing frames', COUNT(*) FROM attendance_log WHERE frame_path IS NULL
UNION ALL
SELECT 'Above threshold (0.36+)', COUNT(*) FROM attendance_log WHERE confidence >= 0.36;
SQL
echo ""

echo -e "${GREEN}3. PROFILE DETECTION SUMMARY${NC}"
echo "---"
sqlite3 backend/profiles.db << 'SQL'
.headers on
.mode column
SELECT name, 
       COUNT(*) as detections,
       ROUND(AVG(confidence), 4) as avg_confidence,
       ROUND(MIN(confidence), 4) as min_conf,
       ROUND(MAX(confidence), 4) as max_conf
FROM attendance_log
GROUP BY name
ORDER BY COUNT(*) DESC
LIMIT 10;
SQL
echo ""

echo -e "${GREEN}4. ADITYA STATUS (Regression Check)${NC}"
echo "---"
COUNT=$(sqlite3 backend/profiles.db "SELECT COUNT(*) FROM attendance_log WHERE name LIKE '%Aditya%'")
echo "Total Aditya detections: $COUNT"
if [ "$COUNT" -gt 0 ]; then
    echo ""
    echo "Recent Aditya detections:"
    sqlite3 backend/profiles.db << 'SQL'
.headers on
.mode column
SELECT timestamp, ROUND(confidence, 4) as confidence, emotion 
FROM attendance_log 
WHERE name LIKE '%Aditya%' 
ORDER BY timestamp DESC 
LIMIT 5;
SQL
else
    echo -e "${GREEN}✅ No Aditya detections (false positives prevented)${NC}"
fi
echo ""

echo -e "${GREEN}5. RECENT DETECTIONS SAMPLE${NC}"
echo "---"
sqlite3 backend/profiles.db << 'SQL'
.headers on
.mode column
SELECT 
    SUBSTR(timestamp, 12, 8) as time,
    name,
    ROUND(confidence, 4) as conf,
    emotion,
    CASE WHEN frame_path IS NULL THEN 'NO' ELSE 'YES' END as frame
FROM attendance_log 
ORDER BY timestamp DESC 
LIMIT 10;
SQL
echo ""

echo -e "${GREEN}6. SYSTEM HEALTH CHECK${NC}"
echo "---"
# Check for errors in log
ERRORS=$(grep -i "error\|exception\|failed" server.log 2>/dev/null | grep -v "No such file" | wc -l)
if [ "$ERRORS" -eq 0 ]; then
    echo -e "${GREEN}✅ No errors in server log${NC}"
else
    echo -e "${YELLOW}⚠️  Found $ERRORS error entries in logs${NC}"
    echo "   Run: tail -20 server.log | grep -i error"
fi
echo ""

echo -e "${GREEN}7. THRESHOLD SETTINGS${NC}"
echo "---"
echo "Configured thresholds:"
grep "recognition_threshold" backend/server.py | head -1 | sed 's/.*recognition_threshold=/  Recognition: /' | sed 's/,.*//'
grep "min_gap = " backend/ai_engine.py | head -1 | sed 's/.*min_gap = /  Gap requirement: /'
echo "  Frame validation: MANDATORY"
echo ""

echo "===================================================================="
echo "INTERPRETATION GUIDE"
echo "===================================================================="
echo ""
echo "✅ SUCCESS METRICS:"
echo "  • Borderline (0.32-0.36): 0 (should be zero)"
echo "  • Missing frames: 0 (should be zero)"
echo "  • Above 0.36: > 0 (legitimate detections working)"
echo "  • Aditya detections: 0 (prevents false positives)"
echo "  • Server errors: 0 (system stable)"
echo ""
echo "⚠️  WARNING SIGNS:"
echo "  • Borderline matches > 0 → Threshold may be too low"
echo "  • Missing frames > 0 → Frame validation not enforced"
echo "  • Above 0.36 = 0 → Threshold may be too high (no legitimate detections)"
echo "  • Aditya detections spike → Investigate confidence scores"
echo "  • Server errors present → Review server.log"
echo ""
echo "===================================================================="
echo ""
