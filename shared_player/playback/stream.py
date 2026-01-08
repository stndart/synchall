from threading import Event, Thread, Lock

import numpy as np
import pyaudio
from Crypto.Cipher import AES
from Crypto.Cipher._mode_ctr import CtrMode

from .convert import StreamConvert


class StreamPlayback:
    # static props
    CHUNK_HTTP = 64 * 1024  # bytes read from HTTP each iteration
    FF_OUTPUT_SAMPLE_RATE = 44100
    FF_OUTPUT_CHANNELS = 2
    FF_OUTPUT_FORMAT = "s16le"  # signed 16-bit little-endian PCM

    # properties
    timeout: float | None

    cipher: CtrMode | None
    convert_stream: StreamConvert
    convert_stream_lock: Lock

    _pd: pyaudio.PyAudio
    audio_stream: pyaudio.Stream
    audio_stream_lock: Lock
    audio_thread: Thread
    _stopped: Event

    volume: float  # from 0 to 1
    unpaused: Event

    def __init__(self, timeout: float | None = 1):
        self.timeout = timeout
        self.cipher = None
        self.convert_stream_lock = Lock()
        self.convert_stream = StreamConvert(
            StreamPlayback.FF_OUTPUT_FORMAT,
            StreamPlayback.FF_OUTPUT_SAMPLE_RATE,
            StreamPlayback.FF_OUTPUT_CHANNELS,
        )

        self._pd = pyaudio.PyAudio()
        self.volume = 0.2
        self.unpaused = Event()
        self.unpaused.set()

        self.audio_stream_lock = Lock()
        self.audio_stream = self._pd.open(
            format=pyaudio.paInt16,
            channels=StreamPlayback.FF_OUTPUT_CHANNELS,
            rate=StreamPlayback.FF_OUTPUT_SAMPLE_RATE,
            output=True,
        )
        self._stopped = Event()
        self.audio_thread = Thread(target=self.audio_thread_fun, daemon=True)
        self.audio_thread.start()

    def pause(self):
        self.unpaused.clear()

    def stop(self):
        self.pause()
        self.convert_stream.flush()

    def resume(self):
        self.unpaused.set()

    def init_stream(self, decryption_key: str | None):
        with self.convert_stream_lock, self.audio_stream_lock:
            self.convert_stream.flush()

            if decryption_key is not None:
                key_bytes = bytes.fromhex(decryption_key)
                self.cipher = AES.new(key_bytes, nonce=bytes(12), mode=AES.MODE_CTR)

    def write(self, chunk: bytes):
        with self.convert_stream_lock:
            if self.cipher:
                chunk = self.cipher.decrypt(chunk)
            if not self._stopped.is_set():
                self.convert_stream.write(chunk)

    def audio_thread_fun(self):
        try:
            while not self._stopped.is_set():
                self.unpaused.wait()

                N = self.audio_stream.get_write_available()
                N *= self.convert_stream.channels * 2  # bytes per channel

                data = self.convert_stream.read(N)
                if not data:
                    continue

                samples = np.frombuffer(data, dtype=np.int16)
                samples_f = samples.astype(np.float32) / (2**15)
                samples_f *= self.volume
                samples_f = np.clip(samples_f, -1.0, 1.0)
                data = (samples_f * (2**15)).astype(np.int16).tobytes()

                with self.audio_stream_lock:
                    self.audio_stream.write(data)
        except Exception as e:
            print("Playback error:", e)

    def close(self, timeout: float | None = 1):
        if timeout is None:  # wait until the track is over
            with self.convert_stream_lock:  # prohibit writing
                self.convert_stream.join()
        else:
            self.convert_stream.close()
            self._stopped.set()
        self.unpaused.set()  # unblock audio_thread

        if self.audio_thread.is_alive():
            self.audio_thread.join(timeout=timeout)

    def __enter__(self) -> "StreamPlayback":
        return self

    def __exit__(self, type, value, traceback):
        self.close(timeout=self.timeout)
