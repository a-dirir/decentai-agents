from ai_runtime.agents_layer.sdk import ToolBase


class FileTool(ToolBase):
    id = "file"

    async def list(self, call):
        contains = str(call.inputs.get("name_contains") or "").lower()
        limit = int(call.inputs.get("limit") or 25)

        records = await call.resources.list_files("document")
        matches = [
            {
                "file_ref": record["resource_ref"],
                "filename": str(record.get("filename") or ""),
            }
            for record in records
            if not contains or contains in str(record.get("filename") or "").lower()
        ]
        return {"documents": matches[:limit], "total": len(matches)}, "success"

    async def read(self, call):
        file_ref = call.inputs["file_ref"]
        limit = int(call.inputs.get("max_characters") or 4000)

        try:
            document = await call.resources.read_file("document", file_ref)
        except Exception:
            return {"error": f"Unknown file_ref '{file_ref}'"}, "error"

        text = str(document.get("content") or "")
        return {
            "filename": str(document.get("filename") or ""),
            # Bounded on purpose: the whole result travels into the model's
            # context, and a large document would crowd out the conversation
            # it was meant to inform.
            "text": text[:limit],
            "characters": len(text),
            "truncated": len(text) > limit,
        }, "success"

    async def save(self, call):
        filename = str(call.inputs["filename"]).strip()
        text = str(call.inputs["text"])

        if not filename:
            return {"error": "filename cannot be blank"}, "error"

        await call.progress(f"Saving {filename}")
        document = await call.resources.create_file("document", filename, text)
        return {
            "file_ref": document["resource_ref"],
            "filename": filename,
            "characters": len(text),
        }, "success"
