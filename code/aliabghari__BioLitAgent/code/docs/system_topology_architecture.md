# BioLitAgent: System Topology & Architecture Specification

## 1. High-Level System Architecture

BioLitAgent is an autonomous multi-agent monitoring, human-in-the-loop validation, and report synthesis platform designed for biopharmaceutical bioprocess and protein production intelligence.

```mermaid
flowchart TD
    subgraph ExternalSources["External Ingestion Feeds"]
        PubMed["NCBI PubMed\n(E-utilities / MCP)"]
        bioRxiv["bioRxiv API\n(Cold Spring Harbor)"]
        FDA["FDA CBER Index\n(HTML Static)"]
        EMA["EMA Scientific Guidelines\n(Drupal 11 Portal)"]
        ICH["ICH Quality & Safety\n(Angular SPA)"]
        InboxPDF["Local inbox/\n(PDF / Patents)"]
    end

    subgraph ManagerSurface["Manager Surface Orchestrator (run_all.py)"]
        Phase1["Phase 1: Parallel Ingestion & Scouting\n(Async Subprocess Isolation)"]
        Phase2["Phase 2: Human Review Checkpoint\n(Interactive Terminal Gate)"]
        Phase3["Phase 3: Digest Generation\n(Read-Only SQLite Engine)"]
        Phase4["Phase 4: Transparency Dashboard\n(Run Audit & Metrics)"]
        Phase1 --> Phase2 --> Phase3 --> Phase4
    end

    subgraph Phase1Agents["Phase 1: Specialized Ingestion Agents"]
        LitScout["literature_scout.py\n- Esearch / Esummary\n- Deduplication Hash\n- Paraphrase Synthesis"]
        RegWatch["regulatory_watch.py\n- Playwright Headless\n- DOM Hash Change Detection\n- Document Extraction"]
        PdfIngest["pdf_ingestion.py\n- PyMuPDF Parser\n- Technical Paraphrase\n- Processed Archival"]
    end

    subgraph LLMInfrastructure["Shared LLM & Cache Infrastructure"]
        ModelCfg["config/model_config.py\nDEFAULT_MODEL = gemini-2.5-flash"]
        GeminiAPI["Google Gemini API\n(gemini-2.5-flash)"]
        DryRunCache[("storage/dry_run_llm_cache.json\n(Stable SHA-256 Keyed Cache)")]
        ModelCfg --> GeminiAPI
        LitScout <--> DryRunCache
        RegWatch <--> DryRunCache
        LitScout --> GeminiAPI
        RegWatch --> GeminiAPI
        PdfIngest --> GeminiAPI
    end

    subgraph StagingQueue["Staging Queue"]
        PendingItems[("storage/pending_items.jsonl\n(JSON Lines Staging Queue)")]
    end

    subgraph HITLGate["Phase 2: Human-in-the-Loop Validation"]
        ReviewCheckpoint["review_checkpoint.py\n- 12-Tag Keyword Auto-Classifier\n- Per-Item Tag / Title Editor\n- Reject Logging\n- Strict 'CONFIRM' Write Barrier"]
        Taxonomy[("config/chapter_taxonomy.json\n(12 Intrinsic Domain Tags)")]
        Taxonomy --> ReviewCheckpoint
    end

    subgraph PermanentStorage["Phase 2: Permanent Audit & Knowledge Store"]
        KnowledgeDB[("storage/knowledge_store.db\n(SQLite: approval_runs,\nknowledge_items)")]
        RejectedLog[("storage/rejected_items_log.jsonl\n(Audit Trail of Discarded Items)")]
        StateFiles[("State Files:\nregulatory_state.json\nliterature_state.json")]
    end

    subgraph ReportingEngine["Phase 3: Client Deliverables Engine"]
        ReportGen["report_generator.py\n- PRAGMA query_only = ON\n- 12-Tag to 8-Chapter Mapper\n- Delta 'What's New' Query"]
        TemplateFile["templates/digest_template.docx\n(Corporate Word Template)"]
        LastReportState[("storage/last_report.json\n(Timestamp Cutoff State)")]
        DocxReport["reports/biolitagent_digest_YYYYMMDD.docx\n(Client-Ready Word Digest)"]
        TemplateFile --> ReportGen
        LastReportState <--> ReportGen
        ReportGen --> DocxReport
    end

    %% Flow connections
    PubMed --> LitScout
    bioRxiv --> LitScout
    FDA --> RegWatch
    EMA --> RegWatch
    ICH --> RegWatch
    InboxPDF --> PdfIngest

    Phase1 --> LitScout
    Phase1 --> RegWatch
    Phase1 --> PdfIngest

    LitScout --> PendingItems
    RegWatch --> PendingItems
    PdfIngest --> PendingItems

    PendingItems --> ReviewCheckpoint
    ReviewCheckpoint -- "On Reviewer 'CONFIRM'" --> KnowledgeDB
    ReviewCheckpoint -- "On Reviewer 'Reject'" --> RejectedLog
    Phase1 -- "On Run Completion" --> StateFiles

    Phase3 --> ReportGen
    KnowledgeDB -. "Read-Only Select" .-> ReportGen
```

