from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional


class FragmentedMp4Writer:
    """Best-effort live fragmented-MP4 writer fed by JPEG frames.

    The writer is intentionally small: it starts ffmpeg with an empty-moov /
    fragmented MP4 output so a LAN client can begin reading the file while the
    capture is still running. If ffmpeg or libx264 is unavailable, callers can
    continue the capture session and expose the finalized preview MP4 instead.
    """

    def __init__(self, path: str | Path, *, fps: float = 15.0, width: int = 640):
        self.path = Path(path)
        self.fps = max(float(fps), 1.0)
        self.width = max(int(width), 160)
        self.proc: Optional[subprocess.Popen] = None
        self.enabled = False
        self.error: Optional[str] = None
        self.frames_written = 0

    def start(self) -> bool:
        if shutil.which("ffmpeg") is None:
            self.error = "ffmpeg not found"
            return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "image2pipe",
            "-vcodec", "mjpeg",
            "-framerate", f"{self.fps:g}",
            "-i", "pipe:0",
            "-vf", f"scale={self.width}:-2",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "zerolatency",
            "-pix_fmt", "yuv420p",
            "-movflags", "frag_keyframe+empty_moov+default_base_moof",
            str(self.path),
        ]
        try:
            self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
            self.enabled = True
            return True
        except Exception as exc:  # pragma: no cover - host ffmpeg dependent
            self.error = str(exc)
            self.proc = None
            self.enabled = False
            return False

    def write_jpeg(self, jpeg: bytes) -> None:
        if not self.enabled or self.proc is None or self.proc.stdin is None:
            return
        if self.proc.poll() is not None:
            self.enabled = False
            self.error = f"ffmpeg exited rc={self.proc.returncode}"
            return
        try:
            self.proc.stdin.write(jpeg)
            self.proc.stdin.flush()
            self.frames_written += 1
        except (BrokenPipeError, OSError) as exc:
            self.enabled = False
            self.error = str(exc)

    def close(self, timeout: float = 10.0) -> None:
        if self.proc is None:
            return
        try:
            if self.proc.stdin is not None and not self.proc.stdin.closed:
                self.proc.stdin.close()
        except Exception:
            pass
        try:
            self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:  # pragma: no cover - host dependent
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        if self.proc.returncode not in (0, None) and self.error is None:
            try:
                stderr = self.proc.stderr.read().decode("utf-8", errors="replace") if self.proc.stderr else ""
            except Exception:
                stderr = ""
            self.error = f"ffmpeg exited rc={self.proc.returncode}: {stderr[-500:]}"
        self.enabled = False
