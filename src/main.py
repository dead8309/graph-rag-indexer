from typing import Any, Dict, List, Optional, Tuple
from langchain_openai import OpenAIEmbeddings
from pydantic import SecretStr

from src import config
from src.parsing.js import JavaScriptParser
from src.parsing.models import CodeFile
from src.store.milvus import MilvusStore
from src.store.neo4j import Neo4jStore

import json

from dotenv import load_dotenv


load_dotenv()

parser = None
embedder = None
vector_store = None
graph_store = None


try:
    if not config.OPENAI_API_KEY:
        print("Error: OPENAI_API_KEY is required")
        exit()

    embedder = OpenAIEmbeddings(
        api_key=SecretStr(config.OPENAI_API_KEY),
        model=config.OPENAI_EMBEDDING_MODEL,
    )
    print("Embedding Generator initialized.")

    parser = JavaScriptParser()
    print("JavaScript Parser initialized.")

    vector_store = MilvusStore(embedding_function=embedder)
    print("Vector Store Initialized (will connect on first use).")

    graph_store = Neo4jStore()
    graph_store.connect()
    if graph_store.driver:
        print("Neo4j Graph Store Connected.")
    else:
        print("Neo4j Graph Store Connection Failed.")
except Exception as e:
    print(f"failed to initialize: {e}")


def parse_codebase(path: str = config.CODEBASE_DIR) -> Optional[List[CodeFile]]:
    if not parser:
        print("parser not initialized.")
        return None

    try:
        print("parsing codebase ...")
        code_files = parser.parse_codebase(path)
        print(f"parser returned data for {len(code_files)} files.")
        if not code_files:
            print("no files parsed or no data extracted.")
            return None
        return code_files
    except Exception as e:
        print(f"error during codebase parsing: {e}")
        return None


def populate_vector_store(code_files: List[CodeFile]):
    if not vector_store:
        print("vector store not initialized, skipping population.")
        return

    if not code_files:
        print("no code files data to populate vector store.")
        return

    print("adding function snippets to vector store ...")
    function_snippets: Dict[str, str] = {}
    for file_node in code_files:
        for func_name, func_info in file_node.functions.items():
            snippet_id = f"{file_node.file_path}::{func_name}"
            function_snippets[snippet_id] = func_info.code_block

    if not function_snippets:
        print("no function snippets found to add.")
    else:
        print(f"prepared {len(function_snippets)} function snippets.")
        try:
            vector_store.add_snippets(snippets=function_snippets, drop_existing=True)
        except Exception as e:
            print(f"error adding snippets to vector store: {e}")


def perform_vector_search(query: str) -> List[str]:
    rag_ids = []
    if not vector_store:
        print("vector store not initialized, skipping search.")
        return rag_ids

    print(f"\n--- Performing Vector Search ---")
    print(f" Query: '{query}'")
    try:
        rag_results = vector_store.search_snippets(query=query)
        if rag_results:
            print(f"\n  Top Vector Search Results:")
            for snippet_id, score in rag_results:
                if snippet_id != "ID_NOT_FOUND_IN_METADATA":
                    print(f"- id: {snippet_id} (score: {score:.4f})")
                    rag_ids.append(snippet_id)
                else:
                    print(f"- warning: found result with missing ID metadata.")
            if not rag_ids:
                print("no valid results found.")
        else:
            print("no vector search results found.")
        return rag_ids
    except Exception as e:
        print(f"error during vector search: {e}")
        return []


def build_knowledge_graph(code_files: List[CodeFile], clear_existing: bool = False):
    if not graph_store:
        print("graph store not initialized, skipping graph build.")
        return

    if not code_files:
        print("no code files data to build graph.")
        return

    if clear_existing:
        graph_store.clear_graph()

    graph_store.build_graph_from_files(code_files)


def perform_graph_rag_query(
    rag_ids: List[str],
) -> Tuple[List[str], List[Dict[str, Any]]]:

    graph_traversal_res: List[Dict[str, Any]] = []
    print(f"\n--- Performing Graph Retrieval ---")
    if rag_ids and graph_store:
        graph_traversal_res = graph_store.query_graph_related(rag_ids)
        print(f"found {len(graph_traversal_res)} related nodes in graph.")
    elif not rag_ids:
        print("no RAG IDs found to query graph.")
    else:
        print("graph store not initialized, skipping query.")
        return rag_ids, []

    combined_data_dict: Dict[str, Dict[str, Any]] = {}
    for res in graph_traversal_res:
        node_id = res["id"]
        if node_id in combined_data_dict:
            combined_data_dict[node_id].update(res)
            combined_data_dict[node_id]["source"] = "vector_search + graph_traversal"
        else:
            combined_data_dict[node_id] = res

    combined_results_list = sorted(
        list(combined_data_dict.values()),
        key=lambda x: (x.get("file_path", ""), x.get("start_line", 0)),
    )
    return rag_ids, combined_results_list


def main():
    if not vector_store:
        print("vector Store not initialized.")
        exit()

    code_files = parse_codebase(config.CODEBASE_DIR)

    if not code_files:
        print("no files processed.")
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

        print(f"wrote data for {len(output)} files and {total_functions} functions.")
    except Exception as e:
        print(f"error generating output: {e}")

    # already populated
    # populate_vector_store(code_files)

    build_knowledge_graph(code_files, clear_existing=True)

    search_query = "create a new product"
    rag_ids = perform_vector_search(search_query)
    if rag_ids:
        print(f"\n  RAG IDs found: {rag_ids}")
    else:
        print("no RAG IDs found.")

    _, graphrag_res = perform_graph_rag_query(rag_ids)
    if not graphrag_res:
        print("no combined results found.")

    for i, res in enumerate(graphrag_res):
        print(f"ID : {res.get('id')}")
        print(f"Name: {res.get('name', 'N/A')}")
        print(f"Type: {res.get('type')}")
        print(f"Function Signature: {res.get('signature')}")
        print(f"Start Line: {res.get('start_line', 'N/A')}")
        print(f"End Line: {res.get('end_line', 'N/A')}")
        print(f"LOC: {res.get('loc', 'N/A')}")
        print(f"File: {res.get('file_path', 'N/A')}:{res.get('start_line', 'N/A')}")
        print(f"Code: {res.get('code_summary')}")
        print("-" * 80)


if __name__ == "__main__":
    main()
