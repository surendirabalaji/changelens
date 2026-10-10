from dataclasses import dataclass

from langchain_core.tools import BaseTool

@dataclass(frozen=True)
class TurnContext:
    tools: list[BaseTool]
    started_at: float
    sources: tuple[str,...]=()
    unavailable: tuple[str,...]=()    
