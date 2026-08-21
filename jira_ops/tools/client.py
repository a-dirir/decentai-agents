from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import requests


class JiraError(RuntimeError):
    pass


class JiraClient:
    """Small Jira Cloud REST adapter with bounded, sanitized errors."""

    def __init__(self, connection: dict[str, Any]):
        self.base_url = str(connection.get("base_url") or "").rstrip("/")
        self.email = str(connection.get("email") or "")
        self.api_token = str(connection.get("api_token") or "")
        if not self.base_url or not self.email or not self.api_token:
            raise JiraError("The Jira connection is missing base_url, email, or api_token.")
        if not self.base_url.startswith("https://"):
            raise JiraError("The Jira connection must use an https:// base_url.")
        self.connection = connection
        self.session = requests.Session()
        self.session.auth = (self.email, self.api_token)
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "DecentAI-JiraOps/1.0",
        })

    def request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        try:
            response = self.session.request(
                method, f"{self.base_url}{path}", timeout=25, **kwargs
            )
        except requests.RequestException as exc:
            raise JiraError(f"Jira could not be reached: {exc}") from exc
        if response.status_code >= 400:
            message = ""
            try:
                payload = response.json()
                values = payload.get("errorMessages") or []
                message = "; ".join(str(value) for value in values)
                if not message and payload.get("errors"):
                    message = "; ".join(
                        f"{key}: {value}" for key, value in payload["errors"].items()
                    )
            except (ValueError, AttributeError):
                pass
            raise JiraError(
                f"Jira returned HTTP {response.status_code}"
                + (f": {message[:500]}" if message else ".")
            )
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    def search(self, jql: str, max_results: int) -> dict[str, Any]:
        fields = [
            "summary", "status", "issuetype", "priority", "assignee",
            "created", "updated",
        ]
        fields.extend(
            field_id for field_id in (
                self.connection.get("ttr_field_id"),
                self.connection.get("customer_informed_field_id"),
            ) if field_id
        )
        return self.request("GET", "/rest/api/3/search/jql", params={
            "jql": jql,
            "maxResults": max_results,
            "fields": ",".join(fields),
        })

    def issue(self, issue_key: str) -> dict[str, Any]:
        return self.request(
            "GET", f"/rest/api/3/issue/{quote(issue_key, safe='')}",
            params={"fields": "*all"},
        )

    def transitions(self, issue_key: str) -> list[dict[str, Any]]:
        result = self.request(
            "GET", f"/rest/api/3/issue/{quote(issue_key, safe='')}/transitions"
        )
        return result.get("transitions") or []

    def add_internal_comment(self, issue_key: str, body: str) -> dict[str, Any]:
        return self.request(
            "POST", f"/rest/api/3/issue/{quote(issue_key, safe='')}/comment",
            json={
                "body": adf(body),
                "properties": [{
                    "key": "sd.public.comment",
                    "value": {"internal": True},
                }],
            },
        )

    def log_work(self, issue_key: str, time_spent: str, comment: str = "") -> dict[str, Any]:
        payload: dict[str, Any] = {
            "timeSpent": time_spent,
            "started": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%S.000+0000"
            ),
        }
        if comment:
            payload["comment"] = adf(comment)
        return self.request(
            "POST", f"/rest/api/3/issue/{quote(issue_key, safe='')}/worklog",
            json=payload,
        )

    def transition(self, issue_key: str, transition_id: str) -> None:
        self.request(
            "POST", f"/rest/api/3/issue/{quote(issue_key, safe='')}/transitions",
            json={"transition": {"id": transition_id}},
        )


def adf(text: str) -> dict[str, Any]:
    return {
        "type": "doc",
        "version": 1,
        "content": [{
            "type": "paragraph",
            "content": [{"type": "text", "text": text}],
        }],
    }


def text_from_adf(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(filter(None, (text_from_adf(item) for item in value)))
    if not isinstance(value, dict):
        return ""
    own = str(value.get("text") or "")
    children = text_from_adf(value.get("content") or [])
    return "".join(part for part in (own, children) if part)


def display_value(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (str, int, float)):
        return str(value)
    if isinstance(value, list):
        parts = [display_value(item) for item in value]
        return ", ".join(part for part in parts if part) or None
    if isinstance(value, dict):
        for key in ("value", "name", "displayName", "url"):
            if value.get(key) not in (None, ""):
                return str(value[key])
    return str(value)


def sla(value: Any) -> tuple[str, int | None, bool]:
    if not isinstance(value, dict):
        return "N/A", None, False
    cycle = value.get("ongoingCycle")
    if not cycle:
        completed = value.get("completedCycles") or []
        if completed:
            breached = bool(completed[-1].get("breached"))
            return ("Breached" if breached else "Completed"), 0, breached
        return "N/A", None, False
    remaining = cycle.get("remainingTime") or {}
    millis = remaining.get("millis")
    breached = bool(cycle.get("breached")) or (
        isinstance(millis, (int, float)) and millis < 0
    )
    if breached:
        return "BREACHED", int(millis) if millis is not None else None, True
    friendly = remaining.get("friendly")
    if friendly:
        return f"{friendly} left", int(millis) if millis is not None else None, False
    if millis is not None:
        return f"{max(0, round(millis / 60000))}m left", int(millis), False
    return "N/A", None, False


def normalize_issue(issue: dict[str, Any], client: JiraClient, details=False) -> dict[str, Any]:
    fields = issue.get("fields") or {}
    assignee = fields.get("assignee") or {}
    priority = fields.get("priority") or {}
    status = fields.get("status") or {}
    issue_type = fields.get("issuetype") or {}
    ttr_text, ttr_millis, ttr_breached = sla(
        fields.get(client.connection.get("ttr_field_id"))
        if client.connection.get("ttr_field_id") else None
    )
    result = {
        "key": str(issue.get("key") or ""),
        "summary": str(fields.get("summary") or ""),
        "status": str(status.get("name") or ""),
        "issue_type": str(issue_type.get("name") or ""),
        "priority": priority.get("name"),
        "assignee": assignee.get("displayName"),
        "updated": str(fields.get("updated") or ""),
        "url": f"{client.base_url}/browse/{issue.get('key')}",
        "sla_text": ttr_text,
        "sla_millis": ttr_millis,
        "sla_breached": ttr_breached,
    }
    if details:
        result.update({
            "created": str(fields.get("created") or ""),
            "description": text_from_adf(fields.get("description")),
            "customer_informed": display_value(fields.get(
                client.connection.get("customer_informed_field_id")
            )) if client.connection.get("customer_informed_field_id") else None,
        })
    return result
