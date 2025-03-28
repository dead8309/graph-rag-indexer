FUNCTION_QUERY = """
    [
      (function_declaration name: (identifier) @function.name) @function.definition
      (variable_declarator
        name: (identifier) @function.name
        value: [ (function_expression) (arrow_function) ] @function.value
      ) @function.definition
      (expression_statement
        (assignment_expression
          left: (member_expression property: (property_identifier) @function.name)
          right: [ (function_expression) (arrow_function) ] @function.value
        )
      ) @function.definition
      (method_definition name: (property_identifier) @function.name) @function.definition
    ]
"""


CALL_QUERY = """
(call_expression
      function: [
        (identifier) @call.target
        (member_expression property: (property_identifier) @call.target.member) @call.target.expression
        (super) @call.target ; super()
      ]
      arguments: (arguments) @call.arguments
    ) @call.expression
"""

REQUIRE_QUERY = """
    [
     (call_expression
       function: (identifier) @require_func (#eq? @require_func "require")
       arguments: (arguments (string) @require.path.string)
     ) @require.call_expr

     (variable_declarator
       name: (identifier) @require.variable
       value: (call_expression
         function: (identifier) @require_func (#eq? @require_func "require")
         arguments: (arguments (string) @require.path.string)
       )
     ) @require.assignment
    ]
"""

VARIABLE_QUERY = """
(lexical_declaration
      kind: @variable.kind ;; const, let
      (variable_declarator
         name: (identifier) @variable.name
         value: (_)? @variable.value
      )
    ) @variable.declaration

    (variable_declaration
       kind: @variable.kind ;; var
      (variable_declarator
         name: (identifier) @variable.name
         value: (_)? @variable.value
      )
    ) @variable.declaration
"""
