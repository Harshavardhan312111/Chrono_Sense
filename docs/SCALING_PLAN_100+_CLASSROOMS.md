# ChronoSense Scaling Plan: 100+ Classrooms & Corridors

**Current Capacity:** 4-6 cameras per location  
**Target Capacity:** 100+ classrooms + 50+ corridors = 300-500 camera feeds  
**Current Bottlenecks:** SQLite, monolithic server, in-memory profile cache

---

## Phase 0: Scalability Analysis (Current System)

### Current Limits

| Component | Current | Bottleneck | 100+ Classrooms Impact |
|-----------|---------|-----------|------------------------|
| **Database** | SQLite (single file) | ~10-20 concurrent connections | CRITICAL ❌ |
| **API Server** | Monolithic FastAPI (1 process) | ~100 concurrent streams | CRITICAL ❌ |
| **Profile Cache** | In-memory dict, single process | ~5000 profiles max | HIGH ⚠️ |
| **Camera Threads** | 1 thread per camera, no pool | OS thread limit (~1000) | MEDIUM ⚠️ |
| **Attendance Dedup** | In-memory cache per instance | Won't sync across servers | MEDIUM ⚠️ |
| **Storage** | Local filesystem | 1000s of cameras generating 10GB+/day | HIGH ⚠️ |
| **Network** | Single server, no load balancing | All RTSP streams go to 1 machine | HIGH ⚠️ |
| **Emotion Detection** | CPU-only, single-threaded | ~5 FPS per camera with emotion | MEDIUM ⚠️ |

### Math for 100+ Classrooms

```
Scenario: 100 classrooms × 3 cameras + 50 corridors × 2 cameras = 400 streams

Per Camera (800×600 @ 30 FPS):
- Bandwidth: 800×600×3 bytes (RGB) × 30 FPS = 43 MB/s per stream
- Total bandwidth: 43 MB/s × 400 = 17.2 GB/s (!)
- Processed frames (every 3rd): 10 FPS × 400 = 4,000 frames/sec
- Embeddings to compute: 4,000 / 3 = 1,333 embeddings/sec
- Emotions to compute: 1,333 emotions/sec
- Activity recognitions: 1,333 activities/sec

Current system throughput:
- 1 CPU-core can do ~3-5 embeddings/sec (40ms each with InsightFace)
- Would need 267-444 CPU cores just for embeddings (!)
- Plus emotion + activity detection on top

✗ Impossible on single server
```

---

## Phase 1: Database Migration (Weeks 1-2)

**Goal:** Replace SQLite with PostgreSQL for horizontal scalability

### 1.1 PostgreSQL Setup

```bash
# Cloud options:
# - AWS RDS (managed PostgreSQL, multi-AZ failover)
# - Google Cloud SQL (better for distributed teams)
# - Self-hosted (more control, but ops burden)

# Recommended: AWS RDS PostgreSQL 15+
# - High availability (primary + 2 replicas)
# - Automated backups, 35-day retention
# - Encryption at rest + in transit
```

### 1.2 Migration Strategy

**Current:** SQLite schema → **PostgreSQL schema** (with enhancements)

| Table | Current Rows/Day | PostgreSQL Enhancement |
|-------|------------------|------------------------|
| `attendance_log` | ~5,000 | Add **indexes** on (profile_id, date), (location, date) |
| `activity_log` | ~15,000 | Add **partitioning** by date (monthly) |
| `emotion_analytics` | ~5,000 | Add **materialized views** for daily rollups |
| `profiles` | ~1,500 | Add **full-text search** on name |
| `cctv_cameras` | ~500 | Add **location_id** FK to new locations table |

**Key additions:**

```sql
-- New tables for scaling
CREATE TABLE locations (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    building TEXT,
    floor INTEGER,
    timezone TEXT DEFAULT 'Asia/Kolkata',
    region_id INTEGER FK -- For multi-region deployments
);

CREATE TABLE camera_groups (
    id SERIAL PRIMARY KEY,
    location_id INTEGER FK,
    name TEXT, -- "Classroom A", "Corridor 2"
    created_at TIMESTAMP
);

-- Partitioned attendance_log by date (auto-archive old data)
CREATE TABLE attendance_log (
    ...
) PARTITION BY RANGE (DATE(timestamp));

-- Read replicas
CREATE SEQUENCE seq_read_replica;  -- For sticky reads
```

### 1.3 Code Changes (database.py)

