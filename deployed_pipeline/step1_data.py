import sqlite3
import yfinance as yf
from typing import List
import logging

logger = logging.getLogger("step1_data")

CLINICAL_KEYWORDS = [
    "clinical", "trial", "fda", "phase", "study", "data", "results", 
    "efficacy", "safety", "approval", "patient", "therapy", "treatment", "pipeline"
]

def is_clinical_news(headline: str, summary: str) -> bool:
    text = (headline + " " + summary).lower()
    return any(keyword in text for keyword in CLINICAL_KEYWORDS)

def calculate_relevance_score(headline: str, summary: str) -> int:
    """Simple heuristic to rank news relevance."""
    score = 0
    text = (headline + " " + summary).lower()
    high_impact = ["fda", "phase 3", "approval", "results", "milestone", "primary endpoint", "breakthrough"]
    medium_impact = ["phase 2", "clinical", "trial", "data", "efficacy", "safety"]
    
    for word in high_impact:
        if word in text: score += 10
    for word in medium_impact:
        if word in text: score += 5
    return score

def setup_database(db_path: str = "ct_fias.db") -> None:
    """Initializes the SQLite database with the strict schema."""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS biotech_pharma_news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                headline TEXT NOT NULL UNIQUE,
                content TEXT,
                source_url TEXT NOT NULL,
                published_date DATETIME,
                ai_processed BOOLEAN DEFAULT 0
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS analysis_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                news_id INTEGER,
                ticker TEXT NOT NULL,
                fda_expert_summary TEXT,
                financial_impact_prediction TEXT,
                final_markdown TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (news_id) REFERENCES biotech_pharma_news (id)
            )
        """)
        conn.commit()

def ingest_daily_news(tickers: List[str], db_path: str = "ct_fias.db") -> int:
    """Fetches news and inserts into database avoiding duplicates."""
    logger.info(f"Ingesting news for tickers: {tickers}")
    new_rows_count = 0
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        for ticker_symbol in tickers:
            try:
                ticker_obj = yf.Ticker(ticker_symbol)
                news_list = ticker_obj.news
                
                if not news_list:
                    continue
                
                scored_news = []
                for item in news_list:
                    content_dict = item.get('content', {})
                    if content_dict:
                        headline = content_dict.get('title')
                        source_url = content_dict.get('canonicalUrl', {}).get('url') or content_dict.get('clickThroughUrl', {}).get('url')
                        summary = content_dict.get('summary', "")
                        pub_date = content_dict.get('pubDate')
                    else:
                        headline = item.get('title')
                        source_url = item.get('link')
                        summary = ""
                        pub_date = item.get('providerPublishTime')

                    if not headline or not source_url:
                        continue

                    if is_clinical_news(headline, summary):
                        score = calculate_relevance_score(headline, summary)
                        scored_news.append({
                            'score': score,
                            'headline': headline,
                            'summary': summary,
                            'source_url': source_url,
                            'pub_date': pub_date
                        })

                # Rank by score and take top 2
                scored_news.sort(key=lambda x: x['score'], reverse=True)
                top_news = scored_news[:2]

                for news in top_news:
                    cursor.execute("""
                        INSERT OR IGNORE INTO biotech_pharma_news 
                        (ticker, headline, content, source_url, published_date) 
                        VALUES (?, ?, ?, ?, ?)
                    """, (ticker_symbol, news['headline'], news['summary'], news['source_url'], news['pub_date']))
                    
                    if cursor.rowcount > 0:
                        logger.info(f"Top-ranked news for {ticker_symbol} (Score {news['score']}): {news['headline']}")
                        new_rows_count += 1
                        
            except Exception as e:
                logger.error(f"Error fetching news for {ticker_symbol}: {e}")
                continue
        
        conn.commit()
    
    return new_rows_count
