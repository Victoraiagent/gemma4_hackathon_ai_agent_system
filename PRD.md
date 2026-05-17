Product Requirements Document (PRD)
Project Title: CT-FIAS (Clinical Trial Financial Impact Analysis System)
Document Status: V1 

1. Executive Summary & Primary Objective
Build an automated, test-driven data pipeline to synthesize biotech and pharmaceutical clinical news exclusively via yfinance. The system utilizes a local, multi-agent AI framework to validate media sentiment against empirical clinical science, separating "hype" from "fact," and outputs a verified, human-readable PDF financial report.

2. Functional Requirements (User Stories & Workflows)
F1. Data Ingestion & Deduplication:

The system must run a daily cron/schedule to monitor a predefined list of biotech/pharma ticker symbols via the yfinance API.

It must extract the headline, publication date, full article text (if available), and original source URL. It will focus on clinical trial related news and provide relevance ranking, only process the top 2 news per stock tickers. 

Constraint: The system must identify and discard duplicate news items (e.g., if multiple feeds push the exact same press release) using a hashing or SQLite UNIQUE constraint mechanism.

F2. Agentic Verification Pipeline (CrewAI):

Agent 1 (FDA Regulatory Expert): Consumes the raw news and assesses clinical viability, trial phases, FDA guidelines, and scientific merit.

Agent 2 (Financial Analyst): Consumes Agent 1's scientific assessment and correlates it with market mechanics to predict financial impact (bullish/bearish/neutral).

F3. Report Generation & Delivery:

The system must compile the AI analysis into a formatted PDF.

Constraint: Every analyzed news item must include a clickable hyperlink to the original yfinance source for human auditing.

3. Technical Architecture & Stack
Orchestration: Dagster (handles asset materialization, daily scheduling, and failure retries).

Intelligence: CrewAI orchestrating a local Ollama instance running the gemma4:31b model.

Storage: Local SQLite database (Structured to cache raw news, store agent reasoning metadata, and track generated report history).

Data Source: yfinance Python library exclusively.

Design Philosophy (Strict Modularity): The architecture must be decoupled. Scraper, Database Manager, AI Agent Runner, and PDF Generator must be standalone Python scripts capable of being tested individually via the CLI before being wrapped in Dagster.

4. Non-Functional Requirements (NFRs)
Privacy (Air-Gapped AI): Zero data, prompts, or telemetry may leave the local host. The LLM must run 100% locally.

System Resilience: Orchestration must feature isolation. If the LLM inference fails, times out, or hallucinates for "Ticker A", the Dagster pipeline must catch the exception, log the error, and successfully continue processing "Ticker B".

Data Integrity (Ticker Aliases): The ingestion engine must map and normalize ticker aliases (e.g., handling pre/post-merger tickers or OTC variants) to ensure accurate historical tracking.

Performance: The local inference pipeline must be optimized to prevent VRAM overflow, processing one ticker's news sequentially rather than loading all context into memory simultaneously.

5. Acceptance Criteria (Definition of Done)
[ ] The system successfully fetches daily news for 5 test tickers without throwing API rate-limit errors.

[ ] SQLite database shows no duplicate entries when the script is run twice in the same hour.

[ ] The PDF is successfully generated locally, and all source URLs are active and clickable.

[ ] Disconnecting the machine from the internet (after the yfinance fetch phase) results in a successful AI analysis, proving 100% local LLM execution.
