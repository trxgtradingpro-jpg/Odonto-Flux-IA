from __future__ import annotations

import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from app.core.config import settings
from app.core.logging import logger


class AudioTranscriptionUnavailable(RuntimeError):
    pass


class AudioTranscriptionError(RuntimeError):
    pass


def _normalize_audio_suffix(*, mime_type: str | None, file_name: str | None) -> str:
    file_suffix = Path(file_name or "").suffix.strip()
    if file_suffix:
        return file_suffix

    mime_value = (mime_type or "").lower().strip()
    if "ogg" in mime_value or "opus" in mime_value:
        return ".ogg"
    if "mpeg" in mime_value or "mp3" in mime_value:
        return ".mp3"
    if "wav" in mime_value or "wave" in mime_value:
        return ".wav"
    if "mp4" in mime_value or "m4a" in mime_value:
        return ".m4a"
    if "webm" in mime_value:
        return ".webm"
    return ".bin"


def _normalize_text_for_compare(text: str) -> str:
    value = re.sub(r"\s+", " ", str(text or "").strip().lower())
    return re.sub(r"[^\w\s]", "", value, flags=re.UNICODE).strip()


@lru_cache(maxsize=8)
def _get_whisper_model(model_name: str):
    if not settings.audio_transcription_enabled:
        raise AudioTranscriptionUnavailable("audio_transcription_disabled")

    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise AudioTranscriptionUnavailable("faster_whisper_not_installed") from exc

    download_root = Path(settings.storage_base_path) / ".models" / "faster-whisper"
    download_root.mkdir(parents=True, exist_ok=True)

    normalized_model_name = str(model_name or "").strip() or settings.audio_transcription_model
    logger.info(
        "audio_transcription.model_loading",
        model=normalized_model_name,
        device=settings.audio_transcription_device,
        compute_type=settings.audio_transcription_compute_type,
    )
    return WhisperModel(
        normalized_model_name,
        device=settings.audio_transcription_device,
        compute_type=settings.audio_transcription_compute_type,
        download_root=str(download_root),
    )


def _average_segment_metric(segment_list: list[Any], attribute: str) -> float | None:
    values: list[float] = []
    for segment in segment_list:
        raw_value = getattr(segment, attribute, None)
        if raw_value is None:
            continue
        try:
            values.append(float(raw_value))
        except (TypeError, ValueError):
            continue

    if not values:
        return None
    return sum(values) / len(values)


def _transcript_quality_score(candidate: dict[str, Any]) -> float:
    text = str(candidate.get("text") or "").strip()
    tokens = [token for token in re.split(r"\s+", text) if token]
    token_count = len(tokens)
    unique_ratio = (len(set(token.lower() for token in tokens)) / token_count) if token_count else 0.0

    language_probability = candidate.get("language_probability")
    try:
        normalized_language_probability = max(0.0, min(float(language_probability), 1.0))
    except (TypeError, ValueError):
        normalized_language_probability = 0.0

    avg_logprob = candidate.get("avg_logprob")
    try:
        normalized_logprob = (max(min(float(avg_logprob), 0.0), -2.5) + 2.5) / 2.5
    except (TypeError, ValueError):
        normalized_logprob = 0.0

    avg_no_speech_prob = candidate.get("avg_no_speech_prob")
    try:
        normalized_speech_presence = 1.0 - max(0.0, min(float(avg_no_speech_prob), 1.0))
    except (TypeError, ValueError):
        normalized_speech_presence = 0.5

    text_density = min(token_count, 40) / 40 if token_count else 0.0
    refined_bonus = 0.06 if candidate.get("system") == "refined" else 0.0

    return round(
        (text_density * 0.24)
        + (unique_ratio * 0.12)
        + (normalized_language_probability * 0.2)
        + (normalized_logprob * 0.28)
        + (normalized_speech_presence * 0.1)
        + refined_bonus,
        6,
    )


def _build_transcribe_kwargs(*, beam_size: int) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "beam_size": max(int(beam_size or 1), 1),
        "vad_filter": True,
        "condition_on_previous_text": False,
        "temperature": 0.0,
    }
    if settings.audio_transcription_language:
        kwargs["language"] = settings.audio_transcription_language
    if settings.audio_transcription_initial_prompt:
        kwargs["initial_prompt"] = settings.audio_transcription_initial_prompt
    return kwargs


def _transcribe_file_with_model(
    *,
    audio_path: Path,
    model_name: str,
    beam_size: int,
    system_name: str,
    source_variant: str,
) -> dict[str, Any]:
    model = _get_whisper_model(model_name)
    segments, info = model.transcribe(str(audio_path), **_build_transcribe_kwargs(beam_size=beam_size))
    segment_list = list(segments)
    text = " ".join(
        str(segment.text or "").strip()
        for segment in segment_list
        if str(segment.text or "").strip()
    ).strip()
    if not text:
        raise AudioTranscriptionError(f"empty_audio_transcript_{system_name}")

    candidate: dict[str, Any] = {
        "system": system_name,
        "source_variant": source_variant,
        "text": text,
        "language": getattr(info, "language", None),
        "language_probability": getattr(info, "language_probability", None),
        "duration_seconds": getattr(info, "duration", None),
        "model": model_name,
        "beam_size": max(int(beam_size or 1), 1),
        "segments_count": len(segment_list),
        "avg_logprob": _average_segment_metric(segment_list, "avg_logprob"),
        "avg_no_speech_prob": _average_segment_metric(segment_list, "no_speech_prob"),
        "compression_ratio": _average_segment_metric(segment_list, "compression_ratio"),
    }
    candidate["score"] = _transcript_quality_score(candidate)
    return candidate


