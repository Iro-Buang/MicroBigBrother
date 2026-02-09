from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    args_schema: Dict[str, str]
    visible: Callable[[Any], bool]  # ctx -> bool
    choices: Optional[Callable[[Any], Dict[str, list[str]]]] = None


