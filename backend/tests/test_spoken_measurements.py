"""Deterministic spoken-measurement parsing: never invents, never auto-approves."""
from app.ai.provider import parse_measurements_any
from app.domain.spoken_measurements import parse_spoken_measurements


def observations_of(text):
    return [(o["value_mm"], o["kind"], o["intent"]) for o in parse_spoken_measurements(text)["observations"]]


def ambiguity_types(text):
    return [a["type"] for a in parse_spoken_measurements(text)["ambiguities"]]


def test_compound_persian_wall_length():
    result = parse_spoken_measurements("دیوار سه متر و بیست سانتی‌متر طول دارد")
    assert [(o["value_mm"], o["unit"]) for o in result["observations"]] == [(3200, "mm")]
    assert result["observations"][0]["kind"] == "wall_length"
    assert result["observations"][0]["source_text"] == "سه متر و بیست سانتی متر"
    assert result["observations"][0]["needs_review"] is True


def test_compound_wall_height():
    result = parse_spoken_measurements("ارتفاع دیوار دو متر و هفتاد سانتی‌متر است")
    assert [(o["value_mm"], o["kind"]) for o in result["observations"]] == [(2700, "wall_height")]


def test_base_and_wall_cabinet_depths():
    assert observations_of("عمق کابینت زمینی شصت سانتی‌متر است") == [(600, "base_cabinet_depth", "statement")]
    assert observations_of("عمق کابینت دیواری سی و پنج سانتی‌متر است") == [(350, "wall_cabinet_depth", "statement")]


def test_scale_words_compose():
    assert observations_of("سه هزار و دویست میلی‌متر") == [(3200, None, "statement")]


def test_digits_with_decimal_separator():
    assert observations_of("دیوار ۳٫۲ متر") == [(3200, None, "statement")]


def test_elided_tail_unit_is_flagged_not_silent():
    result = parse_spoken_measurements("سه متر و بیست")
    assert [(o["value_mm"], o["unit"]) for o in result["observations"]] == [(3200, "mm")]
    assert "elided_tail_unit" in ambiguity_types("سه متر و بیست")


def test_missing_unit_never_becomes_a_value():
    result = parse_spoken_measurements("طول دیوار ۳۲۰۰")
    assert result["observations"] == []
    assert "missing_unit" in ambiguity_types("طول دیوار ۳۲۰۰")


def test_correction_intent_is_detected_and_preserves_history_marker():
    result = parse_spoken_measurements("نه، طول دیوار سه متر و چهل سانتی‌متر بود")
    assert [(o["value_mm"], o["intent"]) for o in result["observations"]] == [(3400, "correction")]
    assert result["observations"][0]["needs_review"] is True


def test_correction_across_clause_boundary():
    result = parse_spoken_measurements("نه نه، اشتباه گفتم، ارتفاع دو متر و هفتاد سانتی‌متر شد")
    assert [(o["value_mm"], o["kind"], o["intent"]) for o in result["observations"]] == \
        [(2700, "height", "correction")]


def test_numeral_nine_is_not_a_correction_marker():
    result = parse_spoken_measurements("طول دیوار نه متر")
    assert [(o["value_mm"], o["kind"], o["intent"]) for o in result["observations"]] == \
        [(9000, "wall_length", "statement")]


def test_conflicting_values_are_surfaced_not_resolved():
    text = "طول دیوار سه متر و طول دیوار سه متر و بیست سانتی‌متر"
    result = parse_spoken_measurements(text)
    values = sorted(o["value_mm"] for o in result["observations"])
    assert values == [3000, 3200]
    assert "conflicting_values" in ambiguity_types(text)


def test_separate_measurements_never_merge():
    text = "طول سه متر، عرض بیست سانتی‌متر"
    assert [(o["value_mm"], o["kind"]) for o in parse_spoken_measurements(text)["observations"]] == \
        [(3000, "length"), (200, "width")]


def test_window_kind():
    assert observations_of("پنجره یک متر و بیست سانتی‌متر") == [(1200, "window", "statement")]


def test_word_join_ambiguity_for_risky_composition():
    assert "spoken_number_join" in ambiguity_types("سه و بیست سانتی‌متر")
    assert "spoken_number_join" not in ambiguity_types("بیست و پنج سانتی‌متر")


def test_suspicious_value_flagged():
    assert "suspicious_value" in ambiguity_types("سه میلی‌متر")


def test_no_fabrication_without_measurements():
    result = parse_spoken_measurements("سلام")
    assert result["observations"] == []
    assert "no_measurements" in [a["type"] for a in result["ambiguities"]]


def test_parser_never_returns_coordinates_or_approval():
    result = parse_spoken_measurements("دیوار سه متر و بیست سانتی‌متر طول دارد")
    rendered = str(result).lower()
    assert "start_x" not in rendered and "end_y" not in rendered
    assert all(o.get("review_status", "needs_review") != "approved" for o in result["observations"])


def test_number_inside_other_word_is_ignored():
    # "پنجره" contains "پنج"; it must not become a measurement.
    assert observations_of("پنجره یک متر و بیست سانتی‌متر") == [(1200, "window", "statement")]


def test_mixed_spoken_and_labeled_merge_no_duplicates():
    result = parse_measurements_any("دیوار A: 3200 mm")
    assert [(o["value_mm"], o["label"]) for o in result["observations"]] == [(3200, "دیوار A")]


def test_merge_keeps_spoken_proposals_from_plain_transcript():
    text = "دیوار سه متر طول دارد و ارتفاع دیوار ۲۷۰۰ میلی‌متر است"
    result = parse_measurements_any(text)
    kinds = sorted(o["kind"] for o in result["observations"])
    assert kinds == ["wall_height", "wall_length"]
    assert "no_structured_extraction" not in [a["type"] for a in result["ambiguities"]]


def test_labeled_text_still_strict_about_missing_unit():
    result = parse_measurements_any("Wall A: 3200")
    assert result["observations"] == []
    assert any(a["type"] == "missing_unit" for a in result["ambiguities"])
