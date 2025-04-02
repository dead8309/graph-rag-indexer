import os
from time import time
from typing_extensions import LiteralString
from src.parsing.js import JS_BUILTINS, JS_STD_MODULES
import src.config as config
from neo4j import Driver, GraphDatabase, ManagedTransaction, Query
from typing import Any, Dict, List, Optional, cast

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
             MERGE (m:{L_MODULE} {{name: $module_name}})
             SET m.is_external = $is_external,
                 m.is_std_module = $is_std_module
             MERGE (f)-[r:{R_REQUIRES}]->(m)
             SET r.variable_name = $var_name,
                 r.line = $line,
                 r.import_type = $import_type,
                 r.is_default_import = $is_default_import,
                 r.alias = $alias
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

        merge_param_q = f"""
            MATCH (fn:{L_FUNCTION} {{ id: $func_id }})
            MERGE (p:{L_PARAMETER} {{ id: $param_id }})
            SET p.name = $param_name,
                p.position = $position,
                p.default_value = $default_value,
                p.is_rest = $is_rest
            MERGE (fn)-[r:{R_PARAMETER}]->(p)
            SET r.index = $index
    """

        merge_internal_req_q = f"""
            MATCH (fn:{L_FUNCTION} {{ id: $func_id }})
            MERGE (m:{L_MODULE} {{ name: $module_name }})
            SET m.is_external = $is_external,
                m.is_std_module = $is_std_module
            MERGE (fn)-[r:{R_REQUIRES}]->(m)
            SET r.variable_name = $var_name,
                r.line = $line,
                r.import_type = $import_type,
        """

        merge_internal_call_q = f"""
            MATCH (caller_fn:{L_FUNCTION} {{ id: $caller_func_id }})
            MERGE (callee_fn:{L_FUNCTION} {{ id: $target_func_id }})
            ON CREATE SET callee_fn.name = $target_name,
                          callee_fn.is_external_reference = $is_external_ref
            MERGE (caller_fn)-[r:{R_CALLS}]->(callee_fn)
            SET r.line = $line,
                r.arguments = $args,
                r.context = $context,
                r.call_count = coalesce(r.call_count, 0) + 1
        """

        merge_top_call_q = f"""
            MATCH (f:{L_CODE_FILE} {{ path: $file_path }})
            MERGE (callee_fn:{L_FUNCTION} {{ id: $target_func_id }})
            ON CREATE SET callee_fn.name = $target_name,
                          callee_fn.is_external_reference = $is_external_ref
            MERGE (f)-[r:{R_CALLS}]->(callee_fn)
            SET r.line = $line,
                r.arguments = $args,
                r.context = 'top-level',
                r.call_count = coalesce(r.call_count, 0) + 1
        """

        merge_variable_q = f"""
            MATCH (container) WHERE elementId(container) = $container_id
            MERGE (v:{L_VARIABLE} {{ id: $var_id }})
            SET v.name = $var_name,
                v.kind = $kind,
                v.value_summary = $value_summary,
                v.start_line = $start_line
            MERGE (container)-[r:{R_DEFINES_VAR}]->(v)
            SET r.scope = $scope
        """

        file_dependencies_q = f"""
            MATCH (f1:{L_CODE_FILE} {{ path: $file_path }})
            MATCH (f2:{L_CODE_FILE} {{ path: $dependency_path }})
            MERGE (f1)-[r:{R_DEPENDS_ON}]->(f2)
            SET r.reason = $reason,
                r.strength = $strength
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
                is_std_module = req.module_name in JS_STD_MODULES
                is_external = not req.module_name.startswith(".") and not is_std_module
                tx.run(
                    merge_top_req_q,
                    file_path=file_data.file_path,
                    module_name=req.module_name,
                    var_name=req.variable_name,
                    line=req.position.start_line,
                    import_type=(
                        "require" if "require" in file_data.full_code else "import"
                    ),
                    is_default_import=req.variable_name is not None,
                    alias=req.variable_name,
                    is_external=is_external,
                    is_std_module=is_std_module,
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

                for idx, param in enumerate(func_data.parameters):
                    param_id = f"{func_id}::param::{param}"
                    param_name = param.lstrip("...")
                    is_rest = param.startswith("...")
                    default_value = None
                    if "=" in param:
                        param_paths = param.split("=")
                        if len(param_paths) > 1:
                            default_value = param_paths[1].strip()
                        param_name = param.split("=")[0].strip().lstrip("...")

                    tx.run(
                        merge_param_q,
                        func_id=func_id,
                        param_id=param_id,
                        param_name=param_name,
                        position=idx,
                        default_value=default_value,
                        is_rest=is_rest,
                        index=idx,
                    )

                for req in func_data.internal_requires:
                    is_std_module = req.module_name in JS_STD_MODULES
                    is_external = (
                        not req.module_name.startswith(".") and not is_std_module
                    )

                    tx.run(
                        merge_internal_req_q,
                        func_id=func_id,
                        module_name=req.module_name,
                        var_name=req.variable_name,
                        line=req.position.start_line,
                        import_type=(
                            "require" if "require" in func_data.code_block else "import"
                        ),
                    )

                for call in func_data.internal_calls:
                    target_in_file = call.name in file_data.functions
                    target_func_id = (
                        f"{file_data.file_path}::{call.name}"
                        if target_in_file
                        else f"external::{call.name}"
                    )

                    tx.run(
                        merge_internal_call_q,
                        caller_func_id=func_id,
                        target_func_id=target_func_id,
                        target_name=call.name,
                        line=call.position.start_line,
                        args=str(call.arguments[:3]),
                        context=func_name,
                        is_external_ref=not target_in_file,
                    )

                for var in func_data.internal_variables:
                    var_id = f"{func_id}::var::{var.name}"
                    function_node_id_tx = tx.run(
                        query=f"MATCH (fn:{L_FUNCTION} {{id: $func_id}}) RETURN elementId(fn) AS node_id",
                        func_id=func_id,
                    ).single()

                    if not function_node_id_tx:
                        continue

                    function_node_id = function_node_id_tx["node_id"]
                    tx.run(
                        merge_variable_q,
                        container_id=function_node_id,
                        var_id=var_id,
                        var_name=var.name,
                        kind=var.kind or "let",
                        value_summary=var.value[:100] if var.value else None,
                        start_line=var.position.start_line,
                        scope="function",
                    )

            for call in file_data.top_level_calls:
                target_in_file = call.name in file_data.functions
                target_func_id = (
                    f"{file_data.file_path}::{call.name}"
                    if target_in_file
                    else f"external::{call.name}"
                )

                tx.run(
                    merge_top_call_q,
                    file_path=file_data.file_path,
                    target_func_id=target_func_id,
                    target_name=call.name,
                    line=call.position.start_line,
                    args=str(call.arguments),
                    is_external_ref=not target_in_file,
                )

            for var in file_data.top_level_variables:
                var_id = f"{file_data.file_path}::var::{var.name}"

                is_exported = False
                if "module.exports = {" in file_data.full_code:
                    export_parts = file_data.full_code.split("module.exports = {")
                    if len(export_parts) > 1:
                        export_content = export_parts[1].split("}")[0]
                        is_exported = var.name in export_content

                file_node_id_tx = tx.run(
                    f"MATCH (f:{L_CODE_FILE} {{path: $file_path}}) RETURN elementId(f) AS node_id",
                    file_path=file_data.file_path,
                ).single()

                if not file_node_id_tx:
                    continue

                tx.run(
                    merge_variable_q,
                    container_id=file_node_id_tx["node_id"],
                    var_id=var_id,
                    var_name=var.name,
                    kind=var.kind or "let",
                    value_summary=var.value[:100] if var.value else None,
                    start_line=var.position.start_line,
                    is_exported=is_exported,
                    scope="global",
                )

            for req in file_data.top_level_requires:
                if req.module_name.startswith("."):
                    dependency_path = self.resolve_local_path(
                        file_data.file_path, req.module_name
                    )
                    if dependency_path:
                        tx.run(
                            file_dependencies_q,
                            file_path=file_data.file_path,
                            dependency_path=dependency_path,
                            reason="import",
                            strength=1.0,
                        )

            processed_files += 1
            if processed_files % 10 == 0 or processed_files == total_files:
                print(f"  Processed {processed_files}/{total_files} files.")

            # helper
            tx.run(
                f"""
            MATCH (f1:{L_CODE_FILE})-[:{R_CONTAINS}]->(fn1:{L_FUNCTION})
            MATCH (fn1)-[c:{R_CALLS}]->(fn2:{L_FUNCTION})<-[:{R_CONTAINS}]-(f2:{L_CODE_FILE})
            WHERE f1 <> f2
            MERGE (f1)-[r:{R_DEPENDS_ON}]->(f2)
            WITH r, count(c) as call_count
            SET r.strength = coalesce(r.strength, 0) + call_count
        """
            )

        print("graph building transaction phase complete.")

    def resolve_local_path(self, base_path: str, relative_path: str):
        base_dir = os.path.dirname(base_path)

        if relative_path.startswith("./") or relative_path.startswith("../"):
            raw_path = os.path.normpath(os.path.join(base_dir, relative_path))
        else:
            return None

        if not os.path.splitext(raw_path)[1]:
            for ext in [".js", ".jsx"]:
                if os.path.exists(raw_path + ext):
                    return raw_path + ext

            for ext in [".js"]:
                index_path = os.path.join(raw_path, f"index{ext}")
                if os.path.exists(index_path):
                    return index_path

        if os.path.exists(raw_path):
            return raw_path

        return None

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
    ) -> List[Dict[str, Any]]:
        related_nodes_data: Dict[str, Dict[str, Any]] = {}

        if not self.driver:
            return list(related_nodes_data.values())

        if not self.driver and start_node_ids:
            print("no start node provided")
            return list(related_nodes_data.values())

        cypher_query_string = f"""
            MATCH (start_fn:{L_FUNCTION}) WHERE start_fn.id IN $start_ids
            CALL {{
                WITH start_fn
                MATCH p=(start_fn)-[:{R_CALLS}*0..{max_depth}]-(related_fn:{L_FUNCTION})
                RETURN related_fn AS related_node
            UNION
                WITH start_fn
                MATCH (f:{L_CODE_FILE})-[:{R_CONTAINS}]->(start_fn)
                MATCH (f)-[:{R_CONTAINS}]->(sibling_fn:{L_FUNCTION})
                RETURN sibling_fn AS related_node
            }}
            WITH COLLECT(DISTINCT related_node) AS distinct_related_nodes
            UNWIND distinct_related_nodes AS related_fn
            MATCH (f_cont:{L_CODE_FILE})-[:{R_CONTAINS}]->(related_fn)
            RETURN
                related_fn.id AS id,
                related_fn.name AS name,
                related_fn.type AS type,
                related_fn.signature AS signature,
                related_fn.code_summary AS code_summary,
                related_fn.start_line AS start_line,
                related_fn.end_line AS end_line,
                related_fn.loc AS loc,
                f_cont.path AS file_path
        """

        processed_count = 0
        try:
            with self.driver.session(database=self.database) as session:
                result = session.run(
                    cast(LiteralString, cypher_query_string), start_ids=start_node_ids
                )
                for record in result:
                    node_id = record.get("id")
                    if node_id and node_id not in related_nodes_data:
                        related_nodes_data[node_id] = {
                            "id": node_id,
                            "name": record.get("name"),
                            "type": record.get("type"),
                            "signature": record.get("signature"),
                            "code_summary": record.get("code_summary"),
                            "start_line": record.get("start_line"),
                            "end_line": record.get("end_line"),
                            "loc": record.get("loc"),
                            "file_path": record.get("file_path"),
                            "source": "graph_traversal",
                        }
                        processed_count += 1

            print(
                f"graph query processed details for {processed_count} unique related function nodes."
            )

        except Exception as e:
            print(f"error during Neo4j graph query for details: {e}")
            if "unknown function 'apoc" in str(e).lower():
                print("query failed likely due to missing APOC plugin in Neo4j.")

        final_results = list(related_nodes_data.values())
        return final_results
