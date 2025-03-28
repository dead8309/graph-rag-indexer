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

    def parse_codebase(self, codebase_path: str):
        parsed_files = {}
        file_count = 0
        parsed_count = 0

        if not os.path.isdir(codebase_path):
            print(f"directory not found: {codebase_path}")
            return {}

        for root, _, files in os.walk(codebase_path):
            for filename in files:
                if filename.endswith(".js"):
                    file_count += 1
                    file_path = os.path.join(root, filename)
                    relative_path = os.path.relpath(file_path, codebase_path)

                    root_node, code_text = self.parse_file(file_path)

                    if root_node and code_text:
                        parsed_count += 1
                        parsed_files[relative_path] = {
                            "root_node": root_node,
                            "code": code_text[:100] + "...",
                        }

        print(f"parsed {parsed_count} out of {file_count} files")
        return parsed_files
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
if __name__ == "__main__":
    pass
