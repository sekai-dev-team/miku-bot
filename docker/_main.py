import sys

# Pysqlite3 injection for ChromaDB
# fix: "Unsupported vector store provider: chromadb" caused by old sqlite3 in docker
try:
    __import__('pysqlite3')
    sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
except ImportError:
    pass

import nonebot
import bot  # noqa: F401

app = nonebot.get_asgi()
