#!/usr/bin/env python3
"""
External Skill Library Integration for Hermes-Agent

Integrates:
- SkillNet (marketplace: search, download, create, evaluate, analyze, orchestrate)
- Google ADK Skills (skill registry interface, workflow integration)
- Anthropic Agent Skills (SKILL.md format, validation, progressive disclosure)

Provides unified interface for external skill discovery and auto-integration.
"""

import logging
import os
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, cast

# Import our internal systems
sys.path.insert(0, "/mnt/ssd_trabajo/hermes-agent/src")

from src.memory.unified_memory import MemoryType, UnifiedMemory
from src.orchestration.skill_registry import (
    SkillRegistry,
    SkillScope,
    SkillSpec,
    create_skill_registry,
)

# Disable telemetry for external libs
os.environ.setdefault("MEM0_TELEMETRY", "False")
os.environ.setdefault("POSTHOG_DISABLED", "1")
os.environ.setdefault("DO_NOT_TRACK", "1")


class ExternalSkillSource(Enum):
    SKILLNET = "skillnet"
    ADK = "adk"
    ANTHROPIC = "anthropic"
    LOCAL = "local"


@dataclass
class ExternalSkill:
    """Represents a skill from an external source"""

    name: str
    description: str
    source: ExternalSkillSource
    source_url: str
    version: str = "1.0.0"
    tags: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    allowed_tools: list[str] = field(default_factory=list)
    instructions: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    discovered_at: datetime = field(default_factory=datetime.now)


class SkillLibraryConnector(ABC):
    """Abstract base for external skill library connectors"""

    @abstractmethod
    def search(self, query: str, limit: int = 10) -> list[ExternalSkill]:
        """Search for skills"""
        pass

    @abstractmethod
    def download(self, skill: ExternalSkill, target_dir: str) -> str | None:
        """Download/install skill to local directory"""
        pass

    @abstractmethod
    def get_name(self) -> str:
        """Get connector name"""
        pass


