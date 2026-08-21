import re

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


class WebTool(ToolBase):
    id = "web"

    async def fetch(self, call):
        url = str(call.inputs["url"]).strip()
        limit = int(call.inputs.get("max_characters") or 4000)

        await call.progress(f"Fetching {url}")
        try:
            response = requests.get(
                url,
                timeout=20,
                headers={"User-Agent": "DecentAI-WebReader/1.0"},
                # A redirect chain is followed, but not indefinitely.
                allow_redirects=True,
            )
        except requests.RequestException as exc:
            return {"error": f"Could not fetch {url}: {exc}"}, "error"

        if response.status_code >= 400:
            return {
                "error": f"{url} answered {response.status_code}.",
                "status": response.status_code,
            }, "error"

        body = response.text
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
        stripped = WHITESPACE.sub(" ", stripped)
        return BLANK_LINES.sub("\n\n", stripped).strip()

    @staticmethod
    def _collapse(value: str) -> str:
        return WHITESPACE.sub(" ", TAGS.sub(" ", value)).strip()
