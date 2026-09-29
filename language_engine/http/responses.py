"""Reader HTTP responses."""

import gzip as _response_gzip
import json
from typing import Any, Mapping, Sequence

from flask import Response, request


def _client_accepts_gzip() -> bool:
    return "gzip" in str(request.headers.get("Accept-Encoding") or "").lower()


def _lookup_json_response(
    payload: Mapping[str, Any] | Sequence[Any],
    status: int = 200,
    extra_headers: Mapping[str, Any] | None = None,
) -> Response:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Vary": "Accept-Encoding",
    }
    if isinstance(extra_headers, Mapping):
        for key, value in extra_headers.items():
            if value is None:
                continue
            headers[str(key)] = str(value)
    if len(body) >= 512 and _client_accepts_gzip():
        body = _response_gzip.compress(body, compresslevel=6)
        headers["Content-Encoding"] = "gzip"
    return Response(body, status=status, headers=headers)
