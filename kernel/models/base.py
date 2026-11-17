"""
Base Model Client Interface and Standardized Exceptions.
Guarantees Dynamic Model Agnosticism across local open-weights and cloud APIs.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import time

from ..types import ModelConfig, ModelResponse, ExecutionPayload


class ModelKernelException(Exception):
    """Base exception for all model client errors."""
    def __init__(self, message: str, status_code: Optional[int] = None, model_name: str = ""):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.model_name = model_name


class RateLimitException(ModelKernelException):
    """HTTP 429 or quota exceeded rate limit exception."""
    def __init__(self, message: str = "Rate limit reached (HTTP 429)", model_name: str = ""):
        super().__init__(message, status_code=429, model_name=model_name)


class TimeoutException(ModelKernelException):
    """HTTP 408 or connection/request timeout."""
    def __init__(self, message: str = "Request timed out", model_name: str = ""):
        super().__init__(message, status_code=408, model_name=model_name)


class ModelExecutionException(ModelKernelException):
    """General generation or network failure."""
    def __init__(self, message: str, status_code: Optional[int] = None, model_name: str = ""):
        super().__init__(message, status_code=status_code or 500, model_name=model_name)


class BaseModelClient(ABC):
    """
    Abstract interface for all model clients in the System Kernel.
    Ensures that any model (local, cloud, mock) conforms to uniform invocation.
    """

    def __init__(self, config: ModelConfig):
        self.config = config
        self.name = config.name
        self.provider = config.provider
        self.model_id = config.model_id

    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str) -> ModelResponse:
        """
        Executes model generation given uniform system prompt and user prompt.
        Must raise RateLimitException on 429, TimeoutException on timeout,
        or ModelExecutionException on other failures.
        """
        pass

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name='{self.name}' provider='{self.provider}' model_id='{self.model_id}'>"
