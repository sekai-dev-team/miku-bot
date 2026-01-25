import sys

# 尝试替换 sqlite3，模拟正确环境
try:
    __import__('pysqlite3')
    sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
    print("SUCCESS: pysqlite3 injected.")
except ImportError:
    print("WARNING: pysqlite3 not found.")

# 尝试导入 chromadb
try:
    import chromadb
    print(f"SUCCESS: chromadb imported. Version: {chromadb.__version__}")
except Exception as e:
    print(f"ERROR: chromadb import failed: {e}")

# 尝试初始化 mem0
try:
    from mem0 import Memory
    print("SUCCESS: mem0 imported.")
    
    config = {
        "vector_store": {
            "provider": "chromadb",
            "config": {
                "collection_name": "test_collection",
                "path": "./test_db"
            }
        }
    }
    # 这步可能会报错，因为我们没有提供 LLM config，但我们只想测 vector store 是否被接受
    # 或者我们可以提供一个 dummy config
    print("Attempting to validate config...")
    # 这里不实际运行 Memory.from_config(config) 因为它可能需要真实的 API key
    # 但我们可以看看是否有显式的 provider 检查函数
    
except Exception as e:
    print(f"ERROR: mem0 check failed: {e}")
