"""OpenRouter vision API — dental visual findings as structured JSON."""

from __future__ import annotations

import base64
import json
import logging
import re

import httpx

from dantshaant_common.schemas import VisualFinding

from teeth_analyzer.config import settings

logger = logging.getLogger(__name__)

VISION_PROMPT = """You are a dental vision assistant analyzing a photo of teeth or the mouth.
Inspect carefully for: cavities/decay, plaque, tartar, gum inflammation, discoloration,
missing or damaged teeth, cracks, and overall oral health.

Return ONLY valid JSON (no markdown fences) in this exact shape:
{
  "findings": [
    {"label": "<snake_case_label>", "confidence": 0.0-1.0, "region": "<optional area>"}
  ]
}

Allowed labels (use the most specific match):
- healthy_tissue — only if teeth and gums look clearly healthy
- plaque_detected
- tartar
- cavity_suspect — early decay, dark spots, holes starting
- cavity_advanced — obvious large cavities or severe decay
- gingivitis_signs — red/swollen/bleeding gums
- gum_disease_severe
- discoloration — yellow/brown/stained teeth
- missing_or_damaged_teeth — broken, chipped, or missing teeth

Rules:
- List ALL visible issues, not only the dominant one.
- Do NOT label healthy_tissue with high confidence if decay, heavy plaque, or gum disease is visible.
- If the image is not a clear teeth/mouth photo, return one finding: unknown with low confidence.
- Be clinically conservative: flag suspected problems rather than calling severe cases healthy.
Locale hint: __LOCALE__.
"""


def _build_prompt(locale: str) -> str:
    return VISION_PROMPT.replace("__LOCALE__", locale)


def _parse_findings(text: str) -> list[VisualFinding]:
    """Parse JSON findings from model response."""
    text = text.strip()
    
    # Remove markdown code fences if present
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    
    # Extract JSON object
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        text = match.group(0)
    
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON: {e}\nText: {text}")
        return [VisualFinding(label="unknown", confidence=0.3, region="general")]
    
    raw = data.get("findings", data if isinstance(data, list) else [])
    findings: list[VisualFinding] = []
    
    for item in raw:
        findings.append(
            VisualFinding(
                label=str(item.get("label", "unknown")).lower().replace(" ", "_"),
                confidence=float(item.get("confidence", 0.5)),
                region=item.get("region"),
            )
        )
    
    return findings or [VisualFinding(label="unknown", confidence=0.3, region="general")]


def analyze_with_openrouter(jpeg_bytes: bytes, locale: str) -> list[VisualFinding]:
    """
    Analyze teeth image using OpenRouter API with vision-capable models.
    
    OpenRouter provides access to multiple vision models including:
    - google/gemini-flash-1.5
    - google/gemini-pro-1.5
    - anthropic/claude-3.5-sonnet
    - openai/gpt-4-vision-preview
    """
    if not settings.openrouter_api_key:
        raise RuntimeError(
            "TEETH_ANALYZER_OPENROUTER_API_KEY is not set. Add it to the repo root .env file."
        )
    
    # Encode image to base64
    image_base64 = base64.b64encode(jpeg_bytes).decode("utf-8")
    
    # Build the prompt
    prompt = _build_prompt(locale)
    
    # Prepare the request
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/Develosphere/DaantShant",
        "X-Title": "DaantShaant Teeth Analyzer",
    }
    
    # OpenRouter uses standard OpenAI-compatible format
    payload = {
        "model": settings.openrouter_model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt,
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}"
                        },
                    },
                ],
            }
        ],
        "temperature": 0.1,
        "max_tokens": 1024,
    }
    
    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
            )
            
            # Log the response for debugging
            logger.info(f"OpenRouter response status: {response.status_code}")
            
            response.raise_for_status()
            
            result = response.json()
            
            # Extract the response text
            if "choices" not in result or len(result["choices"]) == 0:
                raise RuntimeError(f"OpenRouter returned no choices: {result}")
            
            text = result["choices"][0]["message"]["content"]
            
            # Parse findings
            findings = _parse_findings(text)
            logger.info("OpenRouter findings: %s", [f.model_dump() for f in findings])
            
            return findings
            
    except httpx.HTTPStatusError as e:
        error_detail = e.response.text
        try:
            error_json = e.response.json()
            error_detail = error_json.get("error", {}).get("message", error_detail)
        except Exception:
            pass
        logger.error(f"OpenRouter API error: {error_detail}")
        raise RuntimeError(
            f"OpenRouter API error (status {e.response.status_code}): {error_detail}"
        ) from e
    except httpx.RequestError as e:
        raise RuntimeError(f"OpenRouter request failed: {e}") from e
    except Exception as e:
        logger.exception("OpenRouter analysis failed")
        raise RuntimeError(f"OpenRouter analysis failed: {e}") from e
