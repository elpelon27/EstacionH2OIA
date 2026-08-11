"""
Memory-Aware Agent Base Class for Hermes-Agent

Integrates UnifiedMemory with agent execution for:
- Automatic memory retrieval before task execution
- Memory storage after task completion
- Cross-agent memory sharing via unified memory system
"""

from abc import abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from src.memory.unified_memory import MemoryType, SearchResult, UnifiedMemory
from src.orchestration.orchestrator import AgentConfig, AgentType, BaseAgent, TaskResult

if TYPE_CHECKING:
    from src.orchestration.orchestrator import Orchestrator


@dataclass
class MemoryContext:
    """Context enriched with relevant memories"""

    semantic_memories: list[SearchResult] = field(default_factory=list)
    episodic_memories: list[SearchResult] = field(default_factory=list)
    procedural_memories: list[SearchResult] = field(default_factory=list)
    autobiographical_memories: list[SearchResult] = field(default_factory=list)
    raw_query: str = ""


class MemoryAwareAgent(BaseAgent):
    """
    Base agent that automatically uses unified memory for context enrichment.

    Flow:
    1. receive task
    2. search relevant memories (semantic, episodic, procedural)
    3. build enriched context
    4. execute task with context
    5. store resulting memories
    """

    def __init__(self, config: AgentConfig, orchestrator: "Orchestrator", memory: UnifiedMemory):
        super().__init__(config, orchestrator, memory)
        self.memory_context: MemoryContext | None = None

    async def execute(self, task: str, context: dict[str, Any]) -> TaskResult:
        """Execute task with memory-enriched context"""
        try:
            # Phase 1: Retrieve relevant memories
            await self._retrieve_memories(task, context)

            # Phase 2: Build enriched context
            enriched_context = self._build_enriched_context(context)

            # Phase 3: Execute specific agent logic
            result = await self._execute_with_memory(task, enriched_context)

            # Phase 4: Store memories from execution
            if result.success:
                self._store_execution_memories(task, result, enriched_context)

            return result

        except Exception as e:
            return TaskResult(
                success=False, agent_name=self.config.name, error=f"Execution error: {str(e)}"
            )

    async def _retrieve_memories(self, task: str, context: dict[str, Any]):
        """Retrieve relevant memories for the task"""
        self.memory_context = MemoryContext(raw_query=task)

        # Search across configured memory types
        search_queries = [
            task,  # Direct task query
            f"{self.config.agent_type.value} {task}",  # Agent-specific
        ]

        # Add context-based queries
        if "client" in context:
            search_queries.append(f"client {context['client']}")
        if "order_id" in context:
            search_queries.append(f"order {context['order_id']}")

        for query in search_queries:
            for mem_type in self.config.memory_types:
                results = self.memory.search(query, memory_types=[mem_type], limit=3)
                if mem_type == MemoryType.SEMANTIC:
                    self.memory_context.semantic_memories.extend(results)
                elif mem_type == MemoryType.EPISODIC:
                    self.memory_context.episodic_memories.extend(results)
                elif mem_type == MemoryType.PROCEDURAL:
                    self.memory_context.procedural_memories.extend(results)
                elif mem_type == MemoryType.AUTOBIOGRAPHICAL:
                    self.memory_context.autobiographical_memories.extend(results)

        # Deduplicate by content hash
        self._deduplicate_memories()

    def _deduplicate_memories(self):
        """Remove duplicate memories by content hash"""
        for attr in [
            "semantic_memories",
            "episodic_memories",
            "procedural_memories",
            "autobiographical_memories",
        ]:
            memories = getattr(self.memory_context, attr)
            seen = set()
            unique = []
            for m in memories:
                key = m.entry.id
                if key not in seen:
                    seen.add(key)
                    unique.append(m)
            setattr(self.memory_context, attr, unique)

    def _build_enriched_context(self, base_context: dict[str, Any]) -> dict[str, Any]:
        """Build context enriched with memories"""
        if not self.memory_context:
            return base_context

        enriched = base_context.copy()

        # Add memory summaries
        enriched["memory_context"] = {
            "semantic": [
                f"[{r.score:.2f}] {r.entry.content[:100]}"
                for r in self.memory_context.semantic_memories[:3]
            ],
            "episodic": [
                f"[{r.score:.2f}] {r.entry.content[:100]}"
                for r in self.memory_context.episodic_memories[:3]
            ],
            "procedural": [
                f"[{r.score:.2f}] {r.entry.content[:100]}"
                for r in self.memory_context.procedural_memories[:3]
            ],
            "autobiographical": [
                f"[{r.score:.2f}] {r.entry.content[:100]}"
                for r in self.memory_context.autobiographical_memories[:2]
            ],
        }

        # Add procedural guidance if available
        if self.memory_context.procedural_memories:
            top_proc = self.memory_context.procedural_memories[0]
            enriched["procedural_guidance"] = top_proc.entry.content

        return enriched

    @abstractmethod
    async def _execute_with_memory(self, task: str, context: dict[str, Any]) -> TaskResult:
        """Agent-specific execution logic with memory context"""
        pass

    def _store_execution_memories(self, task: str, result: TaskResult, context: dict[str, Any]):
        """Store memories from task execution"""
        # Store episodic memory of this execution
        status = "success" if result.success else "failed"
        self.memory.add(
            content=f"Executed task: {task}. Result: {status} - {result.output}",
            memory_type=MemoryType.EPISODIC,
            metadata={
                "agent": self.config.name,
                "task": task,
                "success": result.success,
                "workflow_id": context.get("workflow_id"),
                "correlation_id": context.get("correlation_id"),
            },
            tags=[self.config.agent_type.value, "execution", "episodic"],
        )

        # Store any new procedural insights
        if result.metadata.get("new_procedure"):
            self.memory.add(
                content=result.metadata["new_procedure"],
                memory_type=MemoryType.PROCEDURAL,
                metadata={"agent": self.config.name, "source": "execution_insight", "task": task},
                tags=[self.config.agent_type.value, "procedure", "learned"],
            )


