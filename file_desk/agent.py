"""File Desk (see manifest.yaml).

Stateless: every document flows through the mediated ``call.resources``,
which is the platform's file store in production and a dict in tests. The
agent never touches a path on disk.
"""

from ai_runtime.agents_layer.sdk import AgentBase

from .tools import FileTool


class FileDeskAgent(AgentBase):
    def tools(self):
        return [FileTool(self)]
