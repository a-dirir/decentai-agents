from __future__ import annotations

import base64
import binascii
import json
import time
from typing import Any
from urllib.parse import urlsplit

import requests


TOKEN_EXPIRY_MARGIN_SECONDS = 60


class CocError(RuntimeError):
    pass


class CocClient:
    """Authenticated, TLS-verified adapter for the COC HUB `/app` API."""

    ENDPOINT_LIST = "Notification:JiraIncident:GET"
    ENDPOINT_DETAILS = "Notification:JiraIncident:Get_Incident_Details"
    ENDPOINT_PREPARE = "Notification:JiraIncident:Prepare_Incident_Email"
    ENDPOINT_SEND = "Notification:JiraIncident:Send_Email"

    def __init__(self, connection: dict[str, Any]):
        self.base_url = str(connection.get("base_url") or "").rstrip("/")
        self.key_id = str(connection.get("key_id") or "")
        self.key_secret = str(connection.get("key_secret") or "")
        parsed = urlsplit(self.base_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise CocError("The COC HUB connection must use an https:// base_url.")
        if parsed.username or parsed.password:
            raise CocError("The COC HUB base_url cannot contain credentials.")
        if not self.key_id or not self.key_secret:
            raise CocError("The COC HUB connection is missing key_id or key_secret.")

        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "DecentAI-JiraOps/1.1",
        })
        self._access_token = ""
        self._token_expires_at = 0.0

    def list_incidents(self, jql: str = "") -> list[dict[str, Any]]:
        conditions = [{"Jira_Query": jql}] if jql else []
        result = self.call(self.ENDPOINT_LIST, {"conditions": conditions})
        data = result.get("data") or []
        if not isinstance(data, list):
            raise CocError("COC HUB returned an invalid incident list.")
        return [item for item in data if isinstance(item, dict)]

    def get_details(self, issue_key: str) -> dict[str, Any]:
        return self.call(self.ENDPOINT_DETAILS, {"issue_key": issue_key})

    def prepare_email(self, incident_details: dict[str, Any]) -> dict[str, Any]:
        result = self.call(self.ENDPOINT_PREPARE, incident_details)
        data = result.get("data") or {}
        if not isinstance(data, dict):
            raise CocError("COC HUB returned an invalid email draft.")
        return data

    def send_email(
        self,
        issue_key: str,
        subject: str,
        body: str,
        to_contacts: list[str],
        cc_contacts: list[str],
        mode: str,
    ) -> dict[str, Any]:
        return self.call(self.ENDPOINT_SEND, {
            "issue_key": issue_key,
            "Subject": subject,
            "Body": body,
            "toContacts": to_contacts,
            "ccContacts": cc_contacts,
            "Mode": mode,
        })

    def call(self, endpoint: str, data: dict[str, Any]) -> dict[str, Any]:
        token = self._ensure_token()
        response = self._post_app(endpoint, data, token)
        if response.status_code == 401:
            self._access_token = ""
            response = self._post_app(endpoint, data, self._ensure_token())
        return self._json_response(response, endpoint)

    def _authenticate(self) -> None:
        try:
            response = self.session.post(
                f"{self.base_url}/api-key",
                headers={
                    "X-API-Key-ID": self.key_id,
                    "X-API-Key-Secret": self.key_secret,
                },
                json={},
                timeout=25,
                verify=True,
            )
        except requests.RequestException as exc:
            raise CocError(f"COC HUB authentication could not be reached: {exc}") from exc
        payload = self._json_response(response, "authentication")
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise CocError("COC HUB authentication returned no access token.")
        self._access_token = token
        self._token_expires_at = self._extract_expiry(token)

    def _ensure_token(self) -> str:
        if not self._access_token or time.time() >= (
            self._token_expires_at - TOKEN_EXPIRY_MARGIN_SECONDS
        ):
            self._authenticate()
        return self._access_token

    def _post_app(
        self, endpoint: str, data: dict[str, Any], token: str
    ) -> requests.Response:
        try:
            return self.session.post(
                f"{self.base_url}/app",
                cookies={"access_token_cookie": token},
                json={"endpoint": endpoint, "data": data},
                timeout=45,
                verify=True,
            )
        except requests.RequestException as exc:
            raise CocError(f"COC HUB could not be reached: {exc}") from exc

    @staticmethod
    def _json_response(response: requests.Response, operation: str) -> dict[str, Any]:
        if response.status_code >= 400:
            raise CocError(
                f"COC HUB {operation} returned HTTP {response.status_code}."
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise CocError(f"COC HUB {operation} returned invalid JSON.") from exc
        if not isinstance(payload, dict):
            raise CocError(f"COC HUB {operation} returned an invalid response.")
        return payload

    @staticmethod
    def _extract_expiry(token: str) -> float:
        try:
            payload = token.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            decoded = json.loads(base64.urlsafe_b64decode(payload))
            return float(decoded["exp"])
        except (IndexError, KeyError, TypeError, ValueError, binascii.Error):
            return time.time() + 23 * 3600


def contact_strings(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        value = [value]
    contacts: list[str] = []
    for item in value:
        if isinstance(item, (str, int, float)):
            text = str(item).strip()
        elif isinstance(item, dict):
            text = str(next((item[key] for key in (
                "email", "Email", "value", "id", "name", "displayName"
            ) if item.get(key) not in (None, "")), "")).strip()
        else:
            text = ""
        if text and text not in contacts:
            contacts.append(text)
    return contacts


def recommendation_strings(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        value = [value]
    return [
        json.dumps(item, ensure_ascii=False, default=str)
        if isinstance(item, (dict, list)) else str(item)
        for item in value
    ]