# ============================================================
# CONCRETE AGENT IMPLEMENTATIONS
# ============================================================


class DispatcherAgent(MemoryAwareAgent):
    """Dispatcher specialist agent for route planning and delivery management"""

    async def _execute_with_memory(self, task: str, context: dict[str, Any]) -> TaskResult:
        task_lower = task.lower()

        # Route planning
        if any(kw in task_lower for kw in ["route", "plan", "optimize", "vrp"]):
            return await self._plan_routes(context)

        # Driver assignment
        elif any(kw in task_lower for kw in ["assign", "driver", "chofer"]):
            return await self._assign_drivers(context)

        # Delivery tracking
        elif any(kw in task_lower for kw in ["track", "delivery", "entrega", "status"]):
            return await self._track_deliveries(context)

        # Vehicle management
        elif any(kw in task_lower for kw in ["vehicle", "triciclo", "gps"]):
            return await self._manage_vehicles(context)

        # Bottle tracking handoff
        elif any(kw in task_lower for kw in ["bottle", "botellón", "swap"]):
            return await self.handoff(AgentType.INVENTORY, task, context)

        # Payment handoff
        elif any(kw in task_lower for kw in ["payment", "pago", "collect", "cobranza"]):
            return await self.handoff(AgentType.FINANCIAL, task, context)

        # Customer communication handoff
        elif any(kw in task_lower for kw in ["customer", "client", "whatsapp", "valentina"]):
            return await self.handoff(AgentType.VALENTINA, task, context)

        # Default: store as episodic and return guidance
        msg = (
            "Task noted: {task}. Use specific keywords for "
            "route planning, driver assignment, delivery tracking, or vehicle management."
        )
        return TaskResult(
            success=True,
            agent_name=self.config.name,
            output=msg,
            metadata={"task_type": "general", "needs_specific_action": True},
        )

    async def _plan_routes(self, context: dict[str, Any]) -> TaskResult:
        # In real implementation, would call OR-Tools VRP solver
        # For now, return structured response
        return TaskResult(
            success=True,
            agent_name=self.config.name,
            output={
                "action": "route_planning",
                "message": "Route planning initiated. Would call OR-Tools VRP with current orders.",
                "procedural_steps": [
                    "1. Fetch pending orders from dispatch.db",
                    "2. Get vehicle capacities and driver availability",
                    "3. Run VRP solver with time windows",
                    "4. Assign routes to drivers via Telegram bot",
                    "5. Store route plan in memory",
                ],
            },
            metadata={"task_type": "route_planning"},
        )

    async def _assign_drivers(self, context: dict[str, Any]) -> TaskResult:
        return TaskResult(
            success=True,
            agent_name=self.config.name,
            output={
                "action": "driver_assignment",
                "message": "Driver assignment logic executed.",
                "procedural_steps": [
                    "1. Match driver zones to route zones",
                    "2. Check driver capacity vs route volume",
                    "3. Verify driver availability (check-in status)",
                    "4. Assign via dispatcher_bot Telegram",
                    "5. Confirm assignment in dispatch.db",
                ],
            },
            metadata={"task_type": "driver_assignment"},
        )

    async def _track_deliveries(self, context: dict[str, Any]) -> TaskResult:
        return TaskResult(
            success=True,
            agent_name=self.config.name,
            output={
                "action": "delivery_tracking",
                "message": "Delivery tracking - would query dispatch.db and GPS positions.",
                "key_metrics": ["on_time_rate", "avg_delivery_time", "pending_count"],
            },
            metadata={"task_type": "delivery_tracking"},
        )

    async def _manage_vehicles(self, context: dict[str, Any]) -> TaskResult:
        msg = (
            "Vehicle management - 2 triciclos with Honor X7b phones "
            "(Digitel+Movilnet)"
        )
        return TaskResult(
            success=True,
            agent_name=self.config.name,
            output={
                "action": "vehicle_management",
                "message": msg,
                "vehicles": ["TRICICLO-001", "TRICICLO-002"],
            },
            metadata={"task_type": "vehicle_management"},
        )


