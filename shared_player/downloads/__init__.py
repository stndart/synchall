# from .p2p import P2PFinder
# from .yt import YoutubeFinder
from .yn import YnisonFinder

from ..types import Track, Source, DownloadInfo

__all__ = ["Finder"]


supported: list[Source] = ["Yandex"]


class Finder:
    def __init__(self):
        # self.p2p = P2PFinder()
        # self.youtube = YoutubeFinder()
        self.yandex = YnisonFinder()

    def find(self, track: Track) -> DownloadInfo:
        if track.source not in supported:
            raise NotImplementedError(
                f"Support for {track.source} is not implemented yet."
            )

        match track.source:
            case "Local":
                raise NotImplementedError("Local tracks are not supported yet")
            case "Youtube":
                raise NotImplementedError("Youtube tracks are not supported yet")
            case "Spotify":
                raise NotImplementedError("Spotify tracks are not supported yet")
            case "Yandex":
                return self.yandex.find(track)