class SkillNetConnector(SkillLibraryConnector):
    """Connector for SkillNet marketplace (500K+ skills)"""

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key or os.getenv("SKILLNET_API_KEY") or os.getenv("API_KEY")
        self.base_url = base_url or os.getenv("BASE_URL") or "https://api.openai.com/v1"
        self._client: Any = None

    def _get_client(self) -> Any:
        """Lazy load SkillNet client"""
        if self._client is None:
            try:
                # Add SkillNet to path
                skillnet_path = (
                    "/mnt/ssd_trabajo/hermes-agent/external_repos/skills/SkillNet/skillnet-ai/src"
                )
                if skillnet_path not in sys.path:
                    sys.path.insert(0, skillnet_path)

                from skillnet_ai import SkillNetClient  # type: ignore[import-not-found]

                self._client = SkillNetClient(api_key=self.api_key, base_url=self.base_url)
            except ImportError:
                # Fallback to REST API
                self._client = "rest_only"
        return self._client

    def search(self, query: str, limit: int = 10) -> list[ExternalSkill]:
        """Search SkillNet public library (no API key required for search)"""
        skills = []

        try:
            client = self._get_client()

            if client != "rest_only":
                # Use Python SDK
                results = client.search(q=query, mode="vector", threshold=0.75, limit=limit)
                for skill in results:
                    skills.append(
                        ExternalSkill(
                            name=getattr(skill, "skill_name", "unknown"),
                            description=getattr(skill, "skill_description", ""),
                            source=ExternalSkillSource.SKILLNET,
                            source_url=getattr(skill, "skill_url", ""),
                            tags=["skillnet", "marketplace"]
                            + (
                                [skill.category.lower()] if getattr(skill, "category", None) else []
                            ),
                            metadata={"stars": getattr(skill, "stars", 0)},
                        )
                    )
            else:
                # Use REST API fallback
                import requests

                resp = requests.get(
                    "http://api-skillnet.openkg.cn/v1/search",
                    params=cast(
                        Any,
                        {"q": query, "mode": "vector", "threshold": 0.75, "limit": limit},
                    ),
                    timeout=10,
                )
                if resp.status_code == 200:
                    for skill_data in resp.json().get("results", []):
                        skills.append(
                            ExternalSkill(
                                name=skill_data.get("skill_name", "unknown"),
                                description=skill_data.get("description", ""),
                                source=ExternalSkillSource.SKILLNET,
                                source_url=skill_data.get("skill_url", ""),
                                tags=["skillnet", "marketplace"],
                                metadata={"stars": skill_data.get("stars", 0)},
                            )
                        )

        except Exception as e:
            logging.warning(f"SkillNet search failed: {e}")

        return skills

    def download(self, skill: ExternalSkill, target_dir: str) -> str | None:
        """Download skill from GitHub URL"""
        try:
            client = self._get_client()

            if client != "rest_only" and hasattr(client, "download"):
                return cast(str, client.download(skill.source_url, target_dir=target_dir))

            # Fallback: use downloader directly
            skillnet_path = (
                "/mnt/ssd_trabajo/hermes-agent/external_repos/skills/SkillNet/skillnet-ai/src"
            )
            if skillnet_path not in sys.path:
                sys.path.insert(0, skillnet_path)

            from skillnet_ai.downloader import SkillDownloader  # type: ignore[import-not-found]

            downloader = SkillDownloader()
            return cast(str, downloader.download(skill.source_url, target_dir=target_dir))

        except Exception as e:
            logging.error(f"SkillNet download failed: {e}")
            return None

    def get_name(self) -> str:
        return "SkillNet"

    def evaluate_skill(self, skill_path: str) -> dict[str, Any]:
        """Evaluate a local skill using SkillNet evaluator"""
        try:
            skillnet_path = (
                "/mnt/ssd_trabajo/hermes-agent/external_repos/skills/SkillNet/skillnet-ai/src"
            )
            if skillnet_path not in sys.path:
                sys.path.insert(0, skillnet_path)

            from skillnet_ai import SkillNetClient

            client = SkillNetClient(api_key=self.api_key, base_url=self.base_url)
            return cast(dict[str, Any], client.evaluate(skill_path))
        except Exception as e:
            logging.error(f"SkillNet evaluation failed: {e}")
            return {"error": str(e)}

    def analyze_skills(self, skills_dir: str) -> dict[str, Any]:
        """Analyze skill relationships in a directory"""
        try:
            skillnet_path = (
                "/mnt/ssd_trabajo/hermes-agent/external_repos/skills/SkillNet/skillnet-ai/src"
            )
            if skillnet_path not in sys.path:
                sys.path.insert(0, skillnet_path)

            from skillnet_ai import SkillNetClient

            client = SkillNetClient(api_key=self.api_key, base_url=self.base_url)
            return cast(dict[str, Any], client.analyze(skills_dir))
        except Exception as e:
            logging.error(f"SkillNet analysis failed: {e}")
            return {"error": str(e)}


