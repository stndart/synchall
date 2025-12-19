import asyncio
import json
import os
import time
import uuid
from typing import Any
from urllib.parse import quote

import browser_cookie3
import websockets
from dotenv import load_dotenv, set_key, find_dotenv
from yandex_music import Track, Client


def default_payload(device_id: str) -> dict[str, Any]:
    return {
        "update_full_state": {
            "player_state": {
                "player_queue": {
                    "current_playable_index": -1,
                    "entity_id": "",
                    "entity_type": "VARIOUS",
                    "playable_list": [],
                    "options": {"repeat_mode": "NONE"},
                    "shuffle_optional": None,
                    "entity_context": "BASED_ON_ENTITY_BY_DEFAULT",
                    "version": {
                        "device_id": device_id,
                        "version": 8592001060111840000,
                        "timestamp_ms": 0,
                    },
                    "from_optional": "",
                    "initial_entity_optional": None,
                    "adding_options_optional": None,
                    "queue": None,
                },
                "status": {
                    "duration_ms": 0,
                    "paused": True,
                    "playback_speed": 1,
                    "progress_ms": 0,
                    "version": {
                        "device_id": device_id,
                        "version": 3578769351571258400,
                        "timestamp_ms": 0,
                    },
                },
                "player_queue_inject_optional": None,
            },
            "device": {
                "volume": 0.7,
                "capabilities": {
                    "can_be_player": True,
                    "can_be_remote_controller": False,
                    "volume_granularity": 20,
                },
                "info": {
                    "app_name": "Chrome",
                    "app_version": "143.0.0.0",
                    "title": "Browser Chrome",
                    "device_id": device_id,
                    "type": "WEB",
                },
                "volume_info": {"volume": 0.7, "version": None},
                "is_shadow": True,
            },
            "is_currently_active": False,
            "sync_state_from_eov_optional": None,
        },
        "rid": str(uuid.uuid4()),
        "player_action_timestamp_ms": 0,
        "activity_interception_type": "DO_NOT_INTERCEPT_BY_DEFAULT",
    }


def status_payload(device_id: str) -> dict[str, Any]:
    return {
        "update_playing_status": {
            "playing_status": {
                "duration_ms": 155780,
                "progress_ms": 10000,
                "paused": False,
                "playback_speed": 1,
                "version": {
                    "device_id": device_id,
                    "version": 1635218570935773200,
                    "timestamp_ms": int(time.time()),
                },
            }
        },
        "rid": "941b0c45-de3d-4b93-93dc-c6c8ccd70aed",
        "player_action_timestamp_ms": int(time.time()),
        "activity_interception_type": "DO_NOT_INTERCEPT_BY_DEFAULT",
    }


