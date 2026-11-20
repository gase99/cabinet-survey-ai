"""Deterministic spoken-measurement extraction for Persian (fa) and English transcripts.

Rules enforced by this module:
- Never invent values: only explicit number+unit evidence becomes an observation.
- Unit-less or ambiguous phrases become ambiguities/clarification questions, never
  silently approved dimensions.
- Every observation keeps its exact source span, so the UI can show what was said.
- Observations are proposals (needs_review=True); approval is a separate human action.
- Coordinates are never produced here; geometry stays under the deterministic engine.

English spoken numbers are intentionally out of scope: transcription services emit
digits for numbers ("2.7 meters"), so digits are the English evidence path. Persian
spoken numbers are parsed fully, including compounds ("سه متر و بیست سانتی‌متر"),
scale words ("سه هزار و دویست میلی‌متر") and elided tail units ("سه متر و بیست").
"""
import re
from typing import Any

from app.domain.measurements import normalize_numerals

# Persian word numerals. Any alternation that contains shorter substrings must
# list longer tokens first (e.g. "سیصد" before "سی").
_UNITS = {
    "صفر": 0, "یک": 1, "دو": 2, "سه": 3, "چهار": 4, "پنج": 5, "شش": 6,
    "هفت": 7, "هشت": 8, "نه": 9, "ده": 10,
    "یازده": 11, "دوازده": 12, "سیزده": 13, "چهارده": 14, "پانزده": 15, "پونزده": 15,
    "شانزده": 16, "هفده": 17, "هجده": 18, "نوزده": 19,
    "بیست": 20, "سی": 30, "چهل": 40, "پنجاه": 50, "شصت": 60, "هفتاد": 70,
    "هشتاد": 80, "نود": 90,
    "صد": 100, "یکصد": 100, "دویست": 200, "سیصد": 300, "چهارصد": 400,
    "پانصد": 500, "پونصد": 500, "ششصد": 600, "هفتصد": 700, "هشتصد": 800, "نهصد": 900,
}
_SCALES = {"هزار": 1000, "میلیون": 1_000_000}

_PERSIAN_LETTER = r"\u0621-\u064A\u066E-\u06D3"
_NO_PERSIAN_AFTER = rf"(?![{_PERSIAN_LETTER}])"
_NO_PERSIAN_BEFORE = rf"(?<![{_PERSIAN_LETTER}])"

_UNIT_TOKEN_ALTERNATION = "|".join(
    re.escape(token) for token in sorted(list(_UNITS) + list(_SCALES), key=len, reverse=True)
)

# A word number: tokens joined by spaces with optional "و" connectors. Letter
# lookarounds on every token keep numerals from matching inside other words
# ("پنج" inside "پنجره", "سی" inside "سیب").
_WORD_NUM = (
    rf"{_NO_PERSIAN_BEFORE}(?:{_UNIT_TOKEN_ALTERNATION}){_NO_PERSIAN_AFTER}"
    rf"(?:[\s]+(?:و[\s]+)?{_NO_PERSIAN_BEFORE}(?:{_UNIT_TOKEN_ALTERNATION}){_NO_PERSIAN_AFTER})*"
)
_DIGITS = r"\d+(?:\.\d+)?"
_VALUE = rf"(?:{_DIGITS}|{_WORD_NUM})"

# Units, longest first. A trailing letter lookahead keeps English "m" from
# matching inside "mm"/"meter" and keeps Persian "متر" from matching "متری".
_UNIT_MM = r"میلی[\s]+متر|میلیمتر|میلی|millimet(?:er|re)s?|mm"
_UNIT_CM = r"سانتی[\s]+متر|سانتیمتر|سانت[\s]+متر|سانتی|سانت|centimet(?:er|re)s?|cm"
_UNIT_M = r"متر|met(?:er|re)s?|m"
_UNIT_PATTERN = rf"(?:{_UNIT_MM}|{_UNIT_CM}|{_UNIT_M}){_NO_PERSIAN_AFTER}(?![A-Za-z])"

_UNIT_SCALE = {"mm": 1, "cm": 10, "m": 1000}
_WORD_UNITS = {
    "میلی متر": "mm", "میلیمتر": "mm", "میلی": "mm",
    "سانتی متر": "cm", "سانتیمتر": "cm", "سانت متر": "cm", "سانتی": "cm", "سانت": "cm",
    "متر": "m",
}

