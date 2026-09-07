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


def lookup_dental_knowledge(query_text: str, finding_key: Optional[str] = None) -> Optional[str]:
    """Retrieve relevant curated oral health snippet based on query keywords or active finding."""
    query_lower = query_text.lower()

    if finding_key:
        if finding_key in ("discoloration",):
            return KNOWLEDGE_TOPICS["discoloration"]["content"]
        if finding_key in ("tartar", "plaque"):
            return KNOWLEDGE_TOPICS["tartar"]["content"]
        if finding_key in ("cavity_suspect", "cavity_advanced"):
            return KNOWLEDGE_TOPICS["cavity"]["content"]
        if finding_key in ("gingivitis_signs", "gum_disease_severe"):
            return KNOWLEDGE_TOPICS["bleeding_gums"]["content"]
        if finding_key in ("oral_ulcer",):
            return KNOWLEDGE_TOPICS["ulcer"]["content"]

    if any(w in query_lower for w in ("brush", "brushing", "toothbrush", "paste")):
        return KNOWLEDGE_TOPICS["brushing"]["content"]
    if any(w in query_lower for w in ("floss", "flossing")):
        return KNOWLEDGE_TOPICS["flossing"]["content"]
    if any(w in query_lower for w in ("mouthwash", "rinse", "mouth wash")):
        return KNOWLEDGE_TOPICS["mouthwash"]["content"]
    if any(w in query_lower for w in ("checkup", "check-up", "routine visit", "how often should i see a dentist", "frequency")):
        return KNOWLEDGE_TOPICS["checkup"]["content"]
    if any(w in query_lower for w in ("bleed", "bleeding", "gums bleed", "gingivitis")):
        return KNOWLEDGE_TOPICS["bleeding_gums"]["content"]
    if any(w in query_lower for w in ("sensitive", "sensitivity", "cold water", "cold drink")):
        return KNOWLEDGE_TOPICS["sensitivity"]["content"]
    if any(w in query_lower for w in ("yellow", "stain", "color", "discoloration")):
        return KNOWLEDGE_TOPICS["discoloration"]["content"]
    if any(w in query_lower for w in ("tartar", "calculus", "hard buildup")):
        return KNOWLEDGE_TOPICS["tartar"]["content"]
    if any(w in query_lower for w in ("cavity", "cavities", "decay", "caries")):
        return KNOWLEDGE_TOPICS["cavity"]["content"]
    if any(w in query_lower for w in ("ulcer", "canker", "sore", "blister")):
        return KNOWLEDGE_TOPICS["ulcer"]["content"]
    if any(w in query_lower for w in ("breath", "halitosis", "odor")):
        return KNOWLEDGE_TOPICS["bad_breath"]["content"]

    return None


def find_relevant_knowledge(query_text: str) -> list[str]:
    """Retrieve matching knowledge base entries as a list of strings."""
    entry = lookup_dental_knowledge(query_text)
    return [entry] if entry else []
