#!/usr/bin/env python3
"""
Integración de Memoria Unificada para Hermes-Agent
Fase 1: Memoria Unificada (Semántica + Episódica + Procedural + Autobiográfica)

Integra 3 sistemas de memoria:
1. TencentDB-Agent-Memory - Memoria semántica principal + RAG contextual (TypeScript/Node.js)
2. mem0ai/mem0 - Memoria persistente ligera + RAG (Python)
3. letta-ai/letta - Memoria episódica + agents con estado (Python/TypeScript)
"""

import asyncio
import json
import logging
import os
import aiohttp
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

# Configurar logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("unified_memory")

# ============================================================
# TIPOS Y ENUMS
# ============================================================


class MemoryType(Enum):
    SEMANTIC = "semantic"  # Hechos, conocimiento, RAG
    EPISODIC = "episodic"  # Experiencias, conversaciones, sesiones
    PROCEDURAL = "procedural"  # Skills, procedimientos, workflows
    AUTOBIOGRAPHICAL = "autobiographical"  # Identidad, metas, evolución


class MemoryBackend(Enum):
    TENCENTDB = "tencentdb"
    MEM0 = "mem0"
    LETTA = "letta"


@dataclass
class MemoryEntry:
    id: str
    type: MemoryType
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    embeddings: list[float] | None = None
    timestamp: datetime = field(default_factory=datetime.now)
    source: str = "hermes-agent"
    tags: list[str] = field(default_factory=list)
    importance: float = 1.0  # 0.0 - 1.0


@dataclass
class SearchResult:
    entry: MemoryEntry
    score: float
    backend: MemoryBackend


# ============================================================
# INTERFAZ BASE UNIFICADA
# ============================================================


class MemoryBackendInterface(ABC):
    """Interfaz base unificada para todos los backends de memoria"""

    @property
    @abstractmethod
    def backend_type(self) -> MemoryBackend:
        pass

    @property
    @abstractmethod
    def supported_types(self) -> list[MemoryType]:
        pass

    @abstractmethod
    async def initialize(self, config: dict[str, Any]) -> bool:
        pass

    @abstractmethod
    async def add(self, entry: MemoryEntry) -> str:
        """Añadir entrada de memoria. Retorna ID."""
        pass

    @abstractmethod
    async def search(
        self,
        query: str,
        memory_types: list[MemoryType] | None = None,
        limit: int = 10,
        threshold: float = 0.7,
    ) -> list[SearchResult]:
        pass

    @abstractmethod
    async def get(self, entry_id: str) -> MemoryEntry | None:
        pass

    @abstractmethod
    async def update(self, entry_id: str, updates: dict[str, Any]) -> bool:
        pass

    @abstractmethod
    async def delete(self, entry_id: str) -> bool:
        pass

    @abstractmethod
    async def health_check(self) -> dict[str, Any]:
        pass

    @abstractmethod
    async def close(self) -> None:
        pass


# ============================================================
# IMPLEMENTACIONES POR BACKEND
# ============================================================


