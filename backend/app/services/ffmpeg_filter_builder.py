from pathlib import Path
from typing import Union

from app.services.render_crop import RenderCrop


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
) -> list[str]:
    output_duration_sec = duration_sec / playback_rate
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
        "[video_layer][overlay_layer]overlay=0:0:shortest=1[outv]",
    ]
    command = [
        ffmpeg_binary, "-y", "-hide_banner", "-loglevel", "warning",
        "-ss", f"{start_sec:.3f}", "-t", f"{duration_sec:.3f}", "-i", str(source_path),
        "-f", "concat", "-safe", "0", "-i", str(overlay_manifest_path),
    ]
    command.extend([
        "-filter_complex", ";".join(filter_parts),
        "-map", "[outv]", "-map", "0:a:0", "-af", f"atempo={playback_rate:.6f},asetpts=PTS-STARTPTS",
        "-t", f"{output_duration_sec:.3f}", "-r", str(fps), "-c:v", "libx264", "-threads", "1",
        "-preset", preset, "-crf", str(crf), "-profile:v", "high", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "48000", "-b:a", "192k", "-movflags", "+faststart",
        "-progress", "pipe:1", "-nostats", str(temporary_output),
    ])
    return command
