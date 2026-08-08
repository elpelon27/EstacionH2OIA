"""
Memory Package for Hermes-Agent
Unified memory system with mem0 + Ollama + FAISS
"""

from .unified_memory import (
    MemoryEntry,
    MemoryType,
    SearchResult,
    UnifiedMemory,
    create_unified_memory,
    demo,
)

__all__ = [
    'UnifiedMemory',
    'MemoryType',
    'MemoryEntry',
    'SearchResult',
    'create_unified_memory',
    'demo'
]
