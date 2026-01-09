from datetime import datetime
import time
from typing import Any, Literal

from pydantic import BaseModel

Source = Literal["Youtube", "Yandex", "Spotify", "Local"]
DiscoverySource = Literal["Yandex", "WinRT"]


class Track(BaseModel):
    source: Source
    id: str
    title: str
    artist: str
    duration_ms: int


class Playback(BaseModel):
    state: Literal["Playing", "Paused", "Stopped"]
    position_ms: int
    updated_at: float  # unix

    @staticmethod
    def from_win(t: Any):
        from winrt.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
        )

        assert isinstance(t, PlaybackStatus)
        match t:
            case 4:
                return "Playing"
            case 5:
                return "Paused"
            case _:
                return "Stopped"

    def get_started(self) -> float:
        return self.updated_at - self.position_ms / 1000

    def __eq__(self, other: "Playback") -> bool:
        if self.state != other.state:
            return False
        if self.state == "Playing":
            if abs(self.get_started() - other.get_started()) < 1:
                return True
        return self.position_ms == other.position_ms


class Update(BaseModel):
    track: Track
    playback: Playback

    def __eq__(self, other: "Update") -> bool:
        return self.track == other.track and self.playback == other.playback

    def format(self) -> str:
        track = f"{self.track.artist} - {self.track.title}"
        ts = f"{self.playback.position_ms / 1000:.1f} / {self.track.duration_ms / 1000}"
        started = self.playback.get_started()

        formatted = datetime.fromtimestamp(started).strftime("%H:%M:%S")

        if self.playback.state == "Playing":
            return f"Now playing: {track} [{ts}], started at {formatted}"
        else:
            return f"Now paused: {track} [{ts}], started at {formatted}"


class Instance(BaseModel):
    uid: str
    expires_at: float  # unix

    track: Track | None
    playback: Playback
    host_recv_ts: float  # unix

    @staticmethod
    def new(uid: str, expiry: float) -> "Instance":
        return Instance(
            uid=uid,
            expires_at=expiry,
            track=None,
            playback=Playback(state="Stopped", position_ms=0, updated_at=time.time()),
            host_recv_ts=time.time(),
        )


class DownloadInfo(BaseModel):
    url: str
    decryption_key: str
