import os
from typing import Any, Dict, Set, Tuple
from tree_sitter import Language, Node, Parser, Query
from tree_sitter_javascript import language
import src.config as config
import json

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

            self._compile_queries()
            print("Queries compiled")

        except Exception as e:
            print("failed to initialize parser or queries", e)
            raise

    def parse_file(
        self, file_path: str
    ) -> Tuple[Dict[str, Dict[str, Any]], list[str], list[str], str | None]:
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
                function_data, top_requires, top_calls = self._extract_data_from_node(
                    root_node, code_text
                )
                return function_data, top_requires, top_calls, code_text
            else:
                return {}, [], [], code_text

        except FileNotFoundError:
            print(f"file not found: {file_path}")
            return {}, [], [], None
        except Exception as e:
            print(f"failed to parse file: {e}")
            return {}, [], [], None

    def parse_codebase(self, codebase_path: str) -> Dict[str, Dict[str, Any]]:
        aggregated_snippets: Dict[str, Dict[str, Any]] = {}
        all_top_level_requires: Dict[str, list[str]] = {}
        file_count = 0
        parsed_count = 0
        function_count = 0

        if not os.path.isdir(codebase_path):
            print(f"directory not found: {codebase_path}")
            return {}

        for root, _, files in os.walk(codebase_path):
            for filename in files:
                if filename.endswith(".js"):
                    file_count += 1
                    file_path = os.path.join(root, filename)
                    relative_path = os.path.relpath(file_path, codebase_path)

                    file_functions_data, top_requires, top_calls, _ = self.parse_file(
                        file_path
                    )

                    if file_functions_data is not None:
                        parsed_count += 1
                        for func_name, func_data in file_functions_data.items():
                            snippet_id = f"{relative_path}::{func_name}"
                            aggregated_snippets[snippet_id] = func_data
                            function_count += 1

                    if top_requires:
                        all_top_level_requires[relative_path] = top_requires

        print(
            f"codebase scan complete. Found {file_count} '.js' files, sucessfully parsed {parsed_count}."
        )
        print(f"Extracted {function_count} function snippets meeting criteria.")

        if all_top_level_requires:
            print("\nTop level requires:")
            for file, requires in all_top_level_requires.items():
                print(f"File: {file} -> Requires: {requires}")
        else:
            print("No top level requires found.")

        return aggregated_snippets

    def _compile_queries(self):
        _func_query = """
        [
          (function_declaration name: (identifier) @func.name)
          (variable_declarator
            name: (identifier) @func.name
            value: [ (function_expression) (arrow_function) ]
          )
          (expression_statement
            (assignment_expression
              left: (member_expression property: (property_identifier) @func.name)
              right: [ (function_expression) (arrow_function) ]
            )
          )
          (method_definition name: (property_identifier) @func.name)
        ] @function
        """

        self._func_query: Query = self._language.query(_func_query)

        _call_query = """
        (call_expression
          function: [
            (identifier) @call.name
            (member_expression property: (property_identifier) @call.name)
          ]
        )
        """
        self.call_query: Query = self._language.query(_call_query)

        _require_query = """
        (call_expression
           function: (identifier) @require_func
           arguments: (arguments (string (string_fragment) @require_path))
           (#eq? @require_func "require")
        )
        """
        self.require_query: Query = self._language.query(_require_query)

    def _extract_data_from_node(
        self, root_node: Node, code_text: str
    ) -> Tuple[Dict[str, Dict[str, Any]], list[str], list[str]]:
        """
        Extract function definitions, their internal calls, top level require,
        and top level calls from ast

        Returns:
            A tuple containing:
            - function_data: Dict[func_name, {code: str, calls: List[str]}]
            - top_level_requires: List[str]
            - top_level_calls: List[str]
        """
        functions_data: Dict[str, Dict[str, Any]] = {}
        processed_functions: Set[Node] = set()
        top_level_requires: Set[str] = set()
        top_level_calls: Set[str] = set()

        all_function_captures = self._func_query.captures(root_node)
        print(f"all_function_captures: {all_function_captures}")
        if "func.name" in all_function_captures:
            func_name_nodes = all_function_captures["func.name"]

            for node in func_name_nodes:
                func_name = node.text.decode("utf-8")
                func_block_node = node.parent
                if (
                    node.parent.type == "member_expression"
                    and node.parent.parent.type == "assignment_expression"
                ):
                    # upto expression statement
                    func_block_node = node.parent.parent.parent

                # skip already processed functions
                if not func_block_node or func_block_node in processed_functions:
                    continue

                func_code = func_block_node.text.decode("utf-8")

                # skip short functions
                # TODO: recheck this condition, we might also need small functions for indexing purposes
                # they could help in rag maybe
                if len(func_code.strip()) < config.MIN_FUNCTION_LENGTH:
                    continue
                processed_functions.add(func_block_node)

                internal_calls = []
                call_captures_in_block = self.call_query.captures(func_block_node)
                # NOTE: maybe dynamic imports?, will have to check later
                require_captures_in_block = self.require_query.captures(func_block_node)

                if "call.name" in call_captures_in_block:
                    for call_node in call_captures_in_block["call.name"]:
                        call_target = call_node.text.decode("utf-8")
                        if (
                            "." not in call_target
                            or call_target.split(".")[0] not in JS_BUILTINS
                        ):
                            internal_calls.append(call_target)

                if "require_path" in require_captures_in_block:
                    for req_node in require_captures_in_block["require_path"]:
                        require_module = req_node.text.decode("utf-8").strip("'\"")
                        internal_calls.append(f"require:{require_module}")

                functions_data[func_name] = {
                    "code": func_code,
                    "calls": sorted(list(internal_calls)),
                }

        top_require_captures = self.require_query.captures(root_node)
        if "require_path" in top_require_captures:
            for req_node in top_require_captures["require_path"]:
                parent = req_node.parent
                is_already_processed = False
                while parent:
                    if parent in processed_functions:
                        is_already_processed = True
                        break
                    parent = parent.parent
                if not is_already_processed:
                    top_level_requires.add(req_node.text.decode("utf-8").strip("'\""))

        top_call_captures = self.call_query.captures(root_node)
        if "call.name" in top_call_captures:
            for call_node in top_call_captures["call.name"]:
                parent = call_node.parent
                is_already_processed = False
                while parent:
                    if parent in processed_functions:
                        is_already_processed = True
                        break
                    parent = parent.parent

                if not is_already_processed:
                    call_target = call_node.text.decode("utf-8")
                    if (
                        "." not in call_target
                        or call_target.split(".")[0] not in JS_BUILTINS
                    ):
                        top_level_calls.add(call_target)

        return (
            functions_data,
            sorted(list(top_level_requires)),
            sorted(list(top_level_calls)),
        )


if __name__ == "__main__":
    pass
