from __future__ import annotations

import re
import unicodedata

from jarvis.core.contracts import NeedsReview, PlannedAction


MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(char for char in decomposed if not unicodedata.combining(char)).lower().strip()


def extract_month(text: str) -> str:
    normalized = normalize(text)
    iso = re.search(r"\b(20\d{2})-(0[1-9]|1[0-2])\b", normalized)
    if iso:
        return iso.group(0)
    year_match = re.search(r"\b(20\d{2})\b", normalized)
    year = int(year_match.group(1)) if year_match else 2026
    for name, number in MONTHS.items():
        if name in normalized:
            return f"{year:04d}-{number:02d}"
    raise NeedsReview("The request needs an explicit month and year")


class OctopusSpecialist:
    """Deterministic planner for the first laboratory use cases."""

    agent_id = "octopus-specialist"

    def plan(self, request: str) -> PlannedAction:
        text = normalize(request)
        if "revision" in text or "revisar" in text:
            return PlannedAction("review_cases", "octopus.review_cases", {"limit": 20})
        if "resumen" in text or "facturacion" in text or "rentabilidad" in text:
            return PlannedAction("month_summary", "octopus.month_summary", {"month": extract_month(text)})
        match = re.search(r"(?:ficha|cliente)\s+(?:de\s+)?(.+)$", request, flags=re.IGNORECASE)
        if match and match.group(1).strip():
            return PlannedAction(
                "client_snapshot",
                "octopus.client_snapshot",
                {"client_name": match.group(1).strip()},
            )
        raise NeedsReview("Request is outside the three approved JARVIS Lab capabilities")