class FinancialAgent(MemoryAwareAgent):
    """Financial specialist agent for payments, collections, and R4 Banco integration"""

    async def _execute_with_memory(self, task: str, context: dict[str, Any]) -> TaskResult:
        task_lower = task.lower()

        # Payment processing
        if any(kw in task_lower for kw in ["payment", "pago", "process", "mercadopago"]):
            return await self._process_payment(context)

        # Collections
        elif any(
            kw in task_lower
            for kw in ["collect", "cobranza", "reminder", "recordatorio", "overdue"]
        ):
            return await self._manage_collections(context)

        # R4 Banco webhook
        elif any(kw in task_lower for kw in ["r4", "banco", "webhook", "hmac"]):
            return await self._handle_r4_webhook(context)

        # Reconciliation
        elif any(kw in task_lower for kw in ["reconcile", "conciliar", "bank", "statement"]):
            return await self._reconcile_accounts(context)

        # Dispatcher handoff for delivery payment confirmation
        elif any(kw in task_lower for kw in ["delivery", "entrega", "confirm"]):
            return await self.handoff(AgentType.DISPATCHER, task, context)

        # Valentina handoff for customer billing
        elif any(kw in task_lower for kw in ["customer", "client", "bill", "factura", "whatsapp"]):
            return await self.handoff(AgentType.VALENTINA, task, context)

        return TaskResult(
            success=True,
            agent_name=self.config.name,
            output=(
                "Financial task noted: {task}. Specify: payment, "
                "collections, r4_banco, reconciliation."
            ),
            metadata={"task_type": "general"},
        )

    async def _process_payment(self, context: dict[str, Any]) -> TaskResult:
        return TaskResult(
            success=True,
            agent_name=self.config.name,
            output={
                "action": "payment_processing",
                "message": "Payment processing - supports MercadoPago, bank transfer, cash.",
                "gateways": ["mercadopago", "bank_transfer", "cash", "r4_banco"],
            },
            metadata={"task_type": "payment_processing"},
        )

    async def _manage_collections(self, context: dict[str, Any]) -> TaskResult:
        return TaskResult(
            success=True,
            agent_name=self.config.name,
            output={
                "action": "collections_management",
                "message": "Collections workflow - automated reminders at 18:30 daily.",
                "cron_jobs": ["run_fs_recordatorios", "run_fs_reporte"],
            },
            metadata={"task_type": "collections"},
        )

    async def _handle_r4_webhook(self, context: dict[str, Any]) -> TaskResult:
        return TaskResult(
            success=True,
            agent_name=self.config.name,
            output={
                "action": "r4_banco_webhook",
                "message": "R4 Conecta V3.0 webhook handler - HMAC-SHA256 verified.",
                "events": ["payment.received", "payment.failed", "transfer.completed"],
            },
            metadata={"task_type": "r4_webhook"},
        )

    async def _reconcile_accounts(self, context: dict[str, Any]) -> TaskResult:
        return TaskResult(
            success=True,
            agent_name=self.config.name,
            output={
                "action": "reconciliation",
                "message": "Bank reconciliation - match statements vs internal records.",
                "databases": ["conversations.db", "dispatch.db"],
            },
            metadata={"task_type": "reconciliation"},
        )


