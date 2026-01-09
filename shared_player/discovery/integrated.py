import datetime
from threading import Lock, Thread
import time
from typing import Callable, Literal

from ..types import Playback, Track, DiscoverySource, Source, Update

from .win import WinRT_discovery
from .yn import Ynison_discovery, Track as YTrack


class Discovery:
    # static
    YANDEX_POLL_TIME = 5
    GRACE_PERIOD = 15  # seconds after duration divergence to trust Yandex

    # fields
    winrt: WinRT_discovery | None
    yandex: Ynison_discovery | None

    yandex_poll_mode: Literal["upd", "poll", "lazy"]
    yandex_poll_thread: Thread
    yandex_last_track: YTrack | None
    yandex_startup: bool  # raised means "lazy" acts like "poll" to determine new track near beginning
    yandex_last_update: float  # unix time
    yandex_track_lock: Lock

    grace_armed: bool  # True after durations matched
    grace_diverge_time: float | None  # when durations started differing

    desired_source: Source | None

    lastupdate: Update | None

    _callbacks: list[Callable]

    def __init__(
        self,
        desired_source: Source | None = None,
        needed_sources: list[DiscoverySource] = [],
    ):
        self.desired_source = desired_source
        self.lastupdate = None
        self._callbacks = []

        self.yandex = None
        try:
            token = Ynison_discovery.get_session_id()
            self.yandex = Ynison_discovery(token)
        except RuntimeError as re:
            if "Yandex" in needed_sources:
                raise re

        self.winrt = None
        try:
            self.winrt = WinRT_discovery()
            if not self.winrt._get_current_session():
                raise RuntimeError("Failed to get current session")
        except RuntimeError as re:
            if "WinRT" in needed_sources:
                raise re
            else:
                self.winrt = None

        assert self.yandex or self.winrt, "at least one discovery method should work"

        if self.winrt is not None:
            self.yandex_poll_mode = "upd"
            self.winrt.on_update(self.update_yandex)
        else:
            self.yandex_poll_mode = "lazy"

        self.yandex_last_track = None
        self.yandex_startup = True
        self.yandex_track_lock = Lock()
        self.grace_armed = False
        self.grace_diverge_time = None
        self.yandex_last_update = time.time()
        self.yandex_poll_thread = Thread(
            target=self.yandex_poll_thread_fun,
            daemon=True,
        )
        self.yandex_poll_thread.start()

    def on_update(self, callback: Callable):
        self._callbacks.append(callback)
        if self.winrt is not None:
            self.winrt.on_update(callback=callback)

    def clear_callbacks(self):
        self._callbacks.clear()
        if self.winrt is not None:
            self.winrt.clear_callbacks()
            self.winrt.on_update(self.update_yandex)

    def update_yandex(self) -> bool:
        """Update current_track from yandex api. Returns True if any changes were made."""
        if self.yandex is None:
            return False

        new_track = self.yandex.get_current_track()
        with self.yandex_track_lock:
            if (
                self.yandex_last_track is None
                or self.yandex_last_track.id != new_track.id
            ):
                if self.yandex_last_track is not None:
                    self.yandex_startup = False
                self.yandex_last_track = new_track
                self.yandex_last_update = time.time()

                # to avoid double invokation
                if self.yandex_poll_mode != "upd" or self.winrt is None:
                    for cb in self._callbacks:
                        try:
                            cb()
                        except Exception as e:
                            print(f"Error in callback: {str(e)}")
                return True
        return False

    def yandex_poll_thread_fun(self):
        if self.yandex is None:
            return

        while True:
            if self.yandex_poll_mode == "upd":
                pass  # update on winrt updates
            elif self.yandex_poll_mode == "poll":
                self.update_yandex()
            elif self.yandex_poll_mode == "lazy":
                # wait longer if not on startup
                if self.update_yandex() and not self.yandex_startup:
                    delay = self.yandex_last_track.duration_ms or 0
                    delay = max(delay / 1000 - 10, 0)
                    time.sleep(delay)
                    continue
            time.sleep(Discovery.YANDEX_POLL_TIME)
            continue

    def convert_current_track_yandex(self) -> Track | None:
        if self.yandex is None:
            return None

        with self.yandex_track_lock:
            track = self.yandex_last_track
        if track is None:
            return None

        artist = track.artists[0].name if len(track.artists) > 0 else ""

        return Track(
            source="Yandex",
            id=str(track.id),
            title=track.title or "",
            artist=artist or "",
            duration_ms=track.duration_ms or 0,
        )

    def convert_current_track_winrt(self) -> Track | None:
        if self.winrt is None:
            return None

        track = self.winrt.get_current_track()
        if track is None:
            return None

        duration_ms = track.duration.total_seconds() * 1000 if track.duration else 0
        return Track(
            source="Local",
            id=track.title,
            title=track.title,
            artist=track.artist,
            duration_ms=int(duration_ms),
        )

    def convert_current_status_winrt(self) -> Playback | None:
        if self.winrt is None:
            return None

        state = Playback.from_win(self.winrt.status)
        position_ms = self.winrt.get_position().total_seconds() * 1000
        return Playback(
            state=state,
            position_ms=int(position_ms),
            updated_at=time.time(),
        )

    def get_current_track_yandex(self, forced: bool = True) -> Update | None:
        if self.yandex_startup and self.yandex_last_track is None:
            self.update_yandex()

        ytrack = self.convert_current_track_yandex()
        if ytrack is None:
            return None

        wtrack = self.convert_current_track_winrt()
        if wtrack is not None:
            durations_match = abs(wtrack.duration_ms - ytrack.duration_ms) < 200

            if durations_match:
                self.grace_armed = True
                self.grace_diverge_time = None
                playback = self.convert_current_status_winrt()
                assert playback is not None
                return Update(track=ytrack, playback=playback)

            # Durations differ
            if self.winrt.VERBOSE:
                print(
                    f"Different durations: {wtrack.duration_ms} != {ytrack.duration_ms}"
                )

            if self.grace_armed:
                if self.grace_diverge_time is None:
                    self.grace_diverge_time = time.time()
                elapsed = time.time() - self.grace_diverge_time
                if elapsed < Discovery.GRACE_PERIOD:
                    # Within grace: trust Yandex, use divergence time as track start
                    return Update(
                        track=ytrack,
                        playback=Playback(
                            state="Playing",
                            position_ms=int(elapsed * 1000),
                            updated_at=time.time(),
                        ),
                    )
                else:
                    self.grace_armed = False

            # Not in grace period - if not forced, winrt is preferred
            if not forced:
                return

        position_ms: int = 0
        if (
            self.lastupdate is not None and self.lastupdate.track.id == ytrack.id
        ):  # update position
            position_ms = self.lastupdate.playback.position_ms
            position_ms += int(
                (time.time() - self.lastupdate.playback.updated_at) * 1000
            )
        state = "Playing"
        if position_ms > ytrack.duration_ms:
            state = "Stopped"

        return Update(
            track=ytrack,
            playback=Playback(
                state=state,
                position_ms=position_ms,
                updated_at=time.time(),
            ),
        )

    def _get_current(self) -> Update | None:
        if self.desired_source == "Yandex":
            self.lastupdate = self.get_current_track_yandex(forced=True)
            return self.lastupdate
        elif self.desired_source is None:
            yupd = self.get_current_track_yandex(forced=False)
            if yupd is not None:
                self.lastupdate = yupd
                return self.lastupdate

        wtrack = self.convert_current_track_winrt()
        playback = self.convert_current_status_winrt()

        if wtrack is not None and playback is not None:
            self.lastupdate = Update(track=wtrack, playback=playback)
            return self.lastupdate
        elif self.desired_source is None:
            self.lastupdate = self.get_current_track_yandex(forced=True)
            return self.lastupdate
        else:
            self.lastupdate = None
            return self.lastupdate

    def get_current_track(self) -> Track | None:
        self._get_current()
        return self.lastupdate.track if self.lastupdate else None

    def get_position(self) -> datetime.timedelta:
        self._get_current()
        if self.lastupdate is None:
            return datetime.timedelta()
        pos = self.lastupdate.playback.position_ms
        return datetime.timedelta(milliseconds=pos)

    def get_status(self) -> Playback | None:
        upd = self._get_current()
        if upd is None:
            return None
        return upd.playback
