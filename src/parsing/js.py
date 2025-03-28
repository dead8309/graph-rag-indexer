import os
from typing import Tuple
from tree_sitter import Language, Node, Parser
from tree_sitter_javascript import language


class JavaScriptParser:
    def __init__(self):
        """Initialize the parser with the JavaScript grammar"""

        try:
            JS_LANGUAGE = Language(language())
            if not JS_LANGUAGE:
                raise Exception("failed to load language")

            self._language = JS_LANGUAGE
            self._parser = Parser(self._language)
            print(f"javascript parser initialized")

        except Exception as e:
            print("failed to initialize parser:", e)
            raise

    def parse_file(self, file_path: str) -> Tuple[Node | None, str | None]:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                code_text = f.read()
            code_bytes = bytes(code_text, "utf-8")
            tree = self._parser.parse(code_bytes)
            return tree.root_node, code_text
        except FileNotFoundError:
            print(f"file not found: {file_path}")
            return None, None
        except Exception as e:
            print(f"failed to parse file: {e}")
            return None, None

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


if __name__ == "__main__":
    pass