class ADKSkillsConnector(SkillLibraryConnector):
    """Connector for Google ADK skills format"""

    def __init__(
        self,
        adk_skills_path: str = (
            "/mnt/ssd_trabajo/hermes-agent/"
            "external_repos/orchestration/adk-python"
        ),
    ):
        self.adk_skills_path = Path(adk_skills_path)
        self._skill_registry = None

    def search(self, query: str, limit: int = 10) -> list[ExternalSkill]:
        """Search ADK skills directory"""
        skills = []

        # Look for skills in common locations
        search_paths = [
            self.adk_skills_path / "src" / "google" / "adk" / "skills",
            self.adk_skills_path / "contributing" / "samples",
            self.adk_skills_path / ".agents" / "skills",
        ]

        for search_path in search_paths:
            if search_path.exists():
                for skill_dir in search_path.rglob("*"):
                    if skill_dir.is_dir():
                        skill_file = skill_dir / "SKILL.md"
                        if skill_file.exists():
                            skill = self._parse_adk_skill(skill_file, skill_dir)
                            if skill and (
                                not query
                                or query.lower() in skill.name.lower()
                                or query.lower() in skill.description.lower()
                            ):
                                skills.append(skill)
                                if len(skills) >= limit:
                                    return skills

        return skills

    def _parse_adk_skill(self, skill_file: Path, skill_dir: Path) -> ExternalSkill | None:
        """Parse ADK skill format (similar to Agent Skills but with ADK extensions)"""
        try:
            import yaml

            content = skill_file.read_text(encoding="utf-8")

            frontmatter: dict[str, Any] = {}
            instructions = content

            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    parsed = yaml.safe_load(parts[1]) or {}
                    if not isinstance(parsed, dict):
                        parsed = {}
                    frontmatter = parsed
                    instructions = parts[2].strip()

            name = frontmatter.get("name", skill_dir.name)
            description = frontmatter.get("description", "")

            return ExternalSkill(
                name=name,
                description=description,
                source=ExternalSkillSource.ADK,
                source_url=f"file://{skill_dir}",
                version=frontmatter.get("version", "1.0.0"),
                tags=frontmatter.get("tags", []) + ["adk"],
                dependencies=frontmatter.get("dependencies", []),
                allowed_tools=frontmatter.get("allowed_tools", []),
                instructions=instructions,
                metadata={
                    "adk_additional_tools": frontmatter.get("metadata", {}).get(
                        "adk_additional_tools", []
                    ),
                    "adk_inject_state": frontmatter.get("metadata", {}).get(
                        "adk_inject_state", False
                    ),
                    "source_dir": str(skill_dir),
                },
            )
        except Exception as e:
            logging.warning(f"Failed to parse ADK skill {skill_file}: {e}")
            return None

    def download(self, skill: ExternalSkill, target_dir: str) -> str | None:
        """Copy ADK skill to local directory"""
        try:
            import shutil

            source_dir = Path(skill.metadata.get("source_dir", ""))
            if source_dir.exists():
                target = Path(target_dir) / skill.name
                shutil.copytree(source_dir, target, dirs_exist_ok=True)
                return str(target)
            return None
        except Exception as e:
            logging.error(f"ADK skill copy failed: {e}")
            return None

    def get_name(self) -> str:
        return "ADK Skills"


class AnthropicSkillsConnector(SkillLibraryConnector):
    """Connector for Anthropic Agent Skills format (skills-ref)"""

    def __init__(
        self, skills_path: str = "/mnt/ssd_trabajo/hermes-agent/external_repos/skills/skills"
    ):
        self.skills_path = Path(skills_path)

    def search(self, query: str, limit: int = 10) -> list[ExternalSkill]:
        """Search Anthropic skills"""
        skills = []

        # Check skills directory - use rglob to find all SKILL.md files recursively
        if self.skills_path.exists():
            for skill_file in self.skills_path.rglob("SKILL.md"):
                skill_dir = skill_file.parent
                skill = self._parse_anthropic_skill(skill_file, skill_dir)
                if skill and (
                    not query
                    or query.lower() in skill.name.lower()
                    or query.lower() in skill.description.lower()
                ):
                    skills.append(skill)
                    if len(skills) >= limit:
                        break

        return skills

    def _parse_anthropic_skill(self, skill_file: Path, skill_dir: Path) -> ExternalSkill | None:
        """Parse Anthropic Agent Skills SKILL.md format"""
        try:
            import yaml

            content = skill_file.read_text(encoding="utf-8")

            frontmatter: dict[str, Any] = {}
            instructions = content

            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    parsed = yaml.safe_load(parts[1]) or {}
                    if not isinstance(parsed, dict):
                        parsed = {}
                    frontmatter = parsed
                    instructions = parts[2].strip()

            name = frontmatter.get("name", skill_dir.name)
            description = frontmatter.get("description", "")

            return ExternalSkill(
                name=name,
                description=description,
                source=ExternalSkillSource.ANTHROPIC,
                source_url=f"file://{skill_dir}",
                version=frontmatter.get("version", "1.0.0"),
                tags=frontmatter.get("tags", []) + ["anthropic", "agentskills"],
                dependencies=frontmatter.get("dependencies", []),
                allowed_tools=frontmatter.get("allowed_tools", []),
                instructions=instructions,
                metadata={
                    "source_dir": str(skill_dir),
                    "license": frontmatter.get("license", "Apache-2.0"),
                },
            )
        except Exception as e:
            logging.warning(f"Failed to parse Anthropic skill {skill_file}: {e}")
            return None

    def download(self, skill: ExternalSkill, target_dir: str) -> str | None:
        """Copy Anthropic skill to local directory"""
        try:
            import shutil

            source_dir = Path(skill.metadata.get("source_dir", ""))
            if source_dir.exists():
                target = Path(target_dir) / skill.name
                shutil.copytree(source_dir, target, dirs_exist_ok=True)
                return str(target)
            return None
        except Exception as e:
            logging.error(f"Anthropic skill copy failed: {e}")
            return None

    def get_name(self) -> str:
        return "Anthropic Agent Skills"

    def validate_skill(self, skill_path: str) -> list[str]:
        """Validate skill using skills-ref"""
        try:
            skills_ref_path = (
                "/mnt/ssd_trabajo/hermes-agent/external_repos/skills/agentskills/skills-ref/src"
            )
            if skills_ref_path not in sys.path:
                sys.path.insert(0, skills_ref_path)

            from pathlib import Path

            from skills_ref import validate  # type: ignore[import-not-found]

            return cast(list[str], validate(Path(skill_path)))
        except Exception as e:
            logging.error(f"Skills-ref validation failed: {e}")
            return [f"Validation error: {e}"]


