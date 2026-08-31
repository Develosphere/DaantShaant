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


def normalize_issue(issue: str) -> str:
    return issue.lower().strip().replace("_", " ").replace("-", " ")


def specialist_tags_for_issue(issue: str) -> list[str]:
    normalized = normalize_issue(issue)
    tags: set[str] = {"general"}
    for key, values in CONDITION_SPECIALISTS.items():
        if key in normalized:
            tags.update(values)
    return sorted(tags)


def places_keyword_for_issue(issue: str) -> str:
    normalized = normalize_issue(issue)
    for key, keyword in PLACES_KEYWORDS.items():
        if key in normalized:
            return keyword
    return "dentist dental clinic"
