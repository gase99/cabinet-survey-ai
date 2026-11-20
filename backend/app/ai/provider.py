"""Provider-neutral AI boundary. Implementations must return proposals, never approved facts."""
from typing import Any, Protocol
import re
from app.domain.measurements import normalize_numerals, to_mm

class VisionProvider(Protocol):
    async def analyze_sketch(self, image_bytes: bytes, *, language_hint: str = "fa,en") -> dict[str, Any]:
        """Return source-linked observations and ambiguities for human review."""
        ...

class TextProvider(Protocol):
    async def parse_measurements(self, text: str, *, language_hint: str = "fa,en") -> dict[str, Any]:
        ...

class AIUnavailableError(RuntimeError):
    pass

# ---------- Deterministic merged parser (labeled + spoken transcripts) ----------

def parse_measurements_any(text: str) -> dict[str, Any]:
    """Deterministic extraction for labeled text and spoken transcripts, merged.

    Labeled evidence ("دیوار A: ۳۲۰۰ میلی‌متر") wins on overlap because it is
    the most explicit form; spoken observations are kept when they do not
    duplicate a labeled match. No value is ever invented by either path.
    """
    from app.domain.spoken_measurements import parse_spoken_measurements, normalize as spoken_normalize

    normalized = spoken_normalize(text)
    spoken = parse_spoken_measurements(normalized)
    labeled = parse_text_measurements_deterministic(normalized)
    labeled_spans = [(match.start(), match.end()) for match in MEASUREMENT_RE.finditer(normalized)]

    def overlaps_labeled(span: list[int]) -> bool:
        return any(not (span[1] <= start or span[0] >= end) for start, end in labeled_spans)

    observations = list(labeled["observations"]) + [
        observation for observation in spoken["observations"]
        if not overlaps_labeled(observation["source_span"])
    ]
    ambiguities: list[dict[str, Any]] = []
    seen_ambiguities: set[tuple[str, str]] = set()
    # The labeled format ("label: value unit") only matches colon-separated
    # text; its absence-of-structure complaints are noise when the spoken path
    # already extracted proposals from the same transcript.
    labeled_noise = {"no_structured_extraction", "no_measurements"}
    labeled_ambiguities = [ambiguity for ambiguity in labeled["ambiguities"]
                           if ambiguity.get("type") not in labeled_noise or not observations]
    for ambiguity in [*labeled_ambiguities, *spoken["ambiguities"]]:
        key = (ambiguity.get("type", ""), ambiguity.get("detail", ""))
        if key not in seen_ambiguities:
            seen_ambiguities.add(key)
            ambiguities.append(ambiguity)
    questions: list[str] = []
    for question in [*labeled["clarification_questions"], *spoken["clarification_questions"]]:
        if question not in questions:
            questions.append(question)
    return {
        "observations": observations,
        "ambiguities": ambiguities,
        "clarification_questions": questions,
        "provider": "deterministic_local",
        "disclaimer": labeled["disclaimer"],
    }


# ---------- Deterministic explicit-text parser ----------

# Regex for measurements like "Wall A: 3200 mm" or Persian "دیوار A: ۳۲۰۰ میلی‌متر"
# Handles: number + unit, with optional label
MEASUREMENT_RE = re.compile(
    r"(?P<label>[^\n:؛:]{1,60}?)\s*[:：]\s*(?P<value>[\d\u06F0-\u06F9\u0660-\u06690-9\.,٫،]+)\s*(?P<unit>mm|cm|m|millimeter|millimetre|centimeter|centimetre|meter|metre|in|inch|ft|foot|میلی‌?متر|سانت[یي]‌?متر|متر)?",
    re.IGNORECASE,
)

UNIT_NORMALIZE = {
    "میلی‌متر": "mm", "میلیمتر": "mm", "میلی متر": "mm",
    "سانتی‌متر": "cm", "سانتیمتر": "cm", "سانتیمتر": "cm", "سانت": "cm",
    "متر": "m",
}

