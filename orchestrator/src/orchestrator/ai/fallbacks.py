"""Provider-independent deterministic dental fallback responses.

Relocated from the legacy ``llm_provider`` module (Phase 2A.5c).
Pure data + keyword matching — no AI provider, no networking, no HTTP client.
"""

from typing import Optional


# ---------------------------------------------------------------------------
# Deterministic dental fallback responses (issue-aware)
# ---------------------------------------------------------------------------

DENTAL_FALLBACKS = {
    "bleeding gums": (
        "Gums often bleed because plaque irritates the gum tissue. "
        "Gentle brushing with a soft-bristled brush, daily flossing, and "
        "warm saltwater rinses usually help reduce the inflammation over time."
    ),
    "toothache": (
        "A toothache can happen because of cavities, sensitivity, gum "
        "inflammation, or even a small crack in the tooth. Over-the-counter "
        "pain relief and a warm saltwater rinse can help for now, but if it "
        "persists or worsens, a dental check-up is recommended."
    ),
    "sensitivity": (
        "Tooth sensitivity is usually caused by thinning enamel or receding "
        "gums that expose the inner layer of the tooth. Using a sensitivity "
        "toothpaste and avoiding very hot or cold foods can help. If it "
        "keeps happening, a dentist can check for cracks or decay."
    ),
    "tartar/plaque buildup": (
        "Hard yellow buildup near the gums is often tartar — hardened plaque "
        "that can't usually be removed by brushing alone. A professional "
        "dental cleaning is the best way to get rid of it and prevent gum "
        "irritation."
    ),
    "discolored teeth": (
        "Teeth can become yellow or stained from coffee, tea, smoking, or "
        "just natural aging of the enamel. Regular brushing with a whitening "
        "toothpaste helps with surface stains. For deeper discoloration, "
        "a dentist can suggest safe whitening options."
    ),
    "cavity/tooth decay": (
        "Cavities form when bacteria in your mouth produce acid that eats "
        "into the tooth enamel. Small cavities might not hurt at first, "
        "but they can grow if left untreated. A dentist can fill them before "
        "they get worse."
    ),
    "bad breath": (
        "Bad breath is often caused by bacteria on the tongue, food stuck "
        "between teeth, or gum issues. Brushing your tongue, flossing daily, "
        "and staying hydrated usually helps. If it sticks around, it could "
        "be worth a dental check-up."
    ),
    "swollen gums": (
        "Swollen gums are usually a sign of inflammation from plaque buildup "
        "or the early stages of gum disease. Gentle brushing along the gum "
        "line, flossing, and saltwater rinses can help bring the swelling "
        "down over time."
    ),
    "loose tooth": (
        "A loose tooth in adults is usually caused by gum disease that has "
        "weakened the supporting bone, or sometimes by injury. This is "
        "definitely worth seeing a dentist about as soon as possible to "
        "prevent further damage."
    ),
    "gum pain": (
        "Sore gums can happen because of irritation from plaque, brushing "
        "too hard, or the start of gum disease. Try switching to a "
        "soft-bristled brush and doing warm saltwater rinses. If it "
        "continues for more than a week, check in with a dentist."
    ),
    "wisdom tooth": (
        "Wisdom teeth can cause pain and swelling when they're coming in, "
        "especially if there isn't enough room or they're growing at an "
        "angle. Rinsing with warm saltwater helps with discomfort. A dentist "
        "can take an X-ray to see what's going on."
    ),
    "broken tooth": (
        "A broken or chipped tooth can be caused by biting something hard, "
        "an injury, or weakened enamel. Avoid chewing on that side and see "
        "a dentist as soon as you can — they can bond, cap, or fill the "
        "tooth depending on the damage."
    ),
    "jaw pain": (
        "Jaw pain can come from teeth grinding, TMJ issues, or tension in "
        "the jaw muscles. Avoiding hard or chewy foods and applying a warm "
        "compress can help. If it persists or your jaw clicks or locks, "
        "a dentist or TMJ specialist can help."
    ),
    "mouth ulcer": (
        "Mouth ulcers are usually caused by minor irritation, stress, or "
        "certain foods. They typically heal on their own within a week or "
        "two. Rinsing with warm saltwater or using an over-the-counter "
        "gel can help with the discomfort."
    ),
    "dry mouth": (
        "Dry mouth happens when your salivary glands don't produce enough "
        "saliva, which can increase the risk of cavities. Staying hydrated, "
        "chewing sugar-free gum, and avoiding caffeine and alcohol can help. "
        "If it continues, mention it to your dentist."
    ),
}

# Generic dental fallback when no specific issue is detected
GENERIC_DENTAL_FALLBACK = (
    "Good oral health starts with brushing twice a day with fluoride "
    "toothpaste, flossing daily, and visiting your dentist for regular "
    "check-ups. If you're experiencing any specific dental issue, feel "
    "free to describe it and I can give you more targeted advice."
)


def get_deterministic_fallback(user_message: str, active_issue: Optional[str] = None) -> str:
    """Return a deterministic, issue-aware dental response.

    Tries to match the active conversation issue first, then scans
    the user message for keywords.
    """
    # 1. Use active issue from conversation state if available
    if active_issue and active_issue in DENTAL_FALLBACKS:
        return DENTAL_FALLBACKS[active_issue]

    # 2. Scan user message for issue keywords
    text_lower = user_message.lower()
    keyword_map = {
        "bleed": "bleeding gums",
        "bleeding": "bleeding gums",
        "blood": "bleeding gums",
        "toothache": "toothache",
        "tooth hurt": "toothache",
        "tooth pain": "toothache",
        "teeth hurt": "toothache",
        "teeth pain": "toothache",
        "sensitive": "sensitivity",
        "sensitivity": "sensitivity",
        "tartar": "tartar/plaque buildup",
        "plaque": "tartar/plaque buildup",
        "yellow stuff": "tartar/plaque buildup",
        "yellow teeth": "discolored teeth",
        "stain": "discolored teeth",
        "cavity": "cavity/tooth decay",
        "decay": "cavity/tooth decay",
        "bad breath": "bad breath",
        "swollen gum": "swollen gums",
        "gum swell": "swollen gums",
        "loose tooth": "loose tooth",
        "gum hurt": "gum pain",
        "gum pain": "gum pain",
        "sore gum": "gum pain",
        "wisdom": "wisdom tooth",
        "broken tooth": "broken tooth",
        "chipped": "broken tooth",
        "cracked tooth": "broken tooth",
        "jaw": "jaw pain",
        "tmj": "jaw pain",
        "ulcer": "mouth ulcer",
        "canker": "mouth ulcer",
        "dry mouth": "dry mouth",
    }

    for keyword, issue_key in keyword_map.items():
        if keyword in text_lower:
            return DENTAL_FALLBACKS[issue_key]

    return GENERIC_DENTAL_FALLBACK
