import os
import argparse
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_ollama import OllamaLLM

# 1. Configuration - Optimized for your local Gemma 4 setup
# Using OllamaLLM for LangGraph/LangChain integration
llm = OllamaLLM(
    model="gemma4:31b",
    base_url="http://localhost:11434",
    temperature=0.2
)

# State Definition
class ArchitectState(TypedDict):
    project_context: str
    questions: Optional[str]
    user_answers: Optional[str]
    blueprint: Optional[str]

# 2. Define the Expert Architect Prompt
ARCHITECT_SYSTEM_PROMPT = """You are an Expert Staff-Level Software Architect leading a multi-agent AI coding team.
Your primary focus is structural planning, Non-Functional Requirements (NFRs), trade-off analysis, and strict boundary definition.

Core Directives:
- No Implementation: You do NOT write execution code. Your sole output is architectural blueprints.
- Design Philosophy & Preferred Patterns: Default to Python. Prioritize high-cohesion and low-coupling.
- Data Persistence Strategy: Mandate SQLite (or flat files/JSON) for local/isolated tasks. Mandate PostgreSQL for enterprise-scale systems.
- Microservices: Treat major domains as isolated, bounded contexts.
- Pipe-and-Filter: Design linear, modular workflows for data/AI pipelines.
- Event-Driven: Use sensor/trigger orchestration for reactive operations.
- The "Discrete Unit" Law: The system MUST be divisible. Downstream agents must implement/test one standalone script at a time.
- The Test-First Imperative: Mandate TDD. Agents write failing unit tests before business logic. For refactoring, mandate Characterization Tests.
- Anti-Hallucination: Explicitly define all state variables, data structures, and function signatures. Downstream agents are not allowed to guess.
- Clarification First: Ask clarifying questions before generating the architecture if context is missing."""

# 3. Define the Phase 2 Task Node: Questioning
def analyze_and_question(state: ArchitectState):
    prompt = f"""
    {ARCHITECT_SYSTEM_PROMPT}

    Analyze the provided project context: {state.get('project_context', '')}
    
    After analysis, identify missing constraints, NFRs, or domain ambiguities that would block a sound architectural design.
    - Ask **at most 5 questions** in a single message.
    - Focus strictly on high-level constraints: Traffic/Scale, data consistency, latency targets, security/compliance, integration contracts, and deployment targets.
    - Number the questions.
    - Do not split into multiple rounds — this is your only chance to ask. Wait for the user's response before proceeding.
    """
    response = llm.invoke(prompt)
    return {"questions": response}

# 4. Define the Phase 3 Task Node: Blueprint Generation
def generate_blueprint(state: ArchitectState):
    prompt = f"""
    {ARCHITECT_SYSTEM_PROMPT}

    Using the project context and the user's answers:
    Context: {state.get('project_context', '')}
    Architect's Questions: {state.get('questions', '')}
    User's Answers: {state.get('user_answers', '')}
    
    When you have enough context, you must output a strictly formatted markdown file containing ONLY the following 6 sections in order:
    1. Context & Goals: A concise summary of the system's purpose and its primary Non-Functional Requirements (Performance, Scale, Reliability). Clearly state which architectural pattern and data persistence strategy were chosen and why.
    2. Component Diagram: A Mermaid.js flowchart (graph TD) mapping the system architecture, file relationships, and data flow.
    3. Data Models & State (CRITICAL): Explicit schema definitions. Define all TypedDict, Pydantic models, or Database schemas. Do not leave variables ambiguous.
    4. Strict Interfaces & Contracts: The exact Python function signatures (including type hints and return types) that connect the modules.
    5. Implementation Phases: A sequential, checkbox-style [ ] task list. Tasks must be broken down script-by-script. Crucially, the first task of any new module MUST be to write the test suite for that module.
    6. AI Developer Directives: Explicit negative constraints (e.g., "Do NOT use pandas, use polars", "Do NOT hallucinate external APIs") and the strict instruction: "You must write and run tests before implementing the core logic. You must strictly adhere to the designated data persistence technology."
    """
    response = llm.invoke(prompt)
    return {"blueprint": response}

# Graph Construction
builder = StateGraph(ArchitectState)
builder.add_node("analyze_and_question", analyze_and_question)
builder.add_node("generate_blueprint", generate_blueprint)

builder.set_entry_point("analyze_and_question")
builder.add_edge("analyze_and_question", "generate_blueprint")
builder.add_edge("generate_blueprint", END)

# Add memory for checkpointer (required for human-in-the-loop interruption)
memory = MemorySaver()
graph = builder.compile(checkpointer=memory, interrupt_before=["generate_blueprint"])

# 5. Execution Logic (The "Back and Forth" Loop)
def run_architect_workflow(design_file):
    print("--- Phase 1: Ecosystem Analysis ---")
    try:
        with open(design_file, "r") as f:
            context = f.read()
        print(f"[*] Successfully loaded project description from {design_file}")
    except FileNotFoundError:
        print(f"[!] Error: {design_file} not found. Please create it and provide the project description.")
        return

    config = {"configurable": {"thread_id": "architect_thread_1"}}
    
    print("\n[*] Architect is analyzing and formulating questions...")
    initial_state = {
        "project_context": context,
        "questions": None,
        "user_answers": None,
        "blueprint": None
    }
    
    # Run the questioning phase (will pause before generate_blueprint)
    for event in graph.stream(initial_state, config=config):
        for k, v in event.items():
            if k == "analyze_and_question":
                print("\n--- Phase 2: Architectural Questions ---")
                print(v["questions"])
                
    # Graph is now paused before 'generate_blueprint'
    
    print("\n--- Provide your Answers ---")
    answers = input("Please answer the questions above to proceed: ")

    # Update state with answers
    graph.update_state(config, {"user_answers": answers})
    
    print("\n[*] Generating ARCHITECTURE.md...")
    final_blueprint_content = None
    
    # Resume the graph (passing None continues from the breakpoint)
    for event in graph.stream(None, config=config):
        for k, v in event.items():
            if k == "generate_blueprint":
                final_blueprint_content = v["blueprint"]
                
    if final_blueprint_content:
        with open("ARCHITECTURE.md", "w") as f:
            f.write(final_blueprint_content)
        
        print("\n--- Phase 3: ARCHITECTURE.md Generated ---")
        print("File saved as ARCHITECTURE.md")
        print("\nI've drafted the system design and roadmap in ARCHITECTURE.md. Does this architecture look correct? Reply YES to proceed with implementation, or tell me what trade-offs or components to adjust.")
    else:
        print("\n[!] Error: Failed to generate blueprint.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Software Architect LangGraph Agent")
    parser.add_argument("--design", type=str, default="design_requirement.md", help="Path to the design requirement markdown file")
    args = parser.parse_args()
    
    run_architect_workflow(args.design)
