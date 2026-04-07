# TraceFabric

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Rust](https://img.shields.io/badge/Rust-1.77+-orange.svg)](https://www.rust-lang.org/)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15+-blue.svg)](https://www.postgresql.org/)

## Table of Contents

- [About](#about)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Documentation](#documentation)
- [Getting Started](#getting-started)
- [Roadmap](#roadmap)
- [Ethics](#ethics)
- [License](#license)

## About

A distributed, high-speed lead ingestion and deployment engine built for Foward Deployed AI Engineering.

TraceFabric bridges the gap between traditional machine learning and advanced LLM orchestration. It is an asynchronous, multi-agent pipeline designed to identify localized digital service gaps, evaluate their economic viability, and autonomously deploy deterministic software solutions.

## Key Features

* **Mass Ingestion Engine (Rust):** Memory-safe, high-concurrency DOM parsing built on `tokio` and `reqwest`.
* **ZeroMQ IPC Bridge:** Sub-millisecond inter-process communication using strict Protobuf serialization, bypassing standard HTTP/REST overhead.
* **$0.00 ML Cost-Gating:** A local XGBoost gatekeeper filters leads for economic viability before any frontier LLM tokens are spent.
* **"No-Drop" Data Strategy:** All data flows into a central PostgreSQL warehouse to build a Teacher-Student ML self-reinforcing cycle for future model training.

## Architecture


## Documentation

Read the below links for additional information.

[System Architecture](docs/ARCHITECTURE.md)

## Getting Started

### Prerequisites

* Docker & Docker Compose
* Rust & Cargo (Latest Stable)
* Python 3.11+
* `protoc` (Protocol Buffer Compiler)

### Installation

To install and run TraceFabric, follow these steps:

1. Clone the TraceFabric repository:

```bash
git clone https://github.com/tesahe/trace-fabric.git
```

2. Navigate to the project directory and start the data infrastructure:

```
cd tracefabric
docker-compose up -d
```

3. Initialize the Python Logic Engine (ML Gatekeeper / LLM Router):

```
cd logic-engine
pip install -r requirements.txt
uvicorn app.main:app --reload
```

4. In a new terminal window, start the Rust Ingestion Engine to begin feeding data across the IPC bridge:

```
cd scraper-engine
cargo run --release
```

## Roadmap

* **Phase 1:** `tokio` Crawler + ZeroMQ/Protobuf IPC Bridge benchmarked.
* **Phase 2:** XGBoost routing logic + FastAPI integration live.
* **Phase 3:** Deterministic JSON output generation via Instructor/Outlines.
* **Phase 4:** CI/CD pipelines, TBD.

## Ethics

Trace Fabric is designed to be a responsible web citizen with the following guardrails hardcoded into the architecture.

1. **User-Agent Transparency:** Every request identifies as `TraceFabric/1.0 (+https://github.com/tesahe/trace-fabric)`
2. **Robots.txt Compliance:** The Rust ingestion layer utilizes a `robots.txt` parser to respect crawl exclusions.
3. **Rate-Limiting:** Implements a Token Bucket algorithm via the Governor crate to prevent server strain.
4. **Data Minimization:** We only ingest structural DOM markers required for economic viability analysis; raw PII is not retained.

## License

TraceFabric is licensed under Apache License 2.0.  See the `LICENSE` file for more information.
