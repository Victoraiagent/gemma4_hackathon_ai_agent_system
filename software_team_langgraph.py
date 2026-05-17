import os
import json
import argparse
from typing import TypedDict, Dict, List, Any
from langgraph.graph import StateGraph, END
from langchain_ollama import OllamaLLM
from langgraph.checkpoint.memory import MemorySaver
import subprocess

# Initialize the local LLM
llm = OllamaLLM(model="gemma4:31b")

# --- Helper Functions ---
def parse_json_from_llm(response: str) -> dict:
    """Helper to strip markdown formatting and parse JSON."""
    response = response.strip()
    if response.startswith("```json"):
        response = response[7:]
    elif response.startswith("```"):
        response = response[3:]
    if response.endswith("```"):
        response = response[:-3]
    try:
        return json.loads(response.strip())
    except Exception as e:
        print(f"JSON Parse Error: {e}")
        return {}

def clean_code_from_llm(response: str) -> str:
    """Helper to strip markdown python blocks from generated code."""
    response = response.strip()
    if response.startswith("```python"):
        response = response[9:]
    elif response.startswith("```"):
        response = response[3:]
    if response.endswith("```"):
        response = response[:-3]
    return response.strip() + "\n"

# --- State Definitions ---

class EngineeringState(TypedDict):
    project_goal: str
    design_document: str
    current_step_instruction: str
    target_file: str
    code_artifacts: Dict[str, str]
    active_agent: str 
    qa_feedback: str
    step_count: int

class DevOpsState(TypedDict):
    project_goal: str
    code_artifacts: Dict[str, str]  # Global Index
    file_pointers: List[str]        # List of filenames to process
    current_file_idx: int           # Pointer index
    target_file: str                # Current file being processed
    active_agent: str               
    execution_logs: str
    step_count: int
    target_scripts: List[str]
    error_context: str
    fix_history: List[str]

class ParentState(TypedDict):
    project_goal: str
    design_document: str
    code_artifacts: Dict[str, str]
    phase: str # 'engineering' or 'devops'
    final_output: str
    force_engineering: bool
    target_scripts: List[str]
    error_context: str

# --- TEAM A: Engineering Subgraph ---

def engineering_architect_node(state: EngineeringState):
    """Supervisor for the Engineering Team."""
    step_count = state.get("step_count", 0)
    if step_count > 10: # TTL Circuit Breaker
        print("  [Eng Architect] Safety limit reached. Halting subgraph.")
        return {"active_agent": "end", "step_count": step_count + 1}
        
    prompt = f"""
    You are the Lead Architect (Supervisor) of an AI development team.
    
    Overall Project Design:
    {state['design_document']}
    
    Current Phase/Goal to Implement:
    {state['project_goal']}
    
    Files we have built so far in this phase:
    {list(state.get('code_artifacts', {}).keys())}
    
    QA Feedback (if any):
    {state.get('qa_feedback', 'None')}
    
    Your task:
    Determine the next immediate step. If the phase is entirely complete and all code is written and passes QA, set "active_agent" to "end".
    Otherwise, assign the next step to "coder" (to write/fix code) or "tester" (to review).
    
    Output ONLY a valid JSON object with this exact schema:
    {{
        "current_step_instruction": "Description of the exact code to write next",
        "target_file": "filename.py",
        "active_agent": "coder" or "tester" or "end"
    }}
    """
    print("  [Eng Architect is planning the next step...]")
    response = llm.invoke(prompt)
    parsed = parse_json_from_llm(response)
    
    return {
        "current_step_instruction": parsed.get("current_step_instruction", "Finished"),
        "target_file": parsed.get("target_file", ""),
        "active_agent": parsed.get("active_agent", "end"),
        "step_count": step_count + 1
    }

