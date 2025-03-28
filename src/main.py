from pymilvus import connections
from neo4j import GraphDatabase

from src import config


def connect_milvus():
    try:
        connections.connect(
            alias=config.MILVUS_ALIAS,
            host=config.MILVUS_HOST,
            port=config.MILVUS_PORT,
        )
        print("milvus connected")
    except Exception as e:
        print("failed to connect to milvus:", e)


def connect_neo4j():
    driver = None
    try:
        if not config.NEO4J_PASSWORD:
            raise ValueError("NEO4J_PASSWORD is required")

        driver = GraphDatabase.driver(
            config.NEO4J_URI,
            auth=(config.NEO4J_USER, config.NEO4J_PASSWORD),
        )
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
