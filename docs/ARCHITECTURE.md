# TraceFabric Architecture

## Overview

TraceFabric is split into an ingestion service and an evaluation service connected by a typed async boundary.

- The Rust `scraper-engine` owns discovery, fetch, compliance checks, and homepage artifact collection.
- Protobuf and ZeroMQ provide the service boundary and lead payload transport.
- The Python `logic-engine` owns deterministic screening, staged LLM evaluation, and persistence.
- Postgres stores the canonical lead record and future teacher-label artifacts.

## Runtime Topology

### Ingestion Layer

The Rust service is responsible for:

- Turning a small niche-and-location query into candidate websites
- Applying compliance-aware fetch logic
- Capturing homepage artifacts and metadata
- Building a typed `RawLead` payload for downstream evaluation

### Transport Layer

The transport boundary is intentionally explicit:

- Protobuf defines the message contract
- ZeroMQ provides low-friction async IPC between services
- The payload boundary separates data collection from inference and persistence concerns

### Evaluation Layer

The Python service is responsible for:

- Tier 0 heuristic scanning
- Deterministic evidence-based lead scoring
- Optional Tier 1 constrained LLM validation
- Optional Tier 2 structured extraction
- Persistence of workflow state and outputs

### Persistence Layer

Postgres stores:

- Crawl provenance and metadata
- Extracted website artifacts
- Deterministic evidence
- Qualification state and rejection reasons
- Structured LLM payloads where applicable

## Pipeline Stages

1. Discovery
   Produce a small set of candidate business websites.
2. Compliance and fetch
   Check crawl eligibility and fetch homepage/root artifacts.
3. Payload assembly
   Package crawl results into a typed lead message.
4. Tier 0 heuristic scan
   Reject obvious junk or campaign mismatch early.
5. Deterministic evaluation
   Extract evidence-backed business and website signals.
6. Tier 1 constrained validation
   Optionally verify that the candidate appears to be a real local business.
7. Tier 2 structured extraction
   Optionally produce a constrained structured lead assessment.
8. Persistence
   Save the lead record as an auditable dataset artifact.

## Service Boundaries

TraceFabric’s main design decision is to keep the boundaries clear:

- Rust handles external I/O and crawl-heavy work
- Python handles evaluation logic and orchestration
- The transport contract is typed rather than inferred at runtime
- Persistence happens after structured evaluation state is known

This separation makes the system easier to reason about in interviews and easier to extend without merging scraping, evaluation, and storage into one process.

## Failure Boundaries

High-level failure handling is currently designed around staged degradation:

- Discovery failure prevents candidate generation but does not invalidate the architecture
- Compliance rejection still produces a meaningful excluded lead record
- Deterministic rejection avoids unnecessary LLM calls
- Tier 1 failure should fail soft rather than block the pipeline
- Tier 2 failure should preserve deterministic results even if richer extraction is unavailable

## Architectural Tradeoffs

- Small-batch discovery was chosen over high-volume ingestion
- Typed IPC was chosen over direct HTTP coupling between services
- Staged evaluation was chosen over a single large model pass
- Dataset creation was prioritized over early student-model implementation

## Related Diagrams

- [System Context Diagram](diagrams/system-context.md)
- [Pipeline Sequence Diagram](diagrams/pipeline-sequence.md)
- [Runtime Component Diagram](diagrams/runtime-components.md)