def coder_node(state: EngineeringState):
    """Generates business logic code."""
    target_file = state.get('target_file', 'unknown.py')
    prompt = f"""
    You are the Coder.
    Overall Design: {state['design_document']}
    Task: {state['current_step_instruction']}
    Target File: {target_file}
    QA Feedback: {state.get('qa_feedback', '')}
    
    Output ONLY valid Python code for {target_file}.
    """
    print(f"  [Coder is writing {target_file} ...]")
    new_code = clean_code_from_llm(llm.invoke(prompt))
    
    artifacts = state.get("code_artifacts", {})
    artifacts[target_file] = new_code
    
    # Save immediately to output directory before QA
    output_dir = "generated_code"
    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, target_file), "w", encoding="utf-8") as f:
        f.write(new_code)
        
    return {"code_artifacts": artifacts, "active_agent": "tester"}

def tester_node(state: EngineeringState):
    """Reviews and unit tests the code statically."""
    target_file = state.get('target_file', '')
    current_code = state.get('code_artifacts', {}).get(target_file, '')
    
    prompt = f"""
    You are the Unit Tester.
    Review the code for '{target_file}'.
    Task: {state['current_step_instruction']}
    
    Code:
    {current_code}
    
    If there are logic errors or missing imports, output the required fixes.
    If it looks perfect, output exactly 'PASS'.
    
    Additionally, please provide the terminal command line that should be used to QA this file (e.g., pytest, pylint).
    Format the command inside a ```bash block.
    """
    print(f"  [Tester is reviewing {target_file} ...]")
    feedback = llm.invoke(prompt).strip()
    
    qa_command = f"python3 {target_file}"
    if "```bash" in feedback:
        try:
            qa_command = feedback.split("```bash")[1].split("```")[0].strip()
        except IndexError:
            pass
            
    output_dir = "generated_code"
    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, "qa.md"), "a", encoding="utf-8") as f:
        f.write(f"\\n## QA Command for {target_file}\\n")
        f.write(f"```bash\\n{qa_command}\\n```\\n")
        f.write(f"**Feedback:**\\n{feedback}\\n")
    
    # Route based on feedback
    next_agent = "architect" if "PASS" in feedback else "coder"
    return {"qa_feedback": feedback, "active_agent": next_agent}

def route_engineering(state: EngineeringState):
    agent = state.get("active_agent", "end")
    if agent in ["coder", "tester"]:
        return agent
    return END

builder_eng = StateGraph(EngineeringState)
builder_eng.add_node("architect", engineering_architect_node)
builder_eng.add_node("coder", coder_node)
builder_eng.add_node("tester", tester_node)
builder_eng.set_entry_point("architect")
builder_eng.add_conditional_edges("architect", route_engineering, {"coder": "coder", "tester": "tester", END: END})
builder_eng.add_edge("coder", "tester")
builder_eng.add_edge("tester", "architect")
eng_graph = builder_eng.compile()

# --- TEAM B: DevOps Subgraph (Cleanup Crew) ---

def devops_architect_node(state: DevOpsState):
    """Supervisor for DevOps/Cleanup Crew."""
    step_count = state.get("step_count", 0)
    if step_count > 20: # TTL Circuit Breaker
        print("  [DevOps Architect] Safety limit reached. Halting subgraph.")
        return {"active_agent": "end"}
        
    file_pointers = state.get("file_pointers", [])
    current_file_idx = state.get("current_file_idx", 0)
    
    if current_file_idx < len(file_pointers):
        target_file = file_pointers[current_file_idx]
        return {
            "active_agent": "devops_engineer",
            "target_file": target_file,
            "step_count": step_count + 1
        }
    else:
        # All files processed individually. Proceed to integration.
        if state.get("execution_logs") == "DEPLOY_SUCCESS":
            return {"active_agent": "end"}
        
        return {
            "active_agent": "pipeline_generator",
            "step_count": step_count + 1
        }

