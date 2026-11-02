"""
Wrapper to make Pydantic AI LLM Manager compatible with LlamaIndex
"""
import os
from typing import Any, Dict, List, Optional, Type
from llama_index.core.llms import ChatMessage, ChatResponse, MessageRole
from llama_index.core.base.llms.types import ChatResponseAsyncGen
from pydantic import BaseModel

from rag_service.core.llm_manager import llm_manager


class PydanticAILLMWrapper:
    """
    Wrapper class to make Pydantic AI Manager compatible with LlamaIndex interface.
    This allows using the multi-provider manager with existing LlamaIndex code.
    """
    
    def __init__(
        self, 
        model_provider: str = "openai",
        model_name: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None
    ):
        """
        Initialize the wrapper.
        
        Args:
            model_provider: Provider name or fallback chain name (e.g., "openai", "gemini", "best_speed")
            model_name: Specific model name (e.g., "gpt-4.1", "gemini-2.5-flash")
            temperature: Temperature for generation
            max_tokens: Maximum tokens to generate
        """
        self.model_provider = model_provider
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._structured_output_cls = None
        
        # Resolve the model specification
        if model_name:
            # If specific model is provided, use tuple format
            self.models = (model_provider, model_name)
        else:
            # Otherwise use the provider as a fallback chain name
            self.models = model_provider
    
    def as_structured_llm(self, output_cls: Type[BaseModel]) -> "PydanticAILLMWrapper":
        """
        Return a version of this LLM that outputs structured data.
        Compatible with LlamaIndex's as_structured_llm interface.
        """
        wrapper = PydanticAILLMWrapper(
            model_provider=self.model_provider,
            model_name=self.model_name,
            temperature=self.temperature,
            max_tokens=self.max_tokens
        )
        wrapper._structured_output_cls = output_cls
        return wrapper
    
    def _convert_messages(self, messages: List[ChatMessage]) -> str:
        """Convert LlamaIndex ChatMessage list to a single prompt string."""
        prompt_parts = []
        for msg in messages:
            role = msg.role.value if hasattr(msg.role, 'value') else str(msg.role)
            content = msg.content
            if role == "system":
                prompt_parts.append(f"System: {content}")
            elif role == "user":
                prompt_parts.append(f"User: {content}")
            elif role == "assistant":
                prompt_parts.append(f"Assistant: {content}")
            else:
                prompt_parts.append(content)
        return "\n\n".join(prompt_parts)
    
    async def achat(self, messages: List[ChatMessage], **kwargs) -> ChatResponse:
        """
        Async chat method compatible with LlamaIndex.
        
        Args:
            messages: List of ChatMessage objects
            **kwargs: Additional arguments
            
        Returns:
            ChatResponse object
        """
        prompt = self._convert_messages(messages)
        
        # Determine if we need structured output
        if self._structured_output_cls:
            result = await llm_manager.get_response(
                prompt=prompt,
                models=self.models,
                output_model=self._structured_output_cls,
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )
            
            # Return a ChatResponse with the structured output
            return ChatResponse(
                message=ChatMessage(role=MessageRole.ASSISTANT, content=""),
                raw=result,
                additional_kwargs={}
            )
        else:
            result = await llm_manager.get_response(
                prompt=prompt,
                models=self.models,
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )
            
            return ChatResponse(
                message=ChatMessage(role=MessageRole.ASSISTANT, content=str(result)),
                raw=result,
                additional_kwargs={}
            )
    
    def chat(self, messages: List[ChatMessage], **kwargs) -> ChatResponse:
        """
        Synchronous chat method (not recommended, but provided for compatibility).
        """
        import asyncio
        return asyncio.run(self.achat(messages, **kwargs))
    
    async def astream_chat(self, messages: List[ChatMessage], **kwargs) -> ChatResponseAsyncGen:
        """
        Async streaming chat method.
        
        Args:
            messages: List of ChatMessage objects
            **kwargs: Additional arguments
            
        Yields:
            ChatResponse objects with incremental content
        """
        prompt = self._convert_messages(messages)
        
        async def gen():
            accumulated = ""
            async for chunk in llm_manager.stream_response(
                prompt=prompt,
                models=self.models,
                temperature=self.temperature,
                max_tokens=self.max_tokens
            ):
                accumulated += chunk
                yield ChatResponse(
                    message=ChatMessage(role=MessageRole.ASSISTANT, content=accumulated),
                    delta=chunk,
                    raw=chunk,
                    additional_kwargs={}
                )
        
        return gen()


def get_llm(
    provider: str = None,
    model: str = None,
    temperature: float = 0.0,
    max_tokens: Optional[int] = None
) -> PydanticAILLMWrapper:
    """
    Factory function to create an LLM instance.
    
    Args:
        provider: Provider name or fallback chain (e.g., "openai", "gemini", "best_speed")
                 If None, uses OPENAI_API_KEY environment to determine default
        model: Specific model name (e.g., "gpt-4.1", "gemini-2.5-flash")
        temperature: Temperature for generation
        max_tokens: Maximum tokens to generate
        
    Returns:
        PydanticAILLMWrapper instance
        
    Example:
        # Use specific provider and model
        llm = get_llm(provider="openai", model="gpt-4.1", temperature=0.0)
        
        # Use fallback chain
        llm = get_llm(provider="best_speed", temperature=0.7)
        
        # Use default (OpenAI)
        llm = get_llm()
    """
    if provider is None:
        # Default to OpenAI if available
        provider = "openai" if os.getenv("OPENAI_API_KEY") else "best_speed"
    
    return PydanticAILLMWrapper(
        model_provider=provider,
        model_name=model,
        temperature=temperature,
        max_tokens=max_tokens
    )