# Bare connectors that may join the parts of one compound measurement. A comma
# or any other word separates distinct measurements and must never merge them.
_CONNECTOR = r"[\s]*و[\s]*|[\s]+and[\s]+"

VALUE_RE = re.compile(
    rf"(?P<value>{_VALUE})(?:[\s]*(?P<unit>{_UNIT_PATTERN}))?",
    re.IGNORECASE,
)

# Context keywords. Order matters: the most specific kind wins.
_KIND_KEYWORDS = [
    ("wall_cabinet_depth", r"کابینت[\s]+دیواری|کابینت[\s]+هودی|هودی"),
    ("base_cabinet_depth", r"کابینت[\s]+زمینی|کابینت[\s]+پایه|کابینت[\s]+آشپزخانه"),
    ("wall_length", r"طول[\s]+دیوار|دیوار[\s]+به[\s]+طول"),
    ("wall_height", r"ارتفاع[\s]+دیوار|دیوار[\s]+به[\s]+ارتفاع"),
    ("window", r"پنجره"),
    ("door", r"درب"),
    ("pipe", r"لوله|شیر[\s]+آب|شیر[\s]+گاز|فاضلاب|سیفون"),
    ("electrical", r"پریز|کلید"),
    ("column", r"ستون"),
    ("beam", r"تیر"),
    ("length", r"طول"),
    ("width", r"عرض"),
    ("height", r"ارتفاع"),
    ("depth", r"عمق"),
]
_WALL_RE = re.compile(r"دیوار")

_CORRECTION_RE = re.compile(
    rf"{_NO_PERSIAN_BEFORE}(?:نه نه|نه)(?=[\s]*[,،;؛.]|$)"
    rf"|{_NO_PERSIAN_BEFORE}(?:اشتباه|غلط|اصلاح){_NO_PERSIAN_AFTER}"
    r"|\b(?:no|wrong|correction|actually)\b",
    re.IGNORECASE,
)

# Segments split on sentence punctuation. A decimal point between digits is
# never a sentence separator ("2.7 meters" stays one segment).
_SEGMENT_SPLIT_RE = re.compile(
    rf"(?<!\d)\.(?!\d)|[!؟?\n؛;]+"
)

# Elided tail unit ("سه متر و بیست"): the tail must fit inside the previous
# unit's ratio to be interpreted at all; everything else stays a question.
_ELIDED_TAILS = {"m": (1, 99, "cm"), "cm": (1, 9, "mm")}

MAX_PLAUSIBLE_MM = 20_000
MIN_PLAUSIBLE_MM = 10

DISCLAIMER = (
    "Spoken measurements are candidate proposals extracted verbatim from the transcript. "
    "They require explicit user approval and are never authoritative geometry."
)


def normalize(text: str) -> str:
    """Unify numeral systems, Arabic letter variants, separators and ZWNJ."""
    text = normalize_numerals(text)
    # Arabic Yeh/Kaf to Persian and ZWNJ to a plain space so unit words match
    # written, spoken and mixed variants deterministically.
    text = text.replace("ي", "ی").replace("ك", "ک").replace("\u200c", " ")
    return text.replace("٫", ".").replace("،", ",")


def _compose(tokens: list[str]) -> int:
    """Compose a Persian word number: 3*1000 + 200 -> 3200."""
    total = 0
    current = 0
    for token in tokens:
        if token in _UNITS:
            current += _UNITS[token]
        elif token in _SCALES:
            current = (current if current > 0 else 1) * _SCALES[token]
            total += current
            current = 0
    return total + current


def _word_value(value_text: str) -> int | None:
    # Split on whitespace or the standalone conjunction "و"; the bounded "و"
    # never splits inside numerals themselves ("دو" must stay "دو").
    tokens = [token for token in re.split(
        rf"[\s]+|{_NO_PERSIAN_BEFORE}و{_NO_PERSIAN_AFTER}", value_text.strip()) if token]
    if not tokens or not all(t in _UNITS or t in _SCALES for t in tokens):
        return None
    return _compose(tokens)


