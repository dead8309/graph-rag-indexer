from io import text_encoding
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from pymilvus import MilvusClient, MilvusException, connections, utility
from src import config
from typing import List, Tuple, Dict, Optional
import sys
from langchain_milvus import Milvus


class MilvusStore:
    def __init__(self, embedding_function: Embeddings):
        if not embedding_function:
            print("Embedding function not provided")
            sys.exit(1)

        self.embedding_function = embedding_function
        self.collection_name = config.MILVUS_COLLECTION_NAME
        self.connection_args = {
            "host": config.MILVUS_HOST,
            "port": config.MILVUS_PORT,
        }
        self.vector_store: Optional[Milvus] = None
        self.text_field = config.MILVUS_TEXT_FIELD
        self.vector_field = config.MILVUS_VECTOR_FIELD
        self.id_field = config.MILVUS_ID_FIELD

    def _check_and_drop_collection(self):
        conn_alias = "___temp_setup_alias___"
        try:
            connections.connect(alias=conn_alias, **self.connection_args)

            if utility.has_collection(self.collection_name, using=conn_alias):
                utility.drop_collection(self.collection_name, using=conn_alias)
                print(f"  (Setup) Collection dropped.")
                return True
            else:
                print(f"  (Setup) Collection '{self.collection_name}' does not exist.")
                return False

        except Exception as e:
            raise e
        finally:
            if connections.has_connection(conn_alias):
                connections.disconnect(conn_alias)

    def _initialize_vector_store(self):
        if self.vector_store is None:
            print("initializing vector store")
            if not config.EMBEDDING_DIM:
                raise ValueError(
                    "cannot initialize milvus store without embedding_dimension."
                )

            try:

                index_params = {
                    "metric_type": config.MILVUS_METRIC_TYPE,
                    "index_type": config.MILVUS_INDEX_TYPE,
                    "params": {"nlist": config.MILVUS_NLIST},
                }

                search_params = {"params": {"nprobe": config.MILBUS_NPROBE}}

                self.vector_store = Milvus(
                    embedding_function=self.embedding_function,
                    collection_name=self.collection_name,
                    connection_args=self.connection_args,
                    text_field=self.text_field,
                    vector_field=self.vector_field,
                    auto_id=False,
                    index_params=index_params,
                    search_params=search_params,
                )
                self.vector_store._create_index()

            except Exception as e:
                print(f"unable to initialize vector store with error: {e}")
                self.vector_store = None
                raise

        return self.vector_store

    def add_snippets(self, snippets: Dict[str, str], drop_existing: bool = False):
        if not snippets:
            print("no snippets provided")
            return

        collection_was_dropped = False
        if drop_existing:
            collection_was_dropped = self._check_and_drop_collection()
            if collection_was_dropped:
                self.vector_store = None

        store = self._initialize_vector_store()

        if not store:
            print("failed to initialize vector store")
            return

        print("adding snippets to vector store")
        try:
            ids_to_add: List[str] = []
            texts_to_add: List[str] = []
            metadatas_to_add: List[Dict] = []

            for snippet_id, snippet_text in snippets.items():
                metadata = {self.id_field: snippet_id}
                ids_to_add.append(snippet_id)
                texts_to_add.append(snippet_text)
                metadatas_to_add.append(metadata)

            print(f"adding {len(texts_to_add)} snippets to vector store")
            added_pks = store.add_texts(
                texts=texts_to_add,
                metadatas=metadatas_to_add,
                ids=ids_to_add,
            )

            if hasattr(store.col, "flush"):
                print("flushing vector store")
                store.col.flush() if store.col else None

            print(f"added {len(added_pks)} snippets to vector store")

        except Exception as e:
            print(f"failed to add snippets to vector store: {e}")

    def search_snippets(
        self, query: str, top_k: int = config.VECTOR_SEARCH_TOP_K
    ) -> List[Tuple[str, float]]:
        store = self._initialize_vector_store()

        if not store:
            print("store not initialized")
            return []

        print(f"Searching snippets in vector store with query: {query[:100]}")
        try:
            results_with_scores = store.similarity_search_with_score(query, k=top_k)

            processed_results = []
            for doc, score in results_with_scores:
                snippet_id = doc.metadata.get(self.id_field, "ID_NOT_FOUND_IN_METADATA")
                processed_results.append((snippet_id, score))

            print(f"Search returned {len(processed_results)} results.")
            return processed_results
        except Exception as e:
            print(f"Failed to search snippets in vector store: {e}")
            return []