class TencentDBMemoryBackend(MemoryBackendInterface):
    """Wrapper para TencentDB-Agent-Memory (TypeScript/Node.js via subprocess/HTTP)"""

    @property
    def backend_type(self) -> MemoryBackend:
        return MemoryBackend.TENCENTDB

    @property
    def supported_types(self) -> list[MemoryType]:
        return [MemoryType.SEMANTIC, MemoryType.EPISODIC, MemoryType.PROCEDURAL]

    def __init__(self):
        self.base_url = "http://localhost:8125"  # Puerto por defecto TencentDB
        self.api_key = os.getenv("TENCENT_DB_MEMORY_API_KEY", "")
        self.process = None
        self.initialized = False

    async def initialize(self, config: dict[str, Any]) -> bool:
        try:
            # Verificar si el servicio está corriendo
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/health", timeout=5) as resp:
                    if resp.status == 200:
                        self.initialized = True
                        logger.info("TencentDB-Agent-Memory conectado exitosamente")
                        return True
        except Exception as e:
            logger.warning(f"TencentDB no disponible, intentando iniciar: {e}")
            # Intentar iniciar via deploy script
            return await self._start_service()
        return False

    async def _start_service(self) -> bool:
        try:
            # Verificar si existe el deploy script
            deploy_path = Path(
                "/mnt/ssd_trabajo/hermes-agent/external_repos/memory/TencentDB-Agent-Memory/deploy/global-images/start-all.sh"
            )
            if deploy_path.exists():
                # Configurar .env
                env_path = Path(
                    "/mnt/ssd_trabajo/hermes-agent/external_repos/memory/TencentDB-Agent-Memory/deploy/global-images/.env"
                )
                if not env_path.exists():
                    example_path = Path(
                        "/mnt/ssd_trabajo/hermes-agent/external_repos/memory/TencentDB-Agent-Memory/deploy/global-images/.env.example"
                    )
                    if example_path.exists():
                        import shutil

                        shutil.copy(example_path, env_path)
                        logger.info("Creado .env para TencentDB, configurar LLM keys")

                # Iniciar en background
                import subprocess

                self.process = subprocess.Popen(
                    ["./start-all.sh"],
                    cwd="/mnt/ssd_trabajo/hermes-agent/external_repos/memory/TencentDB-Agent-Memory/deploy/global-images",
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

                # Esperar a que inicie
                await asyncio.sleep(10)

                # Verificar health
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{self.base_url}/health", timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status == 200:
                            self.initialized = True
                            logger.info("TencentDB-Agent-Memory iniciado y saludable")
                            return True
        except Exception as e:
            logger.error(f"Error iniciando TencentDB: {e}")
        return False

    async def add(self, entry: MemoryEntry) -> str:
        # Implementar via HTTP API de TencentDB
        payload = {
            "content": entry.content,
            "metadata": entry.metadata,
            "tags": entry.tags,
            "type": entry.type.value,
        }
        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
            async with session.post(
                f"{self.base_url}/api/memory", json=payload, headers=headers
            ) as resp:
                result = await resp.json()
                return result.get("id", "")

    async def search(
        self,
        query: str,
        memory_types: list[MemoryType] | None = None,
        limit: int = 10,
        threshold: float = 0.7,
    ) -> list[SearchResult]:
        payload = {
            "query": query,
            "limit": limit,
            "threshold": threshold,
            "types": [t.value for t in memory_types] if memory_types else None,
        }
        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
            async with session.post(
                f"{self.base_url}/api/search", json=payload, headers=headers
            ) as resp:
                results = await resp.json()
                return [
                    SearchResult(
                        entry=MemoryEntry(**r["entry"]),
                        score=r["score"],
                        backend=MemoryBackend.TENCENTDB,
                    )
                    for r in results
                ]

    async def get(self, entry_id: str) -> MemoryEntry | None:

        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
            async with session.get(
                f"{self.base_url}/api/memory/{entry_id}", headers=headers
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return MemoryEntry(**data)
        return None

    async def update(self, entry_id: str, updates: dict[str, Any]) -> bool:
        import aiohttp

        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
            async with session.patch(
                f"{self.base_url}/api/memory/{entry_id}", json=updates, headers=headers
            ) as resp:
                return resp.status == 200

    async def delete(self, entry_id: str) -> bool:
        import aiohttp

        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
            async with session.delete(
                f"{self.base_url}/api/memory/{entry_id}", headers=headers
            ) as resp:
                return resp.status == 200

    async def health_check(self) -> dict[str, Any]:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/health", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    return {"healthy": resp.status == 200, "backend": "tencentdb"}
        except Exception as e:
            return {"healthy": False, "backend": "tencentdb", "error": str(e)}

    async def close(self) -> None:
        if self.process:
            self.process.terminate()


class Mem0Backend(MemoryBackendInterface):
    """Wrapper para mem0ai/mem0 (Python nativo)"""

    @property
    def backend_type(self) -> MemoryBackend:
        return MemoryBackend.MEM0

    @property
    def supported_types(self) -> list[MemoryType]:
        return [
            MemoryType.SEMANTIC,
            MemoryType.EPISODIC,
            MemoryType.PROCEDURAL,
            MemoryType.AUTOBIOGRAPHICAL,
        ]

    def __init__(self):
        self.client = None
        self.api_key = os.getenv("MEM0_API_KEY", "")
        self.initialized = False

    async def initialize(self, config: dict[str, Any]) -> bool:
        try:
            # Importar mem0
            from mem0 import Memory

            self.client = Memory()  # Usar Memory local, no MemoryClient
            self.initialized = True
            logger.info("mem0 inicializado correctamente (local)")
            return True
        except Exception as e:
            logger.error(f"Error inicializando mem0: {e}")
            return False

    async def add(self, entry: MemoryEntry) -> str:
        if not self.client:
            return ""

        # mem0 usa add con mensajes
        messages = [{"role": "user", "content": entry.content}]
        metadata = entry.metadata.copy()
        metadata.update(
            {
                "type": entry.type.value,
                "tags": entry.tags,
                "importance": entry.importance,
                "source": entry.source,
            }
        )

        result = self.client.add(
            messages=messages, user_id=metadata.get("user_id", "hermes-agent"), metadata=metadata
        )
        return result.get("id", "") if isinstance(result, dict) else str(result)

    async def search(
        self,
        query: str,
        memory_types: list[MemoryType] | None = None,
        limit: int = 10,
        threshold: float = 0.7,
    ) -> list[SearchResult]:
        if not self.client:
            return []

        results = self.client.search(
            query=query, user_id="hermes-agent", limit=limit, threshold=threshold
        )

        results_list = []
        for r in results.get("results", []):
            entry = MemoryEntry(
                id=r.get("id", ""),
                type=MemoryType(r.get("metadata", {}).get("type", "semantic")),
                content=r.get("memory", ""),
                metadata=r.get("metadata", {}),
                timestamp=datetime.fromisoformat(r.get("created_at", datetime.now().isoformat())),
                tags=r.get("metadata", {}).get("tags", []),
            )
            results_list.append(
                SearchResult(entry=entry, score=r.get("score", 1.0), backend=MemoryBackend.MEM0)
            )
        return results_list

    async def get(self, entry_id: str) -> MemoryEntry | None:
        # mem0 no tiene get directo por ID en API pública
        return None

    async def update(self, entry_id: str, updates: dict[str, Any]) -> bool:
        # mem0 no soporta update directo
        return False

    async def delete(self, entry_id: str) -> bool:
        # mem0 no tiene delete por ID en API pública
        return False

    async def health_check(self) -> dict[str, Any]:
        try:
            # Verificar conexión
            self.client.get_all(user_id="hermes-agent", limit=1)
            return {"healthy": True, "backend": "mem0"}
        except Exception as e:
            return {"healthy": False, "backend": "mem0", "error": str(e)}

    async def close(self) -> None:
        pass


class LettaBackend(MemoryBackendInterface):
    """Wrapper para Letta (Python SDK)"""

    @property
    def backend_type(self) -> MemoryBackend:
        return MemoryBackend.LETTA

    @property
    def supported_types(self) -> list[MemoryType]:
        return [MemoryType.EPISODIC, MemoryType.AUTOBIOGRAPHICAL, MemoryType.PROCEDURAL]

    def __init__(self):
        self.client = None
        self.agent_id = None
        self.api_key = os.getenv("LETTA_API_KEY", "")
        self.initialized = False

    async def initialize(self, config: dict[str, Any]) -> bool:
        try:
            from letta_client import Letta

            self.client = Letta(base_url="http://localhost:8283")  # Puerto por defecto Letta server

            # Crear o recuperar agente
            agent_config = config.get("agent", {})
            agent = self.client.agents.create(
                model=agent_config.get("model", "anthropic/claude-opus-4"),
                name=agent_config.get("name", "prometeo"),
                embedding=agent_config.get("embedding", "text-embedding-3-small"),
                system=agent_config.get(
                    "persona", "Prometeo - Entidad aislada full-stack para Estación H2O"
                ),
            )
            self.agent_id = agent.id
            self.initialized = True
            logger.info(f"Letta inicializado con agente: {self.agent_id}")
            return True
        except Exception as e:
            logger.error(f"Error inicializando Letta: {e}")
            return False

    async def add(self, entry: MemoryEntry) -> str:
        if not self.client or not self.agent_id:
            return ""

        # En Letta, la memoria se gestiona via conversación
        try:
            _ = self.client.agents.messages.create(
                agent_id=self.agent_id, messages=[{"role": "user", "content": entry.content}]
            )
            # Letta gestiona la memoria internamente
            return entry.id
        except Exception as e:
            logger.error(f"Error añadiendo a Letta: {e}")
            return ""

    async def search(
        self,
        query: str,
        memory_types: list[MemoryType] | None = None,
        limit: int = 10,
        threshold: float = 0.7,
    ) -> list[SearchResult]:
        # Letta no expone search directo, se usa core memory blocks
        # Implementación simplificada
        return []

    async def get(self, entry_id: str) -> MemoryEntry | None:
        return None

    async def update(self, entry_id: str, updates: dict[str, Any]) -> bool:
        return False

    async def delete(self, entry_id: str) -> bool:
        return False

    async def health_check(self) -> dict[str, Any]:
        try:
            if self.client and self.agent_id:
                agent = self.client.agents.retrieve(self.agent_id)
                return {"healthy": True, "backend": "letta", "agent_id": self.agent_id}
        except Exception as e:
            return {"healthy": False, "backend": "letta", "error": str(e)}
        return {"healthy": False, "backend": "letta"}

    async def close(self) -> None:
        pass


# ============================================================
# GESTOR DE MEMORIA UNIFICADA
# ============================================================


class UnifiedMemoryManager:
    """
    Gestor principal que coordina todos los backends de memoria
    y proporciona una interfaz unificada para hermes-agent
    """

    def __init__(self):
        self.backends: dict[MemoryBackend, MemoryBackendInterface] = {}
        self.routing_rules: dict[MemoryType, list[MemoryBackend]] = {
            MemoryType.SEMANTIC: [MemoryBackend.TENCENTDB, MemoryBackend.MEM0],
            MemoryType.EPISODIC: [MemoryBackend.LETTA, MemoryBackend.MEM0],
            MemoryType.PROCEDURAL: [
                MemoryBackend.TENCENTDB,
                MemoryBackend.MEM0,
                MemoryBackend.LETTA,
            ],
            MemoryType.AUTOBIOGRAPHICAL: [MemoryBackend.LETTA, MemoryBackend.MEM0],
        }
        self.initialized = False

    async def initialize(self, config: dict[str, Any]) -> bool:
        """Inicializar todos los backends configurados"""

        # 1. TencentDB-Agent-Memory (Semántica principal)
        tencentdb = TencentDBMemoryBackend()
        if await tencentdb.initialize(config.get("tencentdb", {})):
            self.backends[MemoryBackend.TENCENTDB] = tencentdb
            logger.info("✅ TencentDB-Agent-Memory inicializado")

        # 2. mem0 (memoria ligera, fallback)
        mem0 = Mem0Backend()
        if await mem0.initialize(config.get("mem0", {})):
            self.backends[MemoryBackend.MEM0] = mem0
            logger.info("✅ mem0 inicializado")

        # 3. Letta (memoria episódica + agentes)
        letta = LettaBackend()
        if await letta.initialize(config.get("letta", {})):
            self.backends[MemoryBackend.LETTA] = letta
            logger.info("✅ Letta inicializado")

        self.initialized = len(self.backends) > 0
        logger.info(f"Memoria unificada inicializada con {len(self.backends)} backends")
        return self.initialized

    def _select_backends(
        self, memory_type: MemoryType, preferred: MemoryBackend | None = None
    ) -> list[MemoryBackendInterface]:
        """Seleccionar backends para un tipo de memoria, ordenados por prioridad"""
        backends = []

        if preferred and preferred in self.backends:
            if preferred in self.routing_rules.get(memory_type, []):
                backends.append(self.backends[preferred])

        for backend_type in self.routing_rules.get(memory_type, []):
            if backend_type != preferred and backend_type in self.backends:
                backends.append(self.backends[backend_type])

        return backends

    async def add(
        self,
        content: str,
        memory_type: MemoryType,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        importance: float = 1.0,
        preferred_backend: MemoryBackend | None = None,
    ) -> dict[MemoryBackend, str]:
        """Añadir entrada a múltiples backends según reglas de enrutamiento"""

        entry = MemoryEntry(
            id="",  # Se asignará por cada backend
            type=memory_type,
            content=content,
            metadata=metadata or {},
            tags=tags or [],
            importance=importance,
        )

        backends = self._select_backends(memory_type, preferred_backend)
        results = {}

        for backend in backends:
            try:
                entry_id = await backend.add(entry)
                results[backend.backend_type] = entry_id
                logger.debug(f"Añadido a {backend.backend_type.value}: {entry_id}")
            except Exception as e:
                logger.error(f"Error añadiendo a {backend.backend_type}: {e}")
                results[backend.backend_type] = f"ERROR: {e}"

        return results

    async def search(
        self,
        query: str,
        memory_types: list[MemoryType] | None = None,
        limit: int = 10,
        threshold: float = 0.7,
    ) -> list[SearchResult]:
        """Buscar en todos los backends relevantes y fusionar resultados"""

        if memory_types is None:
            memory_types = list(MemoryType)

        all_results = []

        for memory_type in memory_types:
            backends = self._select_backends(memory_type)

            for backend in backends:
                try:
                    results = await backend.search(query, [memory_type], limit, threshold)
                    all_results.extend(results)
                except Exception as e:
                    logger.error(f"Error buscando en {backend.backend_type}: {e}")

        # Ordenar por score descendente y deduplicar por contenido similar
        all_results.sort(key=lambda x: x.score, reverse=True)

        # Deduplicación simple
        seen_content = set()
        unique_results = []
        for result in all_results:
            content_hash = hash(result.entry.content[:100])
            if content_hash not in seen_content:
                seen_content.add(content_hash)
                unique_results.append(result)

        return unique_results[:limit]

    async def get(self, entry_id: str, backend: MemoryBackend | None = None) -> MemoryEntry | None:
        if backend and backend in self.backends:
            return await self.backends[backend].get(entry_id)

        # Buscar en todos
        for b in self.backends.values():
            result = await b.get(entry_id)
            if result:
                return result
        return None

    async def health_check_all(self) -> dict[str, Any]:
        results = {}
        for backend_type, backend in self.backends.items():
            results[backend_type.value] = await backend.health_check()
        return results

    async def close_all(self):
        for backend in self.backends.values():
            await backend.close()


# ============================================================
# FUNCIÓN DE INICIALIZACIÓN PRINCIPAL
# ============================================================


async def initialize_unified_memory() -> UnifiedMemoryManager:
    """Inicializar el sistema de memoria unificada completo"""

    config = {
        "tencentdb": {
            "url": "http://localhost:8125",
            "api_key": os.getenv("TENCENT_DB_MEMORY_API_KEY", ""),
        },
        "mem0": {"api_key": os.getenv("MEM0_API_KEY", "")},
        "letta": {
            "api_key": os.getenv("LETTA_API_KEY", ""),
            "agent": {
                "model": "anthropic/claude-opus-4",
                "human": "Usuario Estación H2O",
                "persona": "Prometeo - Entidad aislada full-stack para Estación H2O",
            },
        },
    }

    manager = UnifiedMemoryManager()
    success = await manager.initialize(config)

    if not success:
        raise RuntimeError("No se pudo inicializar ningún backend de memoria")

    # Health check inicial
    health = await manager.health_check_all()
    logger.info(f"Health check: {json.dumps(health, indent=2)}")

    return manager


# ============================================================
# EJEMPLO DE USO
# ============================================================


async def demo():
    """Demostración de uso del sistema de memoria unificada"""

    logger.info("=== Iniciando demo de memoria unificada ===")

    manager = await initialize_unified_memory()

    try:
        # 1. Añadir memoria semántica (hecho/hecho técnico)
        await manager.add(
            content="Estación H2O usa 165 botellones loaner modelo H2O-001 a H2O-165",
            memory_type=MemoryType.SEMANTIC,
            tags=["h2o", "swap", "botellones", "inventario"],
            importance=0.9,
            metadata={"categoria": "inventario", "fuente": "documentacion_tecnica"},
        )

        # 2. Añadir memoria episódica (experiencia)
        await manager.add(
            content="Cliente Hotel del Lago pidió 10 botellones, entrega completada a las 10:30 AM",
            memory_type=MemoryType.EPISODIC,
            tags=["entrega", "cliente_hotel_del_lago", "completada"],
            importance=0.7,
            metadata={"cliente": "Hotel del Lago", "cantidad": 10, "estado": "completada"},
        )

        # 3. Añadir memoria procedural (skill/procedimiento)
        await manager.add(
            content="Procedimiento entrega: 1) Verificar pedido 2) Cargar botellones 3) Navegar GPS 4) Entregar 5) Recoger vacíos 6) Confirmar en app",
            memory_type=MemoryType.PROCEDURAL,
            tags=["procedimiento", "entrega", "choferes", "workflow"],
            importance=0.9,
            metadata={"tipo": "workflow_entrega", "version": "1.0"},
        )

        # 4. Añadir memoria autobiográfica (identidad/meta)
        await manager.add(
            content="Mi objetivo es ser la entidad aislada full-stack que opere Estación H2O de forma autónoma, gestionando SWAP, despacho, finanzas y logística sin intervención humana constante",
            memory_type=MemoryType.AUTOBIOGRAPHICAL,
            tags=["identidad", "meta", "mision", "autonomia"],
            importance=1.0,
            metadata={"tipo": "declaracion_mision", "version": "1.0"},
        )

        # 5. Búsqueda semántica
        logger.info("\n--- Búsqueda: 'botellones loaner' ---")
        results = await manager.search("botellones loaner", [MemoryType.SEMANTIC], limit=5)
        for r in results:
            logger.info(f"  [{r.backend.value}] Score: {r.score:.2f} - {r.entry.content[:80]}...")

        # 6. Búsqueda episódica
        logger.info("\n--- Búsqueda: 'entrega hotel' ---")
        results = await manager.search("entrega hotel", [MemoryType.EPISODIC], limit=5)
        for r in results:
            logger.info(f"  [{r.backend.value}] Score: {r.score:.2f} - {r.entry.content[:80]}...")

        # 7. Health check final
        health = await manager.health_check_all()
        logger.info(f"\nHealth check final: {json.dumps(health, indent=2, default=str)}")

    finally:
        await manager.close_all()


if __name__ == "__main__":
    asyncio.run(demo())
