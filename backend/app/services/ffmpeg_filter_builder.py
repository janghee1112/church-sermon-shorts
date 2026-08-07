from pathlib import Path

from app.services.render_crop import RenderCrop


def build_ffmpeg_command(
    *,
    ffmpeg_binary: str,
    source_path: Path,
    title_path: Path,
    subtitle_manifest_path: Path,
    banner_path: Path,
    banner_width: int,
    banner_height: int,
    banner_x: int,
    banner_y: int,
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
        "[1:v]format=rgba[title_layer]",
        "[video_layer][title_layer]overlay=0:0:shortest=1[title_composite]",
    ]
    filter_parts.extend([
        "[2:v]format=rgba,setpts=PTS-STARTPTS[subtitle_layer]",
        "[title_composite][subtitle_layer]overlay=0:0:shortest=1[subtitle_composite]",
    ])
    banner_input_index = 3
    filter_parts.append(
        f"[{banner_input_index}:v]scale={banner_width}:{banner_height}:flags=lanczos,format=rgba[banner_layer]"
    )
    filter_parts.append(
        f"[subtitle_composite][banner_layer]overlay={banner_x}:{banner_y}:shortest=1[outv]"
    )
    command = [
        ffmpeg_binary, "-y", "-hide_banner", "-loglevel", "warning",
        "-ss", f"{start_sec:.3f}", "-t", f"{duration_sec:.3f}", "-i", str(source_path),
        "-loop", "1", "-framerate", str(fps), "-i", str(title_path),
        "-f", "concat", "-safe", "0", "-i", str(subtitle_manifest_path),
    ]
    command.extend(["-loop", "1", "-framerate", str(fps), "-i", str(banner_path)])
    command.extend([
        "-filter_complex", ";".join(filter_parts),
        "-map", "[outv]", "-map", "0:a:0", "-af", f"atempo={playback_rate:.6f},asetpts=PTS-STARTPTS",
        "-t", f"{output_duration_sec:.3f}", "-r", str(fps), "-c:v", "libx264",
        "-preset", preset, "-crf", str(crf), "-profile:v", "high", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "48000", "-b:a", "192k", "-movflags", "+faststart",
        "-progress", "pipe:1", "-nostats", str(temporary_output),
    ])
    return command
