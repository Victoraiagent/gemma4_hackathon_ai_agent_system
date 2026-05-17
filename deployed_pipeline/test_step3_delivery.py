import pytest
import sqlite3
import os
from unittest.mock import MagicMock, patch
from pathlib import Path
from step3_delivery import generate_individual_pdfs

@pytest.fixture
def mock_db_conn():
    mock_conn = MagicMock(spec=sqlite3.Connection)
    mock_cursor = MagicMock(spec=sqlite3.Cursor)
    mock_conn.cursor.return_value = mock_cursor
    return mock_conn, mock_cursor

@pytest.fixture
def temp_output_dir(tmp_path):
    reports_dir = tmp_path / "reports"
    return str(reports_dir)

def test_generate_individual_pdfs_empty_db(mock_db_conn, temp_output_dir):
    conn, cursor = mock_db_conn
    cursor.fetchall.return_value = []

    with patch("sqlite3.connect") as mock_connect:
        mock_connect.return_value.__enter__.return_value = conn
        result = generate_individual_pdfs(db_path="dummy.db", output_dir=temp_output_dir)
        
    assert result == []
    if os.path.exists(temp_output_dir):
        assert len(os.listdir(temp_output_dir)) == 0

def test_generate_individual_pdfs_single_ticker(mock_db_conn, temp_output_dir):
    conn, cursor = mock_db_conn
    cursor.fetchall.return_value = [
        ("BIIB", "# Report\nContent", "http://source.com")
    ]

    with patch("sqlite3.connect") as mock_connect:
        mock_connect.return_value.__enter__.return_value = conn
        result = generate_individual_pdfs(db_path="dummy.db", output_dir=temp_output_dir)

    assert len(result) == 1
    assert "BIIB" in result[0]
    assert os.path.exists(result[0])

def test_generate_individual_pdfs_multiple_tickers(mock_db_conn, temp_output_dir):
    conn, cursor = mock_db_conn
    cursor.fetchall.return_value = [
        ("BIIB", "# BIIB Report", "http://source.com"),
        ("VRTX", "# VRTX Report", "http://source.com"),
        ("PFE", "# PFE Report", "http://source.com"),
    ]

    with patch("sqlite3.connect") as mock_connect:
        mock_connect.return_value.__enter__.return_value = conn
        result = generate_individual_pdfs(db_path="dummy.db", output_dir=temp_output_dir)

    assert len(result) == 3
    tickers = ["BIIB", "VRTX", "PFE"]
    for ticker in tickers:
        matching_files = [p for p in result if ticker in p]
        assert len(matching_files) == 1
        assert os.path.exists(matching_files[0])

def test_generate_individual_pdfs_handles_db_error(temp_output_dir):
    with patch("sqlite3.connect", side_effect=sqlite3.OperationalError("Unable to open database")):
        result = generate_individual_pdfs(db_path="invalid.db", output_dir=temp_output_dir)
        assert result == [] # Expect empty list based on implementation try/except
