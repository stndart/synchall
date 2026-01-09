import os

from dotenv import load_dotenv
from yandex_music import Client
from ymd.api import ApiTrackQuality, get_download_info

from ..types import Track, DownloadInfo


class YnisonFinder:
    client: Client

    def __init__(self):
        load_dotenv()

        self.load_ym_client()

    def load_ym_client(self):
        token = os.environ.get("TOKEN", "")

        self.client = Client(token=token)
        self.client.init()

    def find(self, track: Track) -> DownloadInfo:
        tracks = self.client.tracks(track.id)
        assert len(tracks) > 0

        dinfo = get_download_info(tracks[0], quality=ApiTrackQuality.NORMAL)
        return DownloadInfo(url=dinfo.urls[0], decryption_key=dinfo.decryption_key)
