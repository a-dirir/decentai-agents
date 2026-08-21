from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ai_runtime.agents_layer.sdk import ToolBase

from .coc_client import (
    CocClient,
    CocError,
    contact_strings,
    recommendation_strings,
)


class CocIncidentTool(ToolBase):
    id = "coc_incident"

    async def _client(self, call):
        try:
            connection = await call.resources.use_secret("coc_connection")
            return CocClient(connection), None
        except Exception as exc:
            return None, ({"error": str(exc)}, "error")

    async def list_pending(self, call):
        client, error = await self._client(call)
        if error:
            return error
        await call.progress("Loading pending COC HUB incidents")
        try:
            incidents = client.list_incidents(str(call.inputs.get("jql") or ""))
        except CocError as exc:
            return {"error": str(exc)}, "error"
        maximum = int(call.inputs.get("max_results") or 25)
        pending = [
            normalize_incident(item)
            for item in incidents
            if str(item.get("customer_informed") or "").strip().lower() != "yes"
        ]
        return {
            "incidents": pending[:maximum],
            "returned": min(len(pending), maximum),
            "total": len(pending),
        }, "success"

    async def prepare_email(self, call):
        client, error = await self._client(call)
        if error:
            return error
        issue_key = str(call.inputs["issue_key"]).upper()
        await call.progress(f"Preparing the COC HUB email for {issue_key}")
        try:
            response = client.get_details(issue_key)
            data = response.get("data") or {}
            details = data.get("Incident_Details") or {}
            contacts = data.get("Contacts") or {}
            if not isinstance(details, dict) or not details:
                return {"error": f"COC HUB found no incident details for {issue_key}."}, "error"
            email = client.prepare_email(details)
        except CocError as exc:
            return {"error": str(exc)}, "error"

        subject = str(email.get("Subject") or "").strip()
        body = str(email.get("Body") or "").strip()
        to_contacts = contact_strings(contacts.get("Recipients"))
        cc_contacts = contact_strings(contacts.get("CC"))
        if not subject or not body:
            return {"error": "COC HUB returned an empty email subject or body."}, "error"
        if not to_contacts:
            return {"error": "COC HUB resolved no primary recipients."}, "error"

        prepared_at = datetime.now(timezone.utc).isoformat()
        draft = await call.resources.create_data("incident_draft", {
            "issue_key": issue_key,
            "subject": subject,
            "body": body,
            "to_contacts": {"items": to_contacts},
            "cc_contacts": {"items": cc_contacts},
            "prepared_at": prepared_at,
        })
        return {
            "draft_ref": draft["resource_ref"],
            "issue_key": issue_key,
            "subject": subject,
            "body": body,
            "to_contacts": to_contacts,
            "cc_contacts": cc_contacts,
            "recommendations": recommendation_strings(email.get("recommendation")),
            "prepared_at": prepared_at,
        }, "success"

    async def get_draft(self, call):
        issue_key = str(call.inputs["issue_key"]).upper()
        records = await call.resources.list_data(
            "incident_draft", {"issue_key": issue_key}
        )
        if not records:
            return {"error": f"No prepared COC HUB draft exists for {issue_key}."}, "error"
        record = max(
            records, key=lambda item: str(item.get("keys", {}).get("prepared_at") or "")
        )
        return draft_result(record), "success"

    async def send_test(self, call):
        return await self._send(call, "test")

    async def send_live(self, call):
        return await self._send(call, "live")

    async def _send(self, call, mode: str):
        client, error = await self._client(call)
        if error:
            return error
        issue_key = str(call.inputs["issue_key"]).upper()
        draft_ref = call.inputs["draft_ref"]
        try:
            record = await call.resources.read_data("incident_draft", draft_ref)
        except Exception:
            return {"error": f"Unknown draft_ref '{draft_ref}'."}, "error"
        stored = draft_result(record)
        if stored["sent_mode"] == "live":
            return {
                "error": f"Draft '{draft_ref}' was already sent live at {stored['sent_at']}."
            }, "error"
        if stored["sent_mode"] == mode:
            return {
                "error": f"Draft '{draft_ref}' was already sent in {mode} mode at {stored['sent_at']}."
            }, "error"
        supplied = {
            "issue_key": issue_key,
            "subject": str(call.inputs["subject"]),
            "body": str(call.inputs["body"]),
            "to_contacts": list(call.inputs["to_contacts"]),
            "cc_contacts": list(call.inputs.get("cc_contacts") or []),
        }
        for field, value in supplied.items():
            if value != stored[field]:
                return {
                    "error": f"The approved {field} does not match stored draft '{draft_ref}'. Prepare or load the draft again."
                }, "error"

        await call.progress(
            f"Sending the {mode} COC HUB email for {issue_key}"
        )
        try:
            result = client.send_email(
                issue_key=issue_key,
                subject=stored["subject"],
                body=stored["body"],
                to_contacts=stored["to_contacts"],
                cc_contacts=stored["cc_contacts"],
                mode=mode,
            )
        except CocError as exc:
            return {"error": str(exc)}, "error"

        sent_at = datetime.now(timezone.utc).isoformat()
        await call.resources.update_data("incident_draft", draft_ref, {
            "sent_mode": mode,
            "sent_at": sent_at,
        })
        return {
            "issue_key": issue_key,
            "mode": mode,
            "sent": True,
            "sent_at": sent_at,
            "message": response_message(result),
        }, "success"


def normalize_incident(item: dict[str, Any]) -> dict[str, str]:
    return {
        "issue_key": str(item.get("issue_key") or item.get("key") or ""),
        "summary": str(item.get("summary") or item.get("title") or ""),
        "status": str(item.get("status") or ""),
        "customer_informed": str(item.get("customer_informed") or ""),
    }


def draft_result(record: dict[str, Any]) -> dict[str, Any]:
    keys = record.get("keys") or {}
    return {
        "draft_ref": record["resource_ref"],
        "issue_key": str(keys.get("issue_key") or ""),
        "subject": str(keys.get("subject") or ""),
        "body": str(keys.get("body") or ""),
        "to_contacts": list((keys.get("to_contacts") or {}).get("items") or []),
        "cc_contacts": list((keys.get("cc_contacts") or {}).get("items") or []),
        "prepared_at": str(keys.get("prepared_at") or ""),
        "sent_mode": str(keys.get("sent_mode") or ""),
        "sent_at": str(keys.get("sent_at") or ""),
    }


def response_message(result: dict[str, Any]) -> str:
    for key in ("message", "Message", "status", "Status"):
        if result.get(key) not in (None, ""):
            return str(result[key])[:500]
    return "COC HUB accepted the email request."