```python
# Replace sqlite3 with psycopg2/asyncpg
import asyncpg  # Async PostgreSQL driver

class ProfileDatabase:
    def __init__(self, connection_pool: asyncpg.Pool):
        self.pool = connection_pool
    
    async def add_profile(self, name, embedding, ...):
        """Use connection from pool (scales to 100+ concurrent users)"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                'INSERT INTO profiles (name, embedding, ...) VALUES (...)'
            )

# On server startup:
app.add_event_handler(
    "startup",
    lambda: asyncpg.create_pool(
        dsn="postgresql://user:pass@aws-rds.us-east-1.rds.amazonaws.com/chronosense",
        min_size=20,  # Min connections
        max_size=100,  # Max connections (scales with demand)
        command_timeout=60,
    )
)
```

**Effort:** 2-3 days (1 engineer)  
**Cost:** AWS RDS ~$50-200/month (multi-AZ)  
**Benefit:** ✅ Supports 10,000+ concurrent queries, 1M+ rows/day

---

## Phase 2: Distributed Camera Processing (Weeks 3-4)

**Goal:** Distribute camera streams across multiple worker nodes

### 2.1 Architecture: Edge + Central Hub

```
┌─────────────────────────────────────────────────────────┐
│                     CENTRAL HUB (Main Server)            │
│  - API layer (FastAPI, load-balanced)                   │
│  - Profile cache (Redis)                                │
│  - Deduplication cache (Redis)                          │
│  - Database (PostgreSQL)                                │
│  - Analytics aggregation                                │
└──────────────────────────┬──────────────────────────────┘
         │
    ┌────┴────┬───────────┬─────────────┐
    │          │           │             │
┌───▼──┐  ┌──▼───┐   ┌───▼──┐   ┌─────▼─┐
│Worker│  │Worker│   │Worker│   │Worker │ (8-16 workers)
│ Node │  │ Node │   │ Node │   │ Node  │ Processing:
│ (20  │  │ (20  │   │ (20  │   │ (20   │ - Detection
│ fps) │  │ fps) │   │ fps) │   │ fps)  │ - Recognition
└──────┘  └──────┘   └──────┘   └───────┘ - Emotion/Activity
   ↑        ↑          ↑          ↑
  RTSP streams       (TCP/gRPC)
```

### 2.2 Worker Node Design

**Each worker:** 
- Handles 20-30 camera streams
- Runs `CCTVRecognitionEngine` independently
- Sends detections back to hub via gRPC

```python
# worker_node.py (new file)
import grpc
import asyncio
from concurrent import futures
from cctv_recognition import CCTVRecognitionEngine

class RecognitionWorker:
    """Processes cameras, sends results to central hub"""
    def __init__(self, worker_id: int, hub_address: str):
        self.worker_id = worker_id
        self.engine = CCTVRecognitionEngine(...)
        self.hub_stub = HubServiceStub(
            grpc.aio.secure_channel(hub_address, ...)
        )
        self.camera_threads = {}
    
    async def process_camera_stream(self, camera_id: int, stream_url: str):
        """Process one camera, stream results to hub"""
        cap = cv2.VideoCapture(stream_url)
        while True:
            ret, frame = cap.read()
            if not ret: break
            
            # Local processing (very fast)
            detections = self.engine.process_frame(frame, camera_id)
            
            # Send to hub (async, non-blocking)
            await self.hub_stub.log_detections(
                LogDetectionsRequest(
                    worker_id=self.worker_id,
                    camera_id=camera_id,
                    detections=detections,
                    timestamp=time.time()
                )
            )

# On startup, worker connects to hub and receives camera assignments
async def run_worker(worker_id: int, hub_address: str):
    worker = RecognitionWorker(worker_id, hub_address)
    
    # Get assigned cameras from hub
    response = await worker.hub_stub.get_assigned_cameras(
        GetAssignedCamerasRequest(worker_id=worker_id)
    )
    
    # Start processing assigned cameras
    tasks = [
        worker.process_camera_stream(cam.id, cam.source)
        for cam in response.cameras
    ]
    await asyncio.gather(*tasks)
```

### 2.3 Hub Aggregation (server.py changes)

