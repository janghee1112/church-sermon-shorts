from __future__ import annotations

from typing import Tuple


DEFAULT_VIDEO_FADE_DURATION_SEC = 1.0
DEFAULT_AUDIO_FADE_DURATION_SEC = 0.8


def calculate_output_duration(source_duration: float, playback_rate: float) -> float:
    """Return the final timeline duration after playback-rate adjustment."""
    if source_duration < 0:
        raise ValueError("source_duration must be non-negative")
    if playback_rate <= 0:
        raise ValueError("playback_rate must be positive")
    return source_duration / playback_rate


def calculate_fade_window(output_duration: float, requested_duration: float) -> Tuple[float, float]:
    """Return (fade_start, effective_duration) on the final output timeline."""
    if output_duration <= 0:
        return 0.0, 0.0
    effective_duration = min(output_duration, max(0.0, requested_duration))
    return max(0.0, output_duration - effective_duration), effective_duration
