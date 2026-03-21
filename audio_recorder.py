"""
音频录制模块：使用 sounddevice 采集麦克风音频，保存为 .wav 文件。
"""

import datetime
import threading
import time
from pathlib import Path
from typing import List, Optional

import numpy as np
import sounddevice as sd
from scipy.io import wavfile

SAMPLE_RATE = 16000  # 16 kHz，Azure Speech 最佳采样率
CHANNELS = 1  # 单声道


class AudioRecorder:
    """简单的麦克风录音器，支持开始/停止回调。"""

    def __init__(self, output_dir: str = "."):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._frames: List[np.ndarray] = []
        self._stream = None
        self._recording = False
        self._lock = threading.Lock()
        self._elapsed = 0.0
        self._start_time: Optional[float] = None

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def elapsed_seconds(self) -> float:
        if not self._recording:
            return self._elapsed
        if self._start_time is not None:
            import time
            return time.time() - self._start_time
        return 0.0

    def start(self):
        """开始录音。"""
        import time as _time
        with self._lock:
            if self._recording:
                return
            self._frames = []
            self._recording = True
            self._start_time = _time.time()

        def _callback(indata, frames, time_info, status):
            if self._recording:
                self._frames.append(indata.copy())

        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            callback=_callback,
            blocksize=1024,
        )
        self._stream.start()

    def stop(self) -> Optional[str]:
        """停止录音并保存为 .wav，返回文件路径。无数据则返回 None。"""
        with self._lock:
            if not self._recording:
                return None
            self._recording = False

        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        if not self._frames:
            return None

        audio = np.concatenate(self._frames, axis=0)
        self._elapsed = len(audio) / SAMPLE_RATE

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = self.output_dir / f"recording_{timestamp}.wav"
        wavfile.write(str(filepath), SAMPLE_RATE, audio)
        return str(filepath)
