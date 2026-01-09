import threading
import time
import os

import requests

from .stream import StreamPlayback
from ..types import Instance, Track
from ..downloads import Finder


class SyncPlayer:
    # static
    CHUNK_HTTP = 64 * 1024  # bytes read from HTTP each iteration
    POLL_TIME = 1

    # fields
    playing: bool

    host: str
    port: int
    addr: str

    room: str | None
    playback: StreamPlayback
    poll_thread: threading.Thread
    download_thread: threading.Thread | None

    current_track: Track | None

    def __init__(self):
        self.playing = True

        self.host = os.getenv("SYNC_IP", "localhost")
        self.port = int(os.getenv("SYNC_PORT", 5400))
        self.addr = f"http://{self.host}:{self.port}"

        self.room = os.getenv("SYNC_ROOM", None)
        self.playback = StreamPlayback()
        self.poll_thread = threading.Thread(target=self.poll_thread_fun)
        self.poll_thread.start()
        self.download_thread = None

        self.current_track = None
        self.finder = Finder()

    def connect(self, uid: str):
        self.room = uid

    def poll_thread_fun(self):
        while self.playing:
            if self.room is None:
                time.sleep(1)
                continue

            resp = requests.get(self.addr + f"/update/{str(self.room)}")
            assert resp.status_code == 200
            inst = Instance.model_validate_json(resp.content.decode())

            if inst.track is None:
                self.playback.stop()
            elif self.current_track != inst.track:
                self.playback.stop()
                self.schedule_download(inst.track)
                self.current_track = inst.track
            else:
                match inst.playback.state:
                    case "Paused":
                        self.playback.pause()
                    case "Playing":
                        self.playback.resume()
                    case "Stopped":
                        self.playback.stop()

            time.sleep(SyncPlayer.POLL_TIME)

    def schedule_download(self, track: Track):
        dinfo = self.finder.find(track)

        self.playback.init_stream(dinfo.decryption_key)
        self.playback.reopen_convert()

        print(f"Now playing: {track.artist} - {track.title}", flush=True)

        if self.download_thread is not None and self.download_thread.is_alive():
            self.download_thread.join(timeout=1)
        self.download_thread = threading.Thread(
            target=self.download_thread_fun,
            args=(dinfo.url,),
            daemon=True,
        )
        self.download_thread.start()

    def download_thread_fun(self, url: str):
        # Start HTTP stream
        resp = requests.get(url, stream=True)
        resp.raise_for_status()

        N = 0
        for chunk in resp.iter_content(SyncPlayer.CHUNK_HTTP):
            if not chunk:
                continue
            self.playback.write(chunk)
            N += len(chunk)

    def close(self):
        self.playing = False

        self.playback.close(timeout=1)
        if self.download_thread is not None:
            self.download_thread.join()
        self.poll_thread.join()
