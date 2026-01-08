from __future__ import annotations

import asyncio
import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel
from winrt.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionManager as MediaManager,
    GlobalSystemMediaTransportControlsSession as MediaSession,
    GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
)
from winrt.windows.foundation import EventRegistrationToken


class WTrack(BaseModel):
    artist: str
    title: str
    duration: datetime.timedelta | None

    @staticmethod
    def new() -> WTrack:
        return WTrack(artist="", title="", duration=None)

    def __str__(self) -> str:
        if not self.duration:
            return f"{self.artist} - {self.title}"
        return f"{self.artist} - {self.title} [{self.duration}]"

    def __repr__(self) -> str:
        return str(self)


class TUpdate(Enum):
    Timeline = "T"
    Seek = "S"
    Playback = "P"
    Metadata = "M"


NULLDATE = datetime.datetime(1601, 1, 1, 0, 0, tzinfo=datetime.timezone.utc)


def now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class WinRT_discovery:
    manager: MediaManager

    current_track: WTrack | None = None
    status: PlaybackStatus = PlaybackStatus.STOPPED
    position: datetime.timedelta = datetime.timedelta()
    _position_last_update: datetime.datetime = now()
    _last_meaning_update: TUpdate = TUpdate.Metadata

    _target_session: MediaSession | None = None
    _timeline_update_reg_token: EventRegistrationToken
    _playback_update_reg_token: EventRegistrationToken
    _metadata_update_reg_token: EventRegistrationToken

    VERBOSE: bool = False

    @property
    def target_session(self) -> MediaSession:
        assert self._target_session is not None
        return self._target_session

    @target_session.setter
    def target_session(self, session: MediaSession):
        if self._target_session is not None:
            self._target_session.remove_timeline_properties_changed(
                self._timeline_update_reg_token
            )
            self._target_session.remove_playback_info_changed(
                self._playback_update_reg_token
            )
            self._target_session.remove_media_properties_changed(
                self._metadata_update_reg_token
            )
        self._target_session = session
        self._timeline_update_reg_token = (
            self._target_session.add_timeline_properties_changed(self._update_handler_t)
        )
        self._playback_update_reg_token = (
            self._target_session.add_playback_info_changed(self._update_handler_p)
        )
        self._metadata_update_reg_token = (
            self._target_session.add_media_properties_changed(self._update_handler_m)
        )

    @staticmethod
    async def get_manager():
        return await MediaManager.request_async()

    @staticmethod
    async def get_properties(session: MediaSession):
        media_props = await session.try_get_media_properties_async()
        assert media_props is not None
        return media_props

    def __init__(self):
        try:
            self.manager = asyncio.run(WinRT_discovery.get_manager())
        except Exception:
            raise RuntimeError("Failed to get media sessions manager")

        if not self._get_current_session():
            print("Failed to get current session")

    def _get_current_session(self) -> bool:
        session = self.manager.get_current_session()
        if session is None:
            return False

        self.target_session = session
        self._update_handler(self.target_session, TUpdate.Metadata)
        return True

    def capture_session(self, session_id: str = "Automatic") -> bool:
        all_sessions = self.manager.get_sessions()
        target_session: MediaSession | None = None
        if session_id != "Automatic":
            for session in all_sessions:
                # source_app_user_model_id, for example, "chrome.exe"
                if session.source_app_user_model_id == session_id:
                    target_session = session
                    break

            if not target_session:
                raise Exception(f"Selected session '{session_id}' not found.")
            self.target_session = target_session
            return True

        return self._get_current_session()

    def _update_handler_p(self, session: MediaSession, _args: Any):
        self._update_handler(session, TUpdate.Playback)

    def _update_handler_t(self, session: MediaSession, _args: Any):
        update_type = TUpdate.Timeline
        if session.get_timeline_properties().position.microseconds == 0:
            update_type = TUpdate.Seek

        self._update_handler(session, update_type)

    def _update_handler_m(self, session: MediaSession, _args: Any):
        self._update_handler(session, TUpdate.Metadata)

    def _update_handler(self, session: MediaSession, update_type: TUpdate):
        info = asyncio.run(WinRT_discovery.get_properties(session))
        position = session.get_timeline_properties()
        playback_info = session.get_playback_info().playback_status

        if self.VERBOSE:
            match update_type:
                case TUpdate.Playback:
                    print(
                        f"playback update: {playback_info.name}, "
                        f"type: {info.playback_type.name if info.playback_type else info.playback_type}, "
                        f"timeline updated: {now() - position.last_updated_time} ago"
                    )
                case TUpdate.Timeline:
                    print(
                        f"timeline update: {position.position}/{position.end_time}, "
                        f"updated: {position.last_updated_time.time()}, "
                    )
                case TUpdate.Seek:
                    print(
                        f"seek update: {position.position}, "
                        f"updated: {position.last_updated_time.time()}, "
                    )
                case TUpdate.Metadata:
                    print(
                        f"metadata update: {info.artist} - {info.title} [{position.end_time}]"
                    )

        if self.current_track is None:
            self.current_track = WTrack.new()

        self.current_track.artist = info.artist
        self.current_track.title = info.title
        self.current_track.duration = position.end_time

        new_status = self.status

        if playback_info == PlaybackStatus.CLOSED:  # ill update from Ya.Music
            # when pausing/resuming/seeking - playback updates are duplicated
            if update_type == TUpdate.Timeline:
                if (
                    self._last_meaning_update == TUpdate.Seek
                    and now() - self._position_last_update
                    < datetime.timedelta(milliseconds=1)
                ):
                    new_status = PlaybackStatus.PLAYING
                elif self._last_meaning_update == TUpdate.Metadata:
                    new_status = PlaybackStatus.PLAYING
                elif new_status == PlaybackStatus.PAUSED:
                    new_status = PlaybackStatus.PLAYING
                elif new_status == PlaybackStatus.PLAYING:
                    new_status = PlaybackStatus.PAUSED
        else:
            new_status = playback_info

        # foobar doesn't send timeline updates
        if position.last_updated_time == NULLDATE:
            print(
                f"Old pos: {self.position}, new_pos: {self.get_position()}, "
                f"status: {self.status.name}"
            )
            if new_status == PlaybackStatus.PAUSED:
                self.position = self.get_position()
            self._position_last_update = now()
        else:
            self._position_last_update = position.last_updated_time
            self.position = position.position
        self.status = new_status

        if update_type != TUpdate.Playback:
            self._last_meaning_update = update_type

    def print_upd(self):
        if self.current_track is not None:
            print(
                f"{self.status.name} [{self.position} / {self.current_track.duration}] "
                f"{self.current_track.artist} - {self.current_track.title}"
            )
        else:
            print(f"{self.status.name} - no track")

    def get_current_track(self) -> WTrack | None:
        return self.current_track

    def get_position(self) -> datetime.timedelta:
        if self.status == PlaybackStatus.PLAYING:
            return now() - self._position_last_update + self.position
        return self.position