def _unit_code(unit_text: str | None) -> str | None:
    if not unit_text:
        return None
    lowered = re.sub(r"\s+", " ", unit_text.strip().lower())
    if lowered in _WORD_UNITS:
        return _WORD_UNITS[lowered]
    compact = lowered.replace(" ", "")
    for code, names in (("mm", ("mm", "millimeter", "millimetre")),
                        ("cm", ("cm", "centimeter", "centimetre")),
                        ("m", ("m", "meter", "metre"))):
        if compact in names:
            return code
    return None


def _to_mm(value: float, unit: str) -> int:
    return int(round(value * _UNIT_SCALE[unit]))


def _match_value(match: re.Match[str]) -> float | None:
    text = match.group("value")
    if any(character.isdigit() for character in text):
        try:
            return float(text)
        except ValueError:
            return None
    spoken = _word_value(text)
    return None if spoken is None else float(spoken)


def _kind_label(kind: str | None) -> str:
    return _KIND_LABELS.get(kind or "", kind or "measurement")


_KIND_WINDOW = 48


def _kind_near(segment: str, start: int, end: int) -> str | None:
    """Infer the measurement kind from context words nearest to the value span.

    A segment may contain several measurements ("دیوار سه متر طول دارد و ارتفاع
    دیوار ۲۷۰۰ میلی‌متر است"); kind inference must therefore be per value span,
    not per segment, and can never be more specific than its evidence.
    """
    before = segment[max(0, start - _KIND_WINDOW):start]
    after = segment[end:end + _KIND_WINDOW]
    best_kind: str | None = None
    best_distance = _KIND_WINDOW + 1
    for text, distance_of in ((before, lambda position: len(before) - position),
                              (after, lambda position: position)):
        for kind, pattern in _KIND_KEYWORDS:
            match = None
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                pass
            if match is not None:
                distance = distance_of(match.end() if text is before else match.start())
                if distance < best_distance:
                    best_kind, best_distance = kind, distance
    if best_kind in ("length", "height") and (
            _WALL_RE.search(before[-24:]) or _WALL_RE.search(after[:24])):
        return "wall_length" if best_kind == "length" else "wall_height"
    return best_kind


_KIND_LABELS = {
    "wall_length": "wall length",
    "wall_height": "wall height",
    "base_cabinet_depth": "base cabinet depth",
    "wall_cabinet_depth": "wall cabinet depth",
}


def _kind_label(kind: str | None) -> str:
    return _KIND_LABELS.get(kind or "", kind or "measurement")


def _source_slice(segment: str, start: int, end: int) -> str:
    return re.sub(r"\s+", " ", segment[start:end]).strip()


def _segments(text: str) -> list[str]:
    return [segment for segment in _SEGMENT_SPLIT_RE.split(text) if segment.strip()]


def _observation(
    source_text: str,
    span: list[int],
    value_mm: int,
    unit: str,
    kind: str | None,
    correcting: bool,
    *,
    extra_ambiguity: tuple[str, str] | None,
    ambiguities: list[dict[str, Any]],
) -> dict[str, Any]:
    if extra_ambiguity is not None:
        ambiguities.append({
            "type": extra_ambiguity[0],
            "detail": extra_ambiguity[1],
            "source_text": source_text,
            "confidence": 0.6,
        })
    if value_mm < MIN_PLAUSIBLE_MM or value_mm > MAX_PLAUSIBLE_MM:
        ambiguities.append({
            "type": "suspicious_value",
            "label": _kind_label(kind),
            "value_mm": value_mm,
            "detail": f"Value {value_mm} mm outside the typical range for '{_kind_label(kind)}'.",
            "source_text": source_text,
            "confidence": 0.6,
        })
    return {
        "label": _kind_label(kind),
        "kind": kind,
        "intent": "correction" if correcting else "statement",
        "value_raw": source_text,
        "value_mm": value_mm,
        "unit": unit,
        "source_text": source_text,
        "source_span": span,
        "confidence": 0.9,
        "needs_review": True,
        "type": "dimension",
    }


def _missing_unit_ambiguity(ambiguities: list[dict[str, Any]], source_text: str) -> None:
    ambiguities.append({
        "type": "missing_unit",
        "detail": "Measurement unit is missing; specify millimetres, centimetres or metres.",
        "source_text": source_text,
        "confidence": 0.5,
    })


