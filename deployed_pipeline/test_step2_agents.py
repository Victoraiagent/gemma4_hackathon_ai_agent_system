import pytest
import sqlite3
import os
from unittest.mock import MagicMock, patch
from step1_data import setup_database
from step2_agents import process_unanalyzed_news

TEST_DB = "test_ct_fias.db"

@pytest.fixture
def db_setup():
    setup_database(TEST_DB)
    yield TEST_DB
    if os.path.exists(TEST_DB):
        try:
            os.remove(TEST_DB)
        except OSError:
            pass

def insert_mock_news(db_path, ticker, headline, processed=0):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO biotech_pharma_news (ticker, headline, content, source_url, published_date, ai_processed) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (ticker, headline, "Sample content", "http://test.com", "2023-10-27 10:00:00", processed)
    )
    conn.commit()
    news_id = cursor.lastrowid
    conn.close()
    return news_id

def test_process_unanalyzed_news_no_pending(db_setup):
    insert_mock_news(db_setup, "BIIB", "Biogen Success", processed=1)
    processed_count = process_unanalyzed_news(db_setup)
    assert processed_count == 0
    
    conn = sqlite3.connect(db_setup)
    report_count = conn.execute("SELECT COUNT(*) FROM analysis_reports").fetchone()[0]
    conn.close()
    assert report_count == 0

def test_process_unanalyzed_news_success(db_setup):
    news_id = insert_mock_news(db_setup, "MRNA", "Moderna Breakthrough", processed=0)
    
    with patch('crewai.Crew') as MockCrew, \
         patch('crewai.Agent'), \
         patch('crewai.Task') as MockTask:
        
        # Configure Task mock to return a string for .output.raw
        mock_task_instance = MockTask.return_value
        mock_task_instance.output.raw = "Regulatory summary for MRNA."
        
        mock_crew_instance = MockCrew.return_value
        mock_crew_instance.kickoff.return_value = "Final: Comprehensive report on Moderna."
        
        processed_count = process_unanalyzed_news(db_setup)
        assert processed_count == 1
        
        conn = sqlite3.connect(db_setup)
        cursor = conn.cursor()
        
        news_status = cursor.execute("SELECT ai_processed FROM biotech_pharma_news WHERE id = ?", (news_id,)).fetchone()[0]
        assert news_status == 1
        
        report = cursor.execute("SELECT ticker, final_markdown FROM analysis_reports WHERE news_id = ?", (news_id,)).fetchone()
        assert report is not None
        assert report[0] == "MRNA"
        assert "Comprehensive report" in str(report[1])
        
        conn.close()

def test_process_unanalyzed_news_multiple_items(db_setup):
    tickers = ["VRTX", "GILD", "SGEN"]
    for t in tickers:
        insert_mock_news(db_setup, t, f"News for {t}", processed=0)
    
    with patch('crewai.Crew') as MockCrew, \
         patch('crewai.Agent'), \
         patch('crewai.Task') as MockTask:
        
        mock_task_instance = MockTask.return_value
        mock_task_instance.output.raw = "Mocked task summary"
        
        mock_crew_instance = MockCrew.return_value
        mock_crew_instance.kickoff.return_value = "Mocked analysis result"
        
        processed_count = process_unanalyzed_news(db_setup)
        assert processed_count == 3
        
        conn = sqlite3.connect(db_setup)
        unprocessed = conn.execute("SELECT COUNT(*) FROM biotech_pharma_news WHERE ai_processed = 0").fetchone()[0]
        reports_count = conn.execute("SELECT COUNT(*) FROM analysis_reports").fetchone()[0]
        conn.close()
        
        assert unprocessed == 0
        assert reports_count == 3
