"""
Base utilities for classifiers
"""
from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings
from ..llm_config import get_default_llm_config


def get_model_string() -> str:
    """Get model string dynamically from current config"""
    llm_config = get_default_llm_config()
    return llm_config.get_model_string()


def get_temperature() -> float:
    """Get temperature dynamically from current config"""
    llm_config = get_default_llm_config()
    return llm_config.temperature


def create_agent(output_type, name: str) -> Agent:
    """
    Create a Pydantic AI agent with standard configuration
    
    Args:
        output_type: The Pydantic model class for structured output
        name: Display name for the agent (for Logfire)
    
    Returns:
        Configured Agent instance
    """
    return Agent(
        get_model_string(),
        output_type=output_type,
        model_settings=ModelSettings(temperature=get_temperature()),
        name=name
    )
