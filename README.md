<<<<<<< HEAD
# RootGraph 🛰️
> **Autonomous AI-Powered Distributed Systems Incident Intelligence Platform**
=======
# RootGraph 🚀
> **AI-Powered Distributed Systems Incident Intelligence Platform**
>>>>>>> 40be03516ea1c80e72cfff7550a1ca5adbe4cd87

[![Python Version](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-Agentic_StateGraph-1C3C3C?style=for-the-badge&logo=langchain)](https://github.com/langchain-ai/langgraph)
[![OpenTelemetry](https://img.shields.io/badge/OpenTelemetry-W3C_TraceContext-4A154B?style=for-the-badge&logo=opentelemetry)](https://opentelemetry.io)
[![Redis](https://img.shields.io/badge/Redis_Streams-Consumer_Groups-DC382D?style=for-the-badge&logo=redis&logoColor=white)](https://redis.io)
[![Neo4j](https://img.shields.io/badge/Neo4j-GraphRAG-008CC1?style=for-the-badge&logo=neo4j&logoColor=white)](https://neo4j.com)

---

## ⚡ The Problem: Cascading Microservice Outages & Alert Storms

During high-severity P0/P1 cloud outages, microservices fail in cascading chains:
- A downstream third-party partner API begins flapping with 504 timeouts.
- Upstream checkout threads exhaust their connection pools waiting on synchronous RPCs.
- Hundreds of secondary alerts flood Alertmanager across dozens of microservices within 60 seconds.
- Human Site Reliability Engineers (SREs) spend **30 to 45 minutes** manually inspecting Grafana dashboards, tracing Jaeger waterfalls, and reading runbooks.

**RootGraph eliminates this MTTR (Mean Time to Resolution) bottleneck.** 
It ingests distributed telemetry, correlates W3C traceparents, traverses dependency graphs via **Hybrid GraphRAG**, deduplicates alert storms via **SHA-256 idempotency**, and executes an autonomous **cyclic multi-agent diagnostic loop** to localize the root cause in **sub-second time ($0.17$ seconds)**.

---

## 📊 Quantitative AI Benchmark Results (`eval_harness.py`)

RootGraph includes an automated evaluation harness testing seeded enterprise outage ground-truth scenarios:

| Incident Scenario | Ingress Symptom | Ground-Truth Culprit | Localized Root Cause | Detection Time | Status |
| :--- | :--- | :--- | :--- | :---: | :---: |
| **1. European Checkout 504** | 504 Gateway Timeout Cascade | `bank-gateway` | `bank-gateway` | **0.18s** | `PASSED` |
| **2. Inventory Pool Starvation**| `RedisConnectionError` (100/100) | `inventory-service` | `inventory-service` | **0.16s** | `PASSED` |
| **3. Pricing Postgres Deadlock**| Lock Inversion (40P01) | `pricing-service` | `pricing-service` | **0.17s** | `PASSED` |

```text
===================================================================================================
• Root-Cause Localization Accuracy:  100.0% (3/3 Scenarios Correct)
• Precision / Recall / F1 Score:     1.000
• Automated Mean Time to Detect:     0.17 seconds (vs 41.8 minutes human SRE baseline)
• MTTD Reduction:                    > 99.9%
• Compute Cost per Incident:         ~10,630 tokens (~$0.015 compute cost)
===================================================================================================
```

---

## 🏛️ System Architecture

```text
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                ROOTGRAPH SYSTEM ARCHITECTURE                                    │
│                     Autonomous AI Distributed Systems Incident Intelligence                     │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘

 [ INBOUND TELEMETRY & ALERTS ]
   │  • Prometheus / Alertmanager Webhooks
   │  • OpenTelemetry Spans (W3C traceparent headers)
   │  • Microservice JSON Error Logs
   ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 1. INGESTION & IDEMPOTENCY LAYER (FastAPI + Redis Streams)                                      │
│                                                                                                 │
│   ┌───────────────────────────┐      Duplicate Alert Storms                                     │
│   │  SHA-256 Event Fingerprint │ ─────────────────────────────────► [ 409 Deduplicated / Drop ] │
│   └─────────────┬─────────────┘                                                                 │
│                 │ Unique Alert / Incident                                                       │
│                 ▼                                                                               │
│   ┌─────────────────────────────────────────────────────────────┐                               │
│   │ Redis Streams Ingestion Pipeline (Consumer Groups + DLQ)    │                               │
│   └─────────────────────────────┬───────────────────────────────┘                               │
│                                 │ Distributed Lease Lock                                        │
│                                 ▼                                                               │
│                     [ Background Engine Worker ]                                                │
└─────────────────────────────────┼───────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 2. AUTONOMOUS MULTI-AGENT REASONING ENGINE (LangGraph StateGraph)                               │
│                                                                                                 │
│        [ CLASSIFY NODE ] ──► Assesses severity (P0-P3) & failure domain                         │
│               │                                                                                 │
│               ▼                                                                                 │
│        [ TELEMETRY NODE ] ──► Analyzes RED metrics, p99 latency spikes & error ratios           │
│               │                                                                                 │
│               ▼                                                                                 │
│        [ TOPOLOGY NODE ] ──► BFS graph traversal & upstream/downstream blast radius             │
│               │                                                                                 │
│               ▼                                                                                 │
│      ┌─► [ HYPOTHESIZE NODE ] ──► Formulates causal hypotheses (Root Cause vs Victim)           │
│      │        │                                                                                 │
│      │        ▼                                                                                 │
│      │   [ EVALUATOR NODE ] ──── Confidence >= 0.80 ? ─────┐                                    │
│      │        │                                            │ (YES)                              │
│      │        │ (NO: Contradicted)                         ▼                                    │
│      └── [ PIVOT NODE ] ◄──────────── [ KNOWLEDGE NODE ] ◄─┘                                    │
│          Backtrack to downstream        Hybrid GraphRAG + BM25 Subword Match                    │
│                                                │                                                │
│                                                ▼                                                │
│                                         [ REPORT NODE ]                                         │
│                                    Compiles SRE RCA Report                                      │
└────────────────────────────────────────────────┼────────────────────────────────────────────────┘
                                                 │
                                                 ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 3. MODEL CONTEXT PROTOCOL (MCP) TOOL SERVER                                                     │
│                                                                                                 │
│   ┌───────────────────────────┐  ┌───────────────────────────┐  ┌───────────────────────────┐   │
│   │ query_metrics()           │  │ search_traces()           │  │ get_service_deps()        │   │
│   ├───────────────────────────┤  ├───────────────────────────┤  ├───────────────────────────┤   │
│   │ search_runbooks()         │  │ find_similar_incidents()  │  │ get_deployment_history()  │   │
│   └───────────────────────────┘  └───────────────────────────┘  └───────────────────────────┘   │
│                 │                                                             │                 │
│                 ▼                                                             ▼                 │
│   ┌───────────────────────────┐                                 ┌───────────────────────────┐   │
│   │ 3-State Circuit Breakers  │                                 │ Bounded Call Budgets      │   │
│   │ [ CLOSED / OPEN / HALF ]  │                                 │ (Max 15 tool calls/run)   │   │
│   └───────────────────────────┘                                 └───────────────────────────┘   │
└────────────────────────────────────────────────┼────────────────────────────────────────────────┘
                                                 │
                                                 ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 4. VISUAL SRE INCIDENT COCKPIT & ONE-CLICK REMEDIATION                                          │
│                                                                                                 │
│  • 48-Span Trace Waterfall with Critical-Path Bottleneck Highlighting                           │
│  • Interactive SVG Microservices Topology Graph (All 12 Cluster Services)                       │
│  • Live Agent Reasoning Timeline & Confidence Radial Gauges                                     │
│  • 1-Click Runbook Remediation: [ FAILOVER_GATEWAY ] [ ISOLATE_NODE ] [ SCALE_PODS ]            │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🛠️ Key Architectural Innovations

### 1. LangGraph Cyclic Evaluator-Optimizer Loop
Unlike brittle linear chains (`Prompt ➔ LLM ➔ Response`), RootGraph models the investigation as an 8-node cyclic graph:
`classify` $\to$ `telemetry` $\to$ `topology` $\to$ `hypothesize` $\to$ `evaluator` $\to$ `pivot` $\to$ `knowledge` $\to$ `report`.
If an initial hypothesis is contradicted by correlated logs, the **`pivot`** node shifts suspect weight downstream and backtracks false leads autonomously.

### 2. Hybrid GraphRAG & 1.5x Topological Boost
Pure vector embeddings fail because logs across services often share generic wording (*"Connection timed out"*). RootGraph multiplies semantic similarity by an exponential topological factor:
$$\text{Score}(s) = \mathcal{S}_{\text{semantic}}(q, \mathcal{D}_s) \times 1.5^{\text{depth}(s)}$$
Downstream root causes (`bank-gateway`) receive an exponential boost over upstream caller victims (`checkout-service`).

### 3. Model Context Protocol (MCP) Diagnostic Server
Exposes 8 strictly-typed diagnostic tools via Anthropic's official MCP standard. Outfitted with:
- **3-State Circuit Breakers** (`CLOSED` $\to$ `OPEN` $\to$ `HALF-OPEN`) to prevent overwhelming degraded microservices.
- **Bounded Call Budgets** (Max 15 total calls per investigation).

### 4. High-Throughput Alert Storm Ingestion
- **SHA-256 Event Fingerprinting**: `hash(service + alert_type + 60s_window)` prevents redundant LLM invocations during alert floods in $O(1)$ time.
- **Atomic Mutex Leases**: Prevents concurrent duplicate worker investigations.
- **Redis Streams Consumer Groups**: Supports horizontal scaling with at-least-once delivery, explicit `XACK`, and Dead Letter Queue (`DLQ`) routing.

### 5. Cyber-Emerald Interactive Incident Cockpit
A futuristic dark-mode SRE cockpit:
- Real-time 48-span trace waterfall with critical-path bottleneck isolation.
- Interactive SVG dependency graph displaying all 12 cluster microservices.
- Live AI Copilot reasoning stream and 1-click runbook remediation actions.

---

## 🌐 Simulated Cluster Topology (12 Services Across 4 Tiers)

RootGraph ships with realistic multi-region microservice telemetry:

```text
[ TIER 0: INGRESS ] ────────► [ api-gateway ] (us-east-1)
                                   │
    ┌──────────────────────────────┼──────────────────────────────┬──────────────────────────────┐
    ▼                              ▼                              ▼                              ▼
[ frontend-service ]        [ auth-service ]               [ user-service ]             [ checkout-service ] (DEGRADED)
 (us-east-1)                 (us-east-1)                    (us-east-1)                  (us-east-1)
                                                                                                 │
                          ┌───────────────────────────────┬───────────────────────────────┬──────┴────────────────────────┐
                          ▼                               ▼                               ▼                               ▼
                   [ inventory-service ]           [ pricing-service ]            [ payment-service ] (DEGRADED)  [ notification-service ]
                    (us-west-2)                     (us-west-2)                    (eu-west-1)                     (us-east-1)
                                                                                          │
                                                                           ┌──────────────┴──────────────┐
                                                                           ▼                             ▼
                                                                    [ fraud-service ]             [ bank-gateway ] (CRITICAL OUTAGE)
                                                                     (eu-west-1)                   (eu-central-1)
```

---

## 🚀 Quickstart Guide

### 1. Clone & Set Up Virtual Environment

```bash
git clone https://github.com/rahulbhati9965/RootGraph.git
cd RootGraph

# Windows (PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Run Verification Test Suite (45/45 Tests)

RootGraph operates with **Zero-Daemon Standalone Fallback** (SQLite + NetworkX + Memory) out-of-the-box:

```bash
# Windows
cmd.exe /c "set PYTHONPATH=. && .\.venv\Scripts\pytest.exe -v"

# Linux / macOS
PYTHONPATH=. pytest -v
```

### 3. Launch the Interactive Incident Cockpit

```bash
# Windows
cmd.exe /c "set PYTHONPATH=. && .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"

# Linux / macOS
PYTHONPATH=. python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

- **Interactive Incident Cockpit**: [http://127.0.0.1:8000/cockpit](http://127.0.0.1:8000/cockpit)
- **Architecture Blueprints**: [http://127.0.0.1:8000/architecture](http://127.0.0.1:8000/architecture)
- **Interactive OpenAPI Docs**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### 4. Run the Evaluation Benchmark Suite

```bash
python eval_harness.py
```

---

## 🔌 Pluggable Architecture (Zero-Daemon vs Enterprise Production)

Switch seamlessly between zero-setup offline development and live enterprise infrastructure purely via `.env`:

| Component | Standalone Local Mode (Default) | Enterprise Production Mode |
| :--- | :--- | :--- |
| **LLM Reasoning** | Local Graph Heuristics (Zero cost) | `OPENAI_API_KEY` (GPT-4o) / `ANTHROPIC_API_KEY` (Claude 3.5) |
| **Graph Database** | In-Memory NetworkX | Neo4j Enterprise Cluster (`NEO4J_URI=bolt://localhost:7687`) |
| **Event Streaming** | In-Memory Async Queue | Distributed Redis Cluster (`REDIS_URL=redis://localhost:6379/0`) |
| **Relational Storage** | Embedded SQLite (`sqlite+aiosqlite`) | PostgreSQL Cluster (`postgresql+asyncpg`) |

---

## 📖 REST API Reference

| Endpoint | Method | Description |
| :--- | :---: | :--- |
| `/api/v1/alerts` | `POST` | Ingests monitoring webhook with SHA-256 idempotency deduplication |
| `/api/v1/incidents` | `POST` | Manually triggers a high-severity incident investigation |
| `/api/v1/incidents/{id}` | `GET` | Fetches live incident status, assigned severity, and blast radius |
| `/api/v1/investigations/{id}`| `GET` | Polls asynchronous LangGraph agent investigation state |
| `/api/v1/incidents/{id}/report`| `GET` | Retrieves synthesized SRE Postmortem and root-cause verdict |
| `/api/v1/cockpit/data` | `GET` | Streams telemetry, trace waterfall spans, and 12-service DAG |
| `/api/v1/cockpit/investigate-demo`| `POST` | Dispatches autonomous LangGraph loop for custom alerts |
| `/api/v1/cockpit/remediate` | `POST` | Executes automated runbook mitigation action (e.g. circuit trip) |

---

## 📂 Project Structure

```text
RootGraph/
├── app/
│   ├── api/v1/                 # REST endpoints & Cockpit router
│   ├── backend/                # Redis Streams, SHA-256 Idempotency, Repository
│   ├── core/                   # Telemetry W3C headers & OpenTelemetry middleware
│   ├── graph/                  # NetworkX & Neo4j GraphRAG stores
│   ├── mcp/                    # Model Context Protocol server, tools & circuit breakers
│   ├── retrieval/              # Hybrid GraphRAG topological search engine
│   ├── schemas/                # Pydantic v2 schemas for telemetry & incidents
│   ├── services/               # Seed data loaders & telemetry extractors
│   ├── static/                 # Cyber-Emerald Cockpit & Architecture UI
│   ├── vector/                 # Subword vector chunker & cosine index
│   └── workflow/               # LangGraph 8-node cyclic state machine
├── data/                       # Telemetry fixtures, runbooks & postmortems
├── docs/                       # Comprehensive architecture whitepapers
├── tests/                      # Pytest suite covering all 6 phases (45 tests)
├── docker-compose.yml          # Multi-container production stack
├── eval_harness.py             # Quantitative AI SRE benchmark suite
├── requirements.txt            # Python dependencies
└── README.md
```

---

## 📜 License

Distributed under the **MIT License**. See `LICENSE` for details.
Designed and engineered with ❤️ for high-reliability distributed systems.
