import os
from dotenv import load_dotenv

load_dotenv()

# Milvus Config
MILVUS_HOST = os.getenv("MILVUS_HOST", "localhost")
MILVUS_PORT = os.getenv("MILVUS_PORT", 19530)
MILVUS_ALIAS = os.getenv("MILVUS_ALIAS", "default")

# Neo4j Config
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

# PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# codebase for indexing
CODEBASE_DIR = os.path.join("samples-typescript", "express-mongodb")

MIN_FUNCTION_LENGTH = 25

if not NEO4J_PASSWORD:
    raise ValueError("NEO4J_PASSWORD is required")

print("Config loaded")
