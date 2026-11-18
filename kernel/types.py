"""
Kernel Data Types and Schemas
Defines the strict contracts for the Single Source of Truth workspace state,
execution payloads, model configs, and mutation results.
"""

from typing import Dict, List, Optional, Any, Literal
from pydantic import BaseModel, Field
import datetime


class Turn(BaseModel):
    """Represents a single conversation turn in recent_history."""
    turn_id: str = Field(default_factory=lambda: datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
    role: Literal["user", "assistant", "system"]
    content: str
    model_name: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.datetime.now().isoformat())
    diffs: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    handoff_notes: Optional[List[str]] = Field(default_factory=list)


class WorkspaceSnapshot(BaseModel):
    """
    Centralized Single Source of Truth snapshot.
    Contains active file, in-memory open buffers, and recent interaction history.
    """
    active_file: Optional[str] = None
    open_files: Dict[str, str] = Field(default_factory=dict, description="Mapping of relative/absolute file path to latest code string")
    recent_history: List[Turn] = Field(default_factory=list, description="Recent interaction turns for temporal continuity")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Auxiliary state such as checksums, git branch, etc.")


class ExecutionPayload(BaseModel):
    """
    Runtime execution payload sent to the System Kernel.
    """
    task_prompt: str = Field(..., description="The user coding instruction, bug fix request, or query")
    workspace_snapshot: WorkspaceSnapshot = Field(..., description="The centralized state snapshot")
    auto_verify: bool = Field(default=False, description="Whether to automatically run tests after state mutation")


class BlockReplacement(BaseModel):
    """Targeted search and replace block for precise surgical code edits."""
    search: str
    replace: str


class CodeMutation(BaseModel):
    """Represents an atomic mutation applied to the workspace state and disk."""
    action: Literal["create", "update", "replace_block", "delete"]
    file_path: str
    content: Optional[str] = None
    block_replacement: Optional[BlockReplacement] = None
    diff: Optional[str] = None
    syntax_valid: bool = True
    syntax_error: Optional[str] = None
    success: bool = True
    error: Optional[str] = None


CircuitState = Literal["CLOSED", "OPEN", "HALF_OPEN"]


class ModelConfig(BaseModel):
    """Configuration for a registered model client."""
    name: str
    provider: Literal["mock", "openai", "anthropic", "gemini", "ollama", "groq", "openrouter", "custom"]
    model_id: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    timeout_seconds: float = 30.0
    is_fallback: bool = False
    priority: int = 0  # Lower number = higher priority
    # Circuit Breaker attributes
    circuit_state: CircuitState = "CLOSED"
    failure_count: int = 0
    failure_threshold: int = 2
    cooldown_seconds: float = 60.0
    last_failure_time: Optional[float] = None
    # Simulation flags for deterministic failover testing
    simulate_429: bool = False
    simulate_timeout: bool = False
    simulate_error: bool = False


class ModelResponse(BaseModel):
    """Raw response returned by a ModelClient."""
    raw_text: str
    model_name: str
    provider: str
    latency_seconds: float = 0.0
    token_usage: Optional[Dict[str, int]] = None


class ExecutionResult(BaseModel):
    """
    Result returned by the System Kernel orchestrator after execution and state mutation.
    """
    status: Literal["success", "failover_success", "error"]
    task_prompt: str
    response_text: str
    model_used: str
    handoff_notes: List[str] = Field(default_factory=list)
    mutations_applied: List[CodeMutation] = Field(default_factory=list)
    updated_snapshot: WorkspaceSnapshot
    latency_seconds: float = 0.0
    error_message: Optional[str] = None
    verification_passed: Optional[bool] = None
    verification_output: Optional[str] = None
