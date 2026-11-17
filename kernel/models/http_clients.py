"""
HTTP-based Model Clients for Cloud APIs and Local LLM Runtimes.
Implements OpenAI-compatible, Anthropic, Gemini, and Ollama providers
using standard requests with strict HTTP 429, timeout, and failover classification.
"""

import os
import json
import time
import requests
from typing import Optional, Dict, Any

from .base import (
    BaseModelClient,
    RateLimitException,
    TimeoutException,
    ModelExecutionException
)
from ..types import ModelConfig, ModelResponse


class OpenAICompatibleClient(BaseModelClient):
    """
    Standard OpenAI-compatible client.
    Works for OpenAI, Groq, OpenRouter, Mistral, Together AI, vLLM, and LM Studio.
    """

    def __init__(self, config: ModelConfig):
        super().__init__(config)
        self.api_key = config.api_key or os.getenv("OPENAI_API_KEY") or os.getenv("GROQ_API_KEY")
        self.base_url = (config.base_url or "https://api.openai.com/v1").rstrip("/")

    def generate(self, system_prompt: str, user_prompt: str) -> ModelResponse:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key or ''}"
        }
        payload = {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.2
        }

        start_time = time.time()
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=self.config.timeout_seconds)
            latency = time.time() - start_time

            if resp.status_code == 429:
                raise RateLimitException(f"OpenAI rate limit (HTTP 429): {resp.text}", model_name=self.name)
            if resp.status_code == 408:
                raise TimeoutException(f"OpenAI timeout (HTTP 408): {resp.text}", model_name=self.name)
            if resp.status_code >= 400:
                raise ModelExecutionException(f"OpenAI API Error ({resp.status_code}): {resp.text}", status_code=resp.status_code, model_name=self.name)

            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})

            return ModelResponse(
                raw_text=content,
                model_name=self.name,
                provider=self.provider,
                latency_seconds=round(latency, 4),
                token_usage={
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0)
                }
            )

        except requests.exceptions.Timeout as e:
            raise TimeoutException(f"Request timeout to {self.name}: {e}", model_name=self.name)
        except requests.exceptions.RequestException as e:
            raise ModelExecutionException(f"Network error calling {self.name}: {e}", model_name=self.name)


class AnthropicClient(BaseModelClient):
    """
    Anthropic Claude client using the Messages API.
    """

    def __init__(self, config: ModelConfig):
        super().__init__(config)
        self.api_key = config.api_key or os.getenv("ANTHROPIC_API_KEY")
        self.base_url = (config.base_url or "https://api.anthropic.com/v1").rstrip("/")

    def generate(self, system_prompt: str, user_prompt: str) -> ModelResponse:
        url = f"{self.base_url}/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key or "",
            "anthropic-version": "2023-06-01"
        }
        payload = {
            "model": self.model_id,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": 4096,
            "temperature": 0.2
        }

        start_time = time.time()
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=self.config.timeout_seconds)
            latency = time.time() - start_time

            if resp.status_code == 429:
                raise RateLimitException(f"Anthropic rate limit (HTTP 429): {resp.text}", model_name=self.name)
            if resp.status_code == 408:
                raise TimeoutException(f"Anthropic timeout (HTTP 408): {resp.text}", model_name=self.name)
            if resp.status_code >= 400:
                raise ModelExecutionException(f"Anthropic API Error ({resp.status_code}): {resp.text}", status_code=resp.status_code, model_name=self.name)

            data = resp.json()
            content = data["content"][0]["text"]
            usage = data.get("usage", {})

            return ModelResponse(
                raw_text=content,
                model_name=self.name,
                provider=self.provider,
                latency_seconds=round(latency, 4),
                token_usage={
                    "prompt_tokens": usage.get("input_tokens", 0),
                    "completion_tokens": usage.get("output_tokens", 0)
                }
            )

        except requests.exceptions.Timeout as e:
            raise TimeoutException(f"Request timeout to {self.name}: {e}", model_name=self.name)
        except requests.exceptions.RequestException as e:
            raise ModelExecutionException(f"Network error calling {self.name}: {e}", model_name=self.name)


