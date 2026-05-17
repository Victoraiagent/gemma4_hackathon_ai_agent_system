import os
import logging
from dagster import build_asset_context
from dagster_pipeline import database_setup, ingested_news, analyzed_reports, delivery_status, PipelineConfig

def run_pipeline_test():
    config = PipelineConfig()
    
    print("--- Starting Pipeline Execution ---")
    
    context = build_asset_context()
    
    # Step 0: Setup
    setup_ok = database_setup(context, config)
    print(f"Database setup: {setup_ok}")
    
    # Step 1: Ingest
    news_count = ingested_news(context, config, setup_ok)
    print(f"Ingested news: {news_count}")
    
    # Step 2: Analyze
    reports_count = analyzed_reports(context, config, news_count)
    print(f"Analyzed reports: {reports_count}")
    
    # Step 3: Deliver
    delivery_files = delivery_status(context, config, reports_count)
    print(f"Generated PDFs: {len(delivery_files)}")
    for f in delivery_files:
        print(f" - {f}")
    
    print("--- Pipeline Execution Finished ---")
    print(f"Check run.log for details.")

if __name__ == "__main__":
    run_pipeline_test()