```python
# hub_server.py (modified server.py)
from concurrent import futures
import grpc

class ChronoSenseHub:
    def __init__(self):
        self.workers = {}  # {worker_id: worker_stub}
        self.camera_assignments = {}  # {camera_id: worker_id}
        self.profile_cache = RedisCache()  # Redis instead of dict
        self.dedup_cache = RedisCache()
    
    async def log_detections(self, request: LogDetectionsRequest):
        """Receives detections from worker nodes"""
        detections = request.detections
        
        # Log to PostgreSQL (via connection pool)
        async with self.db_pool.acquire() as conn:
            for det in detections:
                await conn.execute(
                    'INSERT INTO attendance_log (...) VALUES (...)',
                    ...
                )
        
        return LogDetectionsResponse(status="OK")
    
    async def assign_cameras(self):
        """Distribute cameras to workers (load balancing)"""
        cameras = await self.get_all_cameras()
        workers = list(self.workers.values())
        
        # Round-robin assignment
        for i, camera in enumerate(cameras):
            worker_id = workers[i % len(workers)].worker_id
            self.camera_assignments[camera.id] = worker_id
            
            # Tell worker to stream this camera
            await workers[i % len(workers)].assign_camera(camera)

# gRPC server setup
async def serve():
    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))
    ADD_CHRONOSENSE_HUB_SERVICE_TO_SERVER(ChronoSenseHub(), server)
    
    await server.start()
    await server.wait_for_termination()
```

**Effort:** 4-5 days (1-2 engineers)  
**Infrastructure:** 8-16 worker nodes (AWS EC2), each $20-50/month  
**Benefit:** ✅ Scales to 300-500 camera streams, 20-30× throughput gain

---

## Phase 3: Caching Layer (Week 5)

**Goal:** Redis for profile cache + deduplication (avoid database thrashing)

### 3.1 Redis Cluster Setup

```bash
# AWS ElastiCache for Redis (managed cluster)
redis-cli -h chronosense-cluster.xxxxx.ng.0001.use1.cache.amazonaws.com
> PING
PONG

# Replication: Primary + 2 read replicas (automatic failover)
# Persistence: RDB snapshots every 5 minutes
```

### 3.2 Profile Caching Strategy

```python
# ai_engine.py (modified)
import redis
import json

class ChronoEngine:
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.profiles = {}  # Local cache (backup)
        self._load_profiles_from_redis()
    
    def _load_profiles_from_redis(self):
        """Load profiles from Redis on startup"""
        profile_keys = self.redis.keys('profile:*')
        for key in profile_keys:
            profile_data = json.loads(self.redis.get(key))
            profile_id = int(key.split(':')[1])
            self.profiles[profile_id] = {
                'name': profile_data['name'],
                'embedding': np.array(profile_data['embedding'], dtype=np.float32),
                'created_at': profile_data['created_at']
            }
        logger.info(f"✓ Loaded {len(self.profiles)} profiles from Redis")
    
    def invalidate_profile_cache(self, profile_id: int):
        """Called when profile updated in database"""
        if profile_id in self.profiles:
            del self.profiles[profile_id]
        self.redis.delete(f"profile:{profile_id}")
        
        # Notify all worker nodes to refresh
        self.redis.publish("profile_update", json.dumps({"profile_id": profile_id}))
    
    def subscribe_to_updates(self):
        """Listen for profile updates from other servers"""
        pubsub = self.redis.pubsub()
        pubsub.subscribe("profile_update")
        
        for message in pubsub.listen():
            if message['type'] == 'message':
                update = json.loads(message['data'])
                self._load_profiles_from_redis()

# Deduplication cache in Redis (survives server restarts)
class DetectionCache:
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.deduplicate_window = 3600  # 60 minutes
    
    def should_log(self, profile_id: int) -> bool:
        key = f"dedup:{profile_id}"
        last_log = self.redis.get(key)
        
        if last_log is None:
            return True
        
        return (time.time() - float(last_log)) >= self.deduplicate_window
    
    def mark_logged(self, profile_id: int):
        self.redis.setex(
            f"dedup:{profile_id}",
            self.deduplicate_window + 300,  # TTL
            time.time()
        )
```

**Effort:** 2-3 days  
**Cost:** AWS ElastiCache ~$30-60/month  
**Benefit:** ✅ Eliminates database query load, scales deduplication across all nodes

---

## Phase 4: Object Storage for Face Snapshots (Week 6)

**Goal:** Move from local filesystem to S3 (scales to 100k+ daily images)

### 4.1 S3 Migration

