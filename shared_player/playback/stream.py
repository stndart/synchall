import subprocess
import threading
from queue import Queue
from time import sleep

import numpy as np
import pyaudio
from Crypto.Cipher import AES
from Crypto.Cipher._mode_ctr import CtrMode


class StreamPlayback:
    # static props
    CHUNK_HTTP = 64 * 1024  # bytes read from HTTP each iteration
    FF_OUTPUT_SAMPLE_RATE = 44100
    FF_OUTPUT_CHANNELS = 2
    FF_OUTPUT_FORMAT = "s16le"  # signed 16-bit little-endian PCM

    # properties
    timeout: float | None

    cipher: CtrMode | None
    convert_thread: threading.Thread | None
    ffmpeg_stream: subprocess.Popen | None
    buffer: Queue

    _pd: pyaudio.PyAudio
    audio_stream: pyaudio.Stream | None
    audio_stream_lock: threading.Lock
    audio_thread: threading.Thread | None

    volume: float  # from 0 to 1
    pause_lock: threading.Lock

    def __init__(self, timeout: float | None = 1):
        assert self.has_ffmpeg(), "ffmpeg should be installed and in path"
        self.timeout = timeout

        self.ffmpeg_cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            "pipe:0",  # input from stdin
            "-f",
            StreamPlayback.FF_OUTPUT_FORMAT,
            "-ar",
            str(StreamPlayback.FF_OUTPUT_SAMPLE_RATE),
            "-ac",
            str(StreamPlayback.FF_OUTPUT_CHANNELS),
            "pipe:1",  # output raw PCM to stdout
        ]

        self.cipher = None
        self.buffer = Queue()
        self.convert_thread = None
        self.ffmpeg_stream = None

        self.audio_stream = None
        self.audio_stream_lock = threading.Lock()
        self.audio_thread = None

        self._pd = pyaudio.PyAudio()
        self.volume = 0.2
        self.pause_lock = threading.Lock()

    @staticmethod
    def has_ffmpeg() -> bool:
        ffmpeg_check_cmd = ["ffmpeg", "-version"]

        ff = subprocess.run(ffmpeg_check_cmd, capture_output=True)
        if ff.stdout.decode().startswith("ffmpeg version"):
            return True
        return False

    def init_stream(self, decryption_key: str | None):
        assert self.ffmpeg_stream is None, "Stream is already initialized"

        self.ffmpeg_stream = subprocess.Popen(
            self.ffmpeg_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        if decryption_key is not None:
            key_bytes = bytes.fromhex(decryption_key)
            # Matches your decrypt_data: AES.new(key=..., nonce=bytes(12), mode=AES.MODE_CTR)
            self.cipher = AES.new(key_bytes, nonce=bytes(12), mode=AES.MODE_CTR)

        with self.audio_stream_lock:
            self.audio_stream = self._pd.open(
                format=pyaudio.paInt16,
                channels=StreamPlayback.FF_OUTPUT_CHANNELS,
                rate=StreamPlayback.FF_OUTPUT_SAMPLE_RATE,
                output=True,
            )

        self.convert_thread = threading.Thread(
            target=self.convert_thread_fun, daemon=True
        )
        self.convert_thread.start()

        self.audio_thread = threading.Thread(target=self.audio_thread_fun, daemon=True)
        self.audio_thread.start()

    def write(self, chunk: bytes):
        self.buffer.put(chunk)

    def convert_thread_fun(self):
        assert self.ffmpeg_stream is not None, "Stream is not initialized"
        assert self.ffmpeg_stream.stdin is not None
        assert self.ffmpeg_stream.stdout is not None

        while True:
            try:
                chunk = self.buffer.get()
                if self.cipher:
                    chunk = self.cipher.decrypt(chunk)
                self.ffmpeg_stream.stdin.write(chunk)
            except BrokenPipeError:
                # ffmpeg exited early (user stopped playback, error, etc.)
                break
            except Exception as e:
                print("Convert error", e)

    def pause(self):
        self.pause_lock.acquire()

    def resume(self):
        self.pause_lock.release()

    def audio_thread_fun(self):
        assert self.audio_stream is not None
        assert self.ffmpeg_stream is not None, "Stream is not initialized"
        assert self.ffmpeg_stream.stdout is not None

        try:
            while True:
                data = self.ffmpeg_stream.stdout.read(4096)
                if not data:
                    break  # no more PCM data

                samples = np.frombuffer(data, dtype=np.int16)
                samples_f = samples.astype(np.float32) / (2**15)
                samples_f *= self.volume
                samples_f = np.clip(samples_f, -1.0, 1.0)
                data = (samples_f * (2**15)).astype(np.int16).tobytes()

                with self.audio_stream_lock:
                    while len(data) > 0:
                        N = self.audio_stream.get_write_available()
                        if N < 1000:
                            sleep(0.01)
                            continue
                        N *= 4  # 2 channels, 2 bytes per channel
                        with self.pause_lock:
                            self.audio_stream.write(data[:N])
                        data = data[N:]
        except Exception as e:
            print("Playback error:", e)
        finally:
            self.ffmpeg_stream.terminate()

    def close(self, timeout: float | None = 1):
        if self.ffmpeg_stream is not None:
            try:
                self.ffmpeg_stream.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.ffmpeg_stream.kill()
        if self.convert_thread is not None:
            self.convert_thread.join(timeout=timeout)
        if self.audio_thread is not None:
            self.audio_thread.join(timeout=timeout)

    def __enter__(self) -> "StreamPlayback":
        return self

    def __exit__(self, type, value, traceback):
        self.close(timeout=self.timeout)
