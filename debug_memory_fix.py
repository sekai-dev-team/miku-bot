import asyncio
import os
from src.common.memory_service import memory_service
from src.common.config_manager import config_manager

async def debug_memory():
    print("--- Initializing Memory Service ---")
    await memory_service.initialize()
    
    user_id = "1184438613"
    print(f"--- searching for user {user_id} ---")
    
    try:
        memories = await memory_service.get_all(user_id=user_id)
        print(f"Result for {user_id}:")
        print(memories)
        
        if isinstance(memories, dict) and "results" in memories:
            print(f"Count: {len(memories['results'])}")
        elif isinstance(memories, list):
            print(f"Count: {len(memories)}")
            
    except Exception as e:
        print(f"Error: {e}")

    # Inspect Chroma directly
    print("\n--- Inspecting ChromaDB Collections ---")
    try:
        import chromadb
        config = config_manager.get_config("memory")
        db_path = config.get("db_path", "./data/memory_store")
        abs_path = os.path.abspath(db_path)
        print(f"DB Path: {abs_path}")
        
        client = chromadb.PersistentClient(path=abs_path)
        collections = client.list_collections()
        print("Collections found:")
        for c in collections:
            print(f" - {c.name} (count: {c.count()})")
            # Peek into the collection
            if c.count() > 0:
                print(f"   Peek 1 item: {c.peek(limit=1)}")
                
    except Exception as e:
        print(f"Chroma inspection failed: {e}")

if __name__ == "__main__":
    asyncio.run(debug_memory())