def devops_engineer_node(state: DevOpsState):
    """Processes ONE Python script at a time to debug or wrap."""
    target_file = state.get("target_file")
    current_code = state.get("code_artifacts", {}).get(target_file, "")
    execution_logs = state.get("execution_logs", "")
    error_context = state.get("error_context", "")
    fix_history = state.get("fix_history", [])
    
    history_str = ""
    if fix_history:
        history_str = "\n    --- PREVIOUS FAILED ATTEMPTS ---\n    " + "\n    ".join(fix_history[-3:])
        
    prompt = f"""
    You are a Senior DevOps Engineer. 
    You process one script at a time to ensure it is robust, bug-free, and production-ready.
    Target File: {target_file}
    
    Current Code:
    {current_code}
    
    User-Provided Initial Context/Error:
    {error_context if error_context else 'None'}
    
    Execution/Error Logs from previous micro-test:
    {execution_logs}
    {history_str}
    
    Fix any infrastructure, syntax, or orchestration bugs mentioned in the logs. 
    If you see PREVIOUS FAILED ATTEMPTS above, DO NOT repeat the exact same changes. Try a different approach or fix the specific error mentioned.
    If appropriate, wrap functions with Dagster decorators (@asset), or ensure correct imports. Note that @asset does NOT take a 'retries' argument. Use `retry_policy=RetryPolicy(max_retries=3)` and ensure `from dagster import RetryPolicy` is imported if you need it.
    Make sure any testing or top-level execution logic is protected by `if __name__ == '__main__':` to prevent long-running tasks or timeouts during module import.
    Do NOT rewrite core business logic, just orchestration and deployment robustness.
    
    Output ONLY valid Python code for {target_file} without markdown formatting or explanations.
    """
    
    print(f"  [DevOps Engineer is processing {target_file} ...]")
    new_code = clean_code_from_llm(llm.invoke(prompt))
    
    artifacts = state.get("code_artifacts", {})
    artifacts[target_file] = new_code
    
    return {
        "code_artifacts": artifacts, 
        "active_agent": "micro_test"
    }