```python
# cctv_recognition.py (modified)
import boto3

class CCTVRecognitionEngine:
    def __init__(self, s3_client: boto3.client):
        self.s3 = s3_client
        self.snapshot_bucket = "chronosense-snapshots"
    
    def _save_face_snapshot(self, face_crop, camera_id: int, name: str) -> str:
        """Save to S3 instead of local filesystem"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]
        safe_name = name.replace(' ', '_')
        key = f"camera_{camera_id}/{safe_name}/{timestamp}.jpg"
        
        # Encode image to bytes
        success, buffer = cv2.imencode('.jpg', face_crop)
        if not success:
            return None
        
        try:
            # Upload to S3 with server-side encryption
            self.s3.put_object(
                Bucket=self.snapshot_bucket,
                Key=key,
                Body=buffer.tobytes(),
                ContentType='image/jpeg',
                ServerSideEncryption='AES256',
                StorageClass='INTELLIGENT_TIERING'  # Save costs
            )
            
            # Return S3 URL
            return f"s3://{self.snapshot_bucket}/{key}"
        except Exception as e:
            logger.error(f"S3 upload failed: {e}")
            return None
```

**Storage Math:**
```
100 classrooms × 3 cameras = 300 cameras
~50 detections/camera/day = 15,000 faces/day
~50 KB per JPEG = 750 MB/day = 22.5 GB/month

AWS S3 costs:
- Storage: 22.5 GB × $0.023/GB = $0.52/month
- Requests: 450K (300×50×30) × $0.0004 = $0.18/month
- Total: ~$1-2/month (incredibly cheap)

With intelligent tiering: Even cheaper after 30 days
```

**Effort:** 2 days  
**Cost:** Negligible ($1-5/month)  
**Benefit:** ✅ Unlimited scalability, automatic backups, versioning

---

## Phase 5: API Load Balancing (Week 7)

**Goal:** Horizontal scaling of API servers (handle 1000s of dashboard users)

### 5.1 Kubernetes / Docker Compose Setup

```yaml
# docker-compose.yml (for scaling)
version: '3.8'

services:
  api-1:
    image: chronosense-api:latest
    environment:
      - POSTGRES_URL=postgresql://user:pass@postgres:5432/chronosense
      - REDIS_URL=redis://redis:6379
      - AWS_S3_BUCKET=chronosense-snapshots
    ports:
      - "8001:8000"
  
  api-2:
    image: chronosense-api:latest
    environment:
      - POSTGRES_URL=postgresql://user:pass@postgres:5432/chronosense
      - REDIS_URL=redis://redis:6379
      - AWS_S3_BUCKET=chronosense-snapshots
    ports:
      - "8002:8000"
  
  api-3:
    image: chronosense-api:latest
    ports:
      - "8003:8000"
  
  nginx:
    image: nginx:latest
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
    depends_on:
      - api-1
      - api-2
      - api-3

# nginx.conf
upstream api_backend {
    least_conn;  # Load balance by active connections
    server api-1:8000 weight=1;
    server api-2:8000 weight=1;
    server api-3:8000 weight=1;
}

server {
    listen 80;
    server_name chronosense.example.com;
    
    location / {
        proxy_pass http://api_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**Effort:** 2-3 days  
**Infrastructure:** 3-5 API servers or Kubernetes cluster  
**Benefit:** ✅ Handles 10,000+ concurrent dashboard users

---

## Phase 6: Analytics & Rollups (Week 8)

**Goal:** Pre-aggregated data for fast dashboard queries

### 6.1 Materialized Views (PostgreSQL)

```sql
-- Compute once/hour, indexes for 1ms queries
CREATE MATERIALIZED VIEW daily_attendance_summary AS
SELECT 
    DATE(timestamp) as date,
    profile_id,
    name,
    COUNT(*) as detections,
    MIN(timestamp) as first_seen,
    MAX(timestamp) as last_seen,
    location
FROM attendance_log
GROUP BY DATE(timestamp), profile_id, name, location;

CREATE INDEX idx_daily_summary_date ON daily_attendance_summary (date DESC);
CREATE INDEX idx_daily_summary_profile ON daily_attendance_summary (profile_id);

-- Refresh every hour
SELECT cron.schedule(
    'refresh_daily_summary',
    '0 * * * *',  -- Every hour
    'REFRESH MATERIALIZED VIEW CONCURRENTLY daily_attendance_summary'
);

-- Similarly for emotions, activities
CREATE MATERIALIZED VIEW hourly_emotion_distribution AS
SELECT 
    DATE_TRUNC('hour', timestamp) as hour,
    EXTRACT(HOUR FROM timestamp) as hour_of_day,
    emotion,
    COUNT(*) as count,
    AVG(emotion_confidence::FLOAT) as avg_confidence,
    location
