from time import time
from typing_extensions import LiteralString
import src.config as config
from neo4j import Driver, GraphDatabase, ManagedTransaction, Query
from typing import List, Optional, cast

from src.parsing.models import CodeFile


L_CODE_FILE = "CodeFile"
L_FUNCTION = "Function"
L_MODULE = "Module"
L_VARIABLE = "Variable"

R_CONTAINS = "CONTAINS"
R_CALLS = "CALLS"
R_REQUIRES = "REQUIRES"
R_DEFINES_VAR = "DEFINES_VAR"
R_USES_VAR = "USES_VAR"


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

    def clear_graph(self):
        if not self.driver:
            print("cannot clear graph without driver")
            return

        confirm = input("delete all data in the graph? (y/n): ")
        if confirm.lower() != "y":
            print("aborting clear graph")
            return

        try:
            with self.driver.session(database=self.database) as session:
                session.run("MATCH (n) DETACH DELETE n")
            print("cleared graph")
        except Exception as e:
            print("failed to clear graph:", e)

    def _build_graph_tx(self, tx: ManagedTransaction, data: List[CodeFile]):
        total_files = len(data)
        processed_files = 0

        merge_file_q = (
            f"MERGE (f:{L_CODE_FILE} {{path: $path}}) SET f.code_summary = $summary"
        )

        merge_top_req_q = f"""
            MATCH (f:{L_CODE_FILE} {{path: $file_path}})
            MATCH (m:{L_MODULE} {{name: $module_name}})
            MATCH (f)-[r:{R_REQUIRES}]->(m)
            SET r.variable_names = $var_name, r.line = $line
        """

        merge_func_q = f"""
            MATCH (f:{L_CODE_FILE} {{ path: $file_path }})
            MERGE (fn:{L_FUNCTION} {{ id: $func_id }})
            SET fn.name = $name, fn.type = $type, fn.signature = $signature,
                fn.code_summary = $code_summary, fn.start_line = $start_line, fn.end_line = $end_line
            MERGE (f)-[:{R_CONTAINS}]->(fn)
        """

        merge_internal_req_q = f"""
            MATCH (fn:{L_FUNCTION} {{ id: $func_id }})
            MERGE (m:{L_MODULE} {{ name: $module_name }})
            MERGE (fn)-[r:{R_REQUIRES}]->(m)
            SET r.variable_name = $var_name, r.line = $line
        """

        for file_data in data:
            tx.run(
                merge_file_q,
                path=file_data.file_path,
                summary=file_data.full_code[:1000] + "...",
            )

            for req in file_data.top_level_requires:
                tx.run(
                    merge_top_req_q,
                    file_path=file_data.file_path,
                    module_name=req.module_name,
                    var_name=req.variable_name,
                    line=req.position.start_line,
                )

            for func_name, func_data in file_data.functions.items():
                func_id = f"{file_data.file_path}::{func_name}"
                tx.run(
                    merge_func_q,
                    file_path=file_data.file_path,
                    func_id=func_id,
                    name=func_name,
                    type=func_data.function_type,
                    signature=f"{func_name}({', '.join(func_data.parameters)})",
                    code_summary=func_data.code_block[:200] + "...",
                    start_line=func_data.position.start_line,
                    end_line=func_data.position.end_line,
                )

                for req in func_data.internal_requires:
                    tx.run(
                        merge_internal_req_q,
                        func_id=func_id,
                        module_name=req.module_name,
                        var_name=req.variable_name,
                        line=req.position.start_line,
                    )

            processed_files += 1
            if processed_files % 10 == 0 or processed_files == total_files:
                print(f"  Processed {processed_files}/{total_files} files.")

        print("  Graph building transaction phase complete.")

        except Exception as e:
