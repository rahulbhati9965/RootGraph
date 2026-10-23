# RootGraph 🚀
> **AI-Powered Distributed Systems Incident Intelligence Platform**

TracePilot is an agentic incident copilot that diagnoses cascading failures in distributed microservice architectures. By combining **GraphRAG**, **LangGraph**, the **Model Context Protocol (MCP)**, and distributed systems engineering patterns, TracePilot autonomously correlates logs, metrics, traces, and service topologies to pinpoint root causes without hallucinations.

---

## ⚡ Architecture at a Glance

- **AI Orchestration**: LangGraph cyclic `StateGraph` with explicit evidence validation loops.
- **Topology & GraphRAG**: Neo4j / NetworkX graph traversal for service dependency chains and blast radius analysis.
- **Semantic Memory**: pgvector / ChromaDB for embedding runbooks and historical post-mortems.
- **Diagnostic Engine**: Standardized Model Context Protocol (MCP) server with strictly typed, read-only tools.
- **Distributed Backend**: FastAPI, Redis Streams (asynchronous ingestion), SHA-256 idempotency deduplication, and atomic leases.
- **Observability**: OpenTelemetry-compatible traces, spans, and correlation ID propagation.

---

## 📁 Repository Layout

```text
TracePilot/
├── app/
│   ├── core/           # Settings & configuration (Adapter pattern)
│   ├── schemas/        # Pydantic schemas (telemetry, incidents, investigations)
│   └── services/       # Data loaders & business logic
├── data/
│   ├── topology/       # Microservice dependency graph (12 services across 4 regions)
│   ├── telemetry/      # 48-span distributed trace waterfalls, metrics & correlated logs
│   ├── runbooks/       # Operational runbooks (e.g. RUNBOOK-PAY-04.md)
│   └── postmortems/    # Historical incident post-mortems (e.g. INC-2024-11.md)
├── tests/              # Verification test suite
├── docker-compose.yml  # Multi-container production deployment
├── requirements.txt    # Python dependencies
└── .env.example        # Environment configuration
```

---

## 🛠️ Quickstart

### 1. Virtual Environment Setup
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Run Verification Tests
```powershell
pytest -v tests/test_phase1_telemetry.py
```

### 3. Production Multi-Container Run (Docker)
```powershell
docker compose up -d
```
