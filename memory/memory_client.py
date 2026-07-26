"""Cliente de memoria semántica con mem0 + Qdrant + embeddings locales.

Usa nomic-embed-text (vía Ollama) para embeddings 100% locales.
Usa Qwen 2.5 7B (vía Ollama) para extracción de memoria (LLM de mem0).
No envía datos de clientes a la nube.
"""
from typing import Any
from core.config import get_settings
from core.logger import get_logger

logger = get_logger("memory")


class MemoryClient:
    """Cliente singleton para mem0 + Qdrant."""

    _instance: "MemoryClient | None" = None

    def __init__(self) -> None:
        from mem0 import Memory  # type: ignore[import-untyped]

        settings = get_settings()
        config = {
            "vector_store": {
                "provider": "qdrant",
                "config": {
                    "url": settings.qdrant_url,
                    "api_key": settings.qdrant_api_key,
                    "collection_name": settings.qdrant_collection,
                },
            },
            "embedder": {
                "provider": "ollama",
                "config": {
                    "model": "nomic-embed-text:latest",
                    "ollama_base_url": settings.ollama_host,
                },
            },
            "llm": {
                "provider": "ollama",
                "config": {
                    "model": "qwen2.5:7b",
                    "ollama_base_url": settings.ollama_host,
                },
            },
        }
        self.client = Memory.from_config(config)
        logger.info("memory_client_initialized", collection=settings.qdrant_collection)

    @classmethod
    def get_instance(cls) -> "MemoryClient":
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def add_memory(
        self,
        content: str,
        user_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Guardar un recuerdo del cliente."""
        try:
            result = self.client.add(
                messages=content,
                user_id=user_id,
                metadata=metadata or {},
            )
            result_dict: dict[str, Any] = {
                "id": result.get("id", ""),
                "event_type": result.get("event", "ADD"),
            }
            logger.info(
                "memory_added",
                user_id=user_id,
                content_preview=content[:50],
                event_type=result_dict["event_type"],
            )
            return result_dict
        except Exception as e:
            logger.error("memory_add_error", user_id=user_id, error=str(e))
            raise

    async def search_memory(
        self,
        query: str,
        user_id: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Buscar recuerdos relevantes del cliente."""
        try:
            results = self.client.search(
                query=query,
                user_id=user_id,
                limit=limit,
            )
            logger.info(
                "memory_search",
                user_id=user_id,
                query_preview=query[:50],
                results_count=len(results) if isinstance(results, list) else 0,
            )
            return results if isinstance(results, list) else []
        except Exception as e:
            logger.error("memory_search_error", user_id=user_id, error=str(e))
            return []

    async def get_client_memories(self, user_id: str) -> list[dict[str, Any]]:
        """Obtener todos los recuerdos de un cliente."""
        try:
            results = self.client.get_all(user_id=user_id)
            logger.info(
                "memory_get_all",
                user_id=user_id,
                total_count=len(results) if isinstance(results, list) else 0,
            )
            return results if isinstance(results, list) else []
        except Exception as e:
            logger.error("memory_get_all_error", user_id=user_id, error=str(e))
            return []

    async def delete_memory(self, memory_id: str) -> bool:
        """Eliminar un recuerdo específico."""
        try:
            self.client.delete(memory_id=memory_id)
            logger.info("memory_deleted", memory_id=memory_id)
            return True
        except Exception as e:
            logger.error("memory_delete_error", memory_id=memory_id, error=str(e))
            return False


async def get_memory() -> MemoryClient:
    """Helper async-friendly."""
    return MemoryClient.get_instance()