def micro_test_node(state: DevOpsState):
    """Runs an actual subprocess dry run on the newly processed file to catch runtime and import errors."""
    target_file = state.get("target_file")
    artifacts = state.get("code_artifacts", {})
    fix_history = state.get("fix_history", [])
    
    print(f"  [Micro-Test validating {target_file} via subprocess...]")
    
    # Write ALL currently loaded artifacts to a temporary deployment directory for testing
    # This ensures that if target_file imports from another script we are debugging, it resolves correctly.
    output_dir = "deployed_pipeline"
    os.makedirs(output_dir, exist_ok=True)
    
    for fname, fcode in artifacts.items():
        with open(os.path.join(output_dir, fname), "w", encoding="utf-8") as f:
            f.write(fcode)
            
    filepath = os.path.join(output_dir, target_file)
        
    try:
        # Run the file using subprocess to capture real tracebacks (like ModuleNotFoundError)
        result = subprocess.run(["python3", filepath], capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0:
            print(f"    -> {target_file} executed successfully.")
            return {
                "execution_logs": "PASS: " + result.stdout,
                "current_file_idx": state.get("current_file_idx", 0) + 1,
                "active_agent": "devops_architect",
                "fix_history": []
            }
        else:
            print(f"    -> Execution Error in {target_file}:\n{result.stderr}")
            fix_history.append(f"Attempt Error:\n{result.stderr.strip()[-500:]}")
            return {
                "execution_logs": f"Execution Error:\n{result.stderr}",
                "active_agent": "devops_engineer",
                "fix_history": fix_history
            }
    except subprocess.TimeoutExpired:
        print(f"    -> Timeout Error in {target_file}")
        fix_history.append("Attempt Error: Timeout")
        return {
            "execution_logs": "Execution timed out. Make sure it does not block indefinitely.",
            "active_agent": "devops_engineer",
            "fix_history": fix_history
        }
    except Exception as e:
        print(f"    -> Subprocess Error: {e}")
        fix_history.append(f"Attempt Error: {str(e)}")
        return {
            "execution_logs": f"Subprocess Error: {str(e)}",
            "active_agent": "devops_engineer",
            "fix_history": fix_history
        }

def integration_tester_node(state: DevOpsState):
    """Integration Test: Writes all files out and finalizes deployment."""
    print("  [Integration Tester is deploying the final pipeline ...]")
    artifacts = state.get("code_artifacts", {})
    output_dir = "deployed_pipeline"
    os.makedirs(output_dir, exist_ok=True)
    
    for filename, code in artifacts.items():
        filepath = os.path.join(output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(code)
            
    return {"execution_logs": "DEPLOY_SUCCESS", "active_agent": "devops_architect"}

def pipeline_generator_node(state: DevOpsState):
    """Generates the overarching dagster_pipeline.py to connect all assets."""
    print("  [Pipeline Generator is creating dagster_pipeline.py ...]")
    file_inventory = "\n".join(state.get("code_artifacts", {}).keys())
    
    prompt = f"""
    You are a Senior DevOps Architect. 
    The team has finished wrapping individual modules for: {state['project_goal']}
    
    Here are the Python files we have processed:
    {file_inventory}
    
    Your task is to generate a 'dagster_pipeline.py' file that imports all the @asset decorated functions from these files 
    and defines a Dagster `Definitions` object.
    
    Output ONLY valid Python code for dagster_pipeline.py without markdown formatting.
    """
    new_code = clean_code_from_llm(llm.invoke(prompt))
    
    artifacts = state.get("code_artifacts", {})
    artifacts["dagster_pipeline.py"] = new_code
    
    return {
        "code_artifacts": artifacts,
        "active_agent": "integration_tester"
    }

def route_devops(state: DevOpsState):
    agent = state.get("active_agent", "end")
    if agent in ["devops_engineer", "integration_tester", "micro_test", "devops_architect", "pipeline_generator"]:
        return agent
    return END

builder_devops = StateGraph(DevOpsState)
builder_devops.add_node("devops_architect", devops_architect_node)
builder_devops.add_node("devops_engineer", devops_engineer_node)
builder_devops.add_node("micro_test", micro_test_node)
builder_devops.add_node("pipeline_generator", pipeline_generator_node)
builder_devops.add_node("integration_tester", integration_tester_node)

builder_devops.set_entry_point("devops_architect")
builder_devops.add_conditional_edges("devops_architect", route_devops, {
    "devops_engineer": "devops_engineer",
    "pipeline_generator": "pipeline_generator",
    END: END
})
builder_devops.add_edge("devops_engineer", "micro_test")
builder_devops.add_conditional_edges("micro_test", route_devops, {
    "devops_architect": "devops_architect",
    "devops_engineer": "devops_engineer"
})
builder_devops.add_conditional_edges("pipeline_generator", route_devops, {
    "integration_tester": "integration_tester"
})
builder_devops.add_edge("integration_tester", "devops_architect")
devops_graph = builder_devops.compile()


# --- Parent Graph ---

def load_existing_code_node(state: ParentState):
    """Loads existing code from 'generated_code' dir. If present, bypasses engineering phase to focus on debugging."""
    artifacts = {}
    phase = state.get("phase", "engineering")
    force_eng = state.get("force_engineering", False)
    target_scripts = state.get("target_scripts", [])
    
    source_dir = "generated_code"
    # Also support deployed_pipeline if they want to debug existing pipelines
    if not os.path.exists(source_dir) and os.path.exists("deployed_pipeline"):
        source_dir = "deployed_pipeline"
        
    if os.path.exists(source_dir):
        for filename in os.listdir(source_dir):
            if filename.endswith(".py"):
                if target_scripts and filename not in target_scripts:
                    continue  # Skip files not matching the target scripts list
                with open(os.path.join(source_dir, filename), "r", encoding="utf-8") as f:
                    artifacts[filename] = f.read()
        if artifacts and phase == "engineering" and not force_eng:
            print(f"[Parent] Existing code found in '{source_dir}'. Bypassing Engineering phase to focus on DevOps Debugging.")
            phase = "devops"
            
    return {"code_artifacts": artifacts, "phase": phase}

def engineering_team_node(state: ParentState):
    print("\n--- Starting Team A: Engineering Subgraph ---")
    eng_state: EngineeringState = {
        "project_goal": state["project_goal"],
        "design_document": state["design_document"],
        "current_step_instruction": "Start implementation",
        "target_file": "",
        "code_artifacts": state.get("code_artifacts", {}),
        "active_agent": "architect",
        "qa_feedback": "",
        "step_count": 0
    }
    final_eng_state = eng_graph.invoke(eng_state)
    return {"code_artifacts": final_eng_state["code_artifacts"], "phase": "devops"}

def devops_team_node(state: ParentState):
    print("\n--- Starting Team B: DevOps Cleanup Crew Subgraph ---")
    artifacts = state.get("code_artifacts", {})
    file_pointers = list(artifacts.keys())
    
    devops_state: DevOpsState = {
        "project_goal": state["project_goal"],
        "code_artifacts": artifacts,
        "file_pointers": file_pointers,
        "current_file_idx": 0,
        "target_file": "",
        "active_agent": "devops_architect",
        "execution_logs": "",
        "step_count": 0,
        "target_scripts": state.get("target_scripts", []),
        "error_context": state.get("error_context", ""),
        "fix_history": []
    }
    final_devops_state = devops_graph.invoke(devops_state)
    return {"code_artifacts": final_devops_state["code_artifacts"], "final_output": "Deployment Ready"}

def route_parent(state: ParentState):
    phase = state.get("phase", "engineering")
    if phase == "engineering":
        return "engineering_team"
    elif phase == "devops":
        return "devops_team"
    return END

builder_parent = StateGraph(ParentState)
builder_parent.add_node("load_existing_code", load_existing_code_node)
builder_parent.add_node("engineering_team", engineering_team_node)
builder_parent.add_node("devops_team", devops_team_node)

builder_parent.set_entry_point("load_existing_code")
builder_parent.add_conditional_edges("load_existing_code", route_parent, {
    "engineering_team": "engineering_team",
    "devops_team": "devops_team"
})
builder_parent.add_edge("engineering_team", "devops_team")
builder_parent.add_edge("devops_team", END)

workflow = builder_parent.compile()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-Crew LangGraph Development Pipeline")
    parser.add_argument("--design", type=str, default="architecture_design_final.md", help="Path to architecture design markdown")
    parser.add_argument("--task", type=str, default="Debug and deploy existing pipeline", help="Specific goal")
    parser.add_argument("--target_scripts", type=str, default="", help="Focus debugging on a list of scripts (comma-separated, e.g. a.py,b.py)")
    parser.add_argument("--error_context", type=str, default="", help="User provided context about how the script was run and the exact error received")
    parser.add_argument("--force_engineering", action="store_true", help="Force running Team A even if generated_code exists")
    args = parser.parse_args()

    print(f"Reading design document from {args.design}...")
    try:
        with open(args.design, "r", encoding="utf-8") as f:
            design_content = f.read()
    except FileNotFoundError:
        print(f"Design document not found at {args.design}, proceeding with empty design.")
        design_content = f"Design for {args.task}"

    initial_state = {
        "project_goal": args.task,
        "design_document": design_content,
        "code_artifacts": {},
        "phase": "engineering",
        "final_output": "",
        "force_engineering": args.force_engineering,
        "target_scripts": [s.strip() for s in args.target_scripts.split(",")] if args.target_scripts else [],
        "error_context": args.error_context
    }

    print(f"Starting the Pipeline for Task: '{args.task}'")
    
    # Run the parent graph
    final_state = workflow.invoke(initial_state)
    
    print("\nWorkflow completed! Check the 'deployed_pipeline' directory for the final robust code.")

