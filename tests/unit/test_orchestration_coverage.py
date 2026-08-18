"""Tests unitarios para src/orchestration/skill_registry.py.

Cubre SkillSpec, SkillRegistry y ExternalSkillIntegrator.
"""

import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.orchestration.skill_registry import (
    ExternalSkillIntegrator,
    SkillRegistry,
    SkillScope,
    SkillSpec,
    create_skill_registry,
)


@pytest.fixture
def empty_registry(tmp_path):
    """Registry con directorio temporal vacio (solo carga python skills)."""
    reg = SkillRegistry(skills_dir=str(tmp_path))
    reg.load_all()
    return reg


class TestSkillSpec:
    def test_defaults(self):
        spec = SkillSpec(name="test_skill", description="A test skill")
        assert spec.name == "test_skill"
        assert spec.version == "1.0.0"
        assert spec.author == "hermes-agent"
        assert spec.license == "MIT"
        assert spec.scope == SkillScope.GLOBAL
        assert spec.allowed_tools == []
        assert spec.dependencies == []
        assert spec.tags == []
        assert spec.instructions == ""
        assert spec.metadata == {}
        assert spec.file_path is None

    def test_discovery_info(self):
        spec = SkillSpec(name="my_skill", description="Does things")
        info = spec.discovery_info
        assert info == {"name": "my_skill", "description": "Does things"}

    def test_activation_info(self):
        spec = SkillSpec(
            name="my_skill",
            description="Does things",
            instructions="Run it",
            allowed_tools=["tool1"],
            dependencies=["dep1"],
            metadata={"key": "val"},
        )
        info = spec.activation_info
        assert info["name"] == "my_skill"
        assert info["instructions"] == "Run it"
        assert info["allowed_tools"] == ["tool1"]
        assert info["dependencies"] == ["dep1"]
        assert info["metadata"] == {"key": "val"}


class TestSkillScope:
    def test_values(self):
        assert SkillScope.GLOBAL.value == "global"
        assert SkillScope.AGENT_SPECIFIC.value == "agent"
        assert SkillScope.WORKFLOW.value == "workflow"


class TestSkillRegistryLoad:
    def test_load_all_with_no_dir(self):
        reg = SkillRegistry(skills_dir="/nonexistent/path")
        count = reg.load_all()
        assert count == 0
        assert reg._loaded is False

    def test_load_all_with_empty_dir(self, tmp_path):
        reg = SkillRegistry(skills_dir=str(tmp_path))
        count = reg.load_all()
        # _load_python_skills always returns 7 built-in skills
        assert count == 7
        assert reg._loaded is True
        assert "dispatcher_skill" in reg.skills
        assert "bottle_tracking" in reg.skills
        assert "payment_processing" in reg.skills

    def test_load_all_with_skill_md(self, tmp_path):
        skill_dir = tmp_path / "my_skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my_skill\ndescription: A custom skill\nversion: 2.0.0\n---\n\nInstructions here.\n",
            encoding="utf-8",
        )
        reg = SkillRegistry(skills_dir=str(tmp_path))
        count = reg.load_all()
        assert "my_skill" in reg.skills
        assert reg.skills["my_skill"].description == "A custom skill"
        assert reg.skills["my_skill"].version == "2.0.0"
        assert reg.skills["my_skill"].instructions == "Instructions here."

    def test_load_all_skill_md_no_frontmatter(self, tmp_path):
        skill_dir = tmp_path / "plain_skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("Plain instructions without frontmatter.\n", encoding="utf-8")
        reg = SkillRegistry(skills_dir=str(tmp_path))
        reg.load_all()
        assert "plain_skill" in reg.skills
        assert "Plain instructions" in reg.skills["plain_skill"].description

    def test_load_all_skill_md_invalid_yaml(self, tmp_path):
        skill_dir = tmp_path / "bad_yaml"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: bad_yaml\ndescription: [invalid\n  yaml: }\n---\n\nInstructions.\n",
            encoding="utf-8",
        )
        reg = SkillRegistry(skills_dir=str(tmp_path))
        reg.load_all()
        # Should still load the skill with default values
        assert "bad_yaml" in reg.skills


class TestSkillRegistryDiscover:
    def test_discover_all(self, empty_registry):
        results = empty_registry.discover()
        assert len(results) == 7

    def test_discover_with_query(self, empty_registry):
        results = empty_registry.discover(query="dispatch")
        assert len(results) >= 1
        assert any("dispatch" in r["name"].lower() for r in results)

    def test_discover_with_limit(self, empty_registry):
        results = empty_registry.discover(limit=2)
        assert len(results) <= 2

    def test_discover_no_match(self, empty_registry):
        results = empty_registry.discover(query="zzz_nonexistent_zzz")
        assert len(results) == 0


class TestSkillRegistryActivate:
    def test_activate_existing(self, empty_registry):
        result = empty_registry.activate("dispatcher_skill")
        assert result is not None
        assert result["name"] == "dispatcher_skill"
        assert "dependencies" in result

    def test_activate_nonexistent(self, empty_registry):
        result = empty_registry.activate("nonexistent_skill")
        assert result is None

    def test_activate_with_dependencies(self, empty_registry):
        result = empty_registry.activate("collections_workflow")
        assert result is not None
        assert "payment_processing" in result["dependencies"]


