from langchain_core.embeddings import Embeddings
from langchain_core.utils import secret_from_env
from langchain_openai import OpenAIEmbeddings
from pydantic import SecretStr

import config


class LangChainEmbeddingGenerator:
    def __init__(self):
        if not config.OPENAI_API_KEY:
            print("Error: OPENAI_API_KEY is required")
            exit()

        try:
            self.model = OpenAIEmbeddings(
                api_key=SecretStr(config.OPENAI_API_KEY),
                model=config.OPENAI_EMBEDDING_MODEL,
            )
        except Exception as e:
            print(f"Error initializing OpenAIEmbeddings: {e}")
            exit()

    def get_embedding_function(self) -> Embeddings:
        return self.model
