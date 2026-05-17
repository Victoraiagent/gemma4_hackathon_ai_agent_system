import os
from typing import List
from dagster import asset, Config, Definitions, RetryPolicy, AssetExecutionContext, ScheduleDefinition, define_asset_job

import step1_data
import step2_agents
import step3_delivery
import logging

# Configure logging to run.log
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("run.log", mode="a"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("pipeline_orchestrator")

class PipelineConfig(Config):
    db_path: str = os.getenv("PIPELINE_DB_PATH", "ct_fias.db")
    tickers: List[str] = []
    output_dir: str = os.getenv("PIPELINE_OUTPUT_DIR", "reports")

def get_active_tickers(config: PipelineConfig) -> List[str]:
    tickers = config.tickers
    if not tickers and os.path.exists("tickers.txt"):
        with open("tickers.txt", "r") as f:
            tickers = [line.strip() for line in f if line.strip()]
    if not tickers:
        tickers = ["PFE", "MRNA", "BNTX", "VRTX", "GILD", "AMGN"] # Default fallback
    return tickers

@asset(
    retry_policy=RetryPolicy(max_retries=3),
    description="Step 1: Setup database schema"
)
def database_setup(context: AssetExecutionContext, config: PipelineConfig) -> bool:
    context.log.info("Starting Step 0: Database Setup")
    step1_data.setup_database(config.db_path)
    context.log.info("Database Setup completed")
    return True

@asset(
    retry_policy=RetryPolicy(max_retries=3),
    description="Step 1: Scrapes news and stores in SQLite."
)
def ingested_news(context: AssetExecutionContext, config: PipelineConfig, database_setup: bool) -> int:
    context.log.info("Starting Step 1: News Ingestion")
    tickers = get_active_tickers(config)
    
    count = step1_data.ingest_daily_news(tickers, config.db_path)
    context.log.info(f"News Ingestion completed. Added {count} new items for tickers: {tickers}")
    if count == 0:
        context.log.info("No new clinical news found. Downstream tasks will run but process 0 items.")
    return count

@asset(
    retry_policy=RetryPolicy(max_retries=2),
    description="Step 2: Runs the CrewAI agentic pipeline for unprocessed news."
)
def analyzed_reports(context: AssetExecutionContext, config: PipelineConfig, ingested_news: int) -> int:
    context.log.info("Starting Step 2: Agentic Analysis")
    count = step2_agents.process_unanalyzed_news(config.db_path)
    context.log.info(f"Agentic Analysis completed. Processed {count} items.")
    return count

@asset(
    retry_policy=RetryPolicy(max_retries=3),
    description="Step 3: Converts reports to PDF."
)
def delivery_status(context: AssetExecutionContext, config: PipelineConfig, analyzed_reports: int) -> List[str]:
    context.log.info("Starting Step 3: PDF Delivery")
    tickers = get_active_tickers(config)
    files = step3_delivery.generate_individual_pdfs(config.db_path, config.output_dir, tickers=tickers)
    context.log.info(f"PDF Delivery completed. Generated {len(files)} files for tickers: {tickers}")
    return files

clinical_news_job = define_asset_job("clinical_news_job", selection="*")
clinical_news_schedule = ScheduleDefinition(
    job=clinical_news_job,
    cron_schedule="0 8 * * 1-5", # 8:00 AM on weekdays
)

defs = Definitions(
    assets=[database_setup, ingested_news, analyzed_reports, delivery_status],
    jobs=[clinical_news_job],
    schedules=[clinical_news_schedule]
)