class TestSkillRegistryResources:
    def test_get_execution_resources_no_file(self, empty_registry):
        # Python skills have no file_path
        result = empty_registry.get_execution_resources("dispatcher_skill")
        assert result == {}

    def test_get_execution_resources_nonexistent_skill(self, empty_registry):
        result = empty_registry.get_execution_resources("nonexistent")
        assert result == {}

    def test_get_execution_resources_with_files(self, tmp_path):
        skill_dir = tmp_path / "res_skill"
        skill_dir.mkdir()
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "run.sh").write_text("#!/bin/bash\necho hi\n")
        (skill_dir / "SKILL.md").write_text(
            "---\nname: res_skill\ndescription: test\n---\n\nInstructions.\n",
            encoding="utf-8",
        )
        reg = SkillRegistry(skills_dir=str(tmp_path))
        reg.load_all()
        result = reg.get_execution_resources("res_skill")
        assert "scripts" in result
        assert "run.sh" in result["scripts"]

    def test_get_execution_resources_with_binary_asset(self, tmp_path):
        skill_dir = tmp_path / "bin_skill"
        skill_dir.mkdir()
        assets_dir = skill_dir / "assets"
        assets_dir.mkdir()
        (assets_dir / "image.bin").write_bytes(b"\x00\x01\x02\x03\xff")
        (skill_dir / "SKILL.md").write_text(
            "---\nname: bin_skill\ndescription: test\n---\n\nInstructions.\n",
            encoding="utf-8",
        )
        reg = SkillRegistry(skills_dir=str(tmp_path))
        reg.load_all()
        result = reg.get_execution_resources("bin_skill")
        assert "assets" in result
        assert "image.bin" in result["assets"]
        assert "binary" in result["assets"]["image.bin"]


class TestSkillRegistryDependencies:
    def test_analyze_dependencies(self, empty_registry):
        graph = empty_registry.analyze_dependencies()
        assert "dispatcher_skill" in graph
        assert "bottle_tracking" in graph["dispatcher_skill"]
        assert graph["payment_processing"] == []

    def test_find_composable_skills(self, empty_registry):
        composable = empty_registry.find_composable_skills("dispatcher_skill")
        assert isinstance(composable, list)

    def test_find_composable_nonexistent(self, empty_registry):
        composable = empty_registry.find_composable_skills("nonexistent")
        assert composable == []


class TestSkillRegistryAgent:
    def test_get_skills_for_agent_global(self, empty_registry):
        # All skills are GLOBAL scope, so all should be returned
        skills = empty_registry.get_skills_for_agent("any_agent")
        assert len(skills) == 7

    def test_get_skills_for_agent_specific(self, empty_registry):
        # Change one skill to AGENT_SPECIFIC
        empty_registry.skills["dispatcher_skill"].scope = SkillScope.AGENT_SPECIFIC
        empty_registry.skills["dispatcher_skill"].tags = ["dispatch_bot"]
        skills = empty_registry.get_skills_for_agent("dispatch_bot")
        assert len(skills) == 7  # 6 global + 1 agent-specific match


class TestSkillRegistryRegister:
    def test_register_skill(self, empty_registry):
        spec = SkillSpec(name="custom", description="Custom skill")
        empty_registry.register_skill(spec)
        assert "custom" in empty_registry.skills
        assert empty_registry.skills["custom"] is spec

    def test_create_skill_file(self, tmp_path):
        reg = SkillRegistry(skills_dir=str(tmp_path))
        spec = SkillSpec(
            name="new_skill",
            description="A new skill",
            instructions="Do things.",
            tags=["test"],
        )
        skill_file = reg.create_skill_file(spec)
        assert skill_file.exists()
        content = skill_file.read_text()
        assert "new_skill" in content
        assert "A new skill" in content
        assert "Do things." in content


class TestExternalSkillIntegrator:
    def test_import_from_skillnet(self, empty_registry):
        integrator = ExternalSkillIntegrator(empty_registry)
        from unittest.mock import MagicMock
        mock_client = MagicMock()
        result = integrator.import_from_skillnet(mock_client, "test", limit=5)
        assert result == []

    def test_import_from_adk_skills_nonexistent(self, empty_registry):
        integrator = ExternalSkillIntegrator(empty_registry)
        result = integrator.import_from_adk_skills("/nonexistent/path")
        assert result == []

    def test_import_from_adk_skills_with_files(self, tmp_path):
        adk_dir = tmp_path / "adk_skills"
        skill_dir = adk_dir / "ext_skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: ext_skill\ndescription: External skill\n---\n\nExternal instructions.\n",
            encoding="utf-8",
        )
        reg = SkillRegistry(skills_dir=str(tmp_path))
        integrator = ExternalSkillIntegrator(reg)
        result = integrator.import_from_adk_skills(str(adk_dir))
        assert len(result) == 1
        assert result[0].name == "ext_skill"
        assert result[0].metadata.get("source") == "adk"

    def test_import_from_anthropic_skills_nonexistent(self, empty_registry):
        integrator = ExternalSkillIntegrator(empty_registry)
        result = integrator.import_from_anthropic_skills("/nonexistent/path")
        assert result == []


class TestCreateSkillRegistry:
    def test_create_skill_registry(self, tmp_path):
        reg = create_skill_registry(skills_dir=str(tmp_path))
        assert isinstance(reg, SkillRegistry)
        assert reg._loaded is True
        assert len(reg.skills) == 7
