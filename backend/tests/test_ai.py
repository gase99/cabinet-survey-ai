from app.ai.provider import parse_text_measurements_deterministic
import asyncio

def test_parse_english_measurements():
    text = "Wall A: 3200 mm\nWall height: 2700 mm\nWindow width: 1200 mm"
    result = asyncio.run(quick_parse(text)) if False else parse_text_measurements_sync(text)
    assert len(result["observations"]) == 3
    assert result["observations"][0]["value_mm"] == 3200
    assert any("height" in o["label"].lower() for o in result["observations"])

def parse_text_measurements_sync(text):
    from app.ai.provider import parse_text_measurements_deterministic
    return parse_text_measurements_deterministic(text)

def test_parse_persian_numerals():
    text = "دیوار A: ۳۲۰۰ میلی‌متر"
    result = parse_text_measurements_sync(text)
    assert len(result["observations"]) == 1
    assert result["observations"][0]["value_mm"] == 3200

def test_parse_no_measurements_flags():
    result = parse_text_measurements_sync("Hello world")
    assert len(result["ambiguities"]) > 0

def test_parse_suspicious_value():
    result = parse_text_measurements_sync("Wall A: 1 mm")
    assert any(a["type"]=="suspicious_value" for a in result["ambiguities"])

def test_no_fabrication():
    # Must never invent dimensions not in text
    result = parse_text_measurements_sync("Wall A: 3200 mm")
    # Only one observation, not missing walls invented
    assert len(result["observations"]) == 1
    # Clarification question about missing height, but not invented value
    assert any("height" in q.lower() for q in result["clarification_questions"])

def test_deterministic_never_ai_creates_coords():
    # The provider never returns drawing coordinates
    result = parse_text_measurements_sync("Wall A: 3200 mm")
    assert "svg" not in str(result).lower()
    assert "coordinates" not in str(result).lower()
