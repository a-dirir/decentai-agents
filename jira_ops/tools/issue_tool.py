from .base import JiraToolBase
from .client import JiraError, normalize_issue


class IssueTool(JiraToolBase):
    id = "issue"

    async def get(self, call):
        client, error = await self.client(call)
        if error:
            return error
        key = str(call.inputs["issue_key"]).upper()
        try:
            issue = client.issue(key)
        except JiraError as exc:
            return {"error": str(exc)}, "error"
        return {"issue": normalize_issue(issue, client, details=True)}, "success"

    async def transitions(self, call):
        client, error = await self.client(call)
        if error:
            return error
        key = str(call.inputs["issue_key"]).upper()
        try:
            values = client.transitions(key)
        except JiraError as exc:
            return {"error": str(exc)}, "error"
        return {"transitions": [{
            "id": str(value.get("id") or ""),
            "name": str(value.get("name") or ""),
            "to_status": str((value.get("to") or {}).get("name") or ""),
        } for value in values]}, "success"

    async def comment(self, call):
        client, error = await self.client(call)
        if error:
            return error
        key = str(call.inputs["issue_key"]).upper()
        body = str(call.inputs["body"]).strip()
        await call.progress(f"Adding an internal comment to {key}")
        try:
            result = client.add_internal_comment(key, body)
        except JiraError as exc:
            return {"error": str(exc)}, "error"
        return {"issue_key": key, "comment_id": str(result.get("id") or "")}, "success"

    async def log_work(self, call):
        client, error = await self.client(call)
        if error:
            return error
        key = str(call.inputs["issue_key"]).upper()
        spent = str(call.inputs["time_spent"]).strip()
        await call.progress(f"Logging {spent} on {key}")
        try:
            result = client.log_work(key, spent, str(call.inputs.get("comment") or ""))
        except JiraError as exc:
            return {"error": str(exc)}, "error"
        return {"issue_key": key, "worklog_id": str(result.get("id") or "")}, "success"

    async def transition(self, call):
        client, error = await self.client(call)
        if error:
            return error
        key = str(call.inputs["issue_key"]).upper()
        target = str(call.inputs["target_status"]).strip()
        try:
            before = client.issue(key)
            previous_status = issue_status(before)
            choices = client.transitions(key)
            match = next((value for value in choices if str(
                (value.get("to") or {}).get("name") or value.get("name") or ""
            ).lower() == target.lower()), None)
            if match is None:
                available = ", ".join(str((value.get("to") or {}).get("name") or "") for value in choices)
                return {
                    "error": f"No direct transition from {key} to '{target}'. Available: {available or 'none'}."
                }, "error"
            await call.progress(f"Moving {key} to {target}")
            client.transition(key, str(match["id"]))
            after = client.issue(key)
            confirmed_status = issue_status(after)
        except JiraError as exc:
            return {"error": str(exc)}, "error"
        if confirmed_status.lower() != target.lower():
            return {
                "error": (
                    f"Jira accepted the transition request for {key}, but "
                    f"verification found status '{confirmed_status or 'unknown'}' "
                    f"instead of '{target}'."
                )
            }, "error"
        return {
            "issue_key": key,
            "previous_status": previous_status,
            "target_status": target,
            "confirmed_status": confirmed_status,
            "transitioned": True,
        }, "success"


def issue_status(issue):
    return str(((issue.get("fields") or {}).get("status") or {}).get("name") or "")
