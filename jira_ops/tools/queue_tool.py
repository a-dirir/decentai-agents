from .base import JiraToolBase
from .client import JiraError, normalize_issue


class QueueTool(JiraToolBase):
    id = "queue"

    async def search(self, call):
        client, error = await self.client(call)
        if error:
            return error
        jql = str(call.inputs["jql"]).strip()
        maximum = int(call.inputs.get("max_results") or 25)
        await call.progress("Searching Jira")
        try:
            result = client.search(jql, maximum)
        except JiraError as exc:
            return {"error": str(exc)}, "error"
        issues = [normalize_issue(issue, client) for issue in result.get("issues") or []]
        return {
            "issues": issues,
            "returned": len(issues),
            "total": int(result.get("total", len(issues))),
        }, "success"

    async def my_open(self, call):
        client, error = await self.client(call)
        if error:
            return error
        maximum = int(call.inputs.get("max_results") or 25)
        jql = (
            "assignee = currentUser() AND statusCategory != Done "
            "ORDER BY priority DESC, updated DESC"
        )
        await call.progress("Loading your open Jira work")
        try:
            result = client.search(jql, maximum)
        except JiraError as exc:
            return {"error": str(exc)}, "error"
        issues = [normalize_issue(issue, client) for issue in result.get("issues") or []]
        return {
            "issues": issues,
            "returned": len(issues),
            "total": int(result.get("total", len(issues))),
        }, "success"