def _word_join_ambiguity(ambiguities: list[dict[str, Any]], source_text: str) -> None:
    ambiguities.append({
        "type": "spoken_number_join",
        "detail": (
            "Confirm the spoken number: 'X و Y' was read as the composed number; "
            "if it meant a decimal value, correct it."
        ),
        "source_text": source_text,
        "confidence": 0.6,
    })


def _chain_observations(
    segment: str,
    matches: list[re.Match[str]],
    chain: list[int],
    kind: str | None,
    correcting: bool,
    ambiguities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Turn one connector-joined chain of value(+unit) matches into observations."""
    def value_of(position: int) -> float | None:
        return _match_value(matches[position])

    def unit_of(position: int) -> str | None:
        return _unit_code(matches[position].group("unit"))

    source_text = _source_slice(segment, matches[chain[0]].start(), matches[chain[-1]].end())
    span = [matches[chain[0]].start(), matches[chain[-1]].end()]

    if len(chain) == 1:
        unit = unit_of(chain[0])
        value = value_of(chain[0])
        if unit is None or value is None:
            _missing_unit_ambiguity(ambiguities, source_text)
            return []
        extra = None
        value_text = matches[chain[0]].group("value")
        if "و" in value_text and not any(character.isdigit() for character in value_text):
            tokens = [token for token in re.split(
                rf"[\s]+|{_NO_PERSIAN_BEFORE}و{_NO_PERSIAN_AFTER}", value_text.strip()) if token]
            has_scale = any(token in _SCALES for token in tokens)
            opens_small = bool(tokens) and tokens[0] in _UNITS and _UNITS[tokens[0]] < 10
            if not has_scale and opens_small:
                extra = ("spoken_number_join",
                         "Confirm the spoken number: it was read as a composed whole number.")
        return [_observation(source_text, span, _to_mm(value, unit), "mm", kind,
                             correcting, extra_ambiguity=extra, ambiguities=ambiguities)]

    # Multi-part chain. An elided tail ("سه متر و بیست") may inherit the smaller
    # unit only when it fits strictly inside the previous unit's ratio.
    if unit_of(chain[-1]) is None and value_of(chain[-1]) is not None:
        head_units = [unit_of(position) for position in chain[:-1]]
        if head_units and all(unit is not None for unit in head_units):
            first_unit = head_units[0]
            tail_value = int(value_of(chain[-1]))
            tail_range = _ELIDED_TAILS.get(first_unit)
            if tail_range and tail_range[0] <= tail_value <= tail_range[1]:
                total = sum(_to_mm(value_of(position), unit_of(position))
                            for position in chain[:-1])
                total += _to_mm(tail_value, tail_range[2])
                return [_observation(
                    source_text, span, total, "mm", kind, correcting,
                    extra_ambiguity=(
                        "elided_tail_unit",
                        f"The tail value had no unit and was read as {tail_range[2]}; confirm the total.",
                    ),
                    ambiguities=ambiguities,
                )]
        # The tail cannot be interpreted deterministically: it becomes a question.
        tail_text = _source_slice(segment, matches[chain[-1]].start(), matches[chain[-1]].end())
        _missing_unit_ambiguity(ambiguities, tail_text)
        return _chain_observations(segment, matches, chain[:-1], kind, correcting, ambiguities)

    # All parts carry units: merge only strictly descending scales (m > cm > mm).
    scales = [_UNIT_SCALE[unit_of(position)] for position in chain]
    if all(scales[i] > scales[i + 1] for i in range(len(scales) - 1)):
        total = sum(_to_mm(value_of(position), unit_of(position)) for position in chain)
        return [_observation(source_text, span, total, "mm", kind, correcting,
                             extra_ambiguity=None, ambiguities=ambiguities)]

    # Mixed, non-descending units: keep the members as separate observations.
    results: list[dict[str, Any]] = []
    for position in chain:
        unit, value = unit_of(position), value_of(position)
        text = _source_slice(segment, matches[position].start(), matches[position].end())
        member_span = [matches[position].start(), matches[position].end()]
        if unit is None or value is None:
            _missing_unit_ambiguity(ambiguities, text)
            continue
        results.append(_observation(
            text, member_span, _to_mm(value, unit), "mm", kind, correcting,
            extra_ambiguity=None, ambiguities=ambiguities,
        ))
    return results


def parse_spoken_measurements(text: str) -> dict[str, Any]:
    """Extract spoken measurement proposals from one transcript. Deterministic."""
    normalized = normalize(text)
    observations: list[dict[str, Any]] = []
    ambiguities: list[dict[str, Any]] = []

    # A correction marker stays in effect for the measurements that follow it
    # in the same transcript ("نه نه، اشتباه گفتم، ارتفاع ... شد"), because
    # speakers separate the marker from the corrected value with a pause.
    correcting = False
    for segment in _segments(normalized):
        if _CORRECTION_RE.search(segment):
            correcting = True
        matches = list(VALUE_RE.finditer(segment))
        if not matches:
            continue

        # A standalone "نه" (or "نه نه") is the spoken correction marker
        # ("no, ..."), not the numeral nine: drop it when nothing follows in
        # the segment. A "نه" with further content stays a missing-unit
        # question, never a silently approved dimension.
        kept = []
        for match in matches:
            value_text = match.group("value").strip()
            if value_text in ("نه", "نه نه"):
                rest = segment[match.end("value"):]
                if not rest.strip() or re.match(r"[\s]*[,،;؛.]", rest):
                    continue
            kept.append(match)
        if not kept:
            continue
        matches = kept

        # Group consecutive matches into connector-joined chains. Any other word
        # in the gap starts a new chain, so distinct measurements never merge.
        chains: list[list[int]] = []
        current: list[int] = []
        for position, match in enumerate(matches):
            if current:
                gap = segment[matches[position - 1].end():match.start()]
                if re.fullmatch(rf"(?:{_CONNECTOR})|[\s]+", gap):
                    current.append(position)
                else:
                    chains.append(current)
                    current = [position]
            else:
                current = [position]
        if current:
            chains.append(current)

        for chain in chains:
            kind = _kind_near(segment, matches[chain[0]].start(), matches[chain[-1]].end())
            observations.extend(
                _chain_observations(segment, matches, chain, kind, correcting, ambiguities))

    if not observations:
        if re.search(r"\d", normalized):
            ambiguities.append({
                "type": "no_structured_extraction",
                "detail": (
                    "Text contains numbers but no usable value and unit. Speak or write "
                    "measurements as 'value + unit', for example 'سه متر و بیست سانتی‌متر'."
                ),
                "confidence": 0.3,
            })
        else:
            ambiguities.append({
                "type": "no_measurements",
                "detail": "No measurements detected. Provide dimensions with their units.",
                "confidence": 0.2,
            })

    _flag_conflicts(observations, ambiguities)
    return {
        "observations": observations,
        "ambiguities": ambiguities,
        "clarification_questions": _clarification_questions(observations),
        "provider": "deterministic_spoken",
        "disclaimer": DISCLAIMER,
    }


def _flag_conflicts(observations: list[dict[str, Any]], ambiguities: list[dict[str, Any]]) -> None:
    """The same kind spoken with different values is a conflict, never auto-resolved."""
    by_kind: dict[str, list[dict[str, Any]]] = {}
    for observation in observations:
        if observation.get("kind"):
            by_kind.setdefault(observation["kind"], []).append(observation)
    for kind, group in by_kind.items():
        values = sorted({o["value_mm"] for o in group})
        if len(values) > 1:
            ambiguities.append({
                "type": "conflicting_values",
                "kind": kind,
                "values_mm": values,
                "detail": (
                    f"Multiple different {kind} values were spoken "
                    f"({', '.join(str(v) for v in values)} mm). Resolve the conflict manually."
                ),
                "confidence": 0.7,
            })


def _clarification_questions(observations: list[dict[str, Any]]) -> list[str]:
    questions: list[str] = []
    kinds = {o.get("kind") for o in observations}
    if kinds & {"wall_length", "length"} and not kinds & {"wall_height", "height"}:
        questions.append("Wall height not specified — please provide wall height(s).")
    if kinds & {"wall_height", "height"} and not kinds & {"wall_length", "length"}:
        questions.append("Wall length not specified — please provide wall length(s).")
    return questions
