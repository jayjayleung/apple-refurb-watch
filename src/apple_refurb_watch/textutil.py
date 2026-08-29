from __future__ import annotations

import re


def norm_text(value: str | None) -> str:
    if not value:
        return ""
    text = value.replace("\xa0", " ").replace("\u200d", "").replace("\u200b", "")
    return re.sub(r"\s+", "", text).lower()
