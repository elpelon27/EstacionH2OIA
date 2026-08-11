"""
Skill Registry for Hermes-Agent

Implements Agent Skills specification (agentskills.io):
- Progressive disclosure: Discovery -> Activation -> Execution
- SKILL.md parsing with frontmatter
- Skill composition and dependency analysis
- Integration with external skill libraries (SkillNet, ADK skills)
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

import yaml


class SkillScope(Enum):
    """Scope of skill availability"""

    GLOBAL = "global"
    AGENT_SPECIFIC = "agent"
    WORKFLOW = "workflow"


@dataclass
class SkillSpec:
    """Skill specification following Agent Skills format"""

    name: str
    description: str
    version: str = "1.0.0"
    author: str = "hermes-agent"
    license: str = "MIT"
    scope: SkillScope = SkillScope.GLOBAL
    allowed_tools: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    instructions: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    file_path: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    @property
    def discovery_info(self) -> dict[str, str]:
        return {"name": self.name, "description": self.description}

    @property
    def activation_info(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "instructions": self.instructions,
            "allowed_tools": self.allowed_tools,
            "dependencies": self.dependencies,
            "metadata": self.metadata,
        }


class SkillRegistry:
    def __init__(self, skills_dir: str = "/mnt/ssd_trabajo/hermes-agent/skills"):
        self.skills_dir = Path(skills_dir)
        self.skills: dict[str, SkillSpec] = {}
        self.agent_skills: dict[str, list[str]] = {}
        self._loaded = False

    def load_all(self) -> int:
        if not self.skills_dir.exists():
            print(f"Skills directory not found: {self.skills_dir}")
            return 0

        count = 0
        for skill_file in self.skills_dir.rglob("SKILL.md"):
            try:
                skill = self._parse_skill_file(skill_file)
                if skill:
                    self.skills[skill.name] = skill
                    count += 1
            except Exception as e:
                print(f"Error loading skill from {skill_file}: {e}")

        count += self._load_python_skills()
        self._loaded = True
        return count

    def _parse_skill_file(self, skill_file: Path) -> SkillSpec | None:
        content = skill_file.read_text(encoding="utf-8")

        frontmatter = {}
        instructions = content

        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                try:
                    frontmatter = yaml.safe_load(parts[1]) or {}
                    instructions = parts[2].strip()
                except yaml.YAMLError:
                    pass

        name = frontmatter.get("name", skill_file.parent.name)
        description = frontmatter.get("description", "")

        if not description:
            first_para = instructions.split("\n\n")[0] if instructions else ""
            description = first_para[:200]

        return SkillSpec(
            name=name,
            description=description,
            version=frontmatter.get("version", "1.0.0"),
            author=frontmatter.get("author", "hermes-agent"),
            license=frontmatter.get("license", "MIT"),
            scope=SkillScope(frontmatter.get("scope", "global")),
            allowed_tools=frontmatter.get("allowed_tools", []),
            dependencies=frontmatter.get("dependencies", []),
            tags=frontmatter.get("tags", []),
            instructions=instructions,
            metadata=frontmatter.get("metadata", {}),
            file_path=str(skill_file),
        )

    def _load_python_skills(self) -> int:
        count = 0
        py_skills = {
            "dispatcher_skill": {
                "name": "dispatcher_skill",
                "description": "Dispatcher operations: route planning, driver assignment, delivery tracking",
                "tags": ["dispatch", "routing", "driver", "delivery"],
                "allowed_tools": ["route_optimizer", "vehicle_tracker", "driver_assigner"],
                "dependencies": ["bottle_tracking"],
            },
            "bottle_tracking": {
                "name": "bottle_tracking",
                "description": "Individual bottle lifecycle tracking for 165 SWAP loaners",
                "tags": ["inventory", "bottle", "swap", "tracking"],
                "allowed_tools": ["bottle_tracker", "swap_manager", "cycle_counter"],
                "dependencies": [],
            },
            "payment_processing": {
                "name": "payment_processing",
                "description": "Multi-gateway payment processing with R4 Banco integration",
                "tags": ["financial", "payment", "r4_banco", "mercadopago"],
                "allowed_tools": ["payment_processor", "r4_banco_client"],
                "dependencies": [],
            },
            "collections_workflow": {
                "name": "collections_workflow",
                "description": "Automated collections reminders and overdue management",
                "tags": ["financial", "collections", "reminders"],
                "allowed_tools": ["collections_manager"],
                "dependencies": ["payment_processing"],
            },
            "customer_communication": {
                "name": "customer_communication",
                "description": "WhatsApp customer interactions via Valentina",
                "tags": ["valentina", "whatsapp", "customer", "orders"],
                "allowed_tools": ["whatsapp_sender", "order_parser", "status_checker"],
                "dependencies": [],
            },
            "route_planning": {
                "name": "route_planning",
                "description": "VRP route optimization with OR-Tools",
                "tags": ["routing", "optimization", "vrp", "or-tools"],
                "allowed_tools": ["route_optimizer"],
                "dependencies": [],
            },
            "kpi_reporting": {
                "name": "kpi_reporting",
                "description": "KPI calculation and executive dashboard generation",
                "tags": ["analytics", "kpi", "dashboard", "reporting"],
                "allowed_tools": ["report_generator", "metrics_calculator", "dashboard_builder"],
                "dependencies": [],
            },
        }

        for skill_name, skill_data in py_skills.items():
            if skill_name not in self.skills:
                skill = SkillSpec(
                    name=skill_data["name"],
                    description=skill_data["description"],
                    tags=skill_data["tags"],
                    allowed_tools=skill_data["allowed_tools"],
                    dependencies=skill_data["dependencies"],
                    instructions=f"# {skill_name}\n\n{skill_data['description']}\n\nThis skill is implemented in Python.",
                    metadata={"implementation": "python", "module": f"skills.{skill_name}"},
                )
                self.skills[skill_name] = skill
                count += 1

        return count

    def discover(
        self, query: str = "", agent_type: str | None = None, limit: int = 20
    ) -> list[dict[str, str]]:
        results = []
        query_lower = query.lower()

        for skill in self.skills.values():
            if agent_type and skill.scope == SkillScope.AGENT_SPECIFIC:
                if agent_type not in skill.tags and agent_type not in skill.metadata.get(
                    "agent_types", []
                ):
                    continue

            if query_lower:
                if (
                    query_lower not in skill.name.lower()
                    and query_lower not in skill.description.lower()
                ):
                    continue

            results.append(skill.discovery_info)
            if len(results) >= limit:
                break

        return results

    def activate(self, skill_name: str) -> dict[str, Any] | None:
        skill = self.skills.get(skill_name)
        if not skill:
            return None

        dep_info = {}
        for dep_name in skill.dependencies:
            dep_skill = self.skills.get(dep_name)
            if dep_skill:
                dep_info[dep_name] = dep_skill.activation_info

        result = skill.activation_info
        result["dependencies"] = dep_info
        return result

    def get_execution_resources(self, skill_name: str) -> dict[str, Any]:
        skill = self.skills.get(skill_name)
        if not skill or not skill.file_path:
            return {}

        skill_dir = Path(skill.file_path).parent
        resources = {"scripts": {}, "references": {}, "assets": {}}

        scripts_dir = skill_dir / "scripts"
        if scripts_dir.exists():
            for script_file in scripts_dir.glob("*"):
                if script_file.is_file():
                    resources["scripts"][script_file.name] = script_file.read_text()

        refs_dir = skill_dir / "references"
        if refs_dir.exists():
            for ref_file in refs_dir.glob("*"):
                if ref_file.is_file():
                    resources["references"][ref_file.name] = ref_file.read_text()

        assets_dir = skill_dir / "assets"
        if assets_dir.exists():
            for asset_file in assets_dir.glob("*"):
                if asset_file.is_file():
                    try:
                        resources["assets"][asset_file.name] = asset_file.read_text()
                    except UnicodeDecodeError:
                        resources["assets"][asset_file.name] = (
                            f"<binary: {asset_file.stat().st_size} bytes>"
                        )

        return resources

    def analyze_dependencies(self) -> dict[str, list[str]]:
        graph = {}
        for name, skill in self.skills.items():
            graph[name] = skill.dependencies.copy()
        return graph

    def find_composable_skills(self, skill_name: str) -> list[str]:
        skill = self.skills.get(skill_name)
        if not skill:
            return []

        composable = []
        for name, other in self.skills.items():
            if name == skill_name:
                continue
            shared_tags = set(skill.tags) & set(other.tags)
            tool_overlap = set(skill.allowed_tools) & set(other.allowed_tools)
            if shared_tags and not tool_overlap:
                composable.append(name)

        return composable

    def get_skills_for_agent(self, agent_type: str) -> list[SkillSpec]:
        relevant = []
        for skill in self.skills.values():
            if (
                skill.scope == SkillScope.GLOBAL
                or agent_type in skill.tags
                or agent_type in skill.metadata.get("agent_types", [])
            ):
                relevant.append(skill)
        return relevant

    def register_skill(self, skill: SkillSpec):
        self.skills[skill.name] = skill

    def create_skill_file(self, skill: SkillSpec, target_dir: str | None = None) -> Path:
        if target_dir:
            skill_dir = Path(target_dir) / skill.name
        else:
            skill_dir = self.skills_dir / skill.name

        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file = skill_dir / "SKILL.md"

        frontmatter = {
            "name": skill.name,
            "description": skill.description,
            "version": skill.version,
            "author": skill.author,
            "license": skill.license,
            "scope": skill.scope.value,
            "allowed_tools": skill.allowed_tools,
            "dependencies": skill.dependencies,
            "tags": skill.tags,
            "metadata": skill.metadata,
        }

        content = "---\n"
        content += yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True)
        content += "---\n\n"
        content += skill.instructions

        skill_file.write_text(content, encoding="utf-8")
        skill.file_path = str(skill_file)
        self.skills[skill.name] = skill

        return skill_file


class ExternalSkillIntegrator:
    def __init__(self, registry: SkillRegistry):
        self.registry = registry

    def import_from_skillnet(self, skillnet_client, query: str, limit: int = 10) -> list[SkillSpec]:
        return []

    def import_from_adk_skills(self, adk_skills_path: str) -> list[SkillSpec]:
        imported = []
        skills_dir = Path(adk_skills_path)
        if skills_dir.exists():
            for skill_dir in skills_dir.iterdir():
                if skill_dir.is_dir():
                    skill_file = skill_dir / "SKILL.md"
                    if skill_file.exists():
                        skill = self.registry._parse_skill_file(skill_file)
                        if skill:
                            skill.metadata["source"] = "adk"
                            self.registry.skills[skill.name] = skill
                            imported.append(skill)
        return imported

    def import_from_anthropic_skills(self, skills_path: str) -> list[SkillSpec]:
        imported = []
        skills_dir = Path(skills_path)
        if skills_dir.exists():
            for skill_dir in skills_dir.iterdir():
                if skill_dir.is_dir():
                    skill_file = skill_dir / "SKILL.md"
                    if skill_file.exists():
                        skill = self.registry._parse_skill_file(skill_file)
                        if skill:
                            skill.metadata["source"] = "anthropic"
                            self.registry.skills[skill.name] = skill
                            imported.append(skill)
        return imported


def create_skill_registry(
    skills_dir: str = "/mnt/ssd_trabajo/hermes-agent/skills",
) -> SkillRegistry:
    registry = SkillRegistry(skills_dir)
    registry.load_all()
    return registry
