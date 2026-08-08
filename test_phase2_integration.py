#!/usr/bin/env python3
"""
Phase 2 Integration Test: Multi-Agent Orchestration with Unified Memory

Tests the complete Phase 2 system:
1. Unified Memory (mem0 + Ollama + FAISS)
2. Orchestrator with 5 specialist agents
3. Skill Registry with progressive disclosure
4. Memory-aware agent execution
5. Workflow orchestration across agents
"""

import sys
import os

# Critical: Disable PostHog telemetry BEFORE importing mem0
os.environ.setdefault('MEM0_TELEMETRY', 'False')
os.environ.setdefault('POSTHOG_DISABLED', '1')
os.environ.setdefault('DO_NOT_TRACK', '1')

sys.path.insert(0, '/mnt/ssd_trabajo/hermes-agent/src')

from orchestration import Orchestrator, AgentType, SkillRegistry
from memory import create_unified_memory


def test_phase2_integration():
    """Run complete Phase 2 integration test"""
    print("=" * 60)
    print("PHASE 2 INTEGRATION TEST: Multi-Agent Orchestration")
    print("=" * 60)
    
    # 1. Initialize Unified Memory
    print("\n1. Initializing Unified Memory (mem0 + Ollama + FAISS)...")
    memory = create_unified_memory()
    health = memory.health_check()
    assert health['healthy'], f"Memory unhealthy: {health}"
    print(f"   ✅ Memory healthy: {health['vector_store']} + {health['embedder']} + {health['llm']}")
    print(f"   ✅ Storage: {health['storage_path']}")
    
    # 2. Initialize Orchestrator
    print("\n2. Initializing Orchestrator with 5 Specialist Agents...")
    orchestrator = Orchestrator(memory)
    agents = list(orchestrator.agent_configs.keys())
    assert len(agents) == 5, f"Expected 5 agents, got {len(agents)}"
    print(f"   ✅ Agents registered: {[a.value for a in agents]}")
    
    # 3. Test Agent Creation & Execution
    print("\n3. Testing Agent Creation & Task Execution...")
    import asyncio
    
    async def test_agents():
        results = {}
        
        # Test each agent
        for agent_type in agents:
            agent = orchestrator.get_agent(agent_type)
            assert agent is not None, f"Failed to create {agent_type.value}"
            
            # Execute a relevant task
            task_map = {
                AgentType.DISPATCHER: 'plan routes for today',
                AgentType.FINANCIAL: 'process payment',
                AgentType.INVENTORY: 'track bottle H2O-001',
                AgentType.VALENTINA: 'take order from client',
                AgentType.ANALYTICS: 'generate report'
            }
            
            task = task_map.get(agent_type, 'general task')
            result = await agent.execute(task, {})
            
            assert result.success, f"Agent {agent_type.value} failed: {result.error}"
            results[agent_type.value] = result.metadata.get('task_type')
            print(f"   ✅ {agent_type.value}: {results[agent_type.value]}")
        
        return results
    
    agent_results = asyncio.run(test_agents())
    
    # 4. Test Workflow Orchestration
    print("\n4. Testing Multi-Agent Workflow Orchestration...")
    
    async def test_workflow():
        workflow_result = await orchestrator.execute_workflow(
            'daily_operations',
            [
                {'agent': 'dispatcher', 'task': 'plan routes for today'},
                {'agent': 'financial', 'task': 'run collections reminders'},
                {'agent': 'inventory', 'task': 'cycle count reconciliation'}
            ],
            {'date': '2026-08-02', 'shift': 'morning'}
        )
        
        assert len(workflow_result) == 3, f"Expected 3 steps, got {len(workflow_result)}"
        for i, result in enumerate(workflow_result):
            assert result.success, f"Workflow step {i} failed: {result.error}"
            print(f"   ✅ Step {i+1}: {result.agent_name} - {result.metadata.get('task_type')}")
        
        return workflow_result
    
    workflow_results = asyncio.run(test_workflow())
    
    # 5. Test Skill Registry
    print("\n5. Testing Skill Registry (Progressive Disclosure)...")
    registry = SkillRegistry()
    skill_count = registry.load_all()
    assert skill_count >= 7, f"Expected at least 7 skills, got {skill_count}"
    print(f"   ✅ Loaded {skill_count} skills")
    
    # Discovery phase
    dispatch_skills = registry.discover('dispatch')
    assert len(dispatch_skills) > 0, "Should find dispatcher skills"
    print(f"   ✅ Discovery: {dispatch_skills[0]['name']}")
    
    # Activation phase
    activated = registry.activate('dispatcher_skill')
    assert activated is not None, "Should activate dispatcher_skill"
    assert 'instructions' in activated, "Should have instructions"
    print(f"   ✅ Activation: Full instructions loaded ({len(activated['instructions'])} chars)")
    
    # Dependency analysis
    deps = registry.analyze_dependencies()
    assert 'dispatcher_skill' in deps, "Should have dispatcher_skill dependencies"
    assert 'bottle_tracking' in deps['dispatcher_skill'], "dispatcher_skill depends on bottle_tracking"
    print(f"   ✅ Dependencies: {deps}")
    
    # 6. Test Cross-Agent Memory Sharing
    print("\n6. Testing Cross-Agent Memory Sharing...")
    
    # Store memory from dispatcher
    memory.add(
        content="Route plan created for 2026-08-02: 15 deliveries, 2 vehicles",
        memory_type=__import__('memory.unified_memory', fromlist=['MemoryType']).MemoryType.EPISODIC,
        metadata={'agent': 'dispatcher', 'workflow': 'daily_operations'},
        tags=['dispatcher', 'route_plan', '2026-08-02']
    )
    
    # Financial agent should be able to retrieve it
    financial_agent = orchestrator.get_agent(AgentType.FINANCIAL)
    search_results = financial_agent.memory.search("route plan 2026-08-02", limit=3)
    assert len(search_results) > 0, "Cross-agent memory retrieval failed"
    print(f"   ✅ Cross-agent memory: Financial agent retrieved dispatcher's route plan")
    
    # 7. Test Handoff Mechanism
    print("\n7. Testing Agent Handoff Mechanism...")
    
    async def test_handoff():
        dispatcher = orchestrator.get_agent(AgentType.DISPATCHER)
        # Dispatcher hands off bottle tracking to inventory
        handoff_result = await dispatcher.handoff(
            AgentType.INVENTORY,
            'track bottles for today routes',
            {'route_date': '2026-08-02'}
        )
        assert handoff_result.success, f"Handoff failed: {handoff_result.error}"
        print(f"   ✅ Handoff: dispatcher -> inventory successful")
        return handoff_result
    
    handoff_result = asyncio.run(test_handoff())
    
    print("\n" + "=" * 60)
    print("✅ ALL PHASE 2 TESTS PASSED!")
    print("=" * 60)
    print("\nPhase 2 Components Verified:")
    print("  • Unified Memory (mem0 + Ollama nomic-embed-text + FAISS)")
    print("  • Orchestrator with 5 specialist agents")
    print("  • Memory-aware agent execution with context enrichment")
    print("  • Multi-agent workflow orchestration")
    print("  • Skill Registry with progressive disclosure")
    print("  • Cross-agent memory sharing")
    print("  • Agent handoff mechanism")
    print("\nReady for Phase 3: External Skill Library Integration (SkillNet, ADK)")
    
    return True


if __name__ == "__main__":
    test_phase2_integration()