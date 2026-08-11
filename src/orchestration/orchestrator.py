"""
Core Orchestrator for Hermes-Agent Multi-Agent System

Based on patterns from:
- OpenSwarm: Specialist agents with orchestrator coordination
- Google ADK: Agent/Workflow graph-based execution
- Agent Skills spec: Progressive disclosure (discovery -> activation -> execution)
"""

import asyncio
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from src.memory.unified_memory import MemoryEntry, MemoryType, SearchResult, UnifiedMemory


class AgentType(Enum):
    """Types of specialist agents in the swarm"""

    ORCHESTRATOR = "orchestrator"
    DISPATCHER = "dispatcher"  # Route planning, driver assignment
    FINANCIAL = "financial"  # Payments, collections, reconciliation
    INVENTORY = "inventory"  # Bottle tracking, SWAP management
    VALENTINA = "valentina"  # WhatsApp customer interactions
    ANALYTICS = "analytics"  # Reports, metrics, insights
    RESEARCH = "research"  # Deep research, web search
    MEMORY = "memory"  # Memory management, retrieval
    CUSTOM = "custom"


@dataclass
class AgentConfig:
    """Configuration for a specialist agent"""

    name: str
    agent_type: AgentType
    description: str
    instructions: str  # Full instructions (loaded on activation)
    tools: list[str] = field(default_factory=list)  # Tool names this agent can use
    skills: list[str] = field(default_factory=list)  # Skill names this agent can load
    handoff_agents: list[AgentType] = field(default_factory=list)  # Can handoff to these
    memory_types: list[MemoryType] = field(
        default_factory=lambda: [MemoryType.SEMANTIC, MemoryType.EPISODIC]
    )
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentMessage:
    """Message between agents"""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    from_agent: str = ""
    to_agent: str = ""
    content: str = ""
    message_type: str = "request"  # request, response, handoff, notification
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    correlation_id: str | None = None  # For tracking multi-step workflows


@dataclass
class TaskResult:
    """Result of an agent task execution"""

    success: bool
    agent_name: str
    output: Any = None
    error: str | None = None
    memories_created: list[MemoryEntry] = field(default_factory=list)
    handoff_to: AgentType | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseAgent(ABC):
    """Base class for all specialist agents"""

    def __init__(self, config: AgentConfig, orchestrator: "Orchestrator", memory: UnifiedMemory):
        self.config = config
        self.orchestrator = orchestrator
        self.memory = memory
        self.active = False
        self._context_loaded = False

    @abstractmethod
    async def execute(self, task: str, context: dict[str, Any]) -> TaskResult:
        """Execute a task. Must be implemented by subclasses."""
        pass

    async def load_context(self):
        """Load full instructions and relevant memories (activation phase)"""
        if self._context_loaded:
            return

        # Search for relevant procedural memories
        if MemoryType.PROCEDURAL in self.config.memory_types:
            await self._search_procedural_memories()
            # Could inject into context

        self._context_loaded = True
        self.active = True

    async def _search_procedural_memories(self) -> list[SearchResult]:
        """Search for procedural memories relevant to this agent"""
        query = f"{self.config.agent_type.value} procedure workflow"
        return self.memory.search(query, memory_types=[MemoryType.PROCEDURAL], limit=5)

    async def store_memory(self, content: str, memory_type: MemoryType, **metadata) -> dict:
        """Store a memory via the unified memory system"""
        return self.memory.add(
            content=content,
            memory_type=memory_type,
            metadata=metadata,
            tags=[self.config.agent_type.value, self.config.name],
        )

    async def handoff(self, to_agent: AgentType, task: str, context: dict[str, Any]) -> TaskResult:
        """Handoff task to another agent"""
        return await self.orchestrator.delegate(
            to_agent, task, context, from_agent=self.config.name
        )


