import os
from typing import Any, Dict, List, Optional, Set, Tuple
from tree_sitter import Language, Node, Parser, Query
from tree_sitter_javascript import language
from src.parsing.queries import (
    CALL_QUERY,
    FUNCTION_QUERY,
    REQUIRE_QUERY,
    VARIABLE_QUERY,
)
import src.config as config
import json
from src.parsing.models import (
    CallExpr,
    CodeFile,
    Function,
    Position,
    RequireExpr,
    Variable,
)

JS_BUILTINS = [
    "console",
    "Object",
    "Array",
    "Promise",
    "this",
    "Math",
    "process",
    "Buffer",
]

JS_STD_MODULES = ["fs", "path", "http", "crypto", "os", "util"]

JS_TYPES = [
    "string",
    "number",
    "true",
    "false",
    "null",
    "undefined",
]


class JavaScriptParser:
    def __init__(self):
        """Initialize the parser with the JavaScript grammar"""

        try:
            JS_LANGUAGE = Language(language())
            if not JS_LANGUAGE:
                raise RuntimeError("failed to load language")

            self._language = JS_LANGUAGE
            self._parser = Parser(self._language)
            print(f"JavaScript parser initialized")

            self.func_query: Query = self._language.query(FUNCTION_QUERY)
            self.call_query: Query = self._language.query(CALL_QUERY)
            self.require_query: Query = self._language.query(REQUIRE_QUERY)
            self.variable_query: Query = self._language.query(VARIABLE_QUERY)
            print("Queries compiled")

        except Exception as e:
            print("failed to initialize parser or queries", e)
            raise

    def _create_position(self, node: Node) -> Position:
        return Position(
            start_line=node.start_point[0] + 1,  # omg got off by one
            start_col=node.start_point[1],
            end_line=node.end_point[0] + 1,
            end_col=node.end_point[1],
            start_byte=node.start_byte,
            end_byte=node.end_byte,
        )

    def _get_node_text(self, node: Node) -> str:
        return node.text.decode("utf-8") if node.text else "EMPTY_NODE_TEXT"

    def _extract_calls_from_scope(
        self, scope_node: Node, context_name: Optional[str] = None
    ) -> Tuple[List[CallExpr], List[RequireExpr]]:
        calls = []
        requires = []

        call_captures = self.call_query.captures(scope_node)
        require_captures = self.require_query.captures(scope_node)

        processed_require_assignments = set()

        # process require
        if "require.assignment" in require_captures:
            for node in require_captures["require.assignment"]:
                processed_require_assignments.add(node.id)
                var_node = next(
                    (
                        n
                        for n in node.children_by_field_name("name")
                        if isinstance(n, Node)
                    ),
                    None,
                )
                path_node = next(
                    (
                        n
                        for n in node.children_by_field_name("value")[0]
                        .children_by_field_name("arguments")[0]
                        .children
                        if n.type == "string"
                    ),
                    None,
                )

                if var_node and path_node:
                    var_name = self._get_node_text(var_node)
                    module_name = self._get_node_text(path_node).strip("'\"")
                    pos = self._create_position(path_node)
                    requires.append(
                        RequireExpr(
                            module_name=module_name,
                            variable_name=var_name,
                            position=pos,
                            caller_context=context_name,
                        )
                    )

        if "require.call.expr" in require_captures:
            for node in require_captures["require.call.expr"]:
                if node.id in processed_require_assignments:
                    continue

                if node.parent and node.parent.id in processed_require_assignments:
                    continue

                path_node = next(
                    (
                        n
                        for n in node.children_by_field_name("arguments")[0].children
                        if n.type == "string"
                    ),
                    None,
                )

                if path_node:
                    module_name = self._get_node_text(path_node).strip("'\"")
                    pos = self._create_position(path_node)
                    requires.append(
                        RequireExpr(
                            module_name=module_name,
                            variable_name=None,
                            position=pos,
                            caller_context=context_name,
                        )
                    )

        # process calls
        processed_call_expressions = set()

        if "call.expression" in call_captures:
            for node in call_captures["call.expression"]:
                if node.id in processed_call_expressions:
                    continue

                processed_call_expressions.add(node.id)
                target_name = "UNKNOWN_CALL_TARGET"
                is_member = False

                target_node = None

                if "call.target" in self.call_query.captures(node):
                    target_node = self.call_query.captures(node)["call.target"][0]
                    target_name = self._get_node_text(target_node)
                elif "call.target.member" in self.call_query.captures(node):
                    target_node = self.call_query.captures(node)["call.target.member"][
                        0
                    ]
                    # get full expression
                    expr_node = self.call_query.captures(node)[
                        "call.target.expression"
                    ][0]
                    target_name = self._get_node_text(expr_node)
                    is_member = True

                args = []
                if "call.arguments" in self.call_query.captures(node):
                    args_node = self.call_query.captures(node)["call.arguments"][0]
                    args = [
                        (
                            self._get_node_text(arg_child)[:50] + "..."
                            if len(self._get_node_text(arg_child)) > 50
                            else self._get_node_text(arg_child)
                        )
                        for arg_child in args_node.named_children
                    ]

                if target_name != "UNKNOWN_CALL_TARGET" and (
                    "." not in target_name
                    or target_name.split(".")[0] not in JS_BUILTINS
                ):
                    calls.append(
                        CallExpr(
                            name=target_name,
                            arguments=args,
                            position=self._create_position(node),
                            is_member_access=is_member,
                            caller_context=context_name,
                        )
                    )

        return calls, requires

    def _extract_varibles_from_block(
        self, block_node: Node, parent_type: str
    ) -> List[Variable]:
        """
        Extracts variables from the scope node

        Args:
            scope_node: Node
            parent_type: str "program" or "function_declaration"

        Returns:
            List[Variable]
        """

        if parent_type not in ["program", "function_declaration"]:
            raise ValueError(
                "parent_type should be 'program' or 'function_declaration'"
            )

        variables = []

        var_captures = self.variable_query.captures(block_node)

        processed_var_declarations = set()

        if "variable.declaration" not in var_captures:
            return variables

        for decl_node in var_captures["variable.declaration"]:
            if decl_node.id not in processed_var_declarations:
                processed_var_declarations.add(decl_node.id)

                kind = "var" if decl_node.type == "variable_declaration" else None
                if decl_node.type == "lexical_declaration":
                    kind_node = decl_node.children[0]
                    kind = self._get_node_text(kind_node)

                name = "UNKNOWN"
                value_preview = None

                local_captures = self.variable_query.captures(decl_node)

                if (
                    "variable.name" in local_captures
                    and local_captures["variable.name"]
                ):
                    name = self._get_node_text(local_captures["variable.name"][0])
                if (
                    "variable.value" in local_captures
                    and local_captures["variable.value"]
                ):
                    value_node = local_captures["variable.value"][0]
                    if value_node.type in JS_TYPES:
                        value_preview = self._get_node_text(value_node)
                    elif value_node.type in ["object", "array"]:
                        value_preview = value_node.type
                    else:
                        value_preview = f"<{value_node.type}>"

                if name != "UNKNOWN":
                    variables.append(
                        Variable(
                            name=name,
                            kind=kind,
                            value=value_preview,
                            position=self._create_position(decl_node),
                            scope=("global" if parent_type == "program" else "local"),
                        )
                    )

        return variables

    def _extract_file_data(
        self, root_node: Node, code_text: str, relative_path: str
    ) -> CodeFile:
        """Extracts all structured data from the root node of a file."""

        functions: Dict[str, Function] = {}
        processed_func_block_nodes: Set[Node] = set()

        func_captures = self.func_query.captures(root_node)
        if "function.name" in func_captures:
            for name_node in func_captures["function.name"]:
                func_name = self._get_node_text(name_node)
                definition_node = name_node

                current = name_node.parent
                while current:
                    if current.type in [
                        "function_declaration",
                        "variable_declarator",
                        "expression_statement",
                        "method_definition",
                    ]:
                        if "function.definition" in self.func_query.captures(current):
                            definition_node = current
                            break
                    current = current.parent

                if definition_node == name_node:
                    definition_node = name_node.parent

                if definition_node in processed_func_block_nodes:
                    continue

                if not definition_node:
                    continue

                func_code = self._get_node_text(definition_node)
                # NOTE: for now we don't filter out small functions
                # if len(func_code.strip()) < config.MIN_FUNCTION_LENGTH:
                #     continue

                processed_func_block_nodes.add(definition_node)

                func_type = definition_node.type
                if func_type == "variable_declarator" or (
                    func_type == "expression_statement"
                    and "assignment_expression"
                    in [c.type for c in definition_node.children]
                ):
                    # arrow func
                    value_captures = self.func_query.captures(definition_node)
                    if "function.value" in value_captures:
                        func_type = value_captures["function.value"][0].type

                params = []
                param_nodes = definition_node.child_by_field_name("parameters")
                if param_nodes:
                    param_query = self._language.query("(identifier) param")
                    param_captures = param_query.captures(param_nodes)
                    if "param" in param_captures:
                        params = [
                            self._get_node_text(p) for p in param_captures["param"]
                        ]

                internal_calls, internal_requires = self._extract_calls_from_scope(
                    definition_node, func_name
                )

                variables = self._extract_varibles_from_block(
                    definition_node, parent_type="function_declaration"
                )

                functions[func_name] = Function(
                    name=func_name,
                    function_type=func_type,
                    parameters=params,
                    code_block=func_code,
                    position=self._create_position(definition_node),
                    internal_calls=internal_calls,
                    internal_requires=internal_requires,
                    internal_variables=variables,
                )

        top_level_calls, top_level_requires = self._extract_calls_from_scope(root_node)
        top_level_variables = self._extract_varibles_from_block(
            root_node, parent_type="program"
        )

        file_node_data = CodeFile(
            file_path=relative_path,
            full_code=code_text,
            functions=functions,
            top_level_requires=top_level_requires,
            top_level_calls=top_level_calls,
            top_level_variables=top_level_variables,
        )
        return file_node_data

    def parse_file(self, file_path: str) -> Optional[CodeFile]:
        """
        extract functions definitions, their internal calls, top level require
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                code_text = f.read()
            code_bytes = bytes(code_text, "utf-8")
            tree = self._parser.parse(code_bytes)
            root_node = tree.root_node

            if root_node:
                relative_path = file_path
                file_data = self._extract_file_data(root_node, code_text, relative_path)
                return file_data
            else:
                return None

        except FileNotFoundError:
            print(f"file not found: {file_path}")
            return None
        except Exception as e:
            print(f"failed to parse file: {e}, {file_path}")
            return None

    def parse_codebase(self, codebase_path: str) -> List[CodeFile]:
        all_code_files: List[CodeFile] = []
        file_count = 0
        parsed_count = 0

        if not os.path.isdir(codebase_path):
            print(f"directory not found: {codebase_path}")
            return []

        for root, _, files in os.walk(codebase_path):
            for filename in files:
                if filename.endswith(".js"):
                    file_count += 1
                    file_path = os.path.join(root, filename)
                    relative_path = os.path.relpath(file_path, codebase_path)

                    code_file = self.parse_file(file_path)

                    if code_file is not None:
                        parsed_count += 1
                        code_file.file_path = relative_path
                        all_code_files.append(code_file)

        print(
            f"codebase scan complete. Found {file_count} '.js' files, sucessfully parsed {parsed_count}."
        )

        return all_code_files


if __name__ == "__main__":
    pass
