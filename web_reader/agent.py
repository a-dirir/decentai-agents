"""Web Reader (see manifest.yaml).

Declares no resources: it keeps nothing and reads nothing of the
platform's. Its whole surface is one external call, which is exactly why
it is declared at the level that stops for approval.
"""

from ai_runtime.agents_layer.sdk import AgentBase

from .tools import WebTool


class WebReaderAgent(AgentBase):
    def tools(self):
        return [WebTool(self)]
