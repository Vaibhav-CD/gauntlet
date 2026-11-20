"""
Model Registry and Factory.
Enables plug-and-play registration and lookup of local and cloud AI models.
"""

from typing import Dict, List, Optional
from .base import (
    BaseModelClient,
    RateLimitException,
    TimeoutException,
    ModelExecutionException
)
from .mock_client import MockModelClient
from .http_clients import (
    OpenAICompatibleClient,
    AnthropicClient,
    GeminiClient,
    OllamaClient
)
from ..types import ModelConfig


class ModelRegistry:
    """
    Central registry for managing plug-and-play AI model clients.
    """

    def __init__(self):
        self._clients: Dict[str, BaseModelClient] = {}
        self._configs: Dict[str, ModelConfig] = {}

    def register(self, config: ModelConfig, client: Optional[BaseModelClient] = None) -> BaseModelClient:
        """Registers a model config and creates its client."""
        self._configs[config.name] = config
        if client is not None:
            self._clients[config.name] = client
            return client

        # Instantiate based on provider
        if config.provider == "mock":
            inst = MockModelClient(config)
        elif config.provider in ("openai", "groq", "openrouter"):
            inst = OpenAICompatibleClient(config)
        elif config.provider == "anthropic":
            inst = AnthropicClient(config)
        elif config.provider == "gemini":
            inst = GeminiClient(config)
        elif config.provider == "ollama":
            inst = OllamaClient(config)
        else:
            # Default to OpenAI compatible
            inst = OpenAICompatibleClient(config)

        self._clients[config.name] = inst
        return inst

    def get_client(self, name: str) -> BaseModelClient:
        """Retrieves a client by name."""
        if name not in self._clients:
            raise KeyError(f"Model client '{name}' is not registered.")
        return self._clients[name]

    def get_config(self, name: str) -> ModelConfig:
        if name not in self._configs:
            raise KeyError(f"Model config '{name}' not found.")
        return self._configs[name]

    def list_models(self) -> List[ModelConfig]:
        """Returns all registered model configs ordered by priority."""
        return sorted(list(self._configs.values()), key=lambda c: c.priority)

    def unregister(self, name: str):
        if name in self._clients:
            del self._clients[name]
        if name in self._configs:
            del self._configs[name]


def create_default_registry() -> ModelRegistry:
    """
    Sets up a default multi-model registry with primary and fallback models.
    Includes simulated/mock clients for offline use and real cloud adapters.
    """
    registry = ModelRegistry()

    # Primary Mock Client (Fast, local deterministic)
    registry.register(ModelConfig(
        name="primary-mock",
        provider="mock",
        model_id="mock-fast-coder",
        model_tier="fast",
        priority=1,
        is_fallback=False
    ))

    # Secondary Fallback Mock Client
    registry.register(ModelConfig(
        name="fallback-mock",
        provider="mock",
        model_id="mock-resilient-coder",
        model_tier="balanced",
        priority=2,
        is_fallback=True
    ))

    # Cloud Models (Cloud-ready if API keys provided in environment)
    registry.register(ModelConfig(
        name="gemini-1.5-flash",
        provider="gemini",
        model_id="gemini-1.5-flash",
        model_tier="fast",
        priority=3,
        is_fallback=False
    ))

    registry.register(ModelConfig(
        name="gpt-4o-mini",
        provider="openai",
        model_id="gpt-4o-mini",
        model_tier="fast",
        priority=4,
        is_fallback=True
    ))

    registry.register(ModelConfig(
        name="claude-3-5-sonnet",
        provider="anthropic",
        model_id="claude-3-5-sonnet-20241022",
        model_tier="reasoning",
        priority=5,
        is_fallback=False
    ))

    registry.register(ModelConfig(
        name="ollama-qwen",
        provider="ollama",
        model_id="qwen2.5-coder:7b",
        model_tier="balanced",
        priority=6,
        is_fallback=True
    ))

    return registry
