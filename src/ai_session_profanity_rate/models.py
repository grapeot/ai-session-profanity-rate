from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class MessageRecord:
    item_id: str
    timestamp: str
    local_date: str
    source: str
    session_id: str
    source_message_id: str
    model: str | None
    model_family: str
    model_attribution: str
    text: str

    def private_dict(self) -> dict[str, Any]:
        return asdict(self)

    def public_dict(self, profanity_count: int, cache_hit: bool) -> dict[str, Any]:
        data = asdict(self)
        data.pop("text")
        data["profanity_count"] = profanity_count
        data["has_profanity"] = profanity_count > 0
        data["cache_hit"] = cache_hit
        return data
