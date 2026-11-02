"""
Multi-Provider LLM Manager using Pydantic AI
Supports switching between OpenAI, Gemini, and Anthropic (optional)
"""
import os
import logging
from typing import Optional, Dict, Any, AsyncGenerator, Union, List, Tuple, Type
from dotenv import load_dotenv

import httpx
from google.genai.errors import ClientError, ServerError
from openai import APIError as OpenAIAPIError

from pydantic import BaseModel, ValidationError
from pydantic_ai import Agent, ModelHTTPError, StructuredDict
from pydantic_ai.models import Model
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings
from pydantic_ai.exceptions import ModelRetry, UnexpectedModelBehavior

# Optional Anthropic support - skip if not installed
ANTHROPIC_AVAILABLE = False
AnthropicModel = None
AnthropicProvider = None
AnthropicAPIError = Exception  # Fallback type for except clause
try:
    from anthropic import APIError as _AnthropicAPIError
    from pydantic_ai.models.anthropic import AnthropicModel as _AnthropicModel
    from pydantic_ai.providers.anthropic import AnthropicProvider as _AnthropicProvider
    AnthropicModel = _AnthropicModel
    AnthropicProvider = _AnthropicProvider
    AnthropicAPIError = _AnthropicAPIError
    ANTHROPIC_AVAILABLE = True
except ImportError:
    pass

load_dotenv()
logger = logging.getLogger(__name__)

# Log Anthropic availability status
if ANTHROPIC_AVAILABLE:
    logger.info("✓ Anthropic support enabled")
else:
    logger.info("⚠ Anthropic not available (package not installed), using OpenAI/Gemini only")

ProviderInstance = Union[GoogleProvider, OpenAIProvider, Any]  # Any for optional AnthropicProvider


