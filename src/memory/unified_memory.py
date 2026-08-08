#!/usr/bin/env python3
"""
Unified Memory System for Hermes-Agent - SIMPLE & WORKING VERSION
Integrates mem0 + Ollama embeddings + FAISS vector store
Supports 4 memory types: Semantic, Episodic, Procedural, Autobiographical

IMPORTANT: Disables PostHog telemetry by default (MEM0_TELEMETRY=False)
to avoid blocking calls to external analytics service.
"""

import os

# CRITICAL: Disable PostHog telemetry BEFORE importing mem0
os.environ.setdefault('MEM0_TELEMETRY', 'False')
os.environ.setdefault('POSTHOG_DISABLED', '1')
os.environ.setdefault('DO_NOT_TRACK', '1')

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from mem0 import Memory


class MemoryType(Enum):
    SEMANTIC = "semantic"
    EPISODIC = "episodic"
    PROCEDURAL = "procedural"
    AUTOBIOGRAPHICAL = "autobiographical"


@dataclass
class MemoryEntry:
    id: str
    type: MemoryType
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    source: str = "hermes-agent"
    tags: list[str] = field(default_factory=list)
    importance: float = 1.0


@dataclass
class SearchResult:
    entry: MemoryEntry
    score: float


class UnifiedMemory:
    """
    Sistema de memoria unificada SÍNCRONO (simple y robusto).
    Combina mem0 (persistencia) + Ollama (embeddings/LLM) + FAISS (vector store).
    
    Telemetría PostHog DESHABILITADA por defecto para evitar bloqueos.
    """

    def __init__(self, config: dict | None = None):
        self.config = config or self._default_config()
        self._memory = None
        self._initialized = False

    def _default_config(self) -> dict:
        return {
            'embedder': {
                'provider': 'ollama',
                'config': {
                    'model': 'nomic-embed-text:latest',
                    'ollama_base_url': os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434'),
                    'embedding_dims': 768
                }
            },
            'llm': {
                'provider': 'ollama',
                'config': {
                    'model': 'qwen2.5:7b',
                    'ollama_base_url': os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434'),
                    'temperature': 0.1,
                    'max_tokens': 2000
                }
            },
            'vector_store': {
                'provider': 'faiss',
                'config': {
                    'path': '/mnt/valentina_ssd/mem0_faiss',
                    'collection_name': 'hermes-agent',
                    'embedding_model_dims': 768
                }
            }
        }

    def initialize(self) -> bool:
        """Inicializa el sistema de memoria (síncrono)."""
        try:
            self._memory = Memory.from_config(self.config)
            self._initialized = True
            return True
        except Exception as e:
            print(f"Error inicializando memoria unificada: {e}")
            return False

    def _ensure_initialized(self):
        if not self._initialized:
            self.initialize()

    def add(
        self,
        content: str,
        memory_type: 'MemoryType',
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        importance: float = 1.0,
        user_id: str = "hermes-agent"
    ) -> dict[str, Any]:
        """Añade una entrada de memoria (síncrono)."""
        self._ensure_initialized()

        enriched_metadata = metadata or {}
        enriched_metadata.update({
            'memory_type': memory_type.value,
            'tags': tags or [],
            'importance': importance,
            'source': 'hermes-agent',
            'timestamp': datetime.now().isoformat()
        })

        return self._memory.add(
            messages=[{'role': 'user', 'content': content}],
            user_id=user_id,
            metadata=enriched_metadata
        )

    def search(
        self,
        query: str,
        memory_types: list['MemoryType'] | None = None,
        limit: int = 10,
        user_id: str = "hermes-agent"
    ) -> list[SearchResult]:
        """Busca en memoria (síncrono)."""
        self._ensure_initialized()

        results = self._memory.search(query=query, user_id=user_id, limit=limit)

        search_results = []
        for r in results.get('results', []):
            mem_type_str = r.get('metadata', {}).get('memory_type', 'semantic')
            try:
                mem_type = MemoryType(mem_type_str)
            except ValueError:
                mem_type = MemoryType.SEMANTIC

            entry = MemoryEntry(
                id=r.get('id', ''),
                type=mem_type,
                content=r.get('memory', ''),
                metadata=r.get('metadata', {}),
                timestamp=datetime.fromisoformat(r.get('created_at', datetime.now().isoformat())),
                tags=r.get('metadata', {}).get('tags', [])
            )
            search_results.append(SearchResult(entry=entry, score=r.get('score', 0.0)))

        return search_results

    def get_all(
        self,
        memory_type: Optional['MemoryType'] = None,
        user_id: str = "hermes-agent",
        limit: int = 100
    ) -> list[MemoryEntry]:
        """Obtiene todas las memorias (via search con query vacío)."""
        return self.search("", [memory_type] if memory_type else None, limit, user_id)

    def health_check(self) -> dict[str, Any]:
        """Verifica salud del sistema de memoria."""
        try:
            self._ensure_initialized()

            test_result = self.search("test", limit=1)

            return {
                'healthy': True,
                'initialized': self._initialized,
                'vector_store': 'faiss',
                'embedder': 'ollama:nomic-embed-text',
                'llm': 'ollama:qwen2.5:7b',
                'storage_path': '/mnt/valentina_ssd/mem0_faiss',
                'test_search_results': len(test_result)
            }
        except Exception as e:
            return {'healthy': False, 'error': str(e)}

    def close(self):
        pass


