"""Shared fixtures for orchestration tests — mock UnifiedMemory and SkillRegistry."""

import os
import sys
from unittest.mock import MagicMock

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.memory.unified_memory import MemoryEntry, MemoryType, SearchResult


@pytest.fixture
def mock_memory():
    """Mock UnifiedMemory with search() and add() returning predictable results."""
    mem = MagicMock()

    # search returns list[SearchResult]
    entry = MemoryEntry(
        id="mem-001",
        type=MemoryType.SEMANTIC,
        content="Test memory content for orchestration",
        metadata={"source": "test"},
        tags=["test"],
    )
    mem.search.return_value = [SearchResult(entry=entry, score=0.85)]

    # add returns dict
    mem.add.return_value = {"id": "mem-new", "status": "ok"}

    return mem


@pytest.fixture
def mock_orchestrator(mock_memory):
    """Create a real Orchestrator with mock memory."""
    from src.orchestration.orchestrator import Orchestrator

    return Orchestrator(memory=mock_memory)