---

## 2. End-to-End Pipeline Execution Sequence

```mermaid
sequenceDiagram
    autonumber
    actor Reviewer as Human Reviewer
    participant Manager as Manager Surface (run_all.py)
    participant Scout as literature_scout.py
    participant Watch as regulatory_watch.py
    participant Staging as pending_items.jsonl
    participant HITL as review_checkpoint.py
    participant DB as knowledge_store.db
    participant Report as report_generator.py
    participant Docx as biolitagent_digest_<date>.docx

    Manager->>Scout: Spawn async subprocess (parallel)
    Manager->>Watch: Spawn async subprocess (parallel)
    par Literature Ingestion
        Scout->>Scout: Query PubMed / bioRxiv
        Scout->>Scout: Deduplicate vs literature_state.json
        Scout->>Scout: Synthesize technical paraphrase (Gemini)
        Scout->>Staging: Append verified records
    and Regulatory Ingestion
        Watch->>Watch: Playwright scrape FDA / EMA / ICH
        Watch->>Watch: Compare SHA-256 DOM text hashes
        Watch->>Watch: LLM structured extraction (Gemini)
        Watch->>Staging: Append verified records
    end
    Scout-->>Manager: Return exit code 0
    Watch-->>Manager: Return exit code 0

    Manager->>HITL: Launch interactive review checkpoint (Phase 2)
    HITL->>Staging: Read pending items
    HITL->>Reviewer: Display grouped overview (12 chapter tags)
    loop Per Item Review
        Reviewer->>HITL: [A] Approve / [E] Edit tag / [R] Reject / [B] Batch
        HITL->>HITL: Update in-memory staged item
    end
    HITL->>Reviewer: Request explicit typed confirmation ("CONFIRM")
    Reviewer->>HITL: Types "CONFIRM"
    HITL->>DB: Atomic INSERT into approval_runs & knowledge_items
    HITL->>HITL: Append rejected items to rejected_items_log.jsonl
    HITL->>Staging: Purge approved/rejected items
    HITL-->>Manager: Return approval statistics (Approved, Rejected, Skipped)

    alt Approved Count > 0
        Manager->>Report: Execute digest generation (Phase 3)
        Report->>DB: Query approved items (PRAGMA query_only = ON)
        Report->>Report: Map 12 tags into 8 report chapters
        Report->>Docx: Generate Word document (.docx)
        Report->>Report: Update last_report.json cutoff timestamp
        Report-->>Manager: Return report path & exit code 0
    end

    Manager->>Reviewer: Print Run Summary & Transparency Dashboard
```

---

## 3. Layered Architectural Decomposition

### Layer 1: Ingestion & Surface Intelligence
1. **`agents/literature_scout.py`**:
   - Interfaces: NCBI E-utilities (Esearch, Esummary) via HTTP REST with fallback to MCP server protocol (`mcp_config.json`). BioRxiv REST API.
   - Resilience: Exponential backoff retry loop (`2s`, `4s`, `8s`) for HTTP 429 and 503 errors.
   - Deduplication: Maintains `storage/literature_state.json` containing previously harvested PMIDs and DOIs.
   - Paraphrasing: Generates original, concise 2–3 sentence technical syntheses using `DEFAULT_MODEL` with strict constraints prohibiting verbatim text.