class MultiProviderManager:
    """
    A simplified, configuration-driven, and extensible manager for multiple LLM providers.
    Supports named fallback chains and is easy to maintain.
    """
    PROVIDER_REGISTRY: Dict[str, Dict[str, Any]] = {
        "gemini": {
            "model_class": GoogleModel,
            "provider_class": GoogleProvider,
            "api_key_env": "GEMINI_API_KEY",
            "default_model": "gemini-2.0-flash-lite",
            "models": {
                "gemini-2.0-flash": {
                    "max_tokens": 8192,
                    "temperature": 0.7,
                    "input_token_limit": 1048576,
                    "google_thinking_config": {"include_thoughts": False}
                },
                "gemini-2.0-flash-lite": {
                    "max_tokens": 8192,
                    "temperature": 0.7,
                    "input_token_limit": 1048576,
                    "google_thinking_config": {"include_thoughts": False}
                },
                "gemini-2.5-flash": {
                    "max_tokens": 65536,
                    "temperature": 0.7,
                    "input_token_limit": 1048576,
                    "google_thinking_config": {"include_thoughts": False},
                    "top_p": 0.9,
                    "top_k": 64,
                    "candidate_count": 1
                },
                "gemini-2.5-flash-lite": {
                    "max_tokens": 65536,
                    "temperature": 0.7,
                    "input_token_limit": 1048576,
                    "google_thinking_config": {"include_thoughts": False}
                },
                "gemini-2.5-pro": {
                    "max_tokens": 65536,
                    "temperature": 0.7,
                    "input_token_limit": 1048576,
                    "google_thinking_config": {"include_thoughts": False}
                },
            },
        },
        "openai": {
            "model_class": OpenAIChatModel,
            "provider_class": OpenAIProvider,
            "api_key_env": "OPENAI_API_KEY",
            "default_model": "gpt-4o-mini",
            "models": {
                "gpt-4.1": {
                    "max_tokens": 32768,
                    "temperature": 0.7,
                    "input_token_limit": 1047576,
                    "thinking_tags": []
                },
                "gpt-5.1": {
                    "max_tokens": 32768,
                    "temperature": 0.7,
                    "input_token_limit": 1047576,
                    "thinking_tags": []
                },
                 "gpt-5.2-chat-latest": {
                    "max_tokens": 32768,
                    "temperature": 0.7,
                    "input_token_limit": 1047576,
                    "thinking_tags": []
                },
                "gpt-4o": {
                    "max_tokens": 16384,
                    "temperature": 0.7,
                    "input_token_limit": 128000,
                    "thinking_tags": []
                },
                "gpt-4o-mini": {
                    "max_tokens": 16384,
                    "temperature": 0.7,
                    "input_token_limit": 128000,
                    "thinking_tags": []
                },
                "gpt-4.1-mini": {
                    "max_tokens": 32768,
                    "temperature": 0.7,
                    "input_token_limit": 1047576,
                    "thinking_tags": []
                },
                "gpt-5.2-chat-latest": {
                    "max_tokens": 32768,
                    "temperature": 0.7,
                    "input_token_limit": 1047576,
                    "thinking_tags": []
                },
            },
        },
        # Anthropic is added conditionally below if available
    }
    
    # Add Anthropic to registry only if available
    if ANTHROPIC_AVAILABLE and AnthropicModel and AnthropicProvider:
        PROVIDER_REGISTRY["anthropic"] = {
            "model_class": AnthropicModel,
            "provider_class": AnthropicProvider,
            "api_key_env": "ANTHROPIC_API_KEY",
            "default_model": "claude-3-7-sonnet-20250219",
            "models": {
                "claude-3-7-sonnet-20250219": {
                    "max_tokens": 64000,
                    "temperature": 0.7,
                    "input_token_limit": 200000,
                    "timeout": 120.0,
                    "anthropic_thinking": {"type": "disabled"}
                },
                "claude-sonnet-4-20250514": {
                    "max_tokens": 64000,
                    "temperature": 0.7,
                    "input_token_limit": 200000,
                    "timeout": 120.0,
                    "anthropic_thinking": {"type": "disabled"}
                },
                "claude-3-5-haiku-20241022": {
                    "max_tokens": 8192,
                    "temperature": 0.7,
                    "input_token_limit": 200000,
                    "timeout": 120.0,
                    "anthropic_thinking": {"type": "disabled"}
                },
            },
        }

    # Fallback chains - anthropic only included if available
    _BASE_FALLBACK = ["openai", "gemini"] + (["anthropic"] if ANTHROPIC_AVAILABLE else [])
    FALLBACK_CHAINS: Dict[str, List[str]] = {
        "openai": ["openai", "gemini"] + (["anthropic"] if ANTHROPIC_AVAILABLE else []),
        "gemini": ["gemini", "openai"] + (["anthropic"] if ANTHROPIC_AVAILABLE else []),
        "claude": (["anthropic"] if ANTHROPIC_AVAILABLE else []) + ["openai", "gemini"],
        "anthropic": (["anthropic"] if ANTHROPIC_AVAILABLE else []) + ["openai", "gemini"],
        "best_speed": ["openai", "gemini"] + (["anthropic"] if ANTHROPIC_AVAILABLE else []),
    }

    def __init__(self):
        self.agents: Dict[str, Agent] = {}
        if not ANTHROPIC_AVAILABLE:
            logger.warning("Anthropic provider disabled: optional Anthropic dependencies are unavailable or incompatible.")
            self.FALLBACK_CHAINS = {
                name: [provider for provider in chain if provider != "anthropic"]
                for name, chain in self.FALLBACK_CHAINS.items()
                if name not in {"anthropic", "claude"}
            }

    def _create_single_model(
        self, provider: str, model_key: str, max_tokens: Optional[int] = None, temperature: Optional[float] = None, skip_missing_key: bool = False
    ) -> Optional[Model]:
        """Creates a Pydantic AI Model instance using the provider registry."""
        provider_config = self.PROVIDER_REGISTRY.get(provider)
        if not provider_config:
            raise ValueError(f"Unknown provider: '{provider}'. Available: {list(self.PROVIDER_REGISTRY.keys())}")

        api_key_env = provider_config["api_key_env"]
        api_key = os.getenv(api_key_env, "").strip()
        if not api_key:
            if skip_missing_key:
                logger.warning(f"API key environment variable '{api_key_env}' not found for provider '{provider}', skipping.")
                return None
            raise ValueError(f"API key environment variable '{api_key_env}' not found or is empty for provider '{provider}'.")

        model_config = provider_config["models"].get(model_key)
        if not model_config:
            raise ValueError(f"Unknown model '{model_key}' for provider '{provider}'. Available: {list(provider_config['models'].keys())}")

        # Start with base settings from registry, excluding custom keys like 'input_token_limit'
        final_settings = {k: v for k, v in model_config.items() if k != "input_token_limit"}

        # Override with explicit arguments if provided
        if max_tokens:
            final_settings["max_tokens"] = max_tokens
        if temperature is not None:
            final_settings["temperature"] = temperature

        ModelClass: Type[Model] = provider_config["model_class"]
        ProviderClass = provider_config["provider_class"]

        # Explicitly pass the API key to the provider
        provider_instance = ProviderClass(api_key=api_key)

        return ModelClass(model_key, provider=provider_instance, settings=ModelSettings(**final_settings))

    def _get_agent(
        self,
        model_chain: List[Tuple[str, str]],
        output_schema: Optional[Dict[str, Any]] = None,
        output_model: Optional[Type[BaseModel]] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None
    ) -> Agent:
        """Gets or creates a cached Agent."""
        output_type: Optional[type] = None
        if output_schema:
            output_key = f"schema_{hash(str(output_schema))}"
            output_type = StructuredDict(output_schema)
        elif output_model:
            output_key = output_model.__name__
            output_type = output_model
        else:
            output_key = "text"

        agent_key = f"{model_chain!r}_{output_key}_{max_tokens}_{temperature}"

        if agent_key not in self.agents:
            valid_model_chain = [
                (p, m) for p, m in model_chain
                if p in self.PROVIDER_REGISTRY and m in self.PROVIDER_REGISTRY[p]["models"]
            ]
            if not valid_model_chain:
                raise ValueError("No valid models found in the provided chain after validation.")

            # Try to build models, skip those with missing API keys if in fallback mode
            skip_missing = len(valid_model_chain) > 1
            models_to_build = []
            for p, m in valid_model_chain:
                model = self._create_single_model(p, m, max_tokens, temperature, skip_missing_key=skip_missing)
                if model is not None:
                    models_to_build.append(model)
            
            if not models_to_build:
                raise ValueError("No valid models could be created. Check your API keys.")
            
            if len(models_to_build) > 1:
                fallback_exceptions = [
                    ModelHTTPError,
                    httpx.ReadTimeout,
                    httpx.HTTPStatusError,
                    httpx.ConnectError,
                    UnexpectedModelBehavior,
                    ValidationError,
                    ClientError,
                    ServerError,
                    OpenAIAPIError,
                ]
                if AnthropicAPIError is not None:
                    fallback_exceptions.append(AnthropicAPIError)

                final_model = FallbackModel(
                    *models_to_build,
                    fallback_on=tuple(fallback_exceptions)
                )
            else:
                final_model = models_to_build[0]

            agent_config = {
                "model": final_model,
                "output_type": output_type if output_type else str,
                "end_strategy": "exhaustive"
            }
            self.agents[agent_key] = Agent(**agent_config)
            logger.info(f"Created and cached new agent: {agent_key}")

        return self.agents[agent_key]

    def _resolve_model_chain(self, models: Union[str, Tuple[str, str], List[Tuple[str, str]]]) -> List[Tuple[str, str]]:
        """Resolves user input into a concrete list of (provider, model_key) tuples."""
        if isinstance(models, str):
            provider_order = self.FALLBACK_CHAINS.get(models)
            if not provider_order:
                raise ValueError(f"Unknown fallback chain name: '{models}'. Available: {list(self.FALLBACK_CHAINS.keys())}")

            return [
                (provider, self.PROVIDER_REGISTRY[provider]["default_model"])
                for provider in provider_order
            ]
        elif isinstance(models, list):
            return models
        elif isinstance(models, tuple):
            return [models]
        else:
            raise TypeError("'models' must be a string (chain name), a (provider, model) tuple, or a list of tuples.")

    async def run(
        self, prompt: str, models: Union[str, Tuple[str, str], List[Tuple[str, str]]] = "best_speed",
        output_schema: Optional[Dict[str, Any]] = None,
        output_model: Optional[Type[BaseModel]] = None,
        stream: bool = False,
        max_tokens: Optional[int] = None, temperature: Optional[float] = None
    ) -> Any:
        """Run the LLM with the given prompt and configuration."""
        if output_schema and output_model:
            raise ValueError("Provide either 'output_schema' or 'output_model', not both.")

        try:
            model_chain = self._resolve_model_chain(models)
            agent = self._get_agent(model_chain, output_schema, output_model, max_tokens, temperature)

            logger.info(f"Attempting request with model chain: {model_chain}")

            if stream:
                if output_schema or output_model:
                    raise ValueError("Streaming is only supported for plain text output.")
                return agent.run_stream(prompt)
            else:
                result = await agent.run(prompt)
                logger.info(f"Request successful.")
                return result.output
        except ClientError as e:
            error_str = str(e)
            project_id = "unknown"
            if "consumer" in error_str:
                import re
                match = re.search(r"projects/(\d+)", error_str)
                if match:
                    project_id = match.group(1)

            logger.error(f"Google Gemini API Error: {e}", exc_info=True)
            if "API_KEY_SERVICE_BLOCKED" in error_str or "PERMISSION_DENIED" in error_str:
                raise ValueError(
                    "Google Gemini API request was blocked. This usually means the 'Generative Language API' or 'Vertex AI API' is not enabled. "
                    f"Please check the project with ID '{project_id}' in the Google Cloud Console."
                ) from e
            raise
        except (ModelRetry, ExceptionGroup) as e:
            logger.error(f"All models in the chain {model_chain} failed. Error: {e}", exc_info=True)
            raise
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid configuration or input for models '{models}'. Error: {e}", exc_info=True)
            raise

    async def get_response(self, *args, **kwargs) -> Any:
        """Get a non-streaming response from the LLM."""
        return await self.run(*args, **kwargs, stream=False)

    async def stream_response(self, *args, **kwargs) -> AsyncGenerator[str, None]:
        """Stream response from the LLM."""
        try:
            async with await self.run(*args, **kwargs, stream=True) as stream:
                async for chunk in stream.stream_output():
                    yield chunk
        except Exception as e:
            yield f"\n[Error: An error occurred during streaming. Details: {e}]"


# Global instance for use across the application
llm_manager = MultiProviderManager()
