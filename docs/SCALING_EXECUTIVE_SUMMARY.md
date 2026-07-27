# Scaling Summary: Current → 100+ Classrooms

## TL;DR

| Question | Answer |
|----------|--------|
| **Can it scale to 100+ classrooms?** | ✅ YES, with architectural changes |
| **What's the main bottleneck?** | SQLite database (max ~20 concurrent connections) |
| **Time to 100 classrooms?** | 3-4 weeks (Phase 1 only: PostgreSQL + Redis + S3) |
| **Time to 500 classrooms?** | 10 weeks (all 7 phases) |
| **Cost increase?** | From $0 → $600/month (AWS services) |
| **Code rewrite needed?** | 20-30% changes (mostly configuration) |

---

## Current System Limits

```
CURRENT (SQLite):                BOTTLENECK:
- 4-6 cameras per location       SQLite: max ~20 concurrent DB connections
- ~10-20 classrooms max          1 API server: max 100-200 concurrent requests
- 5-10 concurrent users          In-memory profiles: ~5000 max
- ~50,000 rows/day               Local snapshots: ~1GB max storage
- ~50 detections/camera/day
```

```
TARGET (Scaled):
↓ ↓ ↓ ↓ ↓ ↓ ↓
POSTGRES:                        ARCHITECTURE:
- PostgreSQL: 10,000+ concurrent - 16 worker nodes (gRPC-based)
- Redis: profile cache           - PostgreSQL primary + 4 read replicas
- S3: unlimited snapshots        - 5-10 API servers (load balanced)
- 500+ cameras / 300k rows/day   - Multi-region support
```

---

## What Needs to Change: Component-by-Component

| Component | Current | Change Required | Effort | Impact |
|-----------|---------|-----------------|--------|--------|
| **Database** | SQLite | → PostgreSQL | 🟢 Low | CRITICAL |
| **Profile Cache** | In-memory dict | → Redis | 🟢 Low | HIGH |
| **Deduplication** | In-memory cache | → Redis | 🟢 Low | HIGH |
| **Snapshots** | Local filesystem | → AWS S3 | 🟡 Medium | MEDIUM |
| **Camera Processing** | 1 server | → Worker pool (gRPC) | 🔴 High | CRITICAL |
| **API Server** | Single instance | → 3-5 instances + Nginx | 🟡 Medium | MEDIUM |
| **Analytics** | Live queries | → Materialized views | 🟡 Medium | LOW |

---

## Phased Implementation

### **MIN** (Weeks 1-3): Get to 50-100 classrooms

✅ **Phase 1: PostgreSQL** (Week 1)
- Replace SQLite with AWS RDS PostgreSQL
- Add connection pool (asyncpg)
- 1 engineer, minimal code changes
- Result: Supports 100+ concurrent DB connections

✅ **Phase 2A: Redis for caching** (Week 2)
- Move profile dictionary to Redis
- Move deduplication cache to Redis
- 1 engineer, 3-4 existing changes places
- Result: Zero database query load on profiles

✅ **Phase 2B: S3 for snapshots** (Week 2)
- Replace local file saves with S3 upload
- 1 engineer, 3-line code changes in cctv_recognition.py
- Result: Unlimited scalable storage

**Cost:** $80-100/month, **Supports:** 50-100 classrooms

---

### **OPT** (Weeks 4-7): Scale to 250-350 classrooms

✅ **Phase 3: Worker Nodes** (Weeks 3-4)
- Distribute cameras across 8-16 worker nodes
- Each worker processes 20-30 cameras independently
- gRPC for hub-worker communication
- 2 engineers, significant refactoring
- Result: Scales to 300+ cameras/streams

✅ **Phase 4: API Load Balancing** (Week 5)
- 3-5 API instances behind Nginx
- Sticky sessions for WebSocket streams
- 1 engineer, Docker + nginx config
- Result: Handles 1000s of dashboard users

✅ **Phase 5: Analytics Rollups** (Week 6)
- PostgreSQL materialized views (hourly/daily aggregates)
- 1 engineer, SQL + cron job
- Result: Dashboard queries 100× faster (5s → 50ms)

**Cost:** $300-400/month, **Supports:** 250-350 classrooms

