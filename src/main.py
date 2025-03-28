from pymilvus import connections
from dotenv import load_dotenv
from neo4j import GraphDatabase
import os


load_dotenv()
MILVUS_HOST = os.getenv("MILVUS_HOST", "localhost")
MILVUS_PORT = os.getenv("MILVUS_PORT", 19530)
MILVUS_ALIAS = os.getenv("MILVUS_ALIAS", "default")

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password123")


def connect_milvus():
    try:
        connections.connect(
            alias=MILVUS_ALIAS,
            host=MILVUS_HOST,
            port=MILVUS_PORT,
        )
        print("milvus connected")
    except Exception as e:
        print("failed to connect to milvus:", e)


def connect_neo4j():
    driver = None
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        driver.verify_connectivity()
        print("neo4j connected")
        return driver
    except Exception as e:
        print("failed to connect to neo4j:", e)


def main():
    connect_milvus()
    driver = connect_neo4j()


if __name__ == "__main__":
    main()
