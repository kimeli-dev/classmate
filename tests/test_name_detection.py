from sessionly.services.name_detection import NameDetector, normalize_text


def test_normalization_handles_case_punctuation_and_accents():
    assert normalize_text("José—KIPTOO!") == "jose kiptoo"


def test_exact_full_name_matches_across_punctuation():
    result = NameDetector("Kiptoo Solomon").detect("Kiptoo, Solomon, could you answer?")
    assert result.matched
    assert result.matched_alias == "kiptoo solomon"
    assert result.reason == "exact"


def test_first_name_can_be_disabled():
    detector = NameDetector("Kiptoo Solomon", allow_first_name=False)
    assert not detector.detect("Kiptoo, please").matched
    assert detector.detect("Kiptoo Solomon, please").matched


def test_aliases_match_as_whole_words_not_substrings():
    detector = NameDetector("Ann")
    assert not detector.detect("annual budget").matched
    assert detector.detect("Ann, are you there?").matched


def test_low_asr_confidence_is_not_a_match():
    result = NameDetector("Kiptoo", min_asr_confidence=0.7).detect("Kiptoo", asr_confidence=0.4)
    assert not result.matched
    assert result.reason == "low_asr_confidence"


def test_fuzzy_match_is_conservative_and_limited_to_long_tokens():
    detector = NameDetector("Solomon", allow_first_name=False, fuzzy_threshold=0.85)
    result = detector.detect("Salomon, can you hear me?")
    assert result.matched
    assert result.reason == "fuzzy_review"
    assert result.confidence < 1.0


def test_short_name_does_not_use_fuzzy_matching():
    detector = NameDetector("Ali", allow_first_name=False)
    assert not detector.detect("Alix is here").matched


def test_cooldown_suppresses_duplicate_alerts_only():
    detector = NameDetector("Kiptoo", cooldown_seconds=5)
    first = detector.detect("Kiptoo?")
    second = detector.detect("Kiptoo?")
    assert detector.should_alert(first, now=10)
    assert not detector.should_alert(second, now=12)
    assert detector.should_alert(second, now=16)


def test_empty_text_and_invalid_confidence():
    detector = NameDetector("Kiptoo")
    assert detector.detect("  ").reason == "empty_transcript"
    try:
        detector.detect("Kiptoo", asr_confidence=1.1)
    except ValueError:
        pass
    else:
        raise AssertionError("out-of-range confidence should raise ValueError")
