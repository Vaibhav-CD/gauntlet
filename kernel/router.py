"""
Failover Router for Seamless Multi-Model Orchestration.
Catches HTTP 429 rate limits, timeouts, and network errors,
transparently routing the exact same workspace snapshot and task payload
to designated fallback models while preserving handoff notes.
"""

import logging
from typing import List, Tuple, Optional
from .types import ExecutionPayload, ModelResponse, ModelConfig
from .models.base import (
    BaseModelClient,
    RateLimitException,
    TimeoutException,
    ModelExecutionException
)
from .models import ModelRegistry
from .prompt_engine import PromptEngine

logger = logging.getLogger("kernel.router")


class FailoverRouter:
    """
    Executes model requests with transparent failover and handoff note tracking.
    """

    def __init__(self, registry: ModelRegistry):
        self.registry = registry

    def execute_with_failover(
        self,
        payload: ExecutionPayload,
        primary_model_name: str,
        fallback_models: Optional[List[str]] = None
    ) -> Tuple[ModelResponse, List[str]]:
        """
        Executes generation using primary model. If failure occurs, seamlessly
        cascades to fallback models with identical snapshot payload and appends handoff notes.

        Returns:
            (ModelResponse, List[str] handoff_notes)
        """
        # Determine fallback chain
        if fallback_models is None:
            # Auto-detect all registered fallback models ordered by priority
            all_configs = self.registry.list_models()
            fallback_models = [
                c.name for c in all_configs
                if c.is_fallback and c.name != primary_model_name
            ]

        execution_queue = [primary_model_name] + [m for m in fallback_models if m != primary_model_name]
        handoff_notes: List[str] = []
        last_exception = None

        system_prompt = PromptEngine.build_system_prompt()

        for idx, model_name in enumerate(execution_queue):
            try:
                client = self.registry.get_client(model_name)
            except KeyError:
                logger.warning(f"Model '{model_name}' not registered in registry. Skipping.")
                continue

            # Build user prompt with uniform snapshot context and any handoff notes accumulated
            user_prompt = PromptEngine.build_user_prompt(payload, handoff_notes=handoff_notes)

            try:
                response = client.generate(system_prompt=system_prompt, user_prompt=user_prompt)
                # Successful execution
                return response, handoff_notes

            except RateLimitException as e:
                last_exception = e
                note = f"[HANDOFF NOTE]: Model '{model_name}' encountered HTTP 429 Rate Limit. Seamlessly routing to fallback model. Snapshot context preserved."
                logger.warning(note)
                handoff_notes.append(note)

            except TimeoutException as e:
                last_exception = e
                note = f"[HANDOFF NOTE]: Model '{model_name}' timed out (HTTP 408). Seamlessly routing to fallback model. Snapshot context preserved."
                logger.warning(note)
                handoff_notes.append(note)

            except ModelExecutionException as e:
                last_exception = e
                note = f"[HANDOFF NOTE]: Model '{model_name}' encountered generation error ({e.status_code}): {e.message}. Seamlessly routing to fallback model."
                logger.warning(note)
                handoff_notes.append(note)

            except Exception as e:
                last_exception = e
                note = f"[HANDOFF NOTE]: Unexpected error on '{model_name}': {str(e)}. Seamlessly routing to fallback model."
                logger.error(note)
                handoff_notes.append(note)

        # If all models in the failover chain fail, re-raise the last exception
        if last_exception:
            raise last_exception
        raise RuntimeError("No model candidates available in router execution queue.")
