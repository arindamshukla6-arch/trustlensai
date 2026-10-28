"""Weak stylometric indicator for possibly AI-generated statements.

THIS IS NOT AN AI DETECTOR. It counts a few writing-style features that are
*more common* in some machine-generated text. These same features appear in
formal, templated, edited or non-native-English writing. The signal is capped
in scoring so it can never raise a case above Low by itself.
"""
from __future__ import annotations

import re
import statistics

from ..models import Finding, Quality, Signal, SignalResult

KEY, NAME = "ai_text", "Statement style indicator (weak)"

STOCK_PHRASES = [
    "delve", "tapestry", "testament to", "in today's fast-paced world", "ever-evolving", "ever-changing",
    "furthermore", "moreover", "additionally", "i am deeply passionate", "fostering", "foster a",
    "multifaceted", "navigate the complexities", "pivotal", "embark on", "a journey of", "realm of",
    "holistic", "leverage", "unwavering", "in conclusion", "invaluable", "seamlessly", "resonate",
    "intricate", "underscore", "showcasing", "cutting-edge", "dynamic landscape",
]

LIMITATIONS = [
    "Stylometric heuristics have high false-positive rates and must never be used as proof.",
    "Formal, templated, professionally edited and non-native-English writing is frequently flagged.",
    "Easily evaded by paraphrasing; cannot identify which tool, if any, was used.",
    "Weight is capped: this signal alone cannot raise a case above Low.",
]

MIN_WORDS = 150


def analyse(text: str) -> Signal:
    method = "Rule-based stylometry: sentence-length variation, vocabulary diversity, stock-phrase rate, concrete detail rate"
    text = (text or "").strip()
    words = re.findall(r"[A-Za-z']+", text)
    if len(words) < MIN_WORDS:
        return Signal(KEY, NAME, SignalResult.INCONCLUSIVE, evidence=[
            f"Only {len(words)} words; at least {MIN_WORDS} are needed for any style analysis."],
            quality=Quality.POOR, method=method, limitations=LIMITATIONS)

    sentences = [s for s in re.split(r"(?<=[.!?])\s+", text) if len(s.split()) >= 3]
    lengths = [len(s.split()) for s in sentences] or [len(words)]
    mean_len = statistics.mean(lengths)
    cv = statistics.pstdev(lengths) / mean_len if mean_len else 0.0
    lower = [w.lower() for w in words]
    window = 100
    ttrs = [len(set(lower[i:i + window])) / window for i in range(0, len(lower) - window + 1, 25)]
    mattr = statistics.mean(ttrs) if ttrs else len(set(lower)) / len(lower)
    low_text = text.lower()
    hits = sorted({p for p in STOCK_PHRASES if p in low_text})
    phrase_rate = sum(low_text.count(p) for p in hits) / len(words) * 100
    concrete = len(re.findall(r"\b\d+(?:[.,]\d+)?%?\b", text)) + len(re.findall(r"(?<![.!?]\s)(?<!^)\b[A-Z][a-z]+", text))
    concrete_rate = concrete / len(words) * 100

    indicators = []
    if cv < 0.30:
        indicators.append(Finding("Uniform sentence length", f"Variation coefficient {cv:.2f} (< 0.30)", "low",
                                  "Human writing usually varies sentence length more.",
                                  "Careful or templated writing is also uniform."))
    if phrase_rate > 0.8:
        indicators.append(Finding("Stock phrases", f"{phrase_rate:.1f} per 100 words: {', '.join(hits[:8])}", "low",
                                  "These phrases are over-represented in some generated text.",
                                  "Many people, and writing guides, use them."))
    if concrete_rate < 3.0:
        indicators.append(Finding("Few concrete details", f"{concrete_rate:.1f} names/numbers per 100 words", "low",
                                  "Generic text tends to lack specific names, dates and figures.",
                                  "Some genuine personal statements are reflective rather than factual."))
    if mattr < 0.62:
        indicators.append(Finding("Repetitive vocabulary", f"Moving type-token ratio {mattr:.2f}", "low",
                                  "Lower vocabulary diversity.", "Common in simpler or second-language writing."))

    metrics = {"words": len(words), "sentences": len(sentences), "sentence_length_cv": round(cv, 3),
               "mattr": round(mattr, 3), "stock_phrase_rate": round(phrase_rate, 2),
               "stock_phrases_found": hits, "concrete_detail_rate": round(concrete_rate, 2),
               "indicators": len(indicators)}
    evidence = [f"{len(indicators)} of 4 style indicators present."] + [f.observation for f in indicators]
    warning = "Weak signal only — never treat this as evidence that a candidate used AI."
    if len(indicators) >= 3:
        return Signal(KEY, NAME, SignalResult.CONCERN, evidence + [warning], Quality.ADEQUATE, method,
                      LIMITATIONS, severity=0.5, findings=indicators, metrics=metrics)
    return Signal(KEY, NAME, SignalResult.NO_CONCERN, evidence + [warning], Quality.ADEQUATE, method,
                  LIMITATIONS, findings=indicators, metrics=metrics)
