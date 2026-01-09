import time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

Source = Literal["Youtube", "Yandex", "Spotify", "Local"]


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


class Update(BaseModel):
    track: Track
    playback: Playback


class Instance(BaseModel):
    uid: UUID
    expires_at: float  # unix

    track: Track | None
    playback: Playback
    host_recv_ts: float  # unix

    @staticmethod
    def new(uid: UUID, expiry: float) -> "Instance":
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
