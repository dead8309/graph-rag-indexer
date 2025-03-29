from time import time
from typing_extensions import LiteralString
import src.config as config
from neo4j import Driver, GraphDatabase, ManagedTransaction, Query
from typing import List, Optional, cast

from src.parsing.models import CodeFile


class Neo4jStore:
    def __init__(self) -> None:
        self.uri = config.NEO4J_URI
        self.user = config.NEO4J_USER
        self.password = config.NEO4J_PASSWORD
        self.database = config.NEO4J_DATABASE
        self.driver: Optional[Driver] = None

        if not self.password:
            print("NEO4J_PASSWORD is required")

    def connect(self):
        if self.driver:
            print("neo4j driver already connected")
            return

        if not self.password:
            print("cannot connect to neo4j without password")
            return

        try:
            self.driver = GraphDatabase.driver(
                self.uri, auth=(self.user, self.password)
            )
            self.driver.verify_connectivity()
            self._create_constraints()

        except Exception as e:
            print("failed to connect to neo4j:", e)
            self.driver = None

    def _create_constraints(self):
        if not self.driver:
            print("cannot create constraints without driver")
            return

        constraints = [
            Query(
                f"CREATE CONSTRAINT unique_codefile_path IF NOT EXISTS FOR (f:{L_CODE_FILE}) REQUIRE f.path IS UNIQUE"
            ),
            Query(
                f"CREATE CONSTRAINT unique_function_id IF NOT EXISTS FOR (fn:{L_FUNCTION}) REQUIRE fn.id IS UNIQUE"
            ),
            Query(
                f"CREATE CONSTRAINT unique_module_name IF NOT EXISTS FOR (m:{L_MODULE}) REQUIRE m.name IS UNIQUE"
            ),
        ]
        try:
            with self.driver.session(database=self.database) as session:
                for query in constraints:
                    try:
                        session.run(query)
                    except Exception as e:
                        if "already exists" not in str(e):
                            print(f"error creating constraint: {query} - {e}")

            print("created constraints")
        except Exception as e:
            print("failed to create constraints:", e)

    def close(self):
        if self.driver:
            self.driver.close()
            self.driver = None
            print("neo4j driver closed")
        else:
            print("neo4j driver already closed")

        except Exception as e:
        except Exception as e:
