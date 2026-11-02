"""
LLM Configuration Module
Provides abstraction for different LLM providers (Gemini, OpenAI, etc.)
"""
import os
from enum import Enum
from typing import Optional
from pydantic import BaseModel


class LLMProvider(str, Enum):
    """Supported LLM providers"""
    GEMINI = "gemini"
    OPENAI = "openai"


class LLMConfig(BaseModel):
    """Configuration for LLM"""
    provider: LLMProvider = LLMProvider.GEMINI
    model_name: Optional[str] = None
    temperature: float = 0.0
    
    def get_model_string(self) -> str:
        """
        Get the model string for pydantic-ai Agent initialization.
        Format: 'provider:model-name'
        """
        if self.provider == LLMProvider.GEMINI:
            model = self.model_name or "gemini-2.0-flash-lite"
            return f"google-gla:{model}"
        elif self.provider == LLMProvider.OPENAI:
            model = self.model_name or "gpt-4o"
            return f"openai:{model}"
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")


def get_default_llm_config() -> LLMConfig:
    """
    Get default LLM configuration from environment or use defaults.
    Environment variables:
    - LLM_PROVIDER: gemini or openai (default: gemini)
    - LLM_MODEL_NAME: specific model name (optional)
    - LLM_TEMPERATURE: temperature setting (default: 0.0)
    """
    provider_str = os.getenv("LLM_PROVIDER", "gemini").lower()
    provider = LLMProvider.GEMINI if provider_str == "gemini" else LLMProvider.OPENAI
    
    return LLMConfig(
        provider=provider,
        model_name=os.getenv("LLM_MODEL_NAME"),
        temperature=float(os.getenv("LLM_TEMPERATURE", "0.0"))
    )
