import sqlite3
import os
import logging
from datetime import datetime
from typing import List
from fpdf import FPDF
try:
    from fpdf.enums import XPos, YPos
except ImportError:
    # Fallback for older fpdf versions
    class XPos: LMARGIN = 1; RIGHT = 0
    class YPos: NEXT = 1; TOP = 0

logger = logging.getLogger("step3_delivery")

class ReportPDF(FPDF):
    def header(self):
        self.set_font("helvetica", "B", 12)
        self.cell(0, 10, "Clinical Trial Financial Impact Analysis", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font("helvetica", "I", 8)
        self.cell(0, 10, f"Page {self.page_no()} | Generated on {datetime.now().strftime('%Y-%m-%d')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")

def generate_individual_pdfs(db_path: str = "ct_fias.db", output_dir: str = "reports", tickers: List[str] = None) -> List[str]:
    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    generated_files = []
    
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            query = """
                SELECT r.ticker, r.fda_expert_summary, r.final_markdown, n.source_url 
                FROM analysis_reports r
                JOIN biotech_pharma_news n ON r.news_id = n.id
                WHERE r.created_at >= datetime('now', '-24 hours')
            """
            
            if tickers:
                placeholders = ', '.join(['?'] * len(tickers))
                query += f" AND r.ticker IN ({placeholders})"
                cursor.execute(query, tickers)
            else:
                cursor.execute(query)
            reports = cursor.fetchall()

            ticker_counts = {}
            for ticker, fda_summary, financial_report, source_url in reports:
                try:
                    # Update counter for this ticker
                    count = ticker_counts.get(ticker, 0) + 1
                    ticker_counts[ticker] = count
                    
                    pdf = ReportPDF()
                    pdf.add_page()
                    
                    # Title
                    pdf.set_font("helvetica", "B", 16)
                    pdf.cell(0, 10, f"Analysis Report: {ticker} (Part {count})", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                    pdf.ln(5)

                    # Section 1: FDA Regulatory Assessment
                    pdf.set_font("helvetica", "B", 12)
                    pdf.set_fill_color(240, 240, 240)
                    pdf.cell(0, 10, "1. FDA REGULATORY ASSESSMENT", new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
                    pdf.ln(2)
                    pdf.set_font("helvetica", "", 10)
                    pdf.multi_cell(0, 6, fda_summary.encode('latin-1', 'replace').decode('latin-1'))
                    pdf.ln(5)

                    # Section 2: Financial Impact Analysis
                    pdf.set_font("helvetica", "B", 12)
                    pdf.cell(0, 10, "2. FINANCIAL IMPACT ANALYSIS", new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
                    pdf.ln(2)
                    pdf.set_font("helvetica", "", 10)
                    pdf.multi_cell(0, 6, financial_report.encode('latin-1', 'replace').decode('latin-1'))
                    pdf.ln(10)

                    pdf.set_font("helvetica", "B", 11)
                    pdf.cell(0, 10, "VERIFICATION & ORIGINAL SOURCE:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                    pdf.set_font("helvetica", "U", 10)
                    pdf.set_text_color(0, 0, 255)
                    pdf.cell(0, 10, "View original news on Yahoo Finance", link=source_url, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                    pdf.set_text_color(0, 0, 0)
                    pdf.set_font("helvetica", "I", 8)
                    pdf.cell(0, 10, f"Source URL: {source_url}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

                    file_name = f"{ticker}_Analysis_{datetime.now().strftime('%Y%m%d')}_{count}.pdf"
                    file_path = os.path.join(output_dir, file_name)
                    pdf.output(file_path)
                    generated_files.append(file_path)
                    logger.info(f"Generated PDF: {file_path}")
                except Exception as e:
                    logger.error(f"Failed to generate PDF for {ticker}: {e}")

    except Exception as e:
        logger.error(f"Database error during PDF generation: {e}")

    return generated_files
