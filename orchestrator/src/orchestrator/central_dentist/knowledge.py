"""Curated deterministic oral health knowledge base for DaantShaant Central Dentist.

NO embeddings. NO vector store. NO external network calls.
Fast keyword and topic matching based on standard dental hygiene guidelines.
"""

from __future__ import annotations

from typing import Optional

KNOWLEDGE_TOPICS: dict[str, dict[str, str]] = {
    "brushing": {
        "title": "Brushing Guidelines",
        "content": (
            "Brush twice daily for two full minutes using a soft-bristled toothbrush "
            "and fluoride toothpaste. Hold the brush at a 45-degree angle to the gums "
            "and use gentle, circular motions rather than harsh scrubbing. Replace your "
            "brush every 3 months or when bristles flare."
        ),
    },
    "flossing": {
        "title": "Flossing Technique",
        "content": (
            "Floss once daily before bed to clear plaque between teeth where brush bristles "
            "cannot reach. Curve the floss into a C-shape against the side of each tooth "
            "and gently slide beneath the gumline."
        ),
    },
    "bleeding_gums": {
        "title": "Bleeding Gums / Gingivitis Care",
        "content": (
            "Bleeding during brushing or flossing is most commonly caused by plaque "
            "accumulation irritating the gum margin (early gingivitis). Continuing gentle, "
            "consistent brushing and daily flossing usually improves gum health within 10 to 14 days. "
            "If bleeding is heavy, spontaneous, or persists, professional dental scaling is advised."
        ),
    },
    "sensitivity": {
        "title": "Tooth Sensitivity",
        "content": (
            "Tooth sensitivity to cold or hot foods often stems from exposed root dentin, "
            "enamel erosion, or gum recession. Using a potassium-nitrate desensitizing toothpaste "
            "consistently and avoiding highly acidic drinks helps soothe sensitive nerve endings. "
            "Sharp pain localized to a single tooth when biting should be checked by a dentist."
        ),
    },
    "discoloration": {
        "title": "Tooth Discoloration",
        "content": (
            "Tooth discoloration can be extrinsic (surface stains from tea, coffee, smoking, or spices) "
            "or intrinsic (deeper enamel/dentin changes or aging). Surface stains respond well to routine "
            "dental cleanings and polishing. Visual screening cannot confirm the underlying cause, so a "
            "dentist can evaluate whether scaling, whitening, or restorative care is appropriate."
        ),
    },
    "tartar": {
        "title": "Tartar (Dental Calculus)",
        "content": (
            "Tartar is calcified bacterial plaque that hardens onto tooth enamel. Once plaque mineralizes "
            "into tartar, it cannot be removed with a standard toothbrush or floss. Professional ultrasonic "
            "scaling by a dentist or hygienist is required to safely remove tartar and protect gums."
        ),
    },
    "cavity": {
        "title": "Tooth Decay / Cavities",
        "content": (
            "Cavities occur when oral bacteria ferment dietary sugars and produce acids that demineralize "
            "tooth enamel. Early decay can often be remineralized with fluoride, but once structural cavitation "
            "forms, a dental filling is necessary to stop the decay from reaching the tooth pulp."
        ),
    },
    "ulcer": {
        "title": "Oral Ulcers / Mouth Sores",
        "content": (
            "Common aphthous ulcers (canker sores) are non-contagious and typically heal spontaneously "
            "within 7 to 10 days. Warm saltwater rinses provide gentle relief. Any oral sore that fails "
            "to heal after 10 to 14 days, or is accompanied by swelling or difficulty swallowing, requires "
            "prompt clinical examination."
        ),
    },
    "bad_breath": {
        "title": "Halitosis (Bad Breath)",
        "content": (
            "Persistent bad breath is usually caused by bacterial buildup on the tongue, between teeth, "
            "or around inflamed gums. Cleaning the tongue with a scraper, flossing daily, staying hydrated, "
            "and addressing any untreated gum inflammation are the most effective remedies."
        ),
    },
    "mouthwash": {
        "title": "Mouthwash Basics",
        "content": (
            "Use an alcohol-free fluoride or antibacterial mouthwash to freshen breath, reduce bacterial plaque, "
            "and strengthen enamel. Avoid eating or drinking for 30 minutes after rinsing so active ingredients can work."
        ),
    },
    "checkup": {
        "title": "Routine Checkup Frequency",
        "content": (
            "A routine dental checkup and professional cleaning are recommended every 6 months to detect cavities, "
            "remove hardened tartar, and monitor gum health before symptoms develop."
        ),
    },
}


