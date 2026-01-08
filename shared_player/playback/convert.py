from queue import Empty, Queue
import subprocess
from threading import Event, Lock, Thread


class StreamConvert:
    # static
    CHUNK_SIZE = 4096

    # fields
    ffmpeg_cmd: list[str]

    sample_rate: int
    channels: int

    write_buffer: Queue
    read_buffer: bytearray

    _write_thread: Thread
    _read_thread: Thread

    _buf_lock: Lock
    _stopped: Event

    @staticmethod
    def has_ffmpeg() -> bool:
        ffmpeg_check_cmd = ["ffmpeg", "-version"]

        ff = subprocess.run(ffmpeg_check_cmd, capture_output=True)
        if ff.stdout.decode().startswith("ffmpeg version"):
            return True
        return False

    def __init__(
        self, ff_output_format: str, ff_output_sample_rate: int, ff_output_channels: int
    ):
        assert self.has_ffmpeg()

        self.sample_rate = ff_output_sample_rate
        self.channels = ff_output_channels

        self.ffmpeg_cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            "pipe:0",  # input from stdin
            "-f",
            ff_output_format,
            "-ar",
            str(self.sample_rate),
            "-ac",
            str(self.channels),
            "pipe:1",  # output raw PCM to stdout
        ]

        self.ffmpeg_stream = subprocess.Popen(
            self.ffmpeg_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self.write_buffer = Queue()
        self.read_buffer = bytearray()

        self._stopped = Event()
        self._buf_lock = Lock()

        self._write_thread = Thread(target=self._write_thread_fun, daemon=True)
        self._read_thread = Thread(target=self._read_thread_fun, daemon=True)
        self._write_thread.start()
        self._read_thread.start()

    def write(self, data: bytes):
        if not self._stopped.is_set():
            self.write_buffer.put(data)

    def read(self, n: int = -1) -> bytes:
        N = n * self.channels * 2  # bytes per channel
        with self._buf_lock:
            if n < 0:  # draw all
                res = self.read_buffer
                self.read_buffer = bytearray()
            else:
                res = self.read_buffer[:N]
                self.read_buffer = self.read_buffer[N:]
        return bytes(res)

    def flush(self):
        while self.write_buffer.qsize() > 0:
            try:
                self.write_buffer.get_nowait()
            except Empty:
                pass  # because data race

        assert self.ffmpeg_stream.stdin is not None
        if not self.ffmpeg_stream.stdin.closed:
            self.ffmpeg_stream.stdin.flush()

        with self._buf_lock:
            self.read_buffer = bytearray()

        assert self.ffmpeg_stream.stdout is not None
        self.ffmpeg_stream.stdout.flush()

    def join(self):
        self.write_buffer.put(None)
        self._write_thread.join()

        assert self.ffmpeg_stream.stdin is not None
        if not self.ffmpeg_stream.stdin.closed:
            self.ffmpeg_stream.stdin.close()

        self._read_thread.join()

    def close(self):
        self._stopped.set()
        self.flush()
        self.join()

    def _write_thread_fun(self):
        assert self.ffmpeg_stream.stdin is not None

        while not self._stopped.is_set():
            chunk = self.write_buffer.get()
            if chunk is None:
                break
            self.ffmpeg_stream.stdin.write(chunk)

    def _read_thread_fun(self):
        assert self.ffmpeg_stream.stdout is not None

        while not self._stopped.is_set():
            chunk = self.ffmpeg_stream.stdout.read(StreamConvert.CHUNK_SIZE)
            if not chunk:
                break
            with self._buf_lock:
                self.read_buffer.extend(chunk)
