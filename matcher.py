import os
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", str(text or "")).lower()
    text = text.replace("’", "'").replace("`", "'")
    text = re.sub(r"[^\w\s']+", " ", text, flags=re.UNICODE)
    text = re.sub(r"[_]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tokenize(text: str) -> List[str]:
    normalized = normalize_text(text)
    return normalized.split() if normalized else []


def edit_stats(reference: List[str], hypothesis: List[str]) -> Dict[str, int]:
    n, m = len(reference), len(hypothesis)
    dp: List[List[Tuple[int, int, int, int]]] = [
        [(0, 0, 0, 0) for _ in range(m + 1)] for _ in range(n + 1)
    ]
    for i in range(1, n + 1):
        dp[i][0] = (i, 0, i, 0)
    for j in range(1, m + 1):
        dp[0][j] = (j, 0, 0, j)

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if reference[i - 1] == hypothesis[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
                continue
            sub = dp[i - 1][j - 1]
            delete = dp[i - 1][j]
            insert = dp[i][j - 1]
            candidates = [
                (sub[0] + 1, sub[1] + 1, sub[2], sub[3]),
                (delete[0] + 1, delete[1], delete[2] + 1, delete[3]),
                (insert[0] + 1, insert[1], insert[2], insert[3] + 1),
            ]
            dp[i][j] = min(candidates, key=lambda item: (item[0], item[1] + item[2] + item[3]))

    distance, substitutions, deletions, insertions = dp[n][m]
    return {
        "distance": distance,
        "substitutions": substitutions,
        "deletions": deletions,
        "insertions": insertions,
    }


def character_similarity(reference: str, hypothesis: str) -> float:
    a = normalize_text(reference)
    b = normalize_text(hypothesis)
    if not a and not b:
        return 100.0
    return round(SequenceMatcher(None, a, b).ratio() * 100, 2)


def comparison_metrics(reference_text: str, hypothesis_text: str) -> Dict[str, Any]:
    ref_words = tokenize(reference_text)
    hyp_words = tokenize(hypothesis_text)
    stats = edit_stats(ref_words, hyp_words)
    denominator = max(len(ref_words), len(hyp_words), 1)
    match_score = max(0.0, 1.0 - (stats["distance"] / denominator)) * 100
    wer = (stats["distance"] / max(len(ref_words), 1)) * 100
    correct_words = max(0, len(ref_words) - stats["substitutions"] - stats["deletions"])
    word_accuracy = (correct_words / max(len(ref_words), 1)) * 100
    return {
        "matchScore": round(match_score, 2),
        "wordAccuracy": round(max(0.0, word_accuracy), 2),
        "characterSimilarity": character_similarity(reference_text, hypothesis_text),
        "wer": round(wer, 2),
        "referenceWords": len(ref_words),
        "modelWords": len(hyp_words),
        "correctWords": correct_words,
        "substitutions": stats["substitutions"],
        "deletions": stats["deletions"],
        "insertions": stats["insertions"],
    }


def get_number(item: Dict[str, Any], keys: List[str]) -> Optional[float]:
    for key in keys:
        value = item.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def segment_from_item(item: Any, index: int) -> Optional[Dict[str, Any]]:
    if isinstance(item, str):
        text = item.strip()
        if not text:
            return None
        return {"index": index, "text": text, "speaker": None, "start": None, "end": None}
    if not isinstance(item, dict):
        return None

    text = item.get("transcript") or item.get("text") or item.get("utterance") or item.get("content")
    if not isinstance(text, str) or not text.strip():
        return None
    speaker = item.get("speaker_type") or item.get("speaker") or item.get("speaker_id") or item.get("role")
    start = get_number(item, ["start_time", "start_time_seconds", "start", "begin"])
    end = get_number(item, ["end_time", "end_time_seconds", "end", "finish"])
    return {
        "index": index,
        "text": text.strip(),
        "speaker": str(speaker) if speaker is not None else None,
        "start": start,
        "end": end,
    }


def extract_segments(payload: Any) -> List[Dict[str, Any]]:
    candidates: Any = None
    if isinstance(payload, list):
        candidates = payload
    elif isinstance(payload, dict):
        for key in ["segments", "entries", "utterances", "items", "transcription"]:
            if isinstance(payload.get(key), list):
                candidates = payload[key]
                break
        if candidates is None:
            diarized = payload.get("diarized_transcript")
            if isinstance(diarized, dict) and isinstance(diarized.get("entries"), list):
                candidates = diarized["entries"]
        if candidates is None and isinstance(payload.get("transcript"), str):
            candidates = [{"transcript": payload["transcript"]}]

    if candidates is None:
        return []
    segments: List[Dict[str, Any]] = []
    for index, item in enumerate(candidates):
        segment = segment_from_item(item, index)
        if segment:
            segments.append(segment)
    return segments


def extract_reference(payload: Any) -> Tuple[str, List[Dict[str, Any]]]:
    segments = extract_segments(payload)
    if segments:
        return " ".join(segment["text"] for segment in segments), segments
    if isinstance(payload, str) and payload.strip():
        return payload.strip(), [{"index": 0, "text": payload.strip(), "speaker": None, "start": None, "end": None}]
    raise ValueError(
        "No transcript text found. Use an array of objects with a 'transcript' field, "
        "or an object containing 'segments', 'entries', or a 'transcript' string."
    )


def has_indic_script(text: str) -> bool:
    indic_ranges = [
        (0x0900, 0x097F), (0x0980, 0x09FF), (0x0A00, 0x0A7F),
        (0x0A80, 0x0AFF), (0x0B00, 0x0B7F), (0x0B80, 0x0BFF),
        (0x0C00, 0x0C7F), (0x0C80, 0x0CFF), (0x0D00, 0x0D7F),
    ]
    return any(any(start <= ord(ch) <= end for start, end in indic_ranges) for ch in text)


def choose_mode(reference_text: str) -> str:
    configured = os.getenv("SARVAM_MODE", "auto").strip().lower()
    if configured and configured != "auto":
        return configured
    return "transcribe" if has_indic_script(reference_text) else "translit"


def overlap_amount(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def compare_segments(reference_segments: List[Dict[str, Any]], model_segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    model_has_time = any(seg.get("start") is not None and seg.get("end") is not None for seg in model_segments)
    reference_has_time = any(seg.get("start") is not None and seg.get("end") is not None for seg in reference_segments)

    for index, reference in enumerate(reference_segments):
        matched_model: List[Dict[str, Any]] = []
        if reference_has_time and model_has_time and reference.get("start") is not None and reference.get("end") is not None:
            ref_start = float(reference["start"])
            ref_end = float(reference["end"])
            for model in model_segments:
                if model.get("start") is None or model.get("end") is None:
                    continue
                if overlap_amount(ref_start - 0.35, ref_end + 0.35, float(model["start"]), float(model["end"])) > 0:
                    matched_model.append(model)
        elif index < len(model_segments):
            matched_model = [model_segments[index]]

        model_text = " ".join(item["text"] for item in matched_model).strip()
        metrics = comparison_metrics(reference["text"], model_text)
        rows.append({
            "index": index + 1,
            "speaker": reference.get("speaker"),
            "start": reference.get("start"),
            "end": reference.get("end"),
            "reference": reference["text"],
            "model": model_text,
            "score": metrics["matchScore"],
        })
    return rows
