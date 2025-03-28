from pydantic import BaseModel, Field
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

