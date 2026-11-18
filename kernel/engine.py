"""
System Kernel Orchestrator Engine.
The primary entrypoint that ties together Workspace State, Multi-Model Routing,
Failover Handing, and State Mutation.
"""

import time
import logging
from typing import Optional, List, Dict, Any

from .types import (
    WorkspaceSnapshot,
    ExecutionPayload,
    ExecutionResult,
    CodeMutation,
    ModelConfig
)
from .state_manager import WorkspaceStateManager
from .models import ModelRegistry, create_default_registry
from .router import FailoverRouter
from .mutation_parser import MutationParser
from .test_verifier import TestVerifier

logger = logging.getLogger("kernel.engine")


class SystemKernel:
    """
    The System Kernel of the custom multi-model developer environment.
    Guarantees Single Source of Truth, Dynamic Model Agnosticism,
    Transparent Failover, and Automatic State Mutation without manual copy-pasting.
    """

    def __init__(
        self,
        project_root: str = ".",
        primary_model: str = "primary-mock",
        registry: Optional[ModelRegistry] = None,
        max_history_turns: int = 15
    ):
        self.state_manager = WorkspaceStateManager(project_root=project_root, max_history_turns=max_history_turns)
        self.registry = registry or create_default_registry()
        self.router = FailoverRouter(self.registry)
        self.primary_model = primary_model

    def set_primary_model(self, model_name: str):
        """Sets the primary model client."""
        if model_name not in [m.name for m in self.registry.list_models()]:
            raise KeyError(f"Model '{model_name}' not registered.")
        self.primary_model = model_name

    def register_model(self, config: ModelConfig):
        """Registers a new model client dynamically."""
        self.registry.register(config)

    def execute_payload(
        self,
        payload: ExecutionPayload,
        primary_model: Optional[str] = None,
        fallback_models: Optional[List[str]] = None,
        write_to_disk: bool = True
    ) -> ExecutionResult:
        """
        Executes a formal ExecutionPayload containing task_prompt and workspace_snapshot.
        Ensures Single Source of Truth and transparent failover.
        """
        start_time = time.time()
        active_model = primary_model or self.primary_model

        # 1. Update internal snapshot from payload snapshot
        self.state_manager.set_snapshot(payload.workspace_snapshot)

        # Log user prompt into history
        self.state_manager.append_interaction(
            role="user",
            content=payload.task_prompt
        )

        try:
            # 2. Route through Failover Router
            model_response, handoff_notes = self.router.execute_with_failover(
                payload=payload,
                primary_model_name=active_model,
                fallback_models=fallback_models
            )

            # 3. Parse mutations from model output
            explanation, mutations = MutationParser.parse(model_response.raw_text)

            # 4. Apply mutations to Single Source of Truth buffers & disk
            applied_mutations: List[CodeMutation] = []
            for mut in mutations:
                applied = self.state_manager.apply_mutation(mut, write_to_disk=write_to_disk)
                applied_mutations.append(applied)

            # 5. Log assistant turn into history with diffs and handoff notes
            diff_summaries = [
                {"file": m.file_path, "action": m.action, "diff": m.diff, "success": m.success}
                for m in applied_mutations
            ]

            self.state_manager.append_interaction(
                role="assistant",
                content=explanation,
                model_name=model_response.model_name,
                diffs=diff_summaries,
                handoff_notes=handoff_notes
            )

            # 6. Optional Automated Test Verification
            verification_passed = None
            verification_output = None
            if payload.auto_verify:
                verification_passed, verification_output = TestVerifier.run_tests(str(self.state_manager.project_root))

            total_latency = round(time.time() - start_time, 4)
            status = "failover_success" if handoff_notes else "success"

            return ExecutionResult(
                status=status,
                task_prompt=payload.task_prompt,
                response_text=explanation,
                model_used=model_response.model_name,
                handoff_notes=handoff_notes,
                mutations_applied=applied_mutations,
                updated_snapshot=self.state_manager.get_snapshot(),
                latency_seconds=total_latency,
                verification_passed=verification_passed,
                verification_output=verification_output
            )

        except Exception as e:
            total_latency = round(time.time() - start_time, 4)
            logger.error(f"Kernel execution failed: {e}")

            # Record failure in history
            self.state_manager.append_interaction(
                role="assistant",
                content=f"[EXECUTION FAILED]: {str(e)}",
                model_name=active_model
            )

            return ExecutionResult(
                status="error",
                task_prompt=payload.task_prompt,
                response_text=f"Execution error: {str(e)}",
                model_used=active_model,
                handoff_notes=[],
                mutations_applied=[],
                updated_snapshot=self.state_manager.get_snapshot(),
                latency_seconds=total_latency,
                error_message=str(e)
            )

    def execute(
        self,
        task_prompt: str,
        primary_model: Optional[str] = None,
        fallback_models: Optional[List[str]] = None,
        write_to_disk: bool = True,
        auto_verify: bool = False
    ) -> ExecutionResult:
        """
        Convenience execution using current state snapshot and prompt string.
        """
        payload = ExecutionPayload(
            task_prompt=task_prompt,
            workspace_snapshot=self.state_manager.get_snapshot(),
            auto_verify=auto_verify
        )
        return self.execute_payload(
            payload=payload,
            primary_model=primary_model,
            fallback_models=fallback_models,
            write_to_disk=write_to_disk
        )
