"""
FrameSource — uniform interface for any video producer the CV pipeline consumes.

Backends:
  FileFrameSource  — wraps cv2.VideoCapture(path); used by the existing
                     file-based pipeline functions.
  RtspFrameSource  — wraps cv2.VideoCapture(rtsp_url); for live phone streams
                     served via an RTSP relay (MediaMTX) or a phone IP-camera
                     app that exposes RTSP directly.

A future WebRtcFrameSource can implement the same three methods (read, fps,
release) without any change to the pipeline.
"""

from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass
from typing import Protocol

import cv2
import numpy as np


class FrameSource(Protocol):
    fps: float

    def read(self) -> tuple[bool, np.ndarray | None]: ...
    def release(self) -> None: ...


@dataclass
class FileFrameSource:
    path: str

    def __post_init__(self) -> None:
        self._cap = cv2.VideoCapture(self.path)
        self.fps = self._cap.get(cv2.CAP_PROP_FPS) or 30.0

    def read(self) -> tuple[bool, np.ndarray | None]:
        return self._cap.read()

    def release(self) -> None:
        self._cap.release()


class RtspFrameSource:
    """
    RTSP source with a background reader thread that always holds the
    most recent frame. Drops stale frames so the CV pipeline never lags
    behind the live feed.
    """

    def __init__(self, url: str, reconnect: bool = True) -> None:
        self.url = url
        self.reconnect = reconnect
        self._cap = self._open()
        self.fps = self._cap.get(cv2.CAP_PROP_FPS) or 30.0

        self._lock = threading.Lock()
        self._latest: np.ndarray | None = None
        self._stopped = False
        self._thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._thread.start()

    def _open(self) -> cv2.VideoCapture:
        cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
        if not cap.isOpened():
            raise RuntimeError(f"Failed to open RTSP stream: {self.url}")
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def _reader_loop(self) -> None:
        while not self._stopped:
            ok, frame = self._cap.read()
            if not ok:
                if not self.reconnect:
                    break
                time.sleep(0.5)
                try:
                    self._cap.release()
                    self._cap = self._open()
                except RuntimeError:
                    continue
                continue
            with self._lock:
                self._latest = frame

    def read(self) -> tuple[bool, np.ndarray | None]:
        # Block briefly until a frame is available, then return the freshest one.
        for _ in range(100):
            with self._lock:
                if self._latest is not None:
                    frame = self._latest
                    self._latest = None
                    return True, frame
            if self._stopped:
                return False, None
            time.sleep(0.01)
        return False, None

    def release(self) -> None:
        self._stopped = True
        self._thread.join(timeout=1.0)
        self._cap.release()


class WebRtcFrameSource:
    """
    Frame source fed by an aiortc MediaStreamTrack running on the asyncio loop.

    A background asyncio task pulls VideoFrames off the track and stores the
    most recent one. read() (called from the LiveSession worker thread)
    returns whatever is freshest, dropping intermediate frames so the CV
    pipeline never lags behind the live broadcaster.
    """

    def __init__(self, track, loop, fps: float = 30.0) -> None:
        self.fps = fps
        self._track = track
        self._loop = loop
        self._lock = threading.Lock()
        self._latest: np.ndarray | None = None
        self._stopped = False
        self._task = asyncio.run_coroutine_threadsafe(self._reader_loop(), loop)

    async def _reader_loop(self) -> None:
        try:
            while not self._stopped:
                frame = await self._track.recv()  # av.VideoFrame
                bgr = frame.to_ndarray(format="bgr24")
                with self._lock:
                    self._latest = bgr
        except Exception:
            return

    def read(self) -> tuple[bool, np.ndarray | None]:
        for _ in range(200):
            with self._lock:
                if self._latest is not None:
                    frame = self._latest
                    self._latest = None
                    return True, frame
            if self._stopped:
                return False, None
            time.sleep(0.01)
        return False, None

    def release(self) -> None:
        self._stopped = True


def open_source(uri: str) -> FrameSource:
    """Return a FrameSource for a file path, rtsp:// URL, or http(s):// MJPEG URL."""
    lower = uri.lower()
    if lower.startswith(("rtsp://", "rtmp://", "http://", "https://")):
        return RtspFrameSource(uri)
    return FileFrameSource(uri)
