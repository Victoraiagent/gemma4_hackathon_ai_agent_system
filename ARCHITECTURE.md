ARCHITECTURE.md: CT-FIAS (Clinical Trial Financial Impact Analysis System)
1. Context & Goals
System: An automated, test-driven data pipeline to synthesize biotech/pharma clinical news via yfinance, utilizing local AI agentic reasoning (FDA Expert & Financial Analyst) to validate claims and output individual, verified PDF reports per ticker.
Architectural Pattern: Pipe-and-Filter. The workflow is modular and strictly sequential, allowing isolated ingestion, agentic processing, and delivery phases.
Data Persistence Strategy: Local SQLite (ct_fias.db) is mandated to eliminate infrastructure overhead while maintaining strict state and caching between isolated pipeline scripts.
NFRs: 100% local inference (gemma4:31b via Ollama) for privacy. Resilience against API or LLM timeouts. Idempotent news ingestion (no duplicates).

2. Component Diagram
Code snippet
graph TD
    subgraph "Storage Layer"
        DB[(ct_fias.db - SQLite)]
        TICKERS[tickers.txt]
    end

    subgraph "Phase 1: Ingestion (step1_data.py)"
        S1[Scrape yfinance] -->|Insert/Ignore Unique| DB
    end

    subgraph "Phase 2: Agentic Layer (step2_agents.py)"
        S2_Read[Read DB: Unprocessed] --> CrewProcess
        CrewProcess --> FDA[FDA Regulatory Expert Agent]
        FDA --> FA[Financial Analyst Agent]
        FA -->|Write Final Markdown| S2_Write[Update DB]
        CrewProcess -.->|Local Inference| Ollama((Ollama: Gemma 4))
    end

    subgraph "Phase 3: Delivery (step3_delivery.py)"
        S3_Read[Read DB: Today's Reports] --> PDF[Generate Individual PDFs per Ticker]
    end

    subgraph "Phase 4: Orchestrator (dagster_pipeline.py)"
        DAG[Dagster UI & Scheduler]
        DAG -.-> S1
        DAG -.-> S2_Read
        DAG -.-> S3_Read
    end

    TICKERS --> S1
    S1 --> S2_Read
    S2_Write --> S3_Read
3. Data Models & State (CRITICAL)
The system state is strictly managed via SQLite. Agents must use this exact schema. Do not hallucinate columns.

Table: biotech_pharma_news

id (INTEGER PRIMARY KEY AUTOINCREMENT)

ticker (TEXT NOT NULL)

headline (TEXT NOT NULL UNIQUE)

content (TEXT)

source_url (TEXT NOT NULL)

published_date (DATETIME)

ai_processed (BOOLEAN DEFAULT 0)

Table: analysis_reports

id (INTEGER PRIMARY KEY AUTOINCREMENT)

news_id (INTEGER, FOREIGN KEY to biotech_pharma_news.id)

ticker (TEXT NOT NULL)

fda_expert_summary (TEXT)

financial_impact_prediction (TEXT)

final_markdown (TEXT NOT NULL)

created_at (DATETIME DEFAULT CURRENT_TIMESTAMP)

4. Strict Interfaces & Contracts
Modules must be connected using exactly these function signatures.

Script 1: step1_data.py

def setup_database(db_path: str = "ct_fias.db") -> None:

def ingest_daily_news(tickers: List[str], db_path: str = "ct_fias.db") -> int:

Contract: Must use INSERT OR IGNORE to prevent duplicates based on headline. Returns the count of new rows added.

Script 2: step2_agents.py

def process_unanalyzed_news(db_path: str = "ct_fias.db") -> int:

Contract: Queries biotech_pharma_news where ai_processed == 0. Iterates sequentially. Saves output to analysis_reports and updates ai_processed = 1. Returns count of reports generated.

Script 3: step3_delivery.py

def generate_individual_pdfs(db_path: str = "ct_fias.db", output_dir: str = "reports") -> List[str]:

Contract: Pulls completed reports for the current date. Generates one distinct PDF per ticker. Reports must include a clickable source_url. Returns a list of generated file paths.

5. Implementation Phases
Phase 1: Ingestion (step1_data.py)

[ ] Task 1.0: Write the pytest suite for database setup and duplicate-prevention logic.

[ ] Task 1.1: Implement setup_database executing the strict SQLite schema.

[ ] Task 1.2: Implement ingest_daily_news using yfinance. Ensure ticker aliases are handled and exceptions do not crash the loop.

Phase 2: Agentic Core (step2_agents.py)

[ ] Task 2.0: Write characterization/unit tests mocking the CrewAI LLM response to test database read/write updates.

[ ] Task 2.1: Configure CrewAI with local connectivity: LLM(model="ollama/gemma4:31b", base_url="http://localhost:11434").

[ ] Task 2.2: Implement process_unanalyzed_news with a sequential CrewAI process utilizing the FDA and Financial Analyst personas.

Phase 3: Delivery (step3_delivery.py)

[ ] Task 3.0: Write unit tests verifying PDF generation outputs the correct file names.

[ ] Task 3.1: Implement generate_individual_pdfs using the fpdf library to parse Markdown into formatted PDFs.

Phase 4: Pipeline Glue (dagster_pipeline.py)

[ ] Task 4.0: Write a pipeline test verifying execution order.

[ ] Task 4.1: Use Dagster @asset decorators to import the interface functions from Steps 1, 2, and 3, linking them sequentially.

6. AI Developer Directives (Mandatory Guardrails)
The Test-First Imperative: You mandate Test-Driven Development (TDD). You must write failing unit tests (e.g., using pytest) that lock in the expected behavior before writing the business logic for any Phase.

NO HALLUCINATED DEPENDENCIES: You are restricted to standard Python libraries, yfinance, sqlite3, crewai, fpdf, and dagster. Do NOT use pandas or requests for data fetching.

Discrete Unit Law: Write exactly one file at a time based on the active Phase. Do not attempt to write Phase 2 until Phase 1 is fully tested and marked complete.

VRAM Protection: In Phase 2, you must iterate over news items sequentially. Do not pass the entire database contents to the LLM context window at once.