def _preprocess_audio_file(source_path: Path) -> Path:
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        raise AudioTranscriptionUnavailable("ffmpeg_not_installed")

    with NamedTemporaryFile(delete=False, suffix=".wav") as output_file:
        output_path = Path(output_file.name)

    filter_chain = str(settings.audio_transcription_refined_filter or "").strip() or "highpass=f=120, lowpass=f=3800, loudnorm"
    command = [
        ffmpeg_bin,
        "-y",
        "-i",
        str(source_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-af",
        filter_chain,
        str(output_path),
    ]

    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
        return output_path
    except subprocess.CalledProcessError as exc:
        try:
            output_path.unlink(missing_ok=True)
        except Exception:
            pass
        stderr = (exc.stderr or exc.stdout or "").strip()
        raise AudioTranscriptionError(f"ffmpeg_preprocess_failed:{stderr[:400]}") from exc


def _select_best_candidate(candidates: list[dict[str, Any]]) -> tuple[dict[str, Any], str]:
    if not candidates:
        raise AudioTranscriptionError("no_audio_transcription_candidates")

    if len(candidates) == 1:
        return candidates[0], "single_system_only"

    normalized_variants = {_normalize_text_for_compare(item.get("text") or "") for item in candidates}
    ranked = sorted(candidates, key=lambda item: (float(item.get("score") or 0.0), len(str(item.get("text") or ""))), reverse=True)

    if len(normalized_variants) <= 1:
        refined_candidate = next((item for item in ranked if item.get("system") == "refined"), None)
        if refined_candidate is not None:
            return refined_candidate, "matching_transcripts_prefer_refined"
        return ranked[0], "matching_transcripts_highest_score"

    top_candidate = ranked[0]
    second_candidate = ranked[1]
    top_score = float(top_candidate.get("score") or 0.0)
    second_score = float(second_candidate.get("score") or 0.0)
    if top_candidate.get("system") == "refined" and (top_score - second_score) >= -0.02:
        return top_candidate, "refined_score_advantage"
    return top_candidate, "highest_quality_score"


def transcribe_audio_bytes(
    content: bytes,
    *,
    mime_type: str | None = None,
    file_name: str | None = None,
) -> dict[str, Any]:
    if not content:
        raise AudioTranscriptionError("empty_audio_content")

    suffix = _normalize_audio_suffix(mime_type=mime_type, file_name=file_name)
    temp_paths: list[Path] = []
    candidates: list[dict[str, Any]] = []
    candidate_errors: list[str] = []

    try:
        with NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(content)
            source_path = Path(temp_file.name)
        temp_paths.append(source_path)

        try:
            candidates.append(
                _transcribe_file_with_model(
                    audio_path=source_path,
                    model_name=settings.audio_transcription_model,
                    beam_size=settings.audio_transcription_beam_size,
                    system_name="primary",
                    source_variant="original",
                )
            )
        except Exception as exc:
            candidate_errors.append(f"primary:{exc}")
            logger.warning("audio_transcription.primary_failed", error=str(exc))

        if settings.audio_transcription_refined_enabled:
            refined_source_path = source_path
            try:
                if settings.audio_transcription_refined_preprocess_enabled:
                    refined_source_path = _preprocess_audio_file(source_path)
                    if refined_source_path != source_path:
                        temp_paths.append(refined_source_path)

                candidates.append(
                    _transcribe_file_with_model(
                        audio_path=refined_source_path,
                        model_name=settings.audio_transcription_refined_model,
                        beam_size=settings.audio_transcription_refined_beam_size,
                        system_name="refined",
                        source_variant="preprocessed" if refined_source_path != source_path else "original",
                    )
                )
            except Exception as exc:
                candidate_errors.append(f"refined:{exc}")
                logger.warning("audio_transcription.refined_failed", error=str(exc))

        if not candidates:
            raise AudioTranscriptionError("; ".join(candidate_errors) or "all_audio_transcription_systems_failed")

        selected_candidate, selection_reason = _select_best_candidate(candidates)

        return {
            "text": selected_candidate["text"],
            "language": selected_candidate.get("language"),
            "language_probability": selected_candidate.get("language_probability"),
            "duration_seconds": selected_candidate.get("duration_seconds"),
            "model": selected_candidate.get("model"),
            "system": selected_candidate.get("system"),
            "score": selected_candidate.get("score"),
            "selected_system": selected_candidate.get("system"),
            "selection_reason": selection_reason,
            "candidates": candidates,
            "errors": candidate_errors,
        }
    finally:
        for temp_path in {path for path in temp_paths if path is not None}:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception as exc:
                logger.warning("audio_transcription.temp_cleanup_failed", path=str(temp_path), error=str(exc))
