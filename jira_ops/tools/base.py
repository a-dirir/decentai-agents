from ai_runtime.agents_layer.sdk import ToolBase

from .client import JiraClient


class JiraToolBase(ToolBase):
    async def client(self, call):
        try:
            connection = await call.resources.use_secret("connection")
            return JiraClient(connection), None
        except Exception as exc:
            return None, ({"error": str(exc)}, "error")