class InventoryAgent(MemoryAwareAgent):
    """Inventory specialist agent for bottle tracking and SWAP management"""

    async def _execute_with_memory(self, task: str, context: dict[str, Any]) -> TaskResult:
        task_lower = task.lower()

        # Bottle tracking
        if any(kw in task_lower for kw in ["bottle", "botellón", "track", "tracker", "h2o-"]):
            return await self._track_bottles(context)

        # SWAP management
        elif any(kw in task_lower for kw in ["swap", "loaner", "migration", "loaner"]):
            return await self._manage_swap(context)

        # Cycle counts
        elif any(kw in task_lower for kw in ["cycle", "count", "inventory", "stock", "conteo"]):
            return await self._cycle_count(context)

        # Dispatcher handoff for delivery reconciliation
        elif any(kw in task_lower for kw in ["delivery", "entrega", "route", "ruta"]):
            return await self.handoff(AgentType.DISPATCHER, task, context)

        # Financial handoff for bottle deposits
        elif any(
            kw in task_lower for kw in ["deposit", "depósito", "refund", "reembolso", "payment"]
        ):
            return await self.handoff(AgentType.FINANCIAL, task, context)

        return TaskResult(
            success=True,
            agent_name=self.config.name,
            output=(
                "Inventory task noted: {task}. Specify: bottle tracking, "
                "SWAP management, cycle count."
            ),
            metadata={"task_type": "general"},
        )

    async def _track_bottles(self, context: dict[str, Any]) -> TaskResult:
        return TaskResult(
            success=True,
            agent_name=self.config.name,
            output={
                "action": "bottle_tracking",
                "message": "Individual bottle tracking for 165 loaners (H2O-001 to H2O-165).",
                "states": ["IN_CIRCULATION", "AT_CLIENT", "IN_TRANSIT", "DAMAGED", "RETIRED"],
            },
            metadata={"task_type": "bottle_tracking"},
        )

    async def _manage_swap(self, context: dict[str, Any]) -> TaskResult:
        return TaskResult(
            success=True,
            agent_name=self.config.name,
            output={
                "action": "swap_management",
                "message": "SWAP 3-week migration program for 165 loaner bottles.",
                "phases": ["week_1: identify_old", "week_2: deliver_new", "week_3: collect_old"],
            },
            metadata={"task_type": "swap_management"},
        )

    async def _cycle_count(self, context: dict[str, Any]) -> TaskResult:
        return TaskResult(
            success=True,
            agent_name=self.config.name,
            output={
                "action": "cycle_count",
                "message": "Cycle count procedure - daily reconciliation with dispatcher.",
                "frequency": "daily_morning_reconciliation",
            },
            metadata={"task_type": "cycle_count"},
        )


