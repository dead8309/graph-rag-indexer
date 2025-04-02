# grag-indexer

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Overview

Comparing two approaches for retrieving relevant code snippets from a codebase.

To keep things simple for me to test against oss repositories, I've just added [samples-typescript](https://github.com/keploy/samples-typescript) as a git submodule

1.  **Traditional RAG:** Uses semantic vector search (via OpenAI embeddings stored in Milvus) to find code snippets.
2.  **GraphRAG:** Traditional RAG by leveraging a code knowledge graph. It first performs a vector search to get initial candidate snippets, then traverses a structural code graph (built in Neo4j) to find related snippets (e.g., functions called by candidates, functions in the same file, functions related via shared dependencies).

## Stack

- Python 3.10+
- `uv`
- OpenAI
- LangChain
- tree-sitter: Parser generator tool and Python bindings (`tree-sitter`, `tree-sitter-javascript`)
- Docker & Docker Compose
- Milvus: Open-source vector database
- Neo4j: Graph database

## Workflow

1.  **Parsing:** The `JavaScriptParser` reads `.js` files from the target directory, uses `tree-sitter` to build Abstract Syntax Trees (ASTs), and extracts structured information.
2.  **Store Embeddings:** Take extracted function code snippets, embeds them using OpenAI, and stores the embeddings along with snippet IDs in Milvus.
3.  **Building knowledge Graph:** Take the structured `CodeFile` data and populates a Neo4j database, creating nodes (`CodeFile`, `Function`, `Module`, `Variable`) and relationships (`CONTAINS`, `CALLS`, `REQUIRES`, `DECLARES_VARIABLE`).
4.  **Query & Compare:**
    - **Traditional RAG:** Performs a vector similarity search for the query, returning a ranked list of function snippets (based on semantic meaning).
    - **GraphRAG:**
      - Performs the same vector search as above to get initial candidate function IDs.
      - Performs a graph traversal starting from these IDs, following relationships (`CALLS`, `CONTAINS`, shared `REQUIRES`) to find structurally related function snippets.
      - The results from vector search and graph traversal are combined and deduplicated.
5.  **Output:** A `out.json` file containing the detailed parsed structure is also generated for inspection.

## Setup

**1. Prerequisites:**

- OpenAI API Key
- Python 3.10 or later.
- `uv` (recommended) or `pip` for Python package management.
- Docker and Docker Compose installed and running.

**2. Setup Repository:**

- Clone Repository

```bash
git clone https://github.com/dead8309/graph-rag-indexer
cd grag-indexer
```

- Update Git Submodules:

```bash
git submodule update --init --recursive
```

**3. Install Dependencies:**

```bash
uv sync
```

**4. Configure Environment:**

- Copy the example environment file:

  ```bash
  cp .env.example .env
  ```

- Provide your OpenAI API Key
- Verify the `MILVUS_HOST`, `MILVUS_PORT`
- Verify the `NEO4J_URI`, `NEO4J_USER` match your setup.

**5. Start Databases:**

```bash
docker compose up -d
```

## Run

```bash
uv run python -m src.main
```

## Exploring the Graph

You can visualize the code knowledge graph using the Neo4j Browser:

1. Open `http://localhost:7474` in your web browser.
2. Connect using the URI (`bolt://localhost:7687`), username (`neo4j`), and the password you set in `.env`/`docker-compose.yml`.
3. Run Cypher queries to explore the graph, for example:

## License

[MIT](LICENSE)