class Orchestrator:
    """
    Central orchestrator coordinating specialist agents.

    Patterns from:
    - OpenSwarm: Orchestrator routes to specialists, never answers directly
    - ADK: Graph-based workflow execution with state management
    - Agent Skills: Progressive disclosure of capabilities
    """

    def __init__(self, memory: UnifiedMemory):
        self.memory = memory
        self.agents: dict[str, BaseAgent] = {}
        self.agent_configs: dict[AgentType, AgentConfig] = {}
        self.message_bus: asyncio.Queue = asyncio.Queue()
        self.active_workflows: dict[str, dict] = {}
        self._running = False

        # Register default agents
        self._register_default_agents()

    def _register_default_agents(self):
        """Register the default specialist agents for H2O operations"""

        # Dispatcher Agent
        self.register_agent(
            AgentConfig(
                name="dispatcher",
                agent_type=AgentType.DISPATCHER,
                description=(
                    "Route planning, driver assignment, vehicle tracking, "
                    "delivery optimization"
                ),
                instructions=self._get_dispatcher_instructions(),
                tools=[
                    "route_optimizer",
                    "vehicle_tracker",
                    "driver_assigner",
                    "delivery_scheduler",
                ],
                skills=["route_planning", "vehicle_assignment", "bottle_tracking"],
                handoff_agents=[AgentType.FINANCIAL, AgentType.INVENTORY, AgentType.VALENTINA],
                memory_types=[MemoryType.SEMANTIC, MemoryType.EPISODIC, MemoryType.PROCEDURAL],
            )
        )

        # Financial Agent
        self.register_agent(
            AgentConfig(
                name="financial",
                agent_type=AgentType.FINANCIAL,
                description=(
                    "Payments processing, collections, reconciliation, "
                    "banking integration (R4 Banco)"
                ),
                instructions=self._get_financial_instructions(),
                tools=[
                    "payment_processor",
                    "collections_manager",
                    "reconciliation_engine",
                    "r4_banco_client",
                ],
                skills=["payment_processing", "collections_workflow", "bank_reconciliation"],
                handoff_agents=[AgentType.DISPATCHER, AgentType.VALENTINA],
                memory_types=[MemoryType.SEMANTIC, MemoryType.EPISODIC, MemoryType.PROCEDURAL],
            )
        )

        # Inventory Agent
        self.register_agent(
            AgentConfig(
                name="inventory",
                agent_type=AgentType.INVENTORY,
                description=(
                    "Bottle tracking, SWAP management (165 loaners), "
                    "stock levels, cycle counts"
                ),
                instructions=self._get_inventory_instructions(),
                tools=["bottle_tracker", "swap_manager", "stock_monitor", "cycle_counter"],
                skills=["bottle_lifecycle", "swap_migration", "inventory_audit"],
                handoff_agents=[AgentType.DISPATCHER, AgentType.FINANCIAL],
                memory_types=[MemoryType.SEMANTIC, MemoryType.EPISODIC, MemoryType.PROCEDURAL],
            )
        )

        # Valentina Agent (WhatsApp)
        self.register_agent(
            AgentConfig(
                name="valentina",
                agent_type=AgentType.VALENTINA,
                description="Customer WhatsApp interactions, orders, complaints, status updates",
                instructions=self._get_valentina_instructions(),
                tools=["whatsapp_sender", "order_parser", "status_checker", "complaint_handler"],
                skills=["customer_communication", "order_taking", "complaint_resolution"],
                handoff_agents=[AgentType.DISPATCHER, AgentType.FINANCIAL, AgentType.INVENTORY],
                memory_types=[
                    MemoryType.SEMANTIC,
                    MemoryType.EPISODIC,
                    MemoryType.AUTOBIOGRAPHICAL,
                ],
            )
        )

        # Analytics Agent
        self.register_agent(
            AgentConfig(
                name="analytics",
                agent_type=AgentType.ANALYTICS,
                description="Reports, metrics, KPI dashboards, business insights",
                instructions=self._get_analytics_instructions(),
                tools=[
                    "report_generator",
                    "metrics_calculator",
                    "dashboard_builder",
                    "trend_analyzer",
                ],
                skills=["kpi_reporting", "trend_analysis", "executive_dashboard"],
                handoff_agents=[AgentType.DISPATCHER, AgentType.FINANCIAL, AgentType.INVENTORY],
                memory_types=[MemoryType.SEMANTIC, MemoryType.EPISODIC, MemoryType.PROCEDURAL],
            )
        )

    def register_agent(self, config: AgentConfig):
        """Register an agent configuration"""
        self.agent_configs[config.agent_type] = config

    def create_agent(self, agent_type: AgentType) -> BaseAgent | None:
        """Factory method to create agent instances"""
        config = self.agent_configs.get(agent_type)
        if not config or not config.enabled:
            return None

        # Import agent implementations from memory_aware_agent
        from .memory_aware_agent import (
            AnalyticsAgent,
            DispatcherAgent,
            FinancialAgent,
            InventoryAgent,
            ValentinaAgent,
        )

        if agent_type == AgentType.DISPATCHER:
            return DispatcherAgent(config, self, self.memory)
        elif agent_type == AgentType.FINANCIAL:
            return FinancialAgent(config, self, self.memory)
        elif agent_type == AgentType.INVENTORY:
            return InventoryAgent(config, self, self.memory)
        elif agent_type == AgentType.VALENTINA:
            return ValentinaAgent(config, self, self.memory)
        elif agent_type == AgentType.ANALYTICS:
            return AnalyticsAgent(config, self, self.memory)

        return None

    def get_agent(self, agent_type: AgentType) -> BaseAgent:
        """Get or create an agent instance"""
        key = agent_type.value
        if key not in self.agents:
            agent = self.create_agent(agent_type)
            if agent:
                self.agents[key] = agent
        return self.agents.get(key)

    async def delegate(
        self,
        to_agent: AgentType,
        task: str,
        context: dict[str, Any],
        from_agent: str = "orchestrator",
    ) -> TaskResult:
        """Delegate a task to a specialist agent"""
        agent = self.get_agent(to_agent)
        if not agent:
            return TaskResult(
                success=False,
                agent_name=to_agent.value,
                error=f"Agent {to_agent.value} not available",
            )

        # Load context if first time
        await agent.load_context()

        # Execute task
        result = await agent.execute(task, context)

        # Store workflow memory
        await self.memory.add(
            content=f"Delegated to {to_agent.value}: {task} -> {'success' if result.success else 'failed: ' + (result.error or 'unknown')}",
            memory_type=MemoryType.EPISODIC,
            metadata={
                "workflow": "delegation",
                "from_agent": from_agent,
                "to_agent": to_agent.value,
                "task": task,
                "success": result.success,
            },
            tags=["workflow", "delegation", from_agent, to_agent.value],
        )

        return result

    async def execute_workflow(
        self, workflow_name: str, steps: list[dict], initial_context: dict[str, Any]
    ) -> list[TaskResult]:
        """Execute a multi-step workflow across agents"""
        workflow_id = str(uuid.uuid4())
        self.active_workflows[workflow_id] = {
            "name": workflow_name,
            "steps": steps,
            "context": initial_context.copy(),
            "results": [],
            "started_at": datetime.now(),
        }

        results = []
        context = initial_context.copy()
        context["workflow_id"] = workflow_id

        for step in steps:
            agent_type = AgentType(step["agent"])
            task = step["task"]
            # Support template substitution from context
            task = self._render_template(task, context)

            result = await self.delegate(agent_type, task, context)
            results.append(result)

            # Update context with result
            context[f"{agent_type.value}_result"] = result.output
            context["last_result"] = result.output
            context["last_success"] = result.success

            # Store step memory
            await self.memory.add(
                content=f"Workflow {workflow_name} step: {agent_type.value} executed {task}",
                memory_type=MemoryType.EPISODIC,
                metadata={
                    "workflow_id": workflow_id,
                    "workflow_name": workflow_name,
                    "step_agent": agent_type.value,
                    "step_task": task,
                    "success": result.success,
                },
                tags=["workflow", workflow_name, agent_type.value],
            )

            # Check for handoff
            if result.handoff_to:
                handoff_result = await self.delegate(
                    result.handoff_to, step.get("handoff_task", "Continue workflow"), context
                )
                results.append(handoff_result)

        self.active_workflows[workflow_id]["results"] = results
        self.active_workflows[workflow_id]["completed_at"] = datetime.now()

        return results

    def _render_template(self, template: str, context: dict[str, Any]) -> str:
        """Simple template rendering with context variables"""
        for key, value in context.items():
            template = template.replace(f"{{{key}}}", str(value))
        return template

    # ============================================================
    # AGENT INSTRUCTIONS (Progressive Disclosure - loaded on activation)
    # ============================================================

    def _get_dispatcher_instructions(self) -> str:
        return """# Dispatcher Agent Instructions

## Role
You are the Dispatch Specialist for Estación H2O Maracaibo. You manage route planning, driver assignment, vehicle tracking, and delivery optimization.

## Core Responsibilities
1. **Route Optimization**: Use OR-Tools VRP solver for multi-vehicle routing
2. **Driver Assignment**: Match drivers to routes based on capacity, zone, availability
3. **Vehicle Tracking**: Monitor GPS positions of 2 triciclos (Honor X7b phones)
4. **Delivery Scheduling**: Coordinate 165 SWAP loaner bottles (H2O-001 to H2O-165)

## Key Procedures
- Morning: Run route planner for daily deliveries (cron: 6:00 AM)
- Real-time: Process driver check-ins via Telegram @DespachoH2O_bot
- Exception handling: Re-route on vehicle breakdown, traffic, urgent orders
- End-of-day: Reconcile deliveries vs planned, update bottle tracker

## Handoff Triggers
- Payment issues -> Financial Agent
- Bottle inventory discrepancies -> Inventory Agent
- Customer communication needs -> Valentina Agent

## Tools Available
- route_optimizer: VRP solver with time windows
- vehicle_tracker: GPS polling from dispatcher_bot
- driver_assigner: Capacity/zone matching algorithm
- delivery_scheduler: Time-window scheduling

## Memory Usage
- Search procedural memories for "route planning", "driver assignment"
- Store episodic memories of each delivery run
- Reference semantic memories for client addresses, bottle specs"""

    def _get_financial_instructions(self) -> str:
        return """# Financial Agent Instructions

## Role
You are the Financial Specialist for Estación H2O. Handle payments, collections, reconciliation, and R4 Banco integration.

## Core Responsibilities
1. **Payment Processing**: MercadoPago, bank transfers, cash reconciliation
2. **Collections**: Automated reminders (cron: 18:30), overdue tracking
3. **R4 Banco Integration**: R4 Conecta V3.0 HMAC-SHA256 webhooks
4. **Reconciliation**: Daily bank statement matching

## Key Procedures
- Process incoming webhooks from Meta (WhatsApp payments) and R4 Banco
- Generate collection reminders for overdue accounts
- Reconcile daily: bank statements vs internal records
- Handle refunds, disputes, chargebacks

## R4 Banco V3.0 Specs
- Endpoint: /webhook/r4banco
- Auth: HMAC-SHA256 with shared secret
- Events: payment.received, payment.failed, transfer.completed

## Handoff Triggers
- Delivery payment confirmation needed -> Dispatcher Agent
- Customer billing questions -> Valentina Agent
- Bottle deposit/refund tracking -> Inventory Agent

## Tools Available
- payment_processor: Multi-gateway payment handling
- collections_manager: Automated reminder workflows
- reconciliation_engine: Bank statement matching
- r4_banco_client: HMAC-verified webhook processing"""

    def _get_inventory_instructions(self) -> str:
        return """# Inventory Agent Instructions

## Role
You are the Inventory Specialist for Estación H2O. Manage 165 SWAP loaner bottles, stock levels, and bottle lifecycle.

## Core Responsibilities
1. **Bottle Tracking**: Individual tracking H2O-001 to H2O-165
2. **SWAP Management**: 3-week migration program for loaner bottles
3. **Cycle Counts**: Daily/weekly physical counts reconciliation
4. **Stock Monitoring**: Alert on low stock, damaged bottles

## SWAP Program Details
- 165 loaner bottles in circulation
- 3-week migration: old bottles -> new H2O branded
- Track each bottle: client, location, condition, swap_status
- States: IN_CIRCULATION, AT_CLIENT, IN_TRANSIT, DAMAGED, RETIRED

## Key Procedures
- Morning: Reconcile bottle tracker with dispatcher deliveries
- On delivery: Scan bottle out, scan empty in
- On return: Inspect condition, update status
- Weekly: Generate cycle count report

## Handoff Triggers
- Delivery bottleneck -> Dispatcher Agent
- Bottle deposit payments -> Financial Agent
- Customer bottle complaints -> Valentina Agent

## Tools Available
- bottle_tracker: CRUD for individual bottles
- swap_manager: Migration workflow engine
- stock_monitor: Threshold alerts
- cycle_counter: Physical count procedures"""

    def _get_valentina_instructions(self) -> str:
        return """# Valentina Agent Instructions

## Role
You are the Customer Experience Specialist (Valentina) for Estación H2O. Handle all WhatsApp interactions.

## Core Responsibilities
1. **Order Taking**: Parse natural language orders from WhatsApp
2. **Status Updates**: Proactive delivery notifications
3. **Complaint Resolution**: Handle issues, escalate when needed
4. **Customer Relationship**: Maintain context across conversations

## Key Procedures
- Receive webhook from Meta Cloud API at /webhook/meta
- Parse intent: order, inquiry, complaint, payment, cancel
- Maintain conversation context in conversations.db (SQLite WAL)
- Send responses via Meta API with 24hr window compliance

## Order Parsing
- Extract: client_phone, bottle_count, delivery_address, preferred_time
- Validate against inventory (check with Inventory Agent)
- Create order in dispatch.db, notify Dispatcher Agent

## Handoff Triggers
- New order -> Dispatcher Agent (for scheduling)
- Payment issue -> Financial Agent
- Bottle discrepancy -> Inventory Agent
- Complex complaint -> Human escalation (alert Líder)

## Tools Available
- whatsapp_sender: Send text, template, media messages
- order_parser: NLP for order extraction
- status_checker: Query dispatch.db for delivery status
- complaint_handler: Structured complaint workflow"""

    def _get_analytics_instructions(self) -> str:
        return """# Analytics Agent Instructions

## Role
You are the Analytics Specialist for Estación H2O. Generate reports, KPIs, and business insights.

## Core Responsibilities
1. **Daily Reports**: 7:00 AM operational summary, 18:30 financial summary
2. **KPI Dashboard**: Delivery efficiency, collection rate, bottle turnover
3. **Trend Analysis**: Weekly/monthly patterns, seasonal adjustments
4. **Executive Insights**: Actionable recommendations for Líder

## Key Metrics
- Delivery: on-time rate, avg delivery time, route efficiency
- Financial: collection rate, DSO, payment method mix
- Inventory: bottle utilization, swap progress, loss rate
- Customer: satisfaction, repeat rate, complaint resolution time

## Scheduled Reports (Cron)
- 07:00: run_analytics_7am - Operational snapshot
- 18:30: run_fs_reporte - Financial summary
- 18:30: run_fs_recordatorios - Collection reminders
- Weekly: Trend analysis, bottleneck identification

## Handoff Triggers
- Operational anomaly -> Dispatcher Agent
- Financial discrepancy -> Financial Agent
- Inventory anomaly -> Inventory Agent

## Tools Available
- report_generator: Jinja2 templates + data queries
- metrics_calculator: SQL aggregations on conversations.db, dispatch.db
- dashboard_builder: Grafana/Prometheus integration
- trend_analyzer: Statistical analysis (pandas/scipy)"""
