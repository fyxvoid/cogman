import logging
from typing import Callable, Dict, Any, List, Optional

log = logging.getLogger("cogman.tools")


class Tool:
    def __init__(
        self,
        name: str,
        func: Callable,
        description: str,
        parameters: Dict[str, Any],
        requires_confirm: bool = False,
    ):
        self.name = name
        self.func = func
        self.description = description
        self.parameters = parameters
        self.requires_confirm = requires_confirm

    def run(self, **kwargs) -> str:
        try:
            result = self.func(**kwargs)
            return str(result)
        except TypeError as e:
            return f"Error: bad arguments for tool '{self.name}': {e}"
        except Exception as e:
            log.exception("Tool '%s' failed", self.name)
            return f"Error running '{self.name}': {e}"

    def to_anthropic_schema(self) -> Dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": self.parameters,
                "required": [k for k, v in self.parameters.items() if v.get("required", False)],
            },
        }


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(
        self,
        name: str,
        func: Callable,
        description: str,
        parameters: Dict[str, Any] = None,
        requires_confirm: bool = False,
    ) -> "ToolRegistry":
        self._tools[name] = Tool(
            name=name,
            func=func,
            description=description,
            parameters=parameters or {},
            requires_confirm=requires_confirm,
        )
        log.debug("Registered tool: %s", name)
        return self

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def run(self, name: str, args: dict) -> str:
        tool = self.get(name)
        if not tool:
            return f"Unknown tool: '{name}'. Available: {self.list_names()}"
        return tool.run(**args)

    def list_names(self) -> List[str]:
        return list(self._tools.keys())

    def all_schemas(self) -> List[Dict]:
        return [t.to_anthropic_schema() for t in self._tools.values()]

    def summary(self) -> str:
        lines = []
        for t in self._tools.values():
            lines.append(f"  • {t.name}: {t.description}")
        return "\n".join(lines)
