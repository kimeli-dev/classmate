# Name detection: design and limits

Sessionly's name detector is a **text-matching component**, not a meeting listener. It accepts transcript text from a separately enabled speech-to-text component and returns a candidate match for a user-visible notification. It does not capture meeting audio, transmit it, mark attendance, or play a voice reply.

## Current implementation

- Unicode/case/punctuation normalization.
- Exact phrase and whole-token matching for the configured display name and aliases.
- Optional first-name matching, which can be disabled to reduce false positives.
- Conservative fuzzy matching for long single-token names only. Fuzzy matches are labelled `fuzzy_review`.
- Minimum speech-recognition confidence gate and duplicate-alert cooldown.
- No automatic response or attendance state changes.

Example:

```python
from sessionly.services.name_detection import NameDetector

detector = NameDetector(
    "Kiptoo Solomon",
    aliases=["Kiptoo", "Solomon"],
    allow_first_name=True,
    min_asr_confidence=0.60,
)
candidate = detector.detect(
    "Kiptoo, could you answer the question?",
    asr_confidence=0.94,
)
if candidate.matched and detector.should_alert(candidate):
    # Show a notification and let the user decide what to do.
    print(candidate.reason, candidate.confidence, candidate.transcript)
```

## Accuracy expectations

No detector can guarantee zero errors. Recognition quality depends on the speech recognizer, microphone mix, accents, overlapping speech, noise, and names that sound alike. The returned confidence is **not** a calibrated probability that a lecturer intended to address the user. A name can be mentioned in an unrelated sentence; a match does not prove a question or roll call is directed at the user.

Recommended production behaviour:

1. Keep listening opt-in and visibly indicated; explain which audio source is processed.
2. Prefer on-device speech recognition and do not retain raw audio by default.
3. Show the transcript snippet and whether the match was exact or fuzzy.
4. Ask for human confirmation for fuzzy/uncertain cases.
5. Keep existing voice-reply hotkeys user-triggered. Never auto-answer roll call or mark attendance based on name detection.
6. Test with consented, representative recordings before changing thresholds. Measure false positives and missed detections rather than promising perfection.

## Tests

Run with `python -m pytest tests/test_name_detection.py`.

This module currently has no audio capture or UI integration. Those should be implemented separately after choosing and validating an on-device transcription engine and defining Windows audio-source behaviour.