import re

# Deterministic word-boundary matchers for curated guidelines
KNOWLEDGE_TOPIC_MATCHERS: dict[str, list[str]] = {
    "brushing": [
        r"\b(brush|brushing|toothbrush|toothbrushes)\b",
        r"\bhow to brush\b",
        r"\bproper brushing\b",
    ],
    "flossing": [
        r"\b(floss|flossing|dental floss)\b",
        r"\bhow to floss\b",
    ],
    "bleeding_gums": [
        r"\b(bleeding gums?|gums? bleed(ing)?|gum inflammation)\b",
        r"\bgingivitis\b",
    ],
    "sensitivity": [
        r"\b(tooth sensitivity|teeth sensitivity|sensitive to (cold|hot)|cold sensitivity|hot sensitivity)\b",
        r"\bsensitive teeth\b",
    ],
    "discoloration": [
        r"\b(discoloration|discolouration|yellow teeth|stained teeth|teeth stains?|extrinsic stain|intrinsic stain|tooth whitening)\b",
    ],
    "tartar": [
        r"\b(tartar|dental calculus|calculus buildup|hardened plaque|plaque mineralization|ultrasonic scaling)\b",
    ],
    "cavity": [
        r"\b(cavity|cavities|tooth decay|dental caries|enamel demineralization)\b",
    ],
    "ulcer": [
        r"\b(canker sores?|mouth ulcers?|aphthous ulcers?|oral sores?)\b",
    ],
    "bad_breath": [
        r"\b(bad breath|halitosis|breath odor|tongue scraper)\b",
    ],
    "mouthwash": [
        r"\b(mouthwash|oral rinse|mouth rinse|antibacterial rinse)\b",
    ],
    "checkup": [
        r"\b(routine checkup|dental checkup|checkup frequency|routine cleaning|every 6 months)\b",
    ],
}

# Finding key to topic mapping (only used when query or follow-up explicitly matches)
FINDING_TOPIC_MAP: dict[str, str] = {
    "discoloration": "discoloration",
    "tartar": "tartar",
    "plaque": "tartar",
    "cavity_suspect": "cavity",
    "cavity_advanced": "cavity",
    "gingivitis_signs": "bleeding_gums",
    "gum_disease_severe": "bleeding_gums",
    "oral_ulcer": "ulcer",
}


def lookup_dental_knowledge(
    query_text: str,
    finding_key: Optional[str] = None,
    allow_finding_fallback: bool = False,
) -> Optional[str]:
    """Retrieve relevant curated oral health snippet based on strict query relevance.

    If query relevance is below threshold, returns None so LLM answers dynamically.
    Never forces an unrelated guideline into the prompt.
    """
    if not query_text:
        return None

    query_lower = query_text.lower().strip()

    # 1. First, check direct keyword/phrase match against curated topics
    best_topic: Optional[str] = None
    best_score = 0

    for topic_name, patterns in KNOWLEDGE_TOPIC_MATCHERS.items():
        score = sum(1 for p in patterns if re.search(p, query_lower))
        if score > best_score:
            best_score = score
            best_topic = topic_name

    # Topic match requires at least 1 explicit word-boundary match
    if best_topic and best_score >= 1:
        return KNOWLEDGE_TOPICS[best_topic]["content"]

    # 2. Only consider finding_key if caller explicitly allows finding fallback
    # AND the query is an anaphoric follow-up (e.g. "what is that?", "why did it flag it?")
    if allow_finding_fallback and finding_key and finding_key in FINDING_TOPIC_MAP:
        topic_key = FINDING_TOPIC_MAP[finding_key]
        if topic_key in KNOWLEDGE_TOPICS:
            return KNOWLEDGE_TOPICS[topic_key]["content"]

    return None


def find_relevant_knowledge(query_text: str) -> list[str]:
    """Retrieve matching knowledge base entries as a list of strings."""
    entry = lookup_dental_knowledge(query_text)
    return [entry] if entry else []