class SkillCreator:
    """Auto-create skills from execution traces using LLMs"""

    def __init__(self, memory: UnifiedMemory):
        self.memory = memory
        self._skillnet_creator: Any = None

    def _get_skillnet_creator(self) -> Any:
        """Lazy load SkillNet creator"""
        if self._skillnet_creator is None:
            try:
                skillnet_path = (
                    "/mnt/ssd_trabajo/hermes-agent/external_repos/skills/SkillNet/skillnet-ai/src"
                )
                if skillnet_path not in sys.path:
                    sys.path.insert(0, skillnet_path)

                from skillnet_ai import SkillCreator as SkillNetSkillCreator

                self._skillnet_creator = SkillNetSkillCreator(
                    api_key=os.getenv("SKILLNET_API_KEY") or os.getenv("API_KEY"),
                    base_url=os.getenv("BASE_URL") or "https://api.openai.com/v1",
                )
            except Exception as e:
                logging.warning(f"Could not load SkillNet creator: {e}")
                self._skillnet_creator = "unavailable"
        return self._skillnet_creator

    def create_from_trajectory(self, trajectory: str, output_dir: str) -> list[str]:
        """Create skills from execution trajectory using SkillNet"""
        creator = self._get_skillnet_creator()
        if creator == "unavailable":
            return self._create_basic_skill(trajectory, output_dir)

        try:
            return cast(list[str], creator.create_from_trajectory(trajectory, output_dir))
        except Exception as e:
            logging.error(f"SkillNet creation failed: {e}")
            return self._create_basic_skill(trajectory, output_dir)

    def create_from_episodic_memory(self, agent_type: str, limit: int = 10) -> list[str]:
        """Create skills from agent's episodic memories"""
        # Search for recent executions
        results = self.memory.search(
            query=f"{agent_type} execution task", memory_types=[MemoryType.EPISODIC], limit=limit
        )

        if not results:
            return []

        # Build trajectory from memories
        trajectory_parts = []
        for r in results:
            trajectory_parts.append(f"Task: {r.entry.content}")
            trajectory_parts.append(f"Result: {r.entry.metadata}")

        trajectory = "\n\n".join(trajectory_parts)
        output_dir = "/mnt/ssd_trabajo/hermes-agent/skills/auto_generated"

        return self.create_from_trajectory(trajectory, output_dir)

    def _create_basic_skill(self, trajectory: str, output_dir: str) -> list[str]:
        """Create basic skill without external LLM"""
        import hashlib

        skill_name = f"auto_skill_{hashlib.md5(trajectory.encode()).hexdigest()[:8]}"
        skill_dir = Path(output_dir) / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)

        # Create SKILL.md
        skill_md = f"""---
name: {skill_name}
description: Auto-generated skill from execution trajectory
version: 1.0.0
author: hermes-agent-auto
license: MIT
scope: global
tags: [auto-generated, {skill_name}]
dependencies: []
allowed_tools: []
---

# {skill_name}

Auto-generated skill from execution trajectory.

## Trajectory Summary
{trajectory[:1000]}...

## Instructions
This skill was automatically generated from agent execution patterns.
Review and refine the instructions before use.

## Usage
This skill encapsulates a repeated pattern observed in agent executions.
"""
        (skill_dir / "SKILL.md").write_text(skill_md)

        return [str(skill_dir)]