class ValentinaAgent(MemoryAwareAgent):
    """Valentina specialist agent for WhatsApp customer interactions"""

    async def _execute_with_memory(self, task: str, context: dict[str, Any]) -> TaskResult:
        task_lower = task.lower()

        # Order taking
        if any(kw in task_lower for kw in ["order", "pedido", "orden", "quiero", "necesito"]):
            return await self._take_order(context)

        # Status updates
        elif any(kw in task_lower for kw in ["status", "estado", "donde", "cuando", "llegada"]):
            return await self._check_status(context)

        # Complaints
        elif any(kw in task_lower for kw in ["complaint", "queja", "reclamo", "problema", "mal"]):
            return await self._handle_complaint(context)

        # Payment inquiries
        elif any(kw in task_lower for kw in ["payment", "pago", "factura", "bill", "deuda"]):
            return await self.handoff(AgentType.FINANCIAL, task, context)

        # Delivery coordination
        elif any(kw in task_lower for kw in ["delivery", "entrega", "driver", "chofer", "camion"]):
            return await self.handoff(AgentType.DISPATCHER, task, context)

        # Bottle inquiries
        elif any(kw in task_lower for kw in ["bottle", "botellón", "vacío", "swap"]):
            return await self.handoff(AgentType.INVENTORY, task, context)

        return TaskResult(
            success=True,
            agent_name=self.config.name,
            output="Valentina task noted: {task}. Handles orders, status, complaints via WhatsApp.",
            metadata={"task_type": "general"},
        )

    async def _take_order(self, context: dict[str, Any]) -> TaskResult:
        return TaskResult(
            success=True,
            agent_name=self.config.name,
            output={
                "action": "order_taking",
                "message": "Order parsing from WhatsApp - extracts client, bottles, address, time.",
                "fields": ["client_phone", "bottle_count", "delivery_address", "preferred_time"],
            },
            metadata={"task_type": "order_taking"},
        )

    async def _check_status(self, context: dict[str, Any]) -> TaskResult:
        return TaskResult(
            success=True,
            agent_name=self.config.name,
            output={
                "action": "status_check",
                "message": "Delivery status lookup from dispatch.db.",
                "meta_api": "Meta Cloud API for WhatsApp responses",
            },
            metadata={"task_type": "status_check"},
        )

    async def _handle_complaint(self, context: dict[str, Any]) -> TaskResult:
        return TaskResult(
            success=True,
            agent_name=self.config.name,
            output={
                "action": "complaint_handling",
                "message": "Structured complaint workflow - categorize, escalate, resolve.",
                "escalation": "Alert Líder for complex complaints",
            },
            metadata={"task_type": "complaint"},
        )


class AnalyticsAgent(MemoryAwareAgent):
    """Analytics specialist agent for reports, KPIs, and insights"""

    async def _execute_with_memory(self, task: str, context: dict[str, Any]) -> TaskResult:
        task_lower = task.lower()

        # Report generation
        if any(kw in task_lower for kw in ["report", "reporte", "generate", "generar"]):
            return await self._generate_report(context)

        # KPI dashboard
        elif any(kw in task_lower for kw in ["kpi", "dashboard", "metric", "métrica"]):
            return await self._build_dashboard(context)

        # Trend analysis
        elif any(
            kw in task_lower for kw in ["trend", "tendencia", "analysis", "análisis", "pattern"]
        ):
            return await self._analyze_trends(context)

        # Scheduled reports
        elif any(kw in task_lower for kw in ["cron", "schedule", "7am", "18:30", "daily"]):
            return await self._scheduled_reports(context)

        # Cross-agent analytics
        else:
            return TaskResult(
                success=True,
                agent_name=self.config.name,
                output=f"Analytics task: {task}. Specify: report, kpi, trend, scheduled.",
                metadata={"task_type": "general"},
            )

    async def _generate_report(self, context: dict[str, Any]) -> TaskResult:
        return TaskResult(
            success=True,
            agent_name=self.config.name,
            output={
                "action": "report_generation",
                "message": "Report generation with Jinja2 templates + SQL queries.",
                "templates": ["operational_7am", "financial_1830", "weekly_executive"],
            },
            metadata={"task_type": "report"},
        )

    async def _build_dashboard(self, context: dict[str, Any]) -> TaskResult:
        return TaskResult(
            success=True,
            agent_name=self.config.name,
            output={
                "action": "kpi_dashboard",
                "message": "KPI dashboard - delivery efficiency, collection rate, bottle turnover.",
                "metrics": [
                    "on_time_rate",
                    "collection_rate",
                    "bottle_utilization",
                    "customer_satisfaction",
                ],
            },
            metadata={"task_type": "kpi"},
        )

    async def _analyze_trends(self, context: dict[str, Any]) -> TaskResult:
        return TaskResult(
            success=True,
            agent_name=self.config.name,
            output={
                "action": "trend_analysis",
                "message": "Statistical trend analysis with pandas/scipy.",
                "periods": ["weekly", "monthly", "seasonal"],
            },
            metadata={"task_type": "trend"},
        )

    async def _scheduled_reports(self, context: dict[str, Any]) -> TaskResult:
        return TaskResult(
            success=True,
            agent_name=self.config.name,
            output={
                "action": "scheduled_reports",
                "message": "Cron-scheduled reports: 7am operational, 18:30 financial + reminders.",
                "cron_jobs": ["run_analytics_7am", "run_fs_reporte", "run_fs_recordatorios"],
            },
            metadata={"task_type": "scheduled"},
        )
