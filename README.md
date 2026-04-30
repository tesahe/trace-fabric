# TraceFabric

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Rust](https://img.shields.io/badge/Rust-1.85+-orange.svg)](https://www.rust-lang.org/)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-blue.svg)](https://www.postgresql.org/)
[![Status](https://img.shields.io/badge/Status-Active%20Portfolio%20Project-yellow.svg)](#project-status)

## Table of Contents

- [About](#about)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Documentation](#documentation)
- [Project Status](#project-status)
- [Local Development](#local-development)
- [Roadmap](#roadmap)
- [Ethics](#ethics)
- [License](#license)

## About

An async lead-ingestion and evaluation engine built for operators who need an ethical, cost-disciplined way to find and qualify local business leads by analyzing real websites for customer compatibility.

TraceFabric is an asynchronous, two-service pipeline that identifies localized digital service gaps and evaluates their economic viability. It bridges deterministic evaluation and staged LLM orchestration by being cost-aware: cheap, evidence-backed deterministic checks run first, and LLM stages only run on candidates that earn the spend.

Every decision — qualified, rejected, or excluded — is persisted as a structured, teacher-labeled record. That data foundation is the basis for future student-model training, so the pipeline gets cheaper and more self-sufficient over time.

## Key Features

* **Mass Ingestion Engine (Rust):** Memory-safe, high-concurrency crawling and DOM parsing built on `tokio`, `sqlx`, and `reqwest`.
* **ZeroMQ IPC Bridge:** Sub-millisecond inter-process communication using strict Protobuf serialization, bypassing HTTP/REST overhead between services.
* **Cost-Gated LLM Cascade:** A local XGBoost gatekeeper plus deterministic evidence extraction filter leads for economic viability before any frontier LLM tokens are spent. Tier 1 constrained validation and Tier 2 structured extraction (via Instructor) run only on candidates that earn the cost.
* **"No-Drop" Data Strategy:** All leads — qualified, rejected, or excluded — flow into a central PostgreSQL warehouse to build a teacher-student self-reinforcing cycle for future local model training.

## Architecture

```mermaid
%%{init: {"theme": "neutral", "themeVariables": {"fontSize": "14px"}, "flowchart": {"curve": "basis", "padding": 20, "nodeSpacing": 80, "rankSpacing": 100}}}%%
flowchart LR
    U(["Operator"]) --> Q["Niche+Location or URL"]

    subgraph P1[Phase 1 - Rust Ingestion]
        R["scraper-engine<br/>(tokio · sqlx · governor)"]
    end

    subgraph P2[Phase 2 - Python Evaluation]
        L["logic-engine<br/>(FastAPI · Gatekeeper · LLM cascade)"]
    end

    Q --> R
    R -->|"  Protobuf over ZeroMQ  "| L
    L ==>|"  No-Drop persistence  "| DB[("PostgreSQL<br/>lead warehouse")]
    L -.->|"  structured LLM calls  "| LLM["LLM Provider"]
    F["Vite + React<br/>operator console"] --> L

    classDef default fill:#FFFFFF,stroke:#3A3A3A,stroke-width:1.5px,color:#1A1A1A
    classDef actor fill:#F5F5F5,stroke:#3A3A3A,stroke-width:1.5px,color:#1A1A1A
    classDef rust fill:#FBEFE2,stroke:#A0612A,stroke-width:1.5px,color:#5A330F
    classDef python fill:#E8F0FA,stroke:#2E5A8C,stroke-width:1.5px,color:#0F2A52
    classDef data fill:#EDEDED,stroke:#2A2A2A,stroke-width:1.5px,color:#1A1A1A
    classDef external fill:#FAFAFA,stroke:#7A7A7A,stroke-width:1.2px,stroke-dasharray:4 3,color:#3A3A3A
    classDef ui fill:#F0EAF4,stroke:#5C3A6E,stroke-width:1.5px,color:#2A1538

    class U actor
    class R rust
    class L python
    class DB data
    class LLM external
    class F ui

    style P1 fill:#FDF6EE,stroke:#C9A983,stroke-width:1px,color:#5A330F
    style P2 fill:#F2F6FB,stroke:#90AFCE,stroke-width:1px,color:#0F2A52


```

## Documentation

Read the below links for additional information.

- [System Overview](docs/OVERVIEW.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Data Model](docs/DATA_MODEL.md)
- [Evaluation Strategy](docs/EVALUATION_STRATEGY.md)
- [Frontend](docs/FRONTEND.md)
- [Roadmap](docs/ROADMAP.md)
- [Decisions (ADR log)](docs/DECISIONS.md)
- [Demo Guide](docs/DEMO.md)

## Project Status

TraceFabric is an active project demonstrating applied AI engineering across Rust, Python, and a typed IPC boundary. It is **not currently packaged for public redistribution** — there is no hosted demo, no published SDK, and no support model. The repository is open so reviewers can read the code, the architecture decisions, and the evaluation strategy alongside a live development log.

## Local Development

This section is for reviewers, contributors, and future-me. The [Documentation](#documentation) and [Architecture](#architecture) sections give the full picture without needing to run anything locally.

### Prerequisites

Versions reflect what's pinned in this repo today.

* Docker & Docker Compose
* Rust 1.85+ with Cargo (project uses edition 2024, `tokio` 1.51, `sqlx` 0.8)
* Python 3.11+ (logic-engine pins `protobuf` 6.33, `pyzmq` 27.1, `xgboost` 3.2)
* Node 20+ (frontend uses Vite 5, React 18, TypeScript 5)
* PostgreSQL 15 (provisioned via `infra/docker-compose.yml`)
* `protoc` (Protocol Buffer compiler) — required to build the Rust side

### Running locally

1. Start the data infrastructure (Postgres 15):

   ```bash
   docker compose -f infra/docker-compose.yml up -d
   ```
2. Start the Python logic-engine (deterministic eval + LLM router):

   ```bash
   cd logic-engine
   pip install -r requirements.txt
   uvicorn app.main:app --reload
   ```
3. In a new terminal, start the Rust scraper-engine (ingestion + IPC):

   ```bash
   cd scraper-engine
   cargo run --release
   ```
4. (Optional) Start the operator console:

   ```bash
   cd frontend
   npm install
   npm run dev
   ```

A walkthrough of the demo flow lives in [docs/DEMO.md](docs/DEMO.md).

## Roadmap

* **Phase 1:** `tokio` crawler + ZeroMQ/Protobuf IPC bridge benchmarked.
* **Phase 2:** Tier 0 Deterministic evidence extraction + FastAPI integration live.
* **Phase 3:** Deterministic structured-output generation via Instructor across Tier 1 and Tier 2.
* **Phase 4:** Gatekeeper-Eval CI/CD gate, OpenTelemetry tracing, teacher-label dataset export.
* **Phase 5:** XGBoost integration into Tier 0 with saturated dataset export.

See [ROADMAP.md](docs/ROADMAP.md) for detailed exit criteria and out-of-scope items.

## Ethics

TraceFabric is designed to be a responsible web citizen with the following guardrails hardcoded into the architecture.

1. **User-Agent Transparency:** Every request identifies as `TraceFabric/1.0 (+https://github.com/tesahe/trace-fabric)`.
2. **Robots.txt Compliance:** The Rust ingestion layer parses `robots.txt` and respects crawl exclusions. Disallowed sites are recorded as excluded leads and are never fetched.
3. **Rate-Limiting:** Implements a Token Bucket algorithm via the `governor` crate to prevent server strain.
4. **Data Minimization:** Only structural DOM markers required for economic viability analysis are retained; raw PII is not stored.
5. **Auditable Decisions:** Every qualification or rejection is backed by deterministic evidence and persisted alongside model outputs, so any decision can be inspected after the fact.

## License

TraceFabric is licensed under Apache License 2.0. See the `LICENSE` file for more information.