class ExternalSkillIntegrator:
    """
    Main integrator for external skill libraries.

    Provides unified interface for:
    - Searching across all external sources
    - Downloading/installing skills
    - Auto-creating skills from traces
    - Evaluating and analyzing skills
    - Registering skills in local registry
    """

    def __init__(self, memory: UnifiedMemory, skill_registry: SkillRegistry):
        self.memory = memory
        self.skill_registry = skill_registry

        # Initialize connectors
        self.connectors = {
            ExternalSkillSource.SKILLNET: SkillNetConnector(),
            ExternalSkillSource.ADK: ADKSkillsConnector(),
            ExternalSkillSource.ANTHROPIC: AnthropicSkillsConnector(),
        }

        # Skill creator
        self.skill_creator = SkillCreator(memory)

        # Auto-generated skills directory
        self.auto_skills_dir = Path("/mnt/ssd_trabajo/hermes-agent/skills/auto_generated")
        self.auto_skills_dir.mkdir(parents=True, exist_ok=True)

    def search_all_sources(
        self, query: str, limit_per_source: int = 5
    ) -> dict[str, list[ExternalSkill]]:
        """Search all external sources for skills"""
        results = {}
        for source, connector in self.connectors.items():
            try:
                skills = connector.search(query, limit=limit_per_source)
                if skills:
                    results[source.value] = skills
            except Exception as e:
                logging.warning(f"Search failed for {connector.get_name()}: {e}")
        return results

    def install_skill(self, skill: ExternalSkill) -> SkillSpec | None:
        """Download and register an external skill"""
        connector = self.connectors.get(skill.source)
        if not connector:
            return None

        # Download to auto skills directory
        local_path = connector.download(skill, str(self.auto_skills_dir))
        if not local_path:
            return None

        # Parse and register
        skill_dir = Path(local_path)
        skill_file = skill_dir / "SKILL.md"

        if skill_file.exists():
            # Register with our skill registry
            self.skill_registry.create_skill_file(
                SkillSpec(
                    name=skill.name,
                    description=skill.description,
                    version=skill.version,
                    author=skill.metadata.get("author", "external"),
                    license=skill.metadata.get("license", "MIT"),
                    scope=SkillScope.GLOBAL,
                    allowed_tools=skill.allowed_tools,
                    dependencies=skill.dependencies,
                    tags=skill.tags,
                    instructions=skill.instructions,
                    metadata=skill.metadata,
                ),
                target_dir=str(self.auto_skills_dir),
            )

            return self.skill_registry.skills.get(skill.name)

        return None

    def auto_create_skills(self, agent_type: str, limit: int = 10) -> list[SkillSpec]:
        """Auto-create skills from agent's execution history"""
        created_paths = self.skill_creator.create_from_episodic_memory(agent_type, limit)
        registered = []

        for path in created_paths:
            skill_dir = Path(path)
            skill_file = skill_dir / "SKILL.md"
            if skill_file.exists():
                # Register with our skill registry
                self.skill_registry.create_skill_file(
                    SkillSpec(
                        name=skill_dir.name,
                        description="Auto-generated from execution traces",
                        version="1.0.0",
                        author="hermes-agent-auto",
                        license="MIT",
                        scope=SkillScope.GLOBAL,
                        tags=["auto-generated", agent_type],
                        metadata={"source": "auto_creation", "agent_type": agent_type},
                    ),
                    target_dir=str(self.auto_skills_dir),
                )
                registered.append(self.skill_registry.skills.get(skill_dir.name))

        return [s for s in registered if s]

    def evaluate_skill(self, skill_name: str) -> dict[str, Any]:
        """Evaluate a skill using SkillNet evaluator"""
        connector = self.connectors.get(ExternalSkillSource.SKILLNET)
        if isinstance(connector, SkillNetConnector):
            skill_path = str(self.auto_skills_dir / skill_name)
            return connector.evaluate_skill(skill_path)
        return {"error": "SkillNet connector not available"}

    def analyze_skill_relationships(self) -> dict[str, Any]:
        """Analyze relationships between all local skills"""
        connector = self.connectors.get(ExternalSkillSource.SKILLNET)
        if isinstance(connector, SkillNetConnector):
            return connector.analyze_skills(str(self.auto_skills_dir))

        # Fallback: use our registry's dependency analysis
        return {
            "dependencies": self.skill_registry.analyze_dependencies(),
            "composable": {
                name: self.skill_registry.find_composable_skills(name)
                for name in self.skill_registry.skills
            },
        }

    def get_skill_recommendations(self, agent_type: str, task: str) -> list[ExternalSkill]:
        """Get skill recommendations for an agent/task"""
        # Search all sources
        results = self.search_all_sources(task, limit_per_source=3)

        # Filter for agent relevance
        recommendations = []
        for _, skills in results.items():
            for skill in skills:
                # Match if skill has no specific tags (generic) or matches agent type
                skill_tags_lower = [t.lower() for t in skill.tags]
                agent_match = (
                    not skill_tags_lower
                    or agent_type.lower() in skill_tags_lower
                    or any(agent_type.lower() in t for t in skill_tags_lower)
                )
                task_match = (
                    task.lower() in skill.description.lower()
                    or task.lower() in skill.name.lower()
                    or any(word in skill.description.lower() for word in task.lower().split())
                )

                if agent_match or task_match:
                    recommendations.append(skill)

        return recommendations[:10]