2. **`agents/regulatory_watch.py`**:
   - Interfaces: FDA CBER, EMA, and ICH regulatory index pages.
   - SPA Rendering: Headless Chromium via Playwright for JavaScript SPAs (ICH Angular portal); high-throughput HTTPX for static Drupal/HTML pages (FDA, EMA).
   - Change Detection: SHA-256 text normalization hashing against `storage/regulatory_state.json`.
   - Structured Output: Uses `gemini-2.5-flash` with strict JSON schema definition (`title`, `publication_date`, `url`, `description`, `url_unknown`, `date_unknown`).
3. **`agents/pdf_ingestion.py`**:
   - Interfaces: Local filesystem inbox (`inbox/*.pdf`).
   - Parsing: PyMuPDF / pdfplumber text extraction.
   - Lifecycle: Extracted files are safely archived to `inbox/processed/`.

---

### Layer 2: LLM Engine & Quota Preservation
- **Central Model Configuration (`config/model_config.py`)**:
  - `DEFAULT_MODEL = "gemini-2.5-flash"`.
  - Single source of truth imported by all agents to ensure predictable rate-limits and uniform schema capabilities.
- **Dry-Run Cache (`storage/dry_run_llm_cache.json`)**:
  - Stable SHA-256 keys derived from page content hashes or `query_id:title:source_text`.
  - When `--dry-run` is active, checks cache before invoking external APIs.
  - Zero API calls consumed on repeated validation runs.

---

### Layer 3: Taxonomy & Human-in-the-Loop Gate
- **12-Tag Bioprocess Taxonomy (`config/chapter_taxonomy.json`)**:
  1. `host_expression`
  2. `upstream_process`
  3. `downstream_process`
  4. `analytical_characterization`
  5. `qbd_control_strategy`
  6. `hybrid_modeling`
  7. `gmp_manufacturing`
  8. `facility_aseptic`
  9. `regulatory_cmc`
  10. `microbiome_platform_science`
  11. `capa_rca`
  12. `emerging_topics`
- **Review Checkpoint (`agents/review_checkpoint.py`)**:
  - Keyword classification matches items against taxonomy definitions.
  - Interactive CLI allows reviewers to edit title, description, reviewer notes, and chapter tags before approving.
  - **Irreversible Write Gate**: Disk operations require typing the exact word `CONFIRM`.

---

### Layer 4: Storage & Reporting Engine
- **Permanent Knowledge Store (`storage/knowledge_store.db`)**:
  - `approval_runs`: Audit history tracking session start/finish, duration, items approved, rejected, and skipped.
  - `knowledge_items`: Append-only table (`store_id`, `pending_id` UNIQUE, `run_id`, `source_type`, `chapter_tag`, `title`, `description`, `metadata_json`, `reviewer_note`, `reviewed_at`, `reviewer_action`).
- **Word Report Synthesis (`agents/report_generator.py`)**:
  - SQLite opened in strict read-only mode (`PRAGMA query_only = ON`).
  - Chapter aggregation:
    - **Chapter 1**: Executive Summary — What's New (Time-filtered delta since `storage/last_report.json`).
    - **Chapter 2**: Host, Plasmid & Expression System Development (`host_expression`).
    - **Chapter 3**: Process Development — Upstream & Downstream (`upstream_process`, `downstream_process`).
    - **Chapter 4**: Characterization, QbD & Control Strategy (`analytical_characterization`, `qbd_control_strategy`).
    - **Chapter 5**: Digital Process Tools & Hybrid Modeling (`hybrid_modeling`).
    - **Chapter 6**: GMP, Facility & Quality Systems (`gmp_manufacturing`, `facility_aseptic`).
    - **Chapter 7**: Regulatory, CMC & Platform Science (`regulatory_cmc`, `microbiome_platform_science`).
    - **Chapter 8**: CAPA, Root Cause Analysis & Emerging Topics (`capa_rca`, `emerging_topics`).
  - Output: Formatted `.docx` document based on `templates/digest_template.docx`.