def parse_text_measurements_deterministic(text: str) -> dict[str, Any]:
    """
    Deterministic parser for natural language measurements.
    Never invents values — only extracts explicit number+unit pairs.
    Returns proposal observations with source regions omitted (text).
    """
    normalized = normalize_numerals(text)
    observations = []
    ambiguities = []
    for m in MEASUREMENT_RE.finditer(normalized):
        label = m.group("label").strip()
        value_raw = m.group("value").strip().replace(",", "")
        if not m.group("unit"):
            ambiguities.append({"type": "missing_unit", "raw": m.group(0),
                "detail": "Measurement unit is missing; please specify it explicitly."})
            continue
        unit_raw = m.group("unit").strip().lower()
        # normalize Persian unit
        unit_norm = UNIT_NORMALIZE.get(unit_raw, unit_raw)
        if unit_norm not in ("mm", "cm", "m", "in", "inch", "ft", "foot", "millimeter", "millimetre", "centimeter", "centimetre", "meter", "metre"):
            # try lower fallback
            if unit_norm not in ("mm","cm","m"):
                ambiguities.append({
                    "type": "unknown_unit",
                    "raw": m.group(0),
                    "detail": f"Unrecognized unit '{unit_raw}' for '{label}'",
                    "confidence": 0.5,
                })
                continue
        try:
            value_f = float(value_raw)
        except ValueError:
            ambiguities.append({
                "type": "unparsable_number",
                "raw": m.group(0),
                "detail": f"Could not parse number '{value_raw}'",
                "confidence": 0.4,
            })
            continue
        try:
            value_mm = to_mm(value_f, unit_norm)
        except ValueError as e:
            ambiguities.append({"type": "unit_error", "raw": m.group(0), "detail": str(e), "confidence": 0.4})
            continue

        # Heuristic: if value_mm is suspiciously small/large, flag
        if value_mm < 10 or value_mm > 20000:
            ambiguities.append({
                "type": "suspicious_value",
                "label": label,
                "value_mm": value_mm,
                "detail": f"Value {value_mm} mm outside typical range for '{label}'",
                "confidence": 0.6,
            })

        observations.append({
            "label": label,
            "value_raw": m.group("value").strip(),
            "value_mm": value_mm,
            "unit": unit_norm,
            "source_text": m.group(0),
            "confidence": 0.92,
            "needs_review": True,
            "type": "dimension",
        })

    # If no matches but text contains numbers, flag as incomplete
    has_numbers = bool(re.search(r"[\d\u06F0-\u06F9]", normalized))
    if not observations and has_numbers:
        ambiguities.append({
            "type": "no_structured_extraction",
            "detail": "Text contains numbers but no label: value + unit pattern was found. Please use format 'Label: value unit'.",
            "confidence": 0.3,
        })
    elif not observations and not has_numbers:
        ambiguities.append({
            "type": "no_measurements",
            "detail": "No measurements detected. Provide dimensions like 'Wall A: 3200 mm'.",
            "confidence": 0.2,
        })

    # Always return clarification questions for missing typical fields
    clarification_questions = []
    labels_found = {o["label"].lower() for o in observations}
    # Don't invent missing, just ask
    # Example: if we saw walls but no heights
    if observations and not any("height" in l or "ارتفاع" in l for l in labels_found):
        clarification_questions.append("Wall height not specified — please provide wall height(s).")

    return {
        "observations": observations,
        "ambiguities": ambiguities,
        "clarification_questions": clarification_questions,
        "provider": "deterministic_local",
        "disclaimer": "AI proposals are candidate observations only and require user approval before becoming authoritative.",
    }

class DisabledProvider:
    async def analyze_sketch(self, image_bytes: bytes, *, language_hint: str = "fa,en") -> dict[str, Any]:
        raise AIUnavailableError("AI provider is disabled. Configure AI_PROVIDER and AI_API_KEY.")

    async def parse_measurements(self, text: str, *, language_hint: str = "fa,en") -> dict[str, Any]:
        raise AIUnavailableError("AI provider is disabled.")

class DeterministicLocalProvider:
    """Local deterministic parser — no network, used for tests and offline fallback for text."""
    async def analyze_sketch(self, image_bytes: bytes, *, language_hint: str = "fa,en") -> dict[str, Any]:
        # For images without a real vision model, we return a structured placeholder
        # that tells the client human review / manual entry is required.
        # We NEVER infer dimensions from pixels.
        return {
            "observations": [],
            "ambiguities": [{
                "type": "vision_unavailable",
                "detail": "Automated vision extraction requires a configured AI provider. Please enter measurements manually or configure an AI provider.",
                "confidence": 0.0,
            }],
            "clarification_questions": ["Please manually enter wall dimensions visible in the sketch."],
            "provider": "deterministic_local",
            "image_received_bytes": len(image_bytes),
            "disclaimer": "No dimensions were inferred from image pixels. All values must be entered or approved by user.",
        }

    async def parse_measurements(self, text: str, *, language_hint: str = "fa,en") -> dict[str, Any]:
        return parse_text_measurements_deterministic(text)

# Provider factory
def get_ai_provider(name: str):
    if name == "disabled":
        return DisabledProvider()
    if name in ("local", "deterministic", "mock"):
        return DeterministicLocalProvider()
    if name == "openai_compatible":
        from app.ai.online import OpenAICompatibleProvider
        return OpenAICompatibleProvider()
    raise AIUnavailableError("Unknown AI provider")
