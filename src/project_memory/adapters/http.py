import json
from typing import Any

import httpx

from project_memory.domain.models import ProviderUnavailable


def bounded_json(
    client: httpx.Client,
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    max_bytes: int = 2_000_000,
) -> Any:
    """Never include response bodies, auth headers or raw exceptions in public errors."""
    try:
        with client.stream(method, url, json=payload) as response:
            if response.status_code != 200:
                raise ProviderUnavailable(
                    f"Dış servis isteği tamamlanamadı (HTTP {response.status_code})."
                )
            data = bytearray()
            for part in response.iter_bytes():
                data.extend(part)
                if len(data) > max_bytes:
                    raise ProviderUnavailable("Dış servis yanıtı boyut sınırını aştı.")
            return json.loads(data)
    except (httpx.HTTPError, ValueError, TypeError):
        raise ProviderUnavailable("Dış servis erişilemiyor veya geçerli veri döndürmedi.") from None
