from __future__ import annotations
from collections.abc import Iterable
from agent.tools.base import Tool

class ToolRegistry:
    
    def __init__(self, tools: Iterable[Tool]) -> None:
        self._tools: dict[str, Tool] = {}
        for tool in tools:
            self.register(tool)
        
        
    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered.")
        self._tools[tool.name] = tool
        
    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)
    
    def describe(self) -> str:
        """Tool docs for the system prompt."""
        return "\n\n".join(
            f"## {tool.name}\n{tool.description.strip()}" for tool in self._tools.values()
        )