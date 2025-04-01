import os
from time import time
from typing_extensions import LiteralString
from src.parsing.js import JS_BUILTINS, JS_STD_MODULES
import src.config as config
from neo4j import Driver, GraphDatabase, ManagedTransaction, Query
from typing import List, Optional, cast

from src.parsing.models import CodeFile


L_CODE_FILE = "CodeFile"
L_FUNCTION = "Functions"
L_MODULE = "Modules"
L_VARIABLE = "Variables"
L_PARAMETER = "Parameter"

R_CONTAINS = "CONTAINS"
R_CALLS = "CALLS"
R_REQUIRES = "REQUIRES"
R_DEFINES_VAR = "DEFINES_VAR"
R_USES_VAR = "USES_VAR"
R_PARAMETER = "HAS_PARAMETER"
R_DEPENDS_ON = "DEPENDS_ON"


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
            Query(
                f"CREATE CONSTRAINT unique_var_name IF NOT EXISTS FOR (v:{L_VARIABLE}) REQUIRE v.id IS UNIQUE"
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

        merge_file_q = f"""
            MERGE (f:{L_CODE_FILE} {{path: $path}})
            SET f.code_summary = $summary,
                f.file_name = $file_name,
                f.extension = $extension,
                f.last_modified = $last_modified,
                f.loc = $loc,
                f.directory = $directory
        """

        merge_top_req_q = f"""
            MATCH (f:{L_CODE_FILE} {{path: $file_path}})
            MATCH (m:{L_MODULE} {{name: $module_name}})
            MATCH (f)-[r:{R_REQUIRES}]->(m)
            SET r.variable_names = $var_name, r.line = $line
        """

        merge_func_q = f"""
             MATCH (f:{L_CODE_FILE} {{ path: $file_path }})
             MERGE (fn:{L_FUNCTION} {{ id: $func_id }})
             SET fn.name = $name,
                 fn.type = $type,
                 fn.signature = $signature,
                 fn.code_summary = $code_summary,
                 fn.start_line = $start_line,
                 fn.end_line = $end_line,
                 fn.loc = ($end_line - $start_line + 1)
             MERGE (f)-[r:{R_CONTAINS}]->(fn)
             SET r.is_top_level = $is_top_level
        """

        merge_internal_req_q = f"""
            MATCH (fn:{L_FUNCTION} {{ id: $func_id }})
            MERGE (m:{L_MODULE} {{ name: $module_name }})
            MERGE (fn)-[r:{R_REQUIRES}]->(m)
            SET r.variable_name = $var_name, r.line = $line
        """

        merge_internal_call_q = f"""
            MATCH (caller_fn:{L_FUNCTION} {{ id: $caller_func_id }})
            MERGE (callee_fn:{L_FUNCTION} {{ id: $target_func_id_guess }})
            ON CREATE SET callee_fn.name = $target_name
            MERGE (caller_fn)-[r:{R_CALLS}]->(callee_fn)
            SET r.line = $line, r.arguments = $args
        """

        merge_top_call_q = f"""
            MATCH (f:{L_CODE_FILE} {{ path: $file_path }})
            MERGE (callee_fn:{L_FUNCTION} {{ id: $target_func_id_guess }})
            ON CREATE SET callee_fn.name = $target_name
            MERGE (f)-[r:{R_CALLS}]->(callee_fn)
            SET r.line = $line, r.arguments = $args
        """

        for file_data in data:
            path_parts = file_data.file_path.split("/")
            file_name = path_parts[-1] if path_parts else ""
            extension = ""
            if "." in file_name:
                extension_parts = file_name.split(".")
                extension = extension_parts[-1] if extension_parts else ""
            directory = "/".join(path_parts[:-1]) if len(path_parts) > 1 else ""

            tx.run(
                merge_file_q,
                path=file_data.file_path,
                summary=file_data.full_code,
                file_name=file_name,
                extension=extension,
                last_modified=None,
                loc=len(file_data.full_code.splitlines()),
                directory=directory,
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
                    is_top_level=False,
                )

                for req in func_data.internal_requires:
                    tx.run(
                        merge_internal_req_q,
                        func_id=func_id,
                        module_name=req.module_name,
                        var_name=req.variable_name,
                        line=req.position.start_line,
                    )

                for call in func_data.internal_calls:
                    target_func_id_guess = f"{file_data.file_path}::{call.name}"
                    tx.run(
                        merge_internal_call_q,
                        caller_func_id=func_id,
                        target_func_id_guess=target_func_id_guess,
                        target_name=call.name,
                        line=call.position.start_line,
                        args=str(call.arguments[:3]),
                    )

            for call in file_data.top_level_calls:
                target_func_id_guess = f"{file_data.file_path}::{call.name}"
                tx.run(
                    merge_top_call_q,
                    file_path=file_data.file_path,
                    target_func_id_guess=target_func_id_guess,
                    target_name=call.name,
                    line=call.position.start_line,
                    args=str(call.arguments[:3]),
                )

            processed_files += 1
            if processed_files % 10 == 0 or processed_files == total_files:
                print(f"  Processed {processed_files}/{total_files} files.")

        print("  Graph building transaction phase complete.")

    def build_graph_from_files(self, code_files: List[CodeFile]):
        if not self.driver:
            print("cannot build graph without driver")
            return

        start_time = time()
        try:
            with self.driver.session(database=self.database) as session:
                session.execute_write(self._build_graph_tx, code_files)
            end_time = time()
            print("graph build transaction complete")
            print(f"  Time taken: {end_time - start_time:.2f} seconds")
        except Exception as e:
            print("failed to build graph:", e)

    def query_graph_related(
        self,
        start_node_ids: List[str],
        max_depth: int = config.NEO4J_MAX_TRAVERSE_DEPTH,
    ) -> List[str]:
        related_ids = set(start_node_ids)
        if not self.driver:
            print("cannot query graph without driver")
            return list(related_ids)

        if not start_node_ids:
            print("no start node provided")
            return list(related_ids)

        cypher_query_string = f"""
            MATCH (start_fn:{L_FUNCTION}) WHERE start_fn.id IN $start_ids
            CALL {{
                WITH start_fn
                MATCH p=(start_fn)-[:{R_CALLS}*0..{max_depth}]-(related_fn:{L_FUNCTION})
                RETURN related_fn.id AS relatedId
            UNION
                WITH start_fn
                MATCH (f:{L_CODE_FILE})-[:{R_CONTAINS}]->(start_fn)
                MATCH (f)-[:{R_CONTAINS}]->(sibling_fn:{L_FUNCTION})
                RETURN sibling_fn.id AS relatedId
            UNION
                 WITH start_fn
                 MATCH (start_fn)<-[:{R_CONTAINS}]-(f_start:{L_CODE_FILE})
                 MATCH (f_start)-[:{R_REQUIRES}]->(m:{L_MODULE})
                 MATCH (f_other:{L_CODE_FILE})-[:{R_REQUIRES}]->(m)
                 MATCH (f_other)-[:{R_CONTAINS}]->(other_fn:{L_FUNCTION})
                 RETURN other_fn.id as relatedId
            UNION
                 WITH start_fn
                 MATCH (start_fn)-[:{R_REQUIRES}]->(m:{L_MODULE})
                 MATCH (other_node)-[:{R_REQUIRES}]->(m)
                 WHERE other_node:{L_FUNCTION} OR other_node:{L_CODE_FILE}
                 CALL apoc.when(other_node:Function,
                    'RETURN other_node.id AS fnId',
                    'RETURN NULL AS fnId', {{other_node: other_node}}) YIELD value
                 WITH value WHERE value.fnId IS NOT NULL RETURN value.fnId AS relatedId
                 WITH other_node WHERE other_node:CodeFile
                 MATCH (other_node)-[:CONTAINS]->(contained_fn:Function)
                 RETURN contained_fn.id as relatedId
            }}
            RETURN COLLECT(DISTINCT relatedId) AS all_related_ids
        """

        try:
            with self.driver.session(database=self.database) as session:
                query_obj = Query(cast(LiteralString, cypher_query_string))
                result = session.run(query_obj, start_ids=start_node_ids)
                record = result.single()
                if record and record["all_related_ids"]:
                    found_ids = record["all_related_ids"]
                    related_ids.update(found_ids)
                    print(
                        f"  Graph query found {len(found_ids)} potentially related nodes."
                    )
                else:
                    print("  Graph query returned no additional related nodes.")

        except Exception as e:
            if "unknown function 'apoc" in str(e).lower():
                print("apoc library not installed in neo4j, cannot run query")

        return sorted(list(related_ids))
