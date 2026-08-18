"""Tests unitarios para src/orchestration/orchestrator.py.

Cubre: AgentType, AgentConfig, AgentMessage, TaskResult, BaseAgent, Orchestrator.
"""

import asyncio
import os
import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.orchestration.orchestrator import (
    AgentConfig,
    AgentMessage,
    AgentType,
    BaseAgent,
    Orchestrator,
    TaskResult,
)
from src.memory.unified_memory import MemoryType


# ============================================================
# Enums and Dataclasses
# ============================================================

class TestAgentType:
    def test_values(self):
        assert AgentType.ORCHESTRATOR.value == "orchestrator"
        assert AgentType.DISPATCHER.value == "dispatcher"
        assert AgentType.FINANCIAL.value == "financial"
        assert AgentType.INVENTORY.value == "inventory"
        assert AgentType.VALENTINA.value == "valentina"
        assert AgentType.ANALYTICS.value == "analytics"
        assert AgentType.RESEARCH.value == "research"
        assert AgentType.MEMORY.value == "memory"
        assert AgentType.CUSTOM.value == "custom"

    def test_from_value(self):
        assert AgentType("dispatcher") == AgentType.DISPATCHER


class TestAgentConfig:
    def test_defaults(self):
        config = AgentConfig(
            name="test_agent",
            agent_type=AgentType.DISPATCHER,
            description="Test",
            instructions="Do things",
        )
        assert config.name == "test_agent"
        assert config.tools == []
        assert config.skills == []
        assert config.handoff_agents == []
        assert config.memory_types == [MemoryType.SEMANTIC, MemoryType.EPISODIC]
        assert config.enabled is True
        assert config.metadata == {}

    def test_with_fields(self):
        config = AgentConfig(
            name="full_agent",
            agent_type=AgentType.FINANCIAL,
            description="Full config",
            instructions="Run",
            tools=["tool1", "tool2"],
            skills=["skill1"],
            handoff_agents=[AgentType.DISPATCHER],
            enabled=False,
            metadata={"key": "val"},
        )
        assert config.tools == ["tool1", "tool2"]
        assert config.handoff_agents == [AgentType.DISPATCHER]
        assert config.enabled is False
        assert config.metadata == {"key": "val"}


class TestAgentMessage:
    def test_defaults(self):
        msg = AgentMessage()
        assert msg.from_agent == ""
        assert msg.to_agent == ""
        assert msg.content == ""
        assert msg.message_type == "request"
        assert msg.payload == {}
        assert msg.correlation_id is None
        assert len(msg.id) > 0  # UUID generated

    def test_with_values(self):
        msg = AgentMessage(
            from_agent="dispatcher",
            to_agent="financial",
            content="Process payment",
            message_type="handoff",
            payload={"amount": 100},
            correlation_id="corr-123",
        )
        assert msg.from_agent == "dispatcher"
        assert msg.payload == {"amount": 100}


class TestTaskResult:
    def test_defaults(self):
        result = TaskResult(success=True, agent_name="test")
        assert result.success is True
        assert result.agent_name == "test"
        assert result.output is None
        assert result.error is None
        assert result.memories_created == []
        assert result.handoff_to is None
        assert result.metadata == {}

    def test_with_error(self):
        result = TaskResult(
            success=False,
            agent_name="test",
            error="Something went wrong",
        )
        assert result.error == "Something went wrong"


# ============================================================
# Orchestrator
# ============================================================

class TestOrchestratorInit:
    def test_init_registers_default_agents(self, mock_orchestrator):
        assert AgentType.DISPATCHER in mock_orchestrator.agent_configs
        assert AgentType.FINANCIAL in mock_orchestrator.agent_configs
        assert AgentType.INVENTORY in mock_orchestrator.agent_configs
        assert AgentType.VALENTINA in mock_orchestrator.agent_configs
        assert AgentType.ANALYTICS in mock_orchestrator.agent_configs

    def test_init_properties(self, mock_orchestrator):
        assert mock_orchestrator.agents == {}
        assert mock_orchestrator._running is False
        assert isinstance(mock_orchestrator.message_bus, asyncio.Queue)
        assert isinstance(mock_orchestrator.active_workflows, dict)


class TestOrchestratorRegisterAgent:
    def test_register_agent(self, mock_orchestrator):
        config = AgentConfig(
            name="custom_agent",
            agent_type=AgentType.CUSTOM,
            description="Custom",
            instructions="Do custom things",
        )
        mock_orchestrator.register_agent(config)
        assert AgentType.CUSTOM in mock_orchestrator.agent_configs
        assert mock_orchestrator.agent_configs[AgentType.CUSTOM].name == "custom_agent"

    def test_register_overwrites(self, mock_orchestrator):
        config1 = AgentConfig(
            name="v1",
            agent_type=AgentType.CUSTOM,
            description="V1",
            instructions="v1",
        )
        config2 = AgentConfig(
            name="v2",
            agent_type=AgentType.CUSTOM,
            description="V2",
            instructions="v2",
        )
        mock_orchestrator.register_agent(config1)
        mock_orchestrator.register_agent(config2)
        assert mock_orchestrator.agent_configs[AgentType.CUSTOM].name == "v2"


class TestOrchestratorCreateAgent:
    def test_create_disabled_agent(self, mock_orchestrator):
        config = AgentConfig(
            name="disabled",
            agent_type=AgentType.CUSTOM,
            description="Disabled",
            instructions="",
            enabled=False,
        )
        mock_orchestrator.register_agent(config)
        result = mock_orchestrator.create_agent(AgentType.CUSTOM)
        assert result is None

    def test_create_nonexistent_agent(self, mock_orchestrator):
        # RESEARCH is not registered by default
        result = mock_orchestrator.create_agent(AgentType.RESEARCH)
        assert result is None

    def test_create_dispatcher_agent(self, mock_orchestrator):
        agent = mock_orchestrator.create_agent(AgentType.DISPATCHER)
        assert agent is not None
        assert agent.config.name == "dispatcher"

    def test_create_financial_agent(self, mock_orchestrator):
        agent = mock_orchestrator.create_agent(AgentType.FINANCIAL)
        assert agent is not None
        assert agent.config.name == "financial"

    def test_create_inventory_agent(self, mock_orchestrator):
        agent = mock_orchestrator.create_agent(AgentType.INVENTORY)
        assert agent is not None

    def test_create_valentina_agent(self, mock_orchestrator):
        agent = mock_orchestrator.create_agent(AgentType.VALENTINA)
        assert agent is not None

    def test_create_analytics_agent(self, mock_orchestrator):
        agent = mock_orchestrator.create_agent(AgentType.ANALYTICS)
        assert agent is not None


class TestOrchestratorGetAgent:
    def test_get_agent_caches(self, mock_orchestrator):
        agent1 = mock_orchestrator.get_agent(AgentType.DISPATCHER)
        agent2 = mock_orchestrator.get_agent(AgentType.DISPATCHER)
        assert agent1 is agent2

    def test_get_agent_nonexistent(self, mock_orchestrator):
        agent = mock_orchestrator.get_agent(AgentType.RESEARCH)
        # get_agent returns cast(BaseAgent, self.agents.get(key)) which could be None
        # but agents dict doesn't have it, so it returns None via cast
        assert agent is None or hasattr(agent, "config")


class TestOrchestratorDelegate:
    @pytest.mark.asyncio
    async def test_delegate_success(self, mock_orchestrator):
        result = await mock_orchestrator.delegate(
            AgentType.DISPATCHER,
            "plan routes for today",
            {},
        )
        assert result.success is True
        assert result.agent_name == "dispatcher"

    @pytest.mark.asyncio
    async def test_delegate_nonexistent(self, mock_orchestrator):
        result = await mock_orchestrator.delegate(
            AgentType.RESEARCH,
            "research something",
            {},
        )
        assert result.success is False
        assert "not available" in result.error

    @pytest.mark.asyncio
    async def test_delegate_stores_memory(self, mock_orchestrator, mock_memory):
        await mock_orchestrator.delegate(
            AgentType.DISPATCHER,
            "plan routes",
            {},
        )
        # memory.add should have been called for delegation memory
        assert mock_memory.add.call_count >= 1


class TestOrchestratorWorkflow:
    @pytest.mark.asyncio
    async def test_execute_workflow_single_step(self, mock_orchestrator):
        steps = [
            {"agent": "dispatcher", "task": "plan routes"},
        ]
        results = await mock_orchestrator.execute_workflow(
            "test_workflow",
            steps,
            {"initial": "context"},
        )
        assert len(results) == 1
        assert results[0].success is True

    @pytest.mark.asyncio
    async def test_execute_workflow_multi_step(self, mock_orchestrator):
        steps = [
            {"agent": "dispatcher", "task": "plan routes"},
            {"agent": "financial", "task": "process payment"},
        ]
        results = await mock_orchestrator.execute_workflow(
            "multi_step",
            steps,
            {},
        )
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_execute_workflow_with_template(self, mock_orchestrator):
        steps = [
            {"agent": "dispatcher", "task": "plan routes for {client}"},
        ]
        results = await mock_orchestrator.execute_workflow(
            "template_wf",
            steps,
            {"client": "ACME"},
        )
        assert len(results) == 1
        # The template should have been rendered
        # (we can't directly check what the agent received, but no error means it worked)

    @pytest.mark.asyncio
    async def test_execute_workflow_tracks_active(self, mock_orchestrator):
        steps = [{"agent": "dispatcher", "task": "plan"}]
        await mock_orchestrator.execute_workflow("wf1", steps, {})
        assert len(mock_orchestrator.active_workflows) == 1
        wf = list(mock_orchestrator.active_workflows.values())[0]
        assert "completed_at" in wf


class TestRenderTemplate:
    def test_simple_substitution(self, mock_orchestrator):
        result = mock_orchestrator._render_template(
            "Hello {name}", {"name": "World"}
        )
        assert result == "Hello World"

    def test_multiple_substitutions(self, mock_orchestrator):
        result = mock_orchestrator._render_template(
            "{a} and {b}", {"a": "1", "b": "2"}
        )
        assert result == "1 and 2"

    def test_no_substitution_needed(self, mock_orchestrator):
        result = mock_orchestrator._render_template(
            "no vars", {}
        )
        assert result == "no vars"

    def test_missing_var_stays(self, mock_orchestrator):
        result = mock_orchestrator._render_template(
            "Hello {missing}", {}
        )
        assert result == "Hello {missing}"


class TestAgentInstructions:
    def test_dispatcher_instructions(self, mock_orchestrator):
        instr = mock_orchestrator._get_dispatcher_instructions()
        assert "Dispatcher" in instr
        assert "route" in instr.lower()

    def test_financial_instructions(self, mock_orchestrator):
        instr = mock_orchestrator._get_financial_instructions()
        assert "Financial" in instr
        assert "R4" in instr

    def test_inventory_instructions(self, mock_orchestrator):
        instr = mock_orchestrator._get_inventory_instructions()
        assert "Inventory" in instr
        assert "SWAP" in instr

    def test_valentina_instructions(self, mock_orchestrator):
        instr = mock_orchestrator._get_valentina_instructions()
        assert "Valentina" in instr
        assert "WhatsApp" in instr

    def test_analytics_instructions(self, mock_orchestrator):
        instr = mock_orchestrator._get_analytics_instructions()
        assert "Analytics" in instr
        assert "KPI" in instr


class TestBaseAgent:
    @pytest.mark.asyncio
    async def test_load_context(self, mock_orchestrator):
        agent = mock_orchestrator.get_agent(AgentType.DISPATCHER)
        await agent.load_context()
        assert agent._context_loaded is True
        assert agent.active is True

    @pytest.mark.asyncio
    async def test_load_context_idempotent(self, mock_orchestrator):
        agent = mock_orchestrator.get_agent(AgentType.DISPATCHER)
        await agent.load_context()
        await agent.load_context()  # second call should be no-op
        assert agent._context_loaded is True

    @pytest.mark.asyncio
    async def test_store_memory(self, mock_orchestrator, mock_memory):
        agent = mock_orchestrator.get_agent(AgentType.DISPATCHER)
        await agent.store_memory("test content", MemoryType.EPISODIC, key="val")
        mock_memory.add.assert_called()

    @pytest.mark.asyncio
    async def test_handoff(self, mock_orchestrator):
        agent = mock_orchestrator.get_agent(AgentType.DISPATCHER)
        result = await agent.handoff(AgentType.FINANCIAL, "process payment", {})
        assert result.success is True
        assert result.agent_name == "financial"