FROM emotion_analytics
GROUP BY hour, emotion, location;
```

**Effort:** 2 days  
**Benefit:** ✅ Dashboard queries drop from 5-10 seconds to 50-100ms

---

## Phase 7: Multi-Region Deployment (Week 9-10)

**Goal:** Geographic redundancy + local processing (latency optimization)

### 7.1 Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│           GLOBAL CONTROL CENTER (Main Datacenter)               │
│           - Master PostgreSQL                                   │
│           - Global Redis                                        │
│           - Admin dashboards                                    │
└─────────────────────────────────────────────────────────────────┘
     │
     ├─────────────────────────────────────────┐
     │                                         │
  ┌──▼───────────────┐            ┌─────────┴─────────┐
  │ REGION: US-EAST  │            │  REGION: APAC     │
  │ - PostgreSQL     │            │  - PostgreSQL     │
  │   replica (RO)   │            │    replica (RO)   │
  │ - Redis cache    │            │  - Redis cache    │
  │ - 50 workers     │            │  - 50 workers     │
  │ - API servers ×5 │            │  - API servers ×5 │
  └──────────────────┘            └───────────────────┘
        ↓                                ↓
   [200 classrooms]              [150 classrooms]
   US-based schools              India-based schools
```

### 7.2 Cross-Region Replication

```python
# Each region has PostgreSQL replica (read-only)
# Master in primary region replicates to secondaries

# Connection:
# - Regional users connect to local db replica (low latency)
# - All writes go to master (consistency)
# - Redis Cluster spans regions (multi-region cache)

# Example: India region
postgres_replica = psycopg2.connect(
    "postgresql://user@india-db-replica.rds.xxx.com/chronosense"
)

# For writes, route to master
postgres_master = psycopg2.connect(
    "postgresql://user@master-db.rds.xxx.com/chronosense"
)
```

**Effort:** 3-4 days  
**Infrastructure:** Adds ~$100/month per region  
**Benefit:** ✅ Low latency for users worldwide, automatic failover

---

## Implementation Timeline

| Phase | Duration | Team Size | Cumulative Cost | Classrooms Supported |
|-------|----------|-----------|-----------------|---------------------|
| **Current** | — | — | ~$0 | 5-10 |
| **Phase 1: PostgreSQL** | 2 weeks | 1 eng | $50/mo | 20-30 |
| **Phase 2: Workers** | 2 weeks | 2 eng | $250+/mo | 100-150 |
| **Phase 3: Redis** | 1 week | 1 eng | $300+/mo | 150-200 |
| **Phase 4: S3** | 1 week | 1 eng | $305+/mo | 200-250 |
| **Phase 5: Load Balance** | 1 week | 1 eng | $400+/mo | 250-350 |
| **Phase 6: Analytics** | 1 week | 1 eng | $400+/mo | 350-400 |
| **Phase 7: Multi-Region** | 2 weeks | 2 eng | $600+/mo | 500+ |
| **TOTAL** | 10 weeks | 2-3 FTE | ~$600/mo | **500+ classrooms** |

---

## Critical Dependencies & Risks

| Risk | Mitigation |
|------|-----------|
| **Network bottleneck** (RTSP streams to master) | Phase 2 solves via edge workers at each location |
| **Embedding latency** (GPU shortage) | Add GPU workers for emotion/activity in Phase 2 |
| **Database consistency** | Multi-AZ RDS + cross-region replication |
| **Redis failure** | Redis cluster with auto-failover + RDB backups |
| **Worker node crashes** | Kubernetes auto-restart + health checks |
| **S3 outage** | Multi-region replication, fallback to local caching |

---

## Quick-Start: Phase 1 Only (Minimal Effort Path)

**If you only want to get to ~50-100 classrooms with minimal changes:**

1. **Replace SQLite with PostgreSQL** (biggest bang for buck)
   - Same code structure, just change connection strings
   - Supports 100× more concurrent connections
   - Cost: $50/month AWS RDS

2. **Add Redis for profiles + dedup** (2-line changes)
   - Keep single API server
   - Eliminates database thrashing
   - Cost: $30/month

3. **Use S3 for snapshots** (3-line changes)
   - No local storage limits
   - Cost: $1-5/month

**Total effort:** 1-2 weeks, **1 engineer**, **Grows to ~100 classrooms easily**

---

## Next Steps

1. **Choose deployment model:**
   - Option A: Quick win (PostgreSQL + Redis + S3) → 100 classrooms in 3 weeks
   - Option B: Full scale (all phases) → 500+ classrooms in 10 weeks

2. **If Option A:** Start with [PHASE_1_POSTGRES_MIGRATION.md](./PHASE_1_POSTGRES_MIGRATION.md)

3. **If Option B:** We'll create detailed implementation docs for each phase

**What would you prefer?**
