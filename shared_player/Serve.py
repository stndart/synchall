from datetime import datetime
import json
import os
import time
from typing import Any

import requests
from dotenv import load_dotenv

from .discovery.integrated import Discovery
from .types import Update


class SyncHost:
    # static
    POLL_TIME = 1

    # fields
    host: str
    port: int
    addr: str

    room: str | None
    discovery = Discovery()

    _last_event: Update | None = None

    def _get(self, path: str) -> dict[str, Any]:
        resp = requests.get(self.addr + path)
        assert resp.status_code == 200
        return json.loads(resp.content.decode())

    def _post(self, path: str, data: Any) -> dict[str, Any]:
        resp = requests.post(self.addr + path, data=data)
        assert resp.status_code == 200
        return json.loads(resp.content.decode())

    def __init__(self):
        self._last_event = None

        self.host = os.getenv("SYNC_IP", "localhost")
        self.port = int(os.getenv("SYNC_PORT", 5400))
        self.addr = f"http://{self.host}:{self.port}"

        self.room = None
        self.discovery = Discovery()

    def start(self, uid: str | None = None):
        if uid is None:
            self.room = self._get("/host/create")["token"]
        else:
            self.room = self._get(f"/host/create/{uid}")["token"]

        self.discovery.on_update(self.update)
        self.update()

    def stop(self):
        self.discovery.clear_callbacks()

    def update(self):
        if self.room is None:
            return
        try:
            upd = Update(
                track=self.discovery.get_current_track(),
                playback=self.discovery.get_status(),
            )

            if self._last_event is not None:
                if upd.track == self._last_event:
                    print("Skipped:", upd.format())
                    return  # skip, non-informative

            print(
                f"[{datetime.fromtimestamp(time.time()).strftime('%H:%M:%S.2f')}]",
                upd.format(),
            )
            self._last_event = upd
            self._post(f"/host/update/{self.room}", {"json": upd.model_dump_json()})
        except Exception as e:
            print(
                f"[{datetime.fromtimestamp(time.time()).strftime('%H:%M:%S.2f')}]",
                f"error upd post: {str(e)}",
            )
            print(self.discovery.get_current_track())
            return


def main():
    load_dotenv()

    host = SyncHost()
    room = os.getenv("SYNC_ROOM", None)
    host.start(room)

    print(f"Hosted on [{host.room}]")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        host.stop()

    print("Stopped.")