class Ynison_discovery:
    session_id: str
    device_id: str
    user_id: str
    device_info: dict[str, str | int] = {
        "app_name": "Chrome",
        "app_version": "143.0.0.0",
        "type": 1,
    }
    headers: dict[str, str]
    sec_proto_meta: str

    ynison_shard: str
    ynison_session_id: str
    ynison_ticket: str

    client: Client

    @staticmethod
    def get_session_id(skip_environ: bool = False) -> str:
        cj = browser_cookie3.firefox(domain_name="yandex.ru")
        for cookie in cj:
            if cookie.name == "Session_id":
                assert cookie.value is not None, (
                    "Failed to extract Session_id from cookies"
                )
                return cookie.value

        session_id: str | None = None
        if not skip_environ:
            session_id = os.environ.get("Y_SESSION_ID", None)

        if session_id is None:
            raise RuntimeError(
                "Login to https://music.yandex.ru in firefox to use yandex.music integration."
            )
        return session_id

    def __init__(self, session_id: str | None = None):
        load_dotenv()
        if session_id is None:
            session_id = os.environ.get("Y_SESSION_ID", None)

        assert session_id is not None, "Login to https://music.yandex.ru in firefox"

        self.load_ynison_init_state(session_id)
        self.load_ym_client()

        self.get_jumphost()

    def load_ynison_init_state(self, session_id: str):
        self.session_id = session_id

        self.user_id = self.session_id[self.session_id.find("|") + 1 :]
        self.user_id = self.user_id[: self.user_id.find(".")]
        assert len(self.user_id) > 0, "Failed to extract USER_ID from SESSION_ID"

        self.device_id = str(uuid.uuid4())

        self.headers = {
            "Origin": "https://music.yandex.ru",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
            "Cookie": f"Session_id={self.session_id};",
        }

        self.sec_proto_meta = json.dumps(
            {
                "Ynison-Device-Id": self.device_id,
                "Ynison-Device-Info": json.dumps(self.device_info),
                "X-Yandex-Music-Multi-Auth-User-Id": self.user_id,
            }
        )

    def load_ym_client(self):
        token = os.environ.get("TOKEN", "")

        self.client = Client(token)
        self.client.init()

    def get_jumphost(self):
        uri = (
            "wss://ynison.music.yandex.ru/"
            "redirector.YnisonRedirectService/GetRedirectToYnison"
        )
        proto_meta_pct = quote(
            self.sec_proto_meta, safe=""
        )  # encodes all reserved chars

        async def conn():
            async with websockets.connect(
                uri,
                additional_headers=self.headers,
                subprotocols=["Bearer", "v2", proto_meta_pct],  # type: ignore
            ) as ws:
                msg = await ws.recv()
                data = json.loads(msg)
                return data

        response = asyncio.run(conn())
        assert "host" in response, "GetRedirectToYnison failed"

        # successfull login, save id for later
        set_key(find_dotenv(), "Y_SESSION_ID", self.session_id)

        self.ynison_shard = (
            f"wss://{response['host']}/ynison_state.YnisonStateService/PutYnisonState"
        )
        self.ynison_session_id = response["session_id"]
        self.ynison_ticket = response["redirect_ticket"]

    def get_player_state(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if payload is None:
            payload = default_payload(self.device_id)

        SEC_PROTO_META = json.dumps(
            {
                "Ynison-Device-Id": self.device_id,
                "Ynison-Redirect-Ticket": self.ynison_ticket,
                "Ynison-Session-Id": self.ynison_session_id,
                "Ynison-Device-Info": json.dumps(self.device_info),
                "X-Yandex-Music-Multi-Auth-User-Id": self.user_id,
            }
        )

        proto_meta_pct = quote(SEC_PROTO_META, safe="")

        async def conn():
            async with websockets.connect(
                self.ynison_shard,
                additional_headers=self.headers,
                subprotocols=["Bearer", "v2", proto_meta_pct],  # type: ignore
            ) as ws:
                await ws.send(json.dumps(payload))
                return json.loads(await ws.recv())

        return asyncio.run(conn())

    def get_current_track(self, state: dict[str, Any] | None = None) -> Track:
        if state is None:
            state = self.get_player_state()

        queue = state["player_state"]["player_queue"]
        match queue["entity_type"]:
            case "PLAYLIST" | "RADIO":
                i = queue["current_playable_index"]
                playlist = queue["playable_list"]
                track_id = playlist[i]["playable_id"]
            case _:
                raise RuntimeError(f"Unknown entity {queue['entity_type']}")

        tracks = self.client.tracks(track_id)
        assert len(tracks) > 0, f"Illegal track_id {track_id}"

        return tracks[0]

    def get_next_track(self, state: dict[str, Any] | None = None) -> Track | None:
        if state is None:
            state = self.get_player_state()

        queue = state["player_state"]["player_queue"]
        match queue["entity_type"]:
            case "PLAYLIST" | "RADIO":
                i = queue["current_playable_index"]
                playlist = queue["playable_list"]
                if len(playlist) >= i:
                    track_id = playlist[i + 1]["playable_id"]
                else:
                    return None
            case _:
                raise RuntimeError(f"Unknown entity {queue['entity_type']}")

        tracks = self.client.tracks(track_id)
        assert len(tracks) > 0, f"Illegal track_id {track_id}"

        return tracks[0]