# ============================================================
# FACTORY FUNCTIONS
# ============================================================


def create_external_skill_integrator(
    memory: UnifiedMemory, skill_registry: SkillRegistry
) -> ExternalSkillIntegrator:
    """Factory to create the external skill integrator"""
    return ExternalSkillIntegrator(memory, skill_registry)


# ============================================================
# DEMO / TEST
# ============================================================


def demo() -> None:
    """Demo the external skill integration"""
    print("=== External Skill Library Integration Demo ===\n")

    # Initialize memory
    memory = UnifiedMemory()
    print("Memory:", memory.health_check()["healthy"])

    # Initialize skill registry
    skill_registry = create_skill_registry()
    print(f"Skill Registry: {len(skill_registry.skills)} skills loaded")

    # Create integrator
    integrator = create_external_skill_integrator(memory, skill_registry)

    # Search all sources
    print("\n--- Searching External Sources ---")
    results = integrator.search_all_sources("pdf processing", limit_per_source=3)
    for source, skills in results.items():
        print(f"\n{source.upper()}: {len(skills)} skills")
        for skill in skills[:2]:
            print(f"  - {skill.name}: {skill.description[:60]}...")

    # Get recommendations for dispatcher
    print("\n--- Skill Recommendations for Dispatcher ---")
    recs = integrator.get_skill_recommendations("dispatcher", "route optimization")
    for skill in recs[:3]:
        print(f"  - {skill.name} ({skill.source.value}): {skill.description[:60]}...")

    # Analyze skill relationships
    print("\n--- Skill Relationship Analysis ---")
    analysis = integrator.analyze_skill_relationships()
    print(f"Dependencies: {len(analysis.get('dependencies', {}))}")
    print(f"Composable pairs: {sum(len(v) for v in analysis.get('composable', {}).values())}")

    # Auto-create skills from dispatcher memory
    print("\n--- Auto-Creating Skills from Dispatcher Memory ---")
    created = integrator.auto_create_skills("dispatcher", limit=3)
    print(f"Created {len(created)} auto-generated skills")

    print("\n=== Demo Complete ===")


if __name__ == "__main__":
    demo()
