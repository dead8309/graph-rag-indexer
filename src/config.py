import os
from dotenv import load_dotenv

load_dotenv()

# Milvus Config
MILVUS_HOST = os.getenv("MILVUS_HOST", "localhost")
MILVUS_PORT = os.getenv("MILVUS_PORT", 19530)
MILVUS_ALIAS = os.getenv("MILVUS_ALIAS", "default")
MILVUS_COLLECTION_NAME = os.getenv("MILVUS_COLLECTION_NAME", "indexer")
MILVUS_TEXT_FIELD = os.getenv("MILVUS_TEXT_FIELD", "text")
MILVUS_VECTOR_FIELD = os.getenv("MILVUS_VECTOR_FIELD", "vector")
MILVUS_ID_FIELD = os.getenv("MILVUS_ID_FIELD", "id")

MILVUS_METRIC_TYPE = "COSINE"
MILVUS_INDEX_TYPE = "IVF_FLAT"
MILVUS_NLIST = 16384
MILBUS_NPROBE = 16


VECTOR_SEARCH_TOP_K = 3

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

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

EMBEDDING_DIM = os.getenv("EMBEDDING_DIM", 1536)


print("Config loaded")
