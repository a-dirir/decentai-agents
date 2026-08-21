import html
import ipaddress
import re
import socket
from urllib.parse import urljoin, urlsplit

import requests

from ai_runtime.agents_layer.sdk import ToolBase

# Enough to turn a page into something a model can read, without a parser
# dependency: drop the parts that are never prose, then the tags.
NON_PROSE = re.compile(
    r"<(script|style|noscript|template)[^>]*>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
TAGS = re.compile(r"<[^>]+>")
WHITESPACE = re.compile(r"[ \t\r\f\v]+")
BLANK_LINES = re.compile(r"\n{3,}")
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 5


class WebTool(ToolBase):
    id = "web"

    async def fetch(self, call):
        url = str(call.inputs["url"]).strip()
        limit = int(call.inputs.get("max_characters") or 4000)

        await call.progress(f"Fetching {url}")
        try:
            response = self._get_public(url)
        except (ValueError, requests.RequestException, socket.gaierror) as exc:
            return {"error": f"Could not fetch {url}: {exc}"}, "error"

        if response.status_code >= 400:
            return {
                "error": f"{url} answered {response.status_code}.",
                "status": response.status_code,
            }, "error"

        content_type = response.headers.get("Content-Type", "").lower()
        if content_type and not any(
            kind in content_type for kind in ("text/", "application/xhtml+xml")
        ):
            return {
                "error": f"{response.url} is not a readable text page.",
                "status": response.status_code,
            }, "error"

        body = response.content.decode(response.encoding or "utf-8", errors="replace")
        title = TITLE.search(body)
        text = self._readable(body)
        return {
            "url": response.url,
            "status": response.status_code,
            "title": self._collapse(title.group(1)) if title else "",
            # Bounded: the result travels into the model's context, and a
            # whole page would crowd out the conversation asking for it.
            "text": text[:limit],
            "characters": len(text),
            "truncated": len(text) > limit,
        }, "success"

    @classmethod
    def _readable(cls, body: str) -> str:
        stripped = NON_PROSE.sub(" ", body)
        stripped = TAGS.sub(" ", stripped)
        stripped = html.unescape(stripped)
        stripped = WHITESPACE.sub(" ", stripped)
        return BLANK_LINES.sub("\n\n", stripped).strip()

    @staticmethod
    def _collapse(value: str) -> str:
        return WHITESPACE.sub(" ", html.unescape(TAGS.sub(" ", value))).strip()

    @classmethod
    def _get_public(cls, url: str):
        current = url
        headers = {"User-Agent": "DecentAI-WebReader/1.1"}

        for _ in range(MAX_REDIRECTS + 1):
            cls._validate_public_url(current)
            response = requests.get(
                current,
                timeout=20,
                headers=headers,
                allow_redirects=False,
                stream=True,
            )
            if response.is_redirect or response.is_permanent_redirect:
                location = response.headers.get("Location")
                response.close()
                if not location:
                    raise ValueError("redirect response has no destination")
                current = urljoin(current, location)
                continue

            chunks = []
            size = 0
            for chunk in response.iter_content(chunk_size=64 * 1024):
                size += len(chunk)
                if size > MAX_RESPONSE_BYTES:
                    response.close()
                    raise ValueError("page is larger than 2 MB")
                chunks.append(chunk)
            response._content = b"".join(chunks)
            response._content_consumed = True
            return response

        raise ValueError(f"more than {MAX_REDIRECTS} redirects")

    @staticmethod
    def _validate_public_url(url: str) -> None:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("only http(s) URLs with a hostname are supported")
        if parsed.username or parsed.password:
            raise ValueError("URLs containing credentials are not supported")

        hostname = parsed.hostname.rstrip(".").lower()
        if hostname == "localhost" or hostname.endswith(".localhost"):
            raise ValueError("local addresses are not public")

        addresses = {
            info[4][0]
            for info in socket.getaddrinfo(
                hostname, parsed.port or (443 if parsed.scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            )
        }
        if not addresses:
            raise ValueError("hostname did not resolve")
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if not ip.is_global:
                raise ValueError("local or private addresses are not public")
