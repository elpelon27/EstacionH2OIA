#!/usr/bin/env python3
"""
🧠 SKILL: OBSIDIAN INDEXER PARA HERMES AGENT
Este skill permite a Hermes indexar su vault de Obsidian en Mem0 + ChromaDB.

Uso desde el agente:
  > Hermes, indexa mi vault de Obsidian
  > Hermes, busca en mis notas de Obsidian sobre [tema]
  > Hermes, actualiza el índice de Obsidian
"""

import hashlib
import json
import os
import sys
from datetime import datetime
from typing import Any

# Agregar base al path
sys.path.insert(0, "/home/skynet/hermes-unified")

from memory_manager import HermesMemoryManager  # type: ignore[import-not-found]


class ObsidianSkill:
    """Skill para manejar el vault de Obsidian"""

    def __init__(self) -> None:
        self.vault_path = "/mnt/ssd_trabajo/hermes-agent/docs"
        self.state_file = "/mnt/ssd_trabajo/hermes-agent/.obsidian_index_state.json"
        self.memory: HermesMemoryManager | None = None

    def _init_memory(self) -> HermesMemoryManager:
        """Inicializa el gestor de memoria si no está activo"""
        if self.memory is None:
            self.memory = HermesMemoryManager()
        return self.memory

    def _get_file_hash(self, filepath: str) -> str:
        """Calcula hash del archivo"""
        with open(filepath, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()

    def _load_state(self) -> dict[str, Any]:
        """Carga el estado del índice"""
        if os.path.exists(self.state_file):
            with open(self.state_file) as f:
                return json.load(f)  # type: ignore[no-any-return]
        return {}

    def _save_state(self, state: dict[str, Any]) -> None:
        """Guarda el estado del índice"""
        with open(self.state_file, "w") as f:
            json.dump(state, f, indent=2)

    def scan_vault(self) -> list[dict[str, Any]]:
        """Escanea el vault y lista archivos .md"""
        files = []
        for root, dirs, filenames in os.walk(self.vault_path):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ["obsidian"]]
            for filename in filenames:
                if filename.endswith(".md"):
                    filepath = os.path.join(root, filename)
                    rel_path = os.path.relpath(filepath, self.vault_path)
                    files.append(
                        {
                            "path": filepath,
                            "rel_path": rel_path,
                            "filename": filename,
                            "hash": self._get_file_hash(filepath),
                            "category": root.split("/")[-2] if "/" in root else "root",
                            "size": os.path.getsize(filepath),
                        }
                    )
        return files

    def index_obsidian(self, force: bool = False) -> dict[str, Any]:
        """
        Indexa todo el vault de Obsidian en Mem0 + ChromaDB

        Args:
            force: Si True, reindexa todos los archivos aunque no hayan cambiado
        """
        memory = self._init_memory()
        state = self._load_state()
        files = self.scan_vault()

        results: dict[str, Any] = {
            "total": len(files),
            "indexed": 0,
            "skipped": 0,
            "errors": 0,
            "details": [],
        }

        for file_info in files:
            try:
                # Verificar cambios
                rel_path = file_info["rel_path"]
                is_cached = (
                    not force
                    and rel_path in state
                    and state[rel_path]["hash"] == file_info["hash"]
                )
                if is_cached:
                    results["skipped"] += 1
                    results["details"].append(
                        {
                            "file": file_info["rel_path"],
                            "status": "skipped",
                            "reason": "sin cambios",
                        }
                    )
                    continue

                # Leer contenido
                with open(file_info["path"], encoding="utf-8") as f:
                    content = f.read()

                # Indexar en memoria
                memory_id = hashlib.md5(
                    f"{file_info['rel_path']}{datetime.now().isoformat()}".encode()
                ).hexdigest()

                # Extraer título de la primera línea
                title = file_info["filename"].replace(".md", "")
                if content.startswith("# "):
                    title = content.split("\n")[0].replace("# ", "").strip()

                memory.store_memory(
                    content={
                        "file": file_info["rel_path"],
                        "title": title,
                        "content": content[:3000],
                        "category": file_info["category"],
                        "size": file_info["size"],
                    },
                    session_id="obsidian_index",
                    user_id="hermes_agent",
                    memory_type="obsidian_document",
                    importance=7,
                    tags=[
                        "obsidian",
                        file_info["category"],
                        file_info["filename"].replace(".md", ""),
                    ],
                )

                # Actualizar estado
                state[file_info["rel_path"]] = {
                    "hash": file_info["hash"],
                    "last_indexed": datetime.now().isoformat(),
                    "memory_id": memory_id,
                    "title": title,
                }

                results["indexed"] += 1
                results["details"].append(
                    {"file": file_info["rel_path"], "status": "indexed", "title": title}
                )

            except Exception as e:
                results["errors"] += 1
                results["details"].append(
                    {
                        "file": file_info.get("rel_path", "unknown"),
                        "status": "error",
                        "error": str(e),
                    }
                )

        # Guardar estado
        self._save_state(state)

        return results

    def search_obsidian(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Busca en el índice de Obsidian usando Mem0"""
        memory = self._init_memory()
        context = memory.retrieve_context(
            session_id="obsidian_index", query=query, max_results=limit
        )

        results = []
        for item in context.get("user_memory", []):
            if "obsidian" in str(item.get("tags", [])):
                results.append(item)

        # También buscar en ChromaDB
        for item in context.get("past", []):
            if "obsidian" in str(item.get("metadata", {}).get("tags", "")):
                results.append(item)

        return results[:limit]

    def get_stats(self) -> dict[str, Any]:
        """Obtiene estadísticas del vault"""
        files = self.scan_vault()
        state = self._load_state()

        total_size = sum(f["size"] for f in files)
        indexed_count = len(state)

        return {
            "total_files": len(files),
            "indexed_files": indexed_count,
            "pending_files": len(files) - indexed_count,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "categories": list({f["category"] for f in files}),
        }


# ============================================
# COMANDOS PARA EL AGENTE
# ============================================


def index_command() -> dict[str, Any]:
    """Comando: indexar Obsidian"""
    skill = ObsidianSkill()
    print("🧠 Indexando Obsidian...")
    results = skill.index_obsidian()

    print("\n📊 RESULTADO:")
    print(f"   ✅ Indexados: {results['indexed']}")
    print(f"   ⏭️  Sin cambios: {results['skipped']}")
    print(f"   ❌ Errores: {results['errors']}")
    print(f"   📁 Total: {results['total']}")

    return results


def search_command(query: str) -> list[dict[str, Any]]:
    """Comando: buscar en Obsidian"""
    skill = ObsidianSkill()
    results = skill.search_obsidian(query)

    print(f"\n🔍 BÚSQUEDA: '{query}'")
    print(f"   Resultados: {len(results)}")
    for r in results:
        print(f"   - {r.get('content', 'N/A')[:100]}...")

    return results


def stats_command() -> None:
    """Comando: estadísticas de Obsidian"""
    skill = ObsidianSkill()
    stats = skill.get_stats()

    print("\n📊 ESTADÍSTICAS DE OBSIDIAN")
    print(f"   📁 Archivos totales: {stats['total_files']}")
    print(f"   ✅ Indexados: {stats['indexed_files']}")
    print(f"   ⏳ Pendientes: {stats['pending_files']}")
    print(f"   💾 Tamaño total: {stats['total_size_mb']} MB")
    print(f"   📂 Categorías: {', '.join(stats['categories'])}")


if __name__ == "__main__":
    # Punto de entrada para pruebas
    import sys

    if len(sys.argv) > 1:
        if sys.argv[1] == "index":
            index_command()
        elif sys.argv[1] == "stats":
            stats_command()
        elif sys.argv[1] == "search" and len(sys.argv) > 2:
            search_command(" ".join(sys.argv[2:]))
        else:
            print("Uso: python obsidian_indexer.py {index|stats|search 'query'}")
    else:
        stats_command()
