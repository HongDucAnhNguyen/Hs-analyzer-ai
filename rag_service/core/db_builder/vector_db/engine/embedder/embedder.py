import logging
import os
from typing import List, Optional

from dotenv import load_dotenv
from loguru import logger
from openai import AsyncOpenAI, OpenAI
from tenacity import retry, stop_after_attempt, wait_random_exponential

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("knowledge_base")
load_dotenv()


class Embedder:
    """
    Embedder wraps OpenAI embeddings with retry logic.
    """
    def __init__(self,
                 api_key: Optional[str] = None,
                 model: str = "text-embedding-3-large",
                 dimensions: int = 1536,
                 max_retries: int = 6,
                 backoff_min: float = 1,
                 backoff_max: float = 20):
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable or api_key argument must be set")
        self.client = OpenAI(api_key=self.api_key)
        self.async_client = AsyncOpenAI(api_key=self.api_key)
        self.model = model
        self.dimensions = dimensions
        # Configure retry decorator attributes
        self._retry_decorator = retry(
            wait=wait_random_exponential(min=backoff_min, max=backoff_max),
            stop=stop_after_attempt(max_retries)
        )

    def get_embedding(self, text: str, model: Optional[str] = None) -> List[float]:
        """
        Returns embedding vector for a single text.
        """
        _model = model or self.model

        @self._retry_decorator
        def _call_api(_text: str, _model: str) -> List[float]:
            try:
                response = self.client.embeddings.create(
                    input=[_text],
                    model=_model,
                    dimensions=self.dimensions,
                )
                embed = response.data[0].embedding
                return embed
            except Exception as e:
                log.error(f"Error while embedding text: {e}", exc_info=True)
                raise

        return _call_api(text, _model)
    
    def get_embeddings(self, texts: List[str], model: Optional[str] = None) -> List[List[float]]:
        """
        Returns embedding vectors for a list of texts.
        """
        _model = model or self.model

        @self._retry_decorator
        def _call_api(_texts: List[str], _model: str) -> List[List[float]]:
            try:
                response = self.client.embeddings.create(
                    input=_texts,
                    model=_model,
                    dimensions=self.dimensions,
                )
                embeds = [data.embedding for data in response.data]
                return embeds
            except Exception as e:
                log.error(f"Error while embedding texts: {e}", exc_info=True)
                raise

        return _call_api(texts, _model)

    async def aget_embedding(self, text: str, model: Optional[str] = None) -> List[float]:
        """
        Asynchronously returns embedding vector for a single text.
        """
        _model = model or self.model

        @self._retry_decorator
        async def _acall_api(_text: str, _model: str) -> List[float]:
            try:
                response = await self.async_client.embeddings.create(
                    input=[_text],
                    model=_model,
                    dimensions=self.dimensions,
                )
                embed = response.data[0].embedding
                return embed
            except Exception as e:
                log.error(f"Error while async embedding text: {e}", exc_info=True)
                raise

        return await _acall_api(text, _model)

    async def aget_embeddings(self, texts: List[str], model: Optional[str] = None) -> List[List[float]]:
        """
        Asynchronously returns embedding vectors for a list of texts.
        """
        _model = model or self.model

        @self._retry_decorator
        async def _acall_api(_texts: List[str], _model: str) -> List[List[float]]:
            try:
                response = await self.async_client.embeddings.create(
                    input=_texts,
                    model=_model,
                    dimensions=self.dimensions,
                )
                embeds = [data.embedding for data in response.data]
                return embeds
            except Exception as e:
                log.error(f"Error while async embedding texts: {e}", exc_info=True)
                raise

        return await _acall_api(texts, _model)


# Example usage
if __name__ == '__main__':
    embedder = Embedder()
    text = "Your text goes here"
    vec = embedder.get_embedding(text)
    print(f"Embedding dimension: {len(vec)}")
    print(f"Embedding vector: {vec[:10]}...")  # Print first 10 dimensions for brevity