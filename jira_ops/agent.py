"""Focused Jira operations agent (see manifest.yaml)."""

from ai_runtime.agents_layer.sdk import AgentBase

from .tools import CocIncidentTool, IssueTool, QueueTool


class JiraOpsAgent(AgentBase):
    def tools(self):
        return [QueueTool(self), IssueTool(self), CocIncidentTool(self)]
