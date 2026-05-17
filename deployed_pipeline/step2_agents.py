import sqlite3
from typing import Any
import logging
from datetime import datetime

logger = logging.getLogger("step2_agents")

_llm_singleton = None

def get_llm() -> Any:
    global _llm_singleton
    if _llm_singleton is None:
        try:
            from crewai import LLM
            logger.info("Initializing LLM instance: ollama/gemma4:31b")
            _llm_singleton = LLM(
                model="ollama/gemma4:31b", 
                base_url="http://localhost:11434"
            )
        except ImportError as e:
            logger.error(f"Failed to import LLM: {e}")
            raise
    return _llm_singleton

def process_unanalyzed_news(db_path: str = "ct_fias.db") -> int:
    try:
        from crewai import Agent, Task, Crew, Process
    except ImportError as e:
        logger.error(f"CrewAI dependencies missing: {e}")
        raise

    llm_instance = get_llm()

    fda_expert = Agent(
        role="FDA Regulatory Expert",
        goal="Analyze clinical trial news for regulatory viability and FDA approval likelihood.",
        backstory="You are a former FDA reviewer. You spot 'red flags' in clinical data.",
        llm=llm_instance,
        allow_delegation=False,
        verbose=False
    )

    financial_analyst = Agent(
        role="Biotech Financial Analyst",
        goal="Predict the financial impact of clinical news on valuation.",
        backstory="You translate regulatory assessments into potential stock price movements.",
        llm=llm_instance,
        allow_delegation=False,
        verbose=False
    )

    processed_count = 0

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, ticker, headline, content, source_url FROM biotech_pharma_news WHERE ai_processed = 0")
        pending_news = cursor.fetchall()

        if not pending_news:
            return 0

        for news_item in pending_news:
            news_id, ticker, headline, content, source_url = news_item

            fda_task = Task(
                description=(
                    f"Analyze the following news for ticker {ticker}: {headline}. \n\n"
                    f"Content: {content}\n\n"
                    "Identify key clinical milestones and provide a summary of scientific validity."
                ),
                expected_output="A concise regulatory summary.",
                agent=fda_expert
            )

            current_date = datetime.now().strftime("%B %d, %Y")
            financial_task = Task(
                description=(
                    f"Based on the FDA Expert's summary and the news ({headline}), "
                    f"analyze the financial implications for {ticker}. Predict impact on stock price.\n\n"
                    f"ORIGINAL NEWS CONTEXT:\n{content}\n\n"
                    "FORMATTING REQUIREMENT:\n"
                    f"Provide a detailed Markdown report. MUST USE TODAY'S DATE: {current_date} in the report header. AT THE VERY BOTTOM, include a section titled "
                    f"'ORIGINAL SOURCE REFERENCE' with the headline and the clickable URL: {source_url}."
                ),
                expected_output="A detailed financial impact prediction and final Markdown report with source links.",
                agent=financial_analyst,
                context=[fda_task]
            )

            crew = Crew(
                agents=[fda_expert, financial_analyst],
                tasks=[fda_task, financial_task],
                process=Process.sequential,
                verbose=False
            )

            try:
                logger.info(f"Kicking off crew for news_id {news_id} ({ticker})")
                result = crew.kickoff()
                
                # Robustly extract outputs
                fda_summary = fda_task.output.raw if hasattr(fda_task, 'output') and fda_task.output else "Scientific analysis performed."
                final_report = str(result)
                
                if not final_report or len(final_report) < 50:
                    logger.warning(f"LLM produced suspicious output for {news_id}. Result length: {len(final_report)}")
                    # Append source if missing
                    if source_url not in final_report:
                        final_report += f"\n\n---\n**Source:** {source_url}"

                financial_prediction = final_report[:500]

                cursor.execute(
                    """
                    INSERT INTO analysis_reports 
                    (news_id, ticker, fda_expert_summary, financial_impact_prediction, final_markdown) 
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (news_id, ticker, fda_summary, financial_prediction, final_report)
                )

                cursor.execute("UPDATE biotech_pharma_news SET ai_processed = 1 WHERE id = ?", (news_id,))
                conn.commit()
                processed_count += 1
                logger.info(f"Successfully processed news_id {news_id}")

            except Exception as e:
                logger.error(f"Error processing news_id {news_id}: {e}", exc_info=True)
                continue

    return processed_count
