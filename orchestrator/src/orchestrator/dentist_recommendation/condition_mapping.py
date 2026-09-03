"""Map diagnosis conditions to specialist tags and search keywords."""

from __future__ import annotations

# condition fragment -> specialist tags for platform dentist matching
CONDITION_SPECIALISTS: dict[str, list[str]] = {
    "cavity": ["general", "restorative", "endodontist"],
    "caries": ["general", "restorative", "endodontist"],
    "decay": ["general", "restorative", "endodontist"],
    "gingivitis": ["periodontist", "hygienist", "general"],
    "gum": ["periodontist", "hygienist", "general"],
    "plaque": ["hygienist", "general"],
    "tartar": ["hygienist", "general"],
    "whitening": ["cosmetic", "general"],
    "stain": ["cosmetic", "hygienist", "general"],
    "sensitivity": ["general", "restorative"],
    "healthy": ["general", "preventive"],
    "orthodont": ["orthodontist"],
    "alignment": ["orthodontist"],
}

PLACES_KEYWORDS: dict[str, str] = {
    "cavity": "dental clinic cavity treatment",
    "caries": "dental clinic cavity treatment",
    "decay": "dental clinic tooth decay",
    "gingivitis": "periodontist gum disease",
    "gum": "periodontist gum treatment",
    "plaque": "dental cleaning hygienist",
    "tartar": "dental scaling cleaning",
    "whitening": "cosmetic dentist whitening",
    "stain": "cosmetic dentist teeth cleaning",
    "sensitivity": "general dentist sensitivity",
    "healthy": "general dentist checkup",
    "orthodont": "orthodontist braces",
    "alignment": "orthodontist",
}


SPECIALIST_KEYWORD_MAP: dict[str, list[str]] = {
    "restorative": ["restorative", "restorative dentist", "endodontist"],
    "periodont": ["periodontist", "periodontics", "hygienist"],
    "endodont": ["endodontist", "endodontics", "restorative"],
    "orthodont": ["orthodontist", "orthodontics"],
    "prosthodont": ["prosthodontist", "prosthodontics", "restorative"],
    "pediatric": ["pediatric", "pedodontist"],
    "pedodont": ["pediatric", "pedodontist"],
    "surgeon": ["oral surgeon", "maxillofacial", "surgery"],
    "surgery": ["oral surgeon", "maxillofacial", "surgery"],
    "maxillofacial": ["oral surgeon", "maxillofacial"],
    "cosmetic": ["cosmetic", "cosmetic dentist"],
    "hygien": ["hygienist", "dental hygienist"],
    "preventive": ["preventive", "general"],
    "general": ["general", "general dentist"],
}


def normalize_issue(issue: str) -> str:
    return issue.lower().strip().replace("_", " ").replace("-", " ")


def normalize_specialist_candidates(issue: str) -> list[str]:
    """Split compound specialist/issue strings into normalized candidate strings.

    Example: 'general dentist / restorative dentist' -> ['general dentist', 'restorative dentist']
    """
    if not issue:
        return ["general dentist"]
    cleaned = issue.replace(" / ", "/").replace(" and ", "/").replace(" or ", "/").replace(",", "/")
    parts = [p.strip().lower() for p in cleaned.split("/") if p.strip()]
    return parts or [issue.strip().lower()]


def specialist_tags_for_issue(issue: str) -> list[str]:
    """Map an issue or compound specialist string into searchable specialist tags."""
    candidates = normalize_specialist_candidates(issue)
    tags: set[str] = {"general"}

    for candidate in candidates:
        norm_candidate = normalize_issue(candidate)
        # Add the raw candidate words if meaningful
        if norm_candidate and norm_candidate != "dentist":
            tags.add(norm_candidate)

        # Match specialist keyword map
        for key, values in SPECIALIST_KEYWORD_MAP.items():
            if key in norm_candidate:
                tags.update(values)

        # Match condition specialists map
        for key, values in CONDITION_SPECIALISTS.items():
            if key in norm_candidate:
                tags.update(values)

    return sorted(tags)


def places_keyword_for_issue(issue: str) -> str:
    normalized = normalize_issue(issue)
    for key, keyword in PLACES_KEYWORDS.items():
        if key in normalized:
            return keyword
    return "dentist dental clinic"

