from pydantic import BaseModel, Field
from typing import List, Optional, Dict


class Position(BaseModel):
    """Start and end position of the source"""

    start_line: int
    start_col: int
    end_line: int
    end_col: int
    start_byte: int
    end_byte: int


class CallExpr(BaseModel):
    """Call information"""

    name: str
    arguments: List[str] = Field(default_factory=list)
    position: Position
    is_member_access: bool = False  # foo.bar()
    caller_context: Optional[str] = None  # where this was called from


class RequireExpr(BaseModel):
    """imports/require information"""

    module_name: str
    variable_name: Optional[str] = None  # const fs = require('fs') -> 'fs'
    position: Position
    # TODO: i'll have to rethink about this, requires can be also called inside functions (lazy loading)
    # where this was called from
    caller_context: Optional[str] = None


class Variable(BaseModel):
    """Variable information"""

    name: str
    kind: Optional[str]  # const, let, var
    value: Optional[str] = None
    position: Position
    scope: Optional[str] = None  # global, function local


class Function(BaseModel):
    """Function information"""

    name: str
    function_type: str  # function, arrow_function, method
    parameters: List[str] = Field(default_factory=list)
    code_block: str
    position: Position
    internal_calls: List[CallExpr] = Field(default_factory=list)
    internal_requires: List[RequireExpr] = Field(default_factory=list)
    internal_variables: List[Variable] = Field(default_factory=list)


class CodeFile(BaseModel):
    """Code file information"""

    file_path: str
    full_code: str
    functions: Dict[str, Function] = Field(default_factory=dict)
    top_level_requires: List[RequireExpr] = Field(default_factory=list)
    top_level_calls: List[CallExpr] = Field(default_factory=list)
    top_level_variables: List[Variable] = Field(default_factory=list)
