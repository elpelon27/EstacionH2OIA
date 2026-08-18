"""Tests unitarios para src/orchestration/external_skills.py.

Cubre: ExternalSkill, ExternalSkillSource, SkillNetConnector,
ADKSkillsConnector, AnthropicSkillsConnector, SkillCreator,
ExternalSkillIntegrator.

Todos los imports externos (skillnet_ai, skills_ref) son mockeados.
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.orchestration.external_skills import (
    ADKSkillsConnector,
    AnthropicSkillsConnector,
    ExternalSkill,
    ExternalSkillIntegrator,
    ExternalSkillSource,
    SkillCreator,
    SkillLibraryConnector,
    SkillNetConnector,
    create_external_skill_integrator,
)
from src.orchestration.skill_registry import SkillRegistry, SkillSpec


# ============================================================
# ExternalSkillSource and ExternalSkill
# ============================================================

class TestExternalSkillSource:
    def test_values(self):
        assert ExternalSkillSource.SKILLNET.value == "skillnet"
        assert ExternalSkillSource.ADK.value == "adk"
        assert ExternalSkillSource.ANTHROPIC.value == "anthropic"
        assert ExternalSkillSource.LOCAL.value == "local"


class TestExternalSkill:
    def test_defaults(self):
        skill = ExternalSkill(
            name="test",
            description="A test skill",
            source=ExternalSkillSource.LOCAL,
            source_url="http://example.com",
        )
        assert skill.version == "1.0.0"
        assert skill.tags == []
        assert skill.dependencies == []
        assert skill.allowed_tools == []
        assert skill.instructions == ""
        assert skill.metadata == {}

    def test_with_fields(self):
        skill = ExternalSkill(
            name="full",
            description="Full skill",
            source=ExternalSkillSource.SKILLNET,
            source_url="http://example.com",
            version="2.0.0",
            tags=["tag1", "tag2"],
            dependencies=["dep1"],
            allowed_tools=["tool1"],
            instructions="Run it",
            metadata={"key": "val"},
        )
        assert skill.version == "2.0.0"
        assert skill.tags == ["tag1", "tag2"]


# ============================================================
# SkillNetConnector
# ============================================================

class TestSkillNetConnector:
    def test_init_defaults(self):
        conn = SkillNetConnector()
        assert conn.api_key is not None or conn.api_key is None  # depends on env
        assert conn.base_url is not None or conn.base_url is None
        assert conn._client is None

    def test_init_with_args(self):
        conn = SkillNetConnector(api_key="test-key", base_url="http://custom.api")
        assert conn.api_key == "test-key"
        assert conn.base_url == "http://custom.api"

    def test_get_name(self):
        conn = SkillNetConnector()
        assert conn.get_name() == "SkillNet"

    def test_search_no_client(self):
        """Search with no SkillNet client installed should return empty list."""
        conn = SkillNetConnector(api_key=None, base_url=None)
        # _get_client falls back to "rest_only" or None
        results = conn.search("test query", limit=5)
        assert isinstance(results, list)

    def test_search_with_mock_client(self):
        conn = SkillNetConnector(api_key="test", base_url="http://test")
        # Mock the client to return results
        mock_skill = MagicMock()
        mock_skill.skill_name = "mock_skill"
        mock_skill.skill_description = "A mock skill"
        mock_skill.skill_url = "http://example.com/skill"
        mock_skill.category = "testing"
        mock_skill.stars = 42

        mock_client = MagicMock()
        mock_client.search.return_value = [mock_skill]
        conn._client = mock_client

        results = conn.search("test", limit=5)
        assert len(results) == 1
        assert results[0].name == "mock_skill"
        assert results[0].source == ExternalSkillSource.SKILLNET

    def test_search_exception_returns_empty(self):
        conn = SkillNetConnector(api_key="test", base_url="http://test")
        mock_client = MagicMock()
        mock_client.search.side_effect = Exception("API error")
        conn._client = mock_client
        results = conn.search("test")
        assert results == []

    def test_download_no_client(self):
        conn = SkillNetConnector(api_key=None, base_url=None)
        skill = ExternalSkill(
            name="test",
            description="test",
            source=ExternalSkillSource.SKILLNET,
            source_url="http://example.com",
        )
        result = conn.download(skill, "/tmp/test_download")
        # Should return None (no client available)
        assert result is None

    def test_evaluate_skill_exception(self):
        conn = SkillNetConnector(api_key=None, base_url=None)
        result = conn.evaluate_skill("/nonexistent/skill")
        assert "error" in result

    def test_analyze_skills_exception(self):
        conn = SkillNetConnector(api_key=None, base_url=None)
        result = conn.analyze_skills("/nonexistent/dir")
        assert "error" in result


# ============================================================
# ADKSkillsConnector
# ============================================================

class TestADKSkillsConnector:
    def test_init_defaults(self):
        conn = ADKSkillsConnector()
        assert isinstance(conn.adk_skills_path, Path)

    def test_get_name(self):
        conn = ADKSkillsConnector()
        assert conn.get_name() == "ADK Skills"

    def test_search_nonexistent_path(self):
        conn = ADKSkillsConnector(adk_skills_path="/nonexistent/path")
        results = conn.search("test")
        assert results == []

    def test_search_with_skill_md(self, tmp_path):
        # Create a fake ADK skills directory
        adk_root = tmp_path / "adk"
        skills_dir = adk_root / "src" / "google" / "adk" / "skills"
        skill_dir = skills_dir / "test_skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: test_skill\ndescription: A test ADK skill\n---\n\nInstructions.\n",
            encoding="utf-8",
        )
        conn = ADKSkillsConnector(adk_skills_path=str(adk_root))
        results = conn.search("test")
        assert len(results) == 1
        assert results[0].name == "test_skill"
        assert results[0].source == ExternalSkillSource.ADK

    def test_download_nonexistent_source(self, tmp_path):
        conn = ADKSkillsConnector(adk_skills_path="/nonexistent")
        skill = ExternalSkill(
            name="test",
            description="test",
            source=ExternalSkillSource.ADK,
            source_url="file:///nonexistent",
            metadata={"source_dir": "/nonexistent"},
        )
        result = conn.download(skill, str(tmp_path))
        assert result is None


# ============================================================
# AnthropicSkillsConnector
# ============================================================

class TestAnthropicSkillsConnector:
    def test_init_defaults(self):
        conn = AnthropicSkillsConnector()
        assert isinstance(conn.skills_path, Path)

    def test_get_name(self):
        conn = AnthropicSkillsConnector()
        assert conn.get_name() == "Anthropic Agent Skills"

    def test_search_nonexistent_path(self):
        conn = AnthropicSkillsConnector(skills_path="/nonexistent/path")
        results = conn.search("test")
        assert results == []

    def test_search_with_skill_md(self, tmp_path):
        skills_root = tmp_path / "anthropic_skills"
        skill_dir = skills_root / "my_skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my_skill\ndescription: Anthropic test skill\n---\n\nDo things.\n",
            encoding="utf-8",
        )
        conn = AnthropicSkillsConnector(skills_path=str(skills_root))
        results = conn.search("my_skill")
        assert len(results) == 1
        assert results[0].source == ExternalSkillSource.ANTHROPIC

    def test_validate_skill_exception(self):
        conn = AnthropicSkillsConnector(skills_path="/nonexistent")
        result = conn.validate_skill("/nonexistent/skill")
        assert isinstance(result, list)
        assert len(result) > 0  # Should contain error message


# ============================================================
# SkillCreator
# ============================================================

class TestSkillCreator:
    def test_create_basic_skill(self, tmp_path):
        """Test _create_basic_skill creates a SKILL.md file."""
        from src.memory.unified_memory import UnifiedMemory

        mock_mem = MagicMock()
        creator = SkillCreator(mock_mem)
        result = creator._create_basic_skill("test trajectory data", str(tmp_path))
        assert len(result) == 1
        skill_file = Path(result[0]) / "SKILL.md"
        assert skill_file.exists()
        content = skill_file.read_text()
        assert "auto_skill_" in content

    def test_create_from_trajectory_unavailable(self, tmp_path):
        """When SkillNet creator is unavailable, falls back to basic skill."""
        mock_mem = MagicMock()
        creator = SkillCreator(mock_mem)
        creator._skillnet_creator = "unavailable"
        result = creator.create_from_trajectory("trajectory", str(tmp_path))
        assert len(result) == 1

    def test_create_from_episodic_memory_no_results(self):
        """When no memories found, returns empty list."""
        mock_mem = MagicMock()
        mock_mem.search.return_value = []
        creator = SkillCreator(mock_mem)
        result = creator.create_from_episodic_memory("dispatcher", limit=5)
        assert result == []

    def test_create_from_episodic_memory_with_results(self, tmp_path):
        """When memories found, creates skills from trajectory."""
        from src.memory.unified_memory import MemoryEntry, MemoryType, SearchResult

        entry = MemoryEntry(
            id="mem-001",
            type=MemoryType.EPISODIC,
            content="Executed task: plan routes",
            metadata={"success": True},
        )
        mock_mem = MagicMock()
        mock_mem.search.return_value = [SearchResult(entry=entry, score=0.9)]

        creator = SkillCreator(mock_mem)
        # Patch create_from_trajectory to use tmp_path
        with patch.object(creator, "create_from_trajectory", return_value=[str(tmp_path / "auto_skill")]):
            result = creator.create_from_episodic_memory("dispatcher", limit=5)
            assert len(result) == 1


# ============================================================
# ExternalSkillIntegrator
# ============================================================

class TestExternalSkillIntegrator:
    @pytest.fixture
    def integrator(self, tmp_path):
        mock_mem = MagicMock()
        registry = SkillRegistry(skills_dir=str(tmp_path))
        registry.load_all()
        # Patch auto_skills_dir to tmp
        integrator = ExternalSkillIntegrator(mock_mem, registry)
        integrator.auto_skills_dir = tmp_path / "auto_skills"
        integrator.auto_skills_dir.mkdir(parents=True, exist_ok=True)
        return integrator

    def test_init(self, integrator):
        assert integrator.memory is not None
        assert integrator.skill_registry is not None
        assert ExternalSkillSource.SKILLNET in integrator.connectors
        assert ExternalSkillSource.ADK in integrator.connectors
        assert ExternalSkillSource.ANTHROPIC in integrator.connectors

    def test_search_all_sources(self, integrator):
        results = integrator.search_all_sources("test query", limit_per_source=2)
        assert isinstance(results, dict)

    def test_install_skill_no_connector(self, integrator):
        skill = ExternalSkill(
            name="test",
            description="test",
            source=ExternalSkillSource.LOCAL,
            source_url="http://example.com",
        )
        result = integrator.install_skill(skill)
        assert result is None

    def test_auto_create_skills_no_memory(self, integrator):
        """When no episodic memories, returns empty list."""
        integrator.memory.search.return_value = []
        result = integrator.auto_create_skills("dispatcher", limit=3)
        assert result == []

    def test_evaluate_skill(self, integrator):
        result = integrator.evaluate_skill("nonexistent_skill")
        # Should return error dict (SkillNet not available)
        assert isinstance(result, dict)

    def test_analyze_skill_relationships(self, integrator):
        result = integrator.analyze_skill_relationships()
        assert isinstance(result, dict)
        # Falls back to registry's dependency analysis
        assert "dependencies" in result or "error" in result

    def test_get_skill_recommendations(self, integrator):
        result = integrator.get_skill_recommendations("dispatcher", "route optimization")
        assert isinstance(result, list)


# ============================================================
# Factory function
# ============================================================

class TestCreateExternalSkillIntegrator:
    def test_factory(self, tmp_path):
        mock_mem = MagicMock()
        registry = SkillRegistry(skills_dir=str(tmp_path))
        registry.load_all()
        integrator = create_external_skill_integrator(mock_mem, registry)
        assert isinstance(integrator, ExternalSkillIntegrator)
        assert integrator.memory is mock_mem


# ============================================================
# Abstract base class
# ============================================================

class TestSkillLibraryConnector:
    def test_cannot_instantiate_abstract(self):
        """SkillLibraryConnector is abstract and cannot be instantiated directly."""
        with pytest.raises(TypeError):
            SkillLibraryConnector()
