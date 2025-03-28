from tree_sitter import Language, Parser
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

    def parse(self, code: str):
        """Parse the given code"""
        try:
            tree = self._parser.parse(bytes(code, "utf-8"))
            return tree

        except Exception as e:
            print(f"failed to parse code: {e}")


if __name__ == "__main__":
    parser = JavaScriptParser()
    code = """
    const x = 1;
    console.log(x);
    """
    print(parser.parse(code))