---

### **MAX** (Weeks 8-10): Scale to 500+ classrooms

✅ **Phase 6: Multi-Region** (Weeks 7-10)
- Primary datacenter + 2 regional replicas
- Each region has local DB replica + Redis cache
- Cross-region replication
- 2 engineers, DevOps work
- Result: Global deployment with local latency

**Cost:** $600/month, **Supports:** 500+ classrooms worldwide

---

## Decision Tree

```
START HERE:
├─ "I need production NOW for 50K students (50-100 classrooms)"
│  └─ Do PHASES 1, 2A, 2B (3 weeks) → $80/mo
│
├─ "I need to scale to 10K+ students (300+ classrooms)"
│  └─ Do PHASES 1-5 (6 weeks) → $300/mo
│
└─ "I need global deployment (500K+ students, 500+ classrooms)"
   └─ Do ALL PHASES (10 weeks) → $600/mo
```

---

## Current System Performance (for reference)

| Metric | Current | With Phase 1 | With Phase 1-5 |
|--------|---------|-------------|----------------|
| Database connections | 20 | 100 | 200+ |
| Concurrent API users | 50-100 | 500-1000 | 5000+ |
| Camera streams | 5-10 | 50-100 | 300-500 |
| Query latency (avg) | 50-200ms | 5-50ms | 1-10ms |
| Snapshot storage | 50GB (limit) | Unlimited | Unlimited |
| Daily rows | 50K | 500K | 2M+ |
| Uptime | 99% | 99.95% (multi-AZ) | 99.99% (multi-region) |

---

## What Does Each Phase Unlock?

```
CURRENT:
┌─────────────────────────┐
│ 1 Server (SQLite)       │
│ 5-10 cameras            │
│ 1-2K students max       │
└─────────────────────────┘
         ↓ (Phase 1: PostgreSQL)
┌─────────────────────────┐
│ PostgreSQL + Redis      │
│ 50-100 cameras          │
│ 5-10K students          │ ← QUICK WIN (3 weeks)
└─────────────────────────┘
         ↓ (Phases 2-3: Workers + API Load Balance)
┌─────────────────────────┐
│ Worker Pool             │
│ 300-500 cameras         │
│ 50-100K students        │ ← PRODUCTION SCALE (6 weeks)
└─────────────────────────┘
         ↓ (Phases 4-6: Multi-region)
┌─────────────────────────┐
│ Global Deployment       │
│ 500+ cameras            │
│ 500K+ students          │ ← ENTERPRISE SCALE (10 weeks)
└─────────────────────────┘
```

---

## Recommendation

**START WITH PHASE 1 (PostgreSQL + Redis + S3)**

✅ **Why:**
- Minimal code changes (mostly config)
- Gives you 5-10× capacity jump (10→50-100 classrooms)
- Can always add worker nodes later
- Cost only $80/month
- Timeline: 3 weeks with 1 engineer

✅ **How it works:**
1. Week 1: AWS RDS + asyncpg (PostgreSQL driver)
2. Week 2: Redis profile cache + deduplication
3. Week 2: S3 snapshots + boto3
4. Week 3: Testing + validation

✅ **Results:**
- Supports 50-100 classrooms immediately
- Path to 500+ with phases 3-6 later
- Zero downtime migration (gradual)

---

## Next Action

**Which path do you want to take?**

A) **QUICK WIN** (3 weeks, $80/mo)
   - Phase 1 only: PostgreSQL + Redis + S3
   - Get to 50-100 classrooms
   
   → Next: I'll create [PHASE_1_IMPLEMENTATION_GUIDE.md]

B) **PRODUCTION SCALE** (6 weeks, $300/mo)
   - Phases 1-5: Pull worker nodes, load balance, analytics
   - Get to 300+ classrooms
   
   → Next: I'll create detailed implementation docs for each phase

C) **ENTERPRISE SCALE** (10 weeks, $600/mo)
   - All 7 phases: Multi-region, global deployment
   - Get to 500+ classrooms
   
   → Next: Full architecture design docs + DevOps setup

D) **CUSTOM** — Tell me your constraints (budget, time, student count) and I'll tailor a plan