class GeminiClient(BaseModelClient):
    """
    Google Gemini REST client.
    """

    def __init__(self, config: ModelConfig):
        super().__init__(config)
        self.api_key = config.api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.base_url = (config.base_url or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")

    def generate(self, system_prompt: str, user_prompt: str) -> ModelResponse:
        url = f"{self.base_url}/models/{self.model_id}:generateContent?key={self.api_key or ''}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "system_instruction": {
                "parts": [{"text": system_prompt}]
            },
            "contents": [
                {
                    "parts": [{"text": user_prompt}]
                }
            ],
            "generationConfig": {
                "temperature": 0.2
            }
        }

        start_time = time.time()
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=self.config.timeout_seconds)
            latency = time.time() - start_time

            if resp.status_code == 429:
                raise RateLimitException(f"Gemini rate limit (HTTP 429): {resp.text}", model_name=self.name)
            if resp.status_code == 408:
                raise TimeoutException(f"Gemini timeout (HTTP 408): {resp.text}", model_name=self.name)
            if resp.status_code >= 400:
                raise ModelExecutionException(f"Gemini API Error ({resp.status_code}): {resp.text}", status_code=resp.status_code, model_name=self.name)

            data = resp.json()
            candidates = data.get("candidates", [])
            if not candidates:
                raise ModelExecutionException(f"No candidates returned: {resp.text}", model_name=self.name)

            text_parts = candidates[0].get("content", {}).get("parts", [])
            content = "".join([part.get("text", "") for part in text_parts])
            usage = data.get("usageMetadata", {})

            return ModelResponse(
                raw_text=content,
                model_name=self.name,
                provider=self.provider,
                latency_seconds=round(latency, 4),
                token_usage={
                    "prompt_tokens": usage.get("promptTokenCount", 0),
                    "completion_tokens": usage.get("candidatesTokenCount", 0)
                }
            )

        except requests.exceptions.Timeout as e:
            raise TimeoutException(f"Request timeout to {self.name}: {e}", model_name=self.name)
        except requests.exceptions.RequestException as e:
            raise ModelExecutionException(f"Network error calling {self.name}: {e}", model_name=self.name)


class OllamaClient(BaseModelClient):
    """
    Local open-weight model client via Ollama REST API.
    """

    def __init__(self, config: ModelConfig):
        super().__init__(config)
        self.base_url = (config.base_url or "http://localhost:11434").rstrip("/")

    def generate(self, system_prompt: str, user_prompt: str) -> ModelResponse:
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "stream": False
        }

        start_time = time.time()
        try:
            resp = requests.post(url, json=payload, timeout=self.config.timeout_seconds)
            latency = time.time() - start_time

            if resp.status_code == 429:
                raise RateLimitException(f"Ollama rate limit (HTTP 429): {resp.text}", model_name=self.name)
            if resp.status_code >= 400:
                raise ModelExecutionException(f"Ollama API Error ({resp.status_code}): {resp.text}", status_code=resp.status_code, model_name=self.name)

            data = resp.json()
            content = data.get("message", {}).get("content", "")

            return ModelResponse(
                raw_text=content,
                model_name=self.name,
                provider=self.provider,
                latency_seconds=round(latency, 4),
                token_usage={
                    "prompt_tokens": data.get("prompt_eval_count", 0),
                    "completion_tokens": data.get("eval_count", 0)
                }
            )

        except requests.exceptions.Timeout as e:
            raise TimeoutException(f"Request timeout to Ollama ({self.name}): {e}", model_name=self.name)
        except requests.exceptions.RequestException as e:
            raise ModelExecutionException(f"Ollama connection error for {self.name}: {e}", model_name=self.name)
