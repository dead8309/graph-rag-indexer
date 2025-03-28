from pymilvus import connections
from neo4j import GraphDatabase

from src import config
from src.parsing.js import JavaScriptParser
import json


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


if __name__ == "__main__":
    try:
        js_parser = JavaScriptParser()
        print("JavaScript Parser initialized.")
    except Exception as e:
        print(f"Failed to initialize JavaScript Parser: {e}")
        exit()

    code_files = js_parser.parse_codebase(config.CODEBASE_DIR)
    if not code_files:
        print("No files processed.")
        exit()

    output = []
    total_functions = 0
    try:
        for file in code_files:
            file_dict = file.model_dump(mode="json")
            output.append(file_dict)
            total_functions += len(file.functions)

        with open("out.json", "w") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        print(f"Wrote data for {len(output)} files and {total_functions} functions.")
    except Exception as e:
        print(f"Error generating output: {e}")