def create_unified_memory(config: dict | None = None) -> UnifiedMemory:
    """Factory function para crear e inicializar memoria unificada."""
    memory = UnifiedMemory(config)
    memory.initialize()
    return memory


# ============================================================
# DEMO / TEST
# ============================================================

def demo():
    print("=== Inicializando Memoria Unificada ===")

    memory = create_unified_memory()

    health = memory.health_check()
    print(f"Health: {health}")

    print("\n=== Añadiendo memorias ===")

    # Semántica
    memory.add(
        content="Estación H2O usa 165 botellones loaner modelo H2O-001 a H2O-165",
        memory_type=MemoryType.SEMANTIC,
        tags=["h2o", "swap", "inventario", "botellones"],
        importance=0.9
    )
    print("✅ Memoria semántica añadida")

    # Episódica
    memory.add(
        content="Cliente Hotel del Lago pidió 10 botellones, entrega completada a las 10:30 AM",
        memory_type=MemoryType.EPISODIC,
        tags=["entrega", "hotel_del_lago", "completada"],
        importance=0.7,
        metadata={"cliente": "Hotel del Lago", "cantidad": 10}
    )
    print("✅ Memoria episódica añadida")

    # Procedural
    memory.add(
        content="Procedimiento entrega: 1) Verificar pedido 2) Cargar botellones 3) Navegar GPS 4) Entregar 5) Recoger vacíos 6) Confirmar en app",
        memory_type=MemoryType.PROCEDURAL,
        tags=["procedimiento", "entrega", "workflow", "choferes"],
        importance=0.95,
        metadata={"version": "1.0", "tipo": "workflow_entrega"}
    )
    print("✅ Memoria procedural añadida")

    # Autobiográfica
    memory.add(
        content="Mi objetivo es ser la entidad aislada full-stack que opere Estación H2O de forma autónoma, gestionando SWAP, despacho, finanzas y logística sin intervención humana constante",
        memory_type=MemoryType.AUTOBIOGRAPHICAL,
        tags=["identidad", "mision", "autonomia", "objetivo"],
        importance=1.0,
        metadata={"tipo": "declaracion_mision", "version": "1.0"}
    )
    print("✅ Memoria autobiográfica añadida")

    # Búsquedas
    print("\n=== Búsquedas ===")

    results = memory.search("botellones loaner", limit=5)
    print(f"\nBúsqueda 'botellones loaner': {len(results)} resultados")
    for r in results:
        print(f"  [{r.entry.type.value}] Score: {r.score:.3f} - {r.entry.content[:80]}...")

    results = memory.search("entrega hotel", limit=5)
    print(f"\nBúsqueda 'entrega hotel': {len(results)} resultados")
    for r in results:
        print(f"  [{r.entry.type.value}] Score: {r.score:.3f} - {r.entry.content[:80]}...")

    results = memory.search("procedimiento entrega", limit=5)
    print(f"\nBúsqueda 'procedimiento entrega': {len(results)} resultados")
    for r in results:
        print(f"  [{r.entry.type.value}] Score: {r.score:.3f} - {r.entry.content[:80]}...")

    print("\n=== Demo completado ===")


# Re-export para uso externo
__all__ = [
    'UnifiedMemory',
    'MemoryType',
    'MemoryEntry',
    'SearchResult',
    'create_unified_memory',
    'demo'
]


if __name__ == "__main__":
    demo()
