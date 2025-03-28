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

    file_nodes = js_parser.parse_codebase(config.CODEBASE_DIR)
    print(f"Parser returned {len(file_nodes)} FileNode objects.")

    aggregated_snippets = {}
    total_functions = 0
    total_top_requires = 0
    if file_nodes:
        for file_node in file_nodes:
            total_top_requires += len(file_node.top_level_requires)
            for func_name in file_node.functions:
                total_functions += 1
                snippet_id = f"{file_node.file_path}::{func_name}"
                aggregated_snippets[snippet_id] = {
                    "code": file_node.functions[func_name].code_block,
                    "calls": [
                        call.name
                        for call in file_node.functions[func_name].internal_calls
                    ],
                    "file_path": file_node.file_path,
                    "function_name": func_name,
                    "internal_requires": file_node.functions[
                        func_name
                    ].internal_requires,
                    "internal_variables": [
                        n.name
                        for n in file_node.functions[func_name].internal_variables
                    ],
                }
    else:
        print("No file data extracted.")

    json.dump(aggregated_snippets, open("aggregated_snippets.json", "w"))
