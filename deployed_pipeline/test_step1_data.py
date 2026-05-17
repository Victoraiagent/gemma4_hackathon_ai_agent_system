import pytest
import sqlite3
import os
from unittest.mock import MagicMock, patch
from typing import List

try:
    from step1_data import setup_database, ingest_daily_news
except ImportError:
    def setup_database(db_path):
        raise NotImplementedError("setup_database not implemented in step1_data.py")

    def ingest_daily_news(tickers, db_path):
        raise NotImplementedError("ingest_daily_news not implemented in step1_data.py")

DB_TEST_PATH = "test_ct_fias.db"

@pytest.fixture
def clean_db():
    if os.path.exists(DB_TEST_PATH):
        os.remove(DB_TEST_PATH)
    yield DB_TEST_PATH
    if os.path.exists(DB_TEST_PATH):
        try:
            os.remove(DB_TEST_PATH)
        except OSError:
            pass

def test_setup_database_schema(clean_db):
    setup_database(clean_db)
    
    with sqlite3.connect(clean_db) as conn:
        cursor = conn.cursor()
        
        cursor.execute("PRAGMA table_info(biotech_pharma_news)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        expected_columns = {
            "id": "INTEGER",
            "ticker": "TEXT",
            "headline": "TEXT",
            "content": "TEXT",
            "source_url": "TEXT",
            "published_date": "DATETIME",
            "ai_processed": "BOOLEAN"
        }
        for col, dtype in expected_columns.items():
            assert col in columns
            assert columns[col] == dtype

        cursor.execute("PRAGMA table_info(analysis_reports)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        expected_columns = {
            "id": "INTEGER",
            "news_id": "INTEGER",
            "ticker": "TEXT",
            "fda_expert_summary": "TEXT",
            "financial_impact_prediction": "TEXT",
            "final_markdown": "TEXT",
            "created_at": "DATETIME"
        }
        for col, dtype in expected_columns.items():
            assert col in columns
            assert columns[col] == dtype

@patch("yfinance.Ticker")
def test_ingest_daily_news_success(mock_ticker, clean_db):
    setup_database(clean_db)
    
    mock_instance = MagicMock()
    mock_instance.news = [
        {"title": "Clinical Trial A Shows Promise", "link": "http://1", "providerPublishTime": 1700},
        {"title": "FDA Approves Drug B", "link": "http://2", "providerPublishTime": 1701}
    ]
    mock_ticker.return_value = mock_instance
    
    tickers = ["TICK1", "TICK2"]
    count = ingest_daily_news(tickers, clean_db)
    assert count >= 2
    
    with sqlite3.connect(clean_db) as conn:
        res = conn.execute("SELECT COUNT(*) FROM biotech_pharma_news").fetchone()[0]
        assert res == 2

@patch("yfinance.Ticker")
def test_ingest_daily_news_duplicate_prevention(mock_ticker, clean_db):
    setup_database(clean_db)
    
    shared_news = [{"title": "FDA Pipeline Update 1", "link": "http://1", "providerPublishTime": 100}]
    mock_instance = MagicMock()
    mock_instance.news = shared_news
    mock_ticker.return_value = mock_instance
    
    count1 = ingest_daily_news(["TICK1"], clean_db)
    assert count1 == 1
    
    count2 = ingest_daily_news(["TICK1"], clean_db)
    assert count2 == 0
    
    count3 = ingest_daily_news(["TICK2"], clean_db)
    assert count3 == 0
    
    with sqlite3.connect(clean_db) as conn:
        res = conn.execute("SELECT COUNT(*) FROM biotech_pharma_news").fetchone()[0]
        assert res == 1

@patch("yfinance.Ticker")
def test_ingest_daily_news_resilience(mock_ticker, clean_db):
    setup_database(clean_db)
    
    mock_success = MagicMock()
    mock_success.news = [{"title": "Resilient Phase 3 Data", "link": "http://1", "providerPublishTime": 200}]
    
    mock_ticker.side_effect = [Exception("API Timeout"), mock_success]
    
    tickers = ["FAIL_TICK", "SUCCESS_TICK"]
    count = ingest_daily_news(tickers, clean_db)
    
    assert count == 1
    with sqlite3.connect(clean_db) as conn:
        res = conn.execute("SELECT COUNT(*) FROM biotech_pharma_news").fetchone()[0]
        assert res == 1
