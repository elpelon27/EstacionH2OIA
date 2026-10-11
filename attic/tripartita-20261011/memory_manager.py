"""
🧠 HERMES MEMORY MANAGER - Memoria Tripartita Unificada
Integra: Mem0 (capa de usuario) + Tencent (memoria estructurada) + ChromaDB (vectorial)
"""

import os
import json
import hashlib
from datetime import datetime
from typing import Dict, List, Optional, Any
import redis
import chromadb
from chromadb.config import Settings
import yaml
import psycopg2
from psycopg2.extras import Json


class HermesMemoryManager:
    """Gestor unificado de memoria tripartita para HERMES AGENT"""
    
    def __init__(self, deepseek_api_key: Optional[str] = None):
        # Cargar API key de DeepSeek
        self.deepseek_api_key = deepseek_api_key or os.getenv("DEEPSEEK_API_KEY")
        if not self.deepseek_api_key:
            print("⚠️ DEEPSEEK_API_KEY no configurada. Mem0 usará modo fallback.")
        
        # 1. CONEXIONES A SERVICIOS
        self.redis_client = redis.Redis(
            host='localhost',
            port=6379,
            password='hermes_redis_dev_change_me',
            decode_responses=True
        )
        
        self.pg_conn = psycopg2.connect(
            dbname='hermes_memory',
            user='hermes',
            password='hermes123',
            host='localhost'
        )
        
        # 2. INICIALIZAR CHROMADB (memoria vectorial)
        self.chroma_client = chromadb.PersistentClient(
            path=os.path.expanduser("~/hermes-unified/chroma_db")
        )
        
        # Crear colección si no existe
        collections = self.chroma_client.list_collections()
        if "hermes_memory" not in [c.name for c in collections]:
            self.chroma_client.create_collection(
                name="hermes_memory",
                metadata={"hnsw:space": "cosine"}
            )
        self.chroma_collection = self.chroma_client.get_collection("hermes_memory")
        
        # 3. INICIALIZAR MEM0 (memoria de usuario) con configuración personalizada
        try:
            import mem0
            from mem0 import Memory
            
            # Configurar para usar DeepSeek
            config = {
                "memory": {
                    "embedding_model": "openai",
                    "embedding_dim": 1536,
                    "llm": {
                        "provider": "openai",
                        "config": {
                            "model": "deepseek-v4-flash-0731",
                            "api_key": self.deepseek_api_key or "dummy-key",
                            "api_base": "https://api.deepseek.com/v1"
                        }
                    },
                    "vector_store": {
                        "provider": "chroma",
                        "config": {
                            "collection_name": "mem0_hermes",
                            "path": os.path.expanduser("~/hermes-unified/chroma_db")
                        }
                    }
                }
            }
            
            self.mem0_client = Memory.from_config(config)
            print("✅ Mem0 configurado con DeepSeek")
        except Exception as e:
            print(f"⚠️ Mem0 falló al iniciar: {e}")
            print("   Usando modo sin Mem0 (los otros sistemas siguen activos)")
            self.mem0_client = None
        
        # 4. INICIALIZAR TABLA SQL si no existe
        self._init_sql_tables()
        
        print("✅ HermesMemoryManager inicializado correctamente")
        print(f"   - Redis: OK")
        print(f"   - PostgreSQL: OK")
        print(f"   - ChromaDB: OK (colección: hermes_memory)")
        print(f"   - Mem0: {'OK' if self.mem0_client else '❌ (fallback)'}")
    
    def _init_sql_tables(self):
        """Crear tabla de metadatos en PostgreSQL si no existe"""
        cur = self.pg_conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS memory_events (
                id SERIAL PRIMARY KEY,
                session_id VARCHAR(255) NOT NULL,
                user_id VARCHAR(255) NOT NULL,
                event_type VARCHAR(50),
                content JSONB,
                embedding JSONB,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                importance_score INTEGER DEFAULT 1,
                context_tags TEXT[]
            );
            CREATE INDEX IF NOT EXISTS idx_session_id ON memory_events(session_id);
            CREATE INDEX IF NOT EXISTS idx_user_id ON memory_events(user_id);
        """)
        self.pg_conn.commit()
        cur.close()
    
    def store_memory(self, 
                     content: Dict,
                     session_id: str,
                     user_id: str,
                     memory_type: str = "conversation",
                     importance: int = 1,
                     tags: List[str] = None) -> str:
        """
        Almacena memoria en TODOS los sistemas simultáneamente
        """
        memory_id = hashlib.md5(
            f"{session_id}{json.dumps(content)}{datetime.now().isoformat()}".encode()
        ).hexdigest()
        
        text_content = json.dumps(content)
        
        # 1. MEM0 (memoria de usuario)
        if self.mem0_client:
            try:
                self.mem0_client.add(
                    text_content,
                    user_id=user_id,
                    metadata={"session_id": session_id, "type": memory_type}
                )
            except Exception as e:
                print(f"⚠️ Mem0 warning: {e}")
        
        # 2. POSTGRESQL (metadatos estructurados)
        cur = self.pg_conn.cursor()
        cur.execute("""
            INSERT INTO memory_events 
            (session_id, user_id, event_type, content, importance_score, context_tags)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id;
        """, (
            session_id,
            user_id,
            memory_type,
            Json(content),
            importance,
            tags or []
        ))
        event_id = cur.fetchone()[0]
        self.pg_conn.commit()
        cur.close()
        
        # 3. CHROMADB (embeddings vectoriales)
        try:
            import chromadb.utils.embedding_functions as ef
            embedding_fn = ef.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
            embedding = embedding_fn([text_content])[0]
            
            self.chroma_collection.add(
                ids=[memory_id],
                embeddings=[embedding],
                metadatas=[{
                    "session_id": session_id,
                    "user_id": user_id,
                    "type": memory_type,
                    "timestamp": datetime.now().isoformat(),
                    "importance": importance
                }],
                documents=[text_content]
            )
        except Exception as e:
            print(f"⚠️ ChromaDB warning: {e}")
        
        # 4. REDIS (memoria de trabajo - último contexto)
        self.redis_client.rpush(
            f"session:{session_id}:context",
            json.dumps({
                "id": memory_id,
                "content": content,
                "timestamp": datetime.now().isoformat()
            })
        )
        self.redis_client.ltrim(f"session:{session_id}:context", -50, -1)
        
        print(f"✅ Memoria almacenada: {memory_id[:8]}...")
        return memory_id
    
    def retrieve_context(self, 
                         session_id: str,
                         query: str,
                         max_results: int = 5) -> Dict:
        """
        Recupera contexto de TODOS los sistemas combinados
        """
        result = {
            "present": [],
            "past": [],
            "structured": [],
            "user_memory": []
        }
        
        # 1. REDIS - Memoria de trabajo (PRESENTE)
        context_raw = self.redis_client.lrange(f"session:{session_id}:context", -10, -1)
        for item in context_raw:
            try:
                result["present"].append(json.loads(item))
            except:
                pass
        
        # 2. CHROMADB - Búsqueda semántica (PASADO)
        try:
            import chromadb.utils.embedding_functions as ef
            embedding_fn = ef.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
            query_embedding = embedding_fn([query])[0]
            
            results = self.chroma_collection.query(
                query_embeddings=[query_embedding],
                n_results=max_results,
                where={"session_id": session_id}
            )
            
            if results['documents']:
                for idx, doc in enumerate(results['documents'][0]):
                    result["past"].append({
                        "content": json.loads(doc) if doc else {},
                        "metadata": results['metadatas'][0][idx] if results['metadatas'] else {},
                        "relevance": results['distances'][0][idx] if results['distances'] else 0
                    })
        except Exception as e:
            print(f"⚠️ ChromaDB retrieve warning: {e}")
        
        # 3. POSTGRESQL - Búsqueda estructurada
        cur = self.pg_conn.cursor()
        cur.execute("""
            SELECT content, timestamp, event_type, importance_score
            FROM memory_events
            WHERE session_id = %s
            ORDER BY timestamp DESC
            LIMIT %s;
        """, (session_id, max_results))
        
        for row in cur.fetchall():
            result["structured"].append({
                "content": row[0],
                "timestamp": row[1].isoformat() if row[1] else None,
                "type": row[2],
                "importance": row[3]
            })
        cur.close()
        
        # 4. MEM0 - Memoria de usuario
        if self.mem0_client:
            try:
                mem0_results = self.mem0_client.search(query, user_id=session_id)
                for item in mem0_results[:max_results]:
                    result["user_memory"].append({
                        "content": item.get("memory"),
                        "relevance": item.get("score", 0)
                    })
            except Exception as e:
                print(f"⚠️ Mem0 retrieve warning: {e}")
        
        return result
    
    def get_session_state(self, session_id: str) -> Dict:
        """Obtiene el estado actual de una sesión"""
        state = self.redis_client.get(f"session:{session_id}:state")
        if state:
            return json.loads(state)
        return {
            "current_task": None,
            "interaction_count": 0,
            "last_activity": None
        }
    
    def update_session_state(self, session_id: str, state_update: Dict):
        """Actualiza el estado de una sesión"""
        current = self.get_session_state(session_id)
        current.update(state_update)
        current["last_activity"] = datetime.now().isoformat()
        self.redis_client.set(
            f"session:{session_id}:state",
            json.dumps(current),
            ex=86400
        )
    
    def close(self):
        """Cierra todas las conexiones"""
        self.pg_conn.close()
        self.redis_client.close()


# ============================================
# PRUEBA RÁPIDA
# ============================================
if __name__ == "__main__":
    print("🧪 Probando HermesMemoryManager...")
    
    # Cargar API key de DeepSeek desde entorno o archivo
    import os
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        # Intentar cargar desde archivo de configuración
        try:
            with open(os.path.expanduser("~/hermes-unified/.env"), "r") as f:
                for line in f:
                    if line.startswith("DEEPSEEK_API_KEY="):
                        api_key = line.split("=", 1)[1].strip()
                        break
        except:
            pass
        
        if not api_key:
            print("⚠️ DEEPSEEK_API_KEY no encontrada. Mem0 no funcionará correctamente.")
            print("   Puedes configurarla con: export DEEPSEEK_API_KEY='tu-key'")
    
    memory = HermesMemoryManager(deepseek_api_key=api_key)
    
    # Probar almacenamiento
    memory.store_memory(
        content={"message": "Hola, soy un usuario de prueba", "type": "greeting"},
        session_id="test_session_001",
        user_id="test_user",
        memory_type="conversation",
        importance=5,
        tags=["test", "greeting"]
    )
    
    # Probar recuperación
    context = memory.retrieve_context(
        session_id="test_session_001",
        query="Hola",
        max_results=3
    )
    
    print("\n📊 CONTEXTO RECUPERADO:")
    print(f"   - Presente (Redis): {len(context['present'])} items")
    print(f"   - Pasado (ChromaDB): {len(context['past'])} items")
    print(f"   - Estructurado (SQL): {len(context['structured'])} items")
    print(f"   - Memoria usuario (Mem0): {len(context['user_memory'])} items")
    
    memory.close()
    print("\n✅ Prueba completada")
