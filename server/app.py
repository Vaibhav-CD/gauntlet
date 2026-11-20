"""
FastAPI Server for System Kernel Multi-Model Developer Environment.
Provides REST APIs and serves the interactive developer web UI.
"""

import os
from typing import Optional, List, Dict, Any
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from kernel.engine import SystemKernel
from kernel.types import (
    WorkspaceSnapshot,
    ExecutionPayload,
    ExecutionResult,
    ModelConfig
)
from kernel.circuit_breaker import CircuitBreakerManager
from kernel.test_verifier import TestVerifier


app = FastAPI(
    title="System Kernel - Multi-Model Developer Environment",
    description="Single Source of Truth, Dynamic Model Agnosticism, Transparent Failover & Auto State Mutation",
    version="1.0.0"
)

# Project root for developer environment
PROJECT_ROOT = os.getenv("KERNEL_PROJECT_ROOT", ".")
kernel = SystemKernel(project_root=PROJECT_ROOT)

# Pre-populate demo files if workspace is empty
def _init_demo_files():
    root = Path(PROJECT_ROOT).resolve()
    main_py = root / "main.py"
    if not main_py.exists():
        main_py.write_text(
            '"""\nMain application module.\n"""\n\ndef run():\n    # TODO: Implement calculation\n    pass\n\nif __name__ == "__main__":\n    run()\n',
            encoding="utf-8"
        )
        kernel.state_manager.open_file("main.py", set_as_active=True)

_init_demo_files()


class ExecuteRequest(BaseModel):
    task_prompt: str
    primary_model: Optional[str] = None
    workspace_snapshot: Optional[WorkspaceSnapshot] = None
    auto_verify: bool = False


class FileOpenRequest(BaseModel):
    file_path: str


class FileSaveRequest(BaseModel):
    file_path: str
    content: str


class FileCreateRequest(BaseModel):
    file_path: str
    content: Optional[str] = ""


class ModelSelectRequest(BaseModel):
    model_name: str


class SimulationRequest(BaseModel):
    model_name: str
    simulate_429: bool = False
    simulate_timeout: bool = False


@app.get("/api/snapshot")
def get_snapshot():
    """Returns the centralized workspace snapshot (Single Source of Truth)."""
    return kernel.state_manager.get_snapshot()


@app.post("/api/execute")
def execute_task(req: ExecuteRequest) -> ExecutionResult:
    """
    Executes a task prompt using the provided or centralized workspace snapshot.
    Handles transparent failover on HTTP 429/timeouts and applies state mutations.
    """
    snapshot = req.workspace_snapshot or kernel.state_manager.get_snapshot()
    payload = ExecutionPayload(
        task_prompt=req.task_prompt,
        workspace_snapshot=snapshot,
        auto_verify=req.auto_verify
    )
    result = kernel.execute_payload(
        payload=payload,
        primary_model=req.primary_model
    )
    return result


@app.get("/api/models")
def get_models():
    """Returns all registered models, their providers, priorities, and simulation statuses."""
    configs = kernel.registry.list_models()
    return {
        "primary_model": kernel.primary_model,
        "models": [c.model_dump() for c in configs]
    }


@app.post("/api/models/reset-circuit")
def reset_circuit(req: ModelSelectRequest):
    """Resets the circuit breaker state to CLOSED for the given model."""
    try:
        cfg = kernel.registry.get_config(req.model_name)
        CircuitBreakerManager.reset_circuit(cfg)
        return {"status": "success", "model_name": req.model_name, "circuit_state": cfg.circuit_state}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/verify")
def run_verification():
    """Runs project unit tests and returns pass/fail status and output."""
    passed, output = TestVerifier.run_tests(str(kernel.state_manager.project_root))
    return {"passed": passed, "output": output}


@app.post("/api/models/set-primary")
def set_primary_model(req: ModelSelectRequest):
    """Sets the active primary model."""
    try:
        kernel.set_primary_model(req.model_name)
        return {"status": "success", "primary_model": kernel.primary_model}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/models/simulate")
def configure_simulation(req: SimulationRequest):
    """Configures failure simulation (429 rate limit or timeout) for failover testing."""
    try:
        cfg = kernel.registry.get_config(req.model_name)
        cfg.simulate_429 = req.simulate_429
        cfg.simulate_timeout = req.simulate_timeout
        return {
            "status": "success",
            "model_name": req.model_name,
            "simulate_429": cfg.simulate_429,
            "simulate_timeout": cfg.simulate_timeout
        }
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/files")
def list_files():
    """Returns disk files and currently open buffer files."""
    disk_files = kernel.state_manager.list_project_files()
    open_files = list(kernel.state_manager.snapshot.open_files.keys())
    active_file = kernel.state_manager.snapshot.active_file
    return {
        "disk_files": disk_files,
        "open_files": open_files,
        "active_file": active_file
    }


@app.post("/api/files/open")
def open_file(req: FileOpenRequest):
    """Opens a file into the in-memory snapshot buffer and sets it active."""
    try:
        content = kernel.state_manager.open_file(req.file_path, set_as_active=True)
        return {
            "status": "success",
            "file_path": req.file_path,
            "content": content,
            "active_file": kernel.state_manager.snapshot.active_file
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/files/close")
def close_file(req: FileOpenRequest):
    """Closes a file from open buffer snapshot."""
    kernel.state_manager.close_file(req.file_path)
    return {
        "status": "success",
        "file_path": req.file_path,
        "open_files": list(kernel.state_manager.snapshot.open_files.keys()),
        "active_file": kernel.state_manager.snapshot.active_file
    }


@app.post("/api/files/save")
def save_file(req: FileSaveRequest):
    """Updates buffer and writes content directly to disk."""
    from kernel.types import CodeMutation
    mut = CodeMutation(
        action="update",
        file_path=req.file_path,
        content=req.content
    )
    applied = kernel.state_manager.apply_mutation(mut, write_to_disk=True)
    if not applied.success:
        raise HTTPException(status_code=500, detail=applied.error)
    return {"status": "success", "file_path": req.file_path}


@app.post("/api/files/create")
def create_file(req: FileCreateRequest):
    """Creates a new file in buffer and on disk."""
    from kernel.types import CodeMutation
    mut = CodeMutation(
        action="create",
        file_path=req.file_path,
        content=req.content or ""
    )
    applied = kernel.state_manager.apply_mutation(mut, write_to_disk=True)
    if not applied.success:
        raise HTTPException(status_code=500, detail=applied.error)
    return {"status": "success", "file_path": req.file_path}


@app.post("/api/rollback")
def rollback_state():
    """Rollback to the previous snapshot state."""
    snapshot = kernel.state_manager.rollback()
    if snapshot is None:
        return {"status": "empty", "message": "Undo stack is empty"}
    return {"status": "success", "snapshot": snapshot}


# Mount static assets
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/")
    def serve_index():
        return FileResponse(str(static_dir / "index.html"))
