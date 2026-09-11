from pathlib import Path
from typing import Union

from app.services.render_crop import RenderCrop
from app.services.render_timing import (
    DEFAULT_AUDIO_FADE_DURATION_SEC,
    DEFAULT_VIDEO_FADE_DURATION_SEC,
    calculate_fade_window,
    calculate_output_duration,
)


def build_ffmpeg_command(
    *,
    ffmpeg_binary: str,
    source_path: Union[Path, str],
    overlay_manifest_path: Path,
    temporary_output: Path,
    start_sec: float,
    duration_sec: float,
    canvas_width: int,
    canvas_height: int,
    fps: int,
    crf: int,
    preset: str,
    video_top: int,
    video_height: int,
    crop: RenderCrop,
    playback_rate: float = 1.0,
    fade_out_enabled: bool = True,
    video_fade_duration: float = DEFAULT_VIDEO_FADE_DURATION_SEC,
    audio_fade_duration: float = DEFAULT_AUDIO_FADE_DURATION_SEC,
    encoder_threads: int = 1,
    filter_threads: int = 1,
    x264_lookahead_frames: int = 8,
) -> list[str]:
    output_duration_sec = calculate_output_duration(duration_sec, playback_rate)
    video_fade_start, effective_video_fade_duration = calculate_fade_window(
        output_duration_sec, video_fade_duration,
    )
    audio_fade_start, effective_audio_fade_duration = calculate_fade_window(
        output_duration_sec, audio_fade_duration,
    )
    crop_w = max(2, round(crop.crop_width / 2) * 2)
    crop_h = max(2, round(crop.crop_height / 2) * 2)
    crop_x = max(0, round(crop.crop_x / 2) * 2)
    crop_y = max(0, round(crop.crop_y / 2) * 2)
    filter_parts = [
        f"[0:v]crop={crop_w}:{crop_h}:{crop_x}:{crop_y},"
        f"scale={canvas_width}:{video_height}:flags=lanczos,setsar=1,setpts=(PTS-STARTPTS)/{playback_rate:.6f},fps={fps}[sermon];"
        f"color=c=black:s={canvas_width}x{canvas_height}:r={fps}:d={output_duration_sec:.3f}[base];"
        f"[base][sermon]overlay=0:{video_top}:shortest=1[video_layer];"
        "[1:v]format=rgba,setpts=PTS-STARTPTS[overlay_layer]",
        "[video_layer][overlay_layer]overlay=0:0:shortest=1[composited]",
    ]
    if fade_out_enabled and effective_video_fade_duration > 0:
        filter_parts.append(
            f"[composited]fade=t=out:st={video_fade_start:.6f}:"
            f"d={effective_video_fade_duration:.6f}:color=black[outv]"
        )
    else:
        filter_parts.append("[composited]null[outv]")
    audio_filters = [f"atempo={playback_rate:.6f}", "asetpts=PTS-STARTPTS"]
    if fade_out_enabled and effective_audio_fade_duration > 0:
        audio_filters.append(
            f"afade=t=out:st={audio_fade_start:.6f}:d={effective_audio_fade_duration:.6f}"
        )
    command = [
        ffmpeg_binary, "-nostdin", "-y", "-hide_banner", "-loglevel", "warning",
        "-filter_threads", str(filter_threads),
        "-filter_complex_threads", str(filter_threads),
        "-ss", f"{start_sec:.3f}", "-t", f"{duration_sec:.3f}", "-i", str(source_path),
        "-f", "concat", "-safe", "0", "-i", str(overlay_manifest_path),
    ]
    command.extend([
        "-filter_complex", ";".join(filter_parts),
        "-map", "[outv]", "-map", "0:a:0", "-af", ",".join(audio_filters),
        "-t", f"{output_duration_sec:.3f}", "-r", str(fps), "-c:v", "libx264",
        "-threads:v", str(encoder_threads),
        "-x264-params", (
            f"threads={encoder_threads}:sync-lookahead=0:"
            f"rc-lookahead={x264_lookahead_frames}:ref=1"
        ),
        "-preset", preset, "-crf", str(crf), "-profile:v", "high", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-threads:a", "1", "-ar", "48000", "-b:a", "192k", "-movflags", "+faststart",
        "-progress", "pipe:1", "-nostats", str(temporary_output),
    ])
    return command
