"""
Phase 2 — Azure Voice Live 实时语音对话 Tab
SDK: azure-ai-voicelive 1.1.0 (GA)
架构: Voice Live WebSocket → 麦克风 PCM16 24kHz → 流式语音回复
关键设计:
  - UI 更新通过 page.run_task() 调度到 Flet 事件循环 (线程安全)
  - 事件处理只修改控件属性并调用 _mark_dirty(), 自动 debounce
  - 用户转写气泡在 SPEECH_STOPPED 时创建占位, 避免出现在 AI 气泡下方
"""

import asyncio
import base64
import logging
import threading
import time
from typing import Optional
from urllib.parse import urlparse, urlunparse

import numpy as np
import sounddevice as sd
import flet as ft

from config_manager import load_config

# ── 日志 ─────────────────────────────────────────────────────────
log = logging.getLogger("voicelive")
log.setLevel(logging.INFO)
_fh = logging.FileHandler("voicelive_debug.log", encoding="utf-8")
_fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
log.addHandler(_fh)


def _normalize_endpoint(endpoint: str) -> str:
    parsed = urlparse(endpoint)
    return urlunparse((parsed.scheme, parsed.netloc, "/", "", "", ""))


# ── 模型/语音/角色 选项 ──────────────────────────────────────────
MODEL_OPTIONS = [
    ("gpt-realtime", "gpt-realtime（推荐）"),
    ("gpt-realtime-mini", "gpt-realtime-mini（低成本）"),
    ("gpt-4o", "gpt-4o"),
    ("gpt-4.1", "gpt-4.1"),
    ("phi4-mm-realtime", "phi4-mm-realtime（轻量）"),
]

ROLE_PRESETS = {
    "玩具儿童助手": "你是一个友善、活泼的儿童智能玩具助手。用简单、有趣的语言与小朋友对话。回答要简短，语气要温暖、鼓励。",
    "AI 耳机助手": "你是一个智能耳机的 AI 助手。帮助用户管理日程、回答问题、翻译短语。回答简洁高效，像一个贴心的个人助理。",
    "企业客服": "你是一个专业的企业客服代表。用礼貌、专业的语气回答客户问题。始终保持耐心和准确。",
}

VOICE_OPTIONS = [
    # 中文语音
    ("zh-CN-XiaoxiaoNeural", "晓晓（中文女声）"),
    ("zh-CN-XiaoyiNeural", "晓伊（中文女声·温柔）"),
    ("zh-CN-XiaochenNeural", "晓辰（中文女声·成熟）"),
    ("zh-CN-XiaoshuangNeural", "晓双（中文女声·兒童）"),
    ("zh-CN-XiaomoNeural", "晓墨（中文女声·多情感）"),
    ("zh-CN-XiaoxiaoMultilingualNeural", "晓晓多语言（中/英）"),
    ("zh-CN-YunxiNeural", "云希（中文男声）"),
    ("zh-CN-YunjianNeural", "云健（中文男声·新闻）"),
    ("zh-CN-YunyangNeural", "云扬（中文男声·专业）"),
    ("zh-CN-YunzeNeural", "云泽（中文男声·成熟）"),
    # 英文语音
    ("en-US-Ava:DragonHDLatestNeural", "Ava HD（英文女声·高清）"),
    ("en-US-JennyNeural", "Jenny（英文女声）"),
    ("en-US-AriaNeural", "Aria（英文女声·多情感）"),
    ("en-US-AndrewNeural", "Andrew（英文男声）"),
    ("en-US-GuyNeural", "Guy（英文男声）"),
    ("en-US-BrianNeural", "Brian（英文男声·叙述）"),
    # 日韩语音
    ("ja-JP-NanamiNeural", "Nanami（日语女声）"),
    ("ko-KR-SunHiNeural", "SunHi（韩语女声）"),
]

RATE_OPTIONS = [
    ("x-slow", "极慢"),
    ("slow", "慢速"),
    ("medium", "正常"),
    ("fast", "快速"),
    ("x-fast", "极快"),
]

SAMPLE_RATE = 24000
CHANNELS = 1
CHUNK_SIZE = 1200  # 50ms — 麦克风采集 blocksize
OUT_BLOCKSIZE = 4800  # 200ms — 播放 blocksize，增大以吸收网络抖动


# ── 线程安全音频缓冲区 ────────────────────────────────────────────
class _AudioBuffer:
    """Thread-safe audio ring buffer with re-prebuffer underrun handling.

    核心改进 (v3):
    - underrun 时自动重新进入预缓冲，将多次微小断裂合并为一次短暂停顿
    - 暴露 underrun 计数器供自适应算法使用
    - is_outputting 属性支持客户端回声门控
    """
    _FADE_SAMPLES = 240   # 10ms 淡入淡出 (24kHz)

    def __init__(self):
        import threading as _th
        self._buf = bytearray()
        self._lock = _th.Lock()
        self._prebuffering = False
        self._prebuf_bytes = 0
        self._reprebuf_bytes = 0     # 二次预缓冲阈值
        self._active = False
        self._last_good = np.zeros(self._FADE_SAMPLES, dtype=np.int16)
        self._in_underrun = False
        self._underrun_count = 0

    def start_response(self, prebuf_bytes: int, reprebuf_bytes: int = 0):
        with self._lock:
            self._buf.clear()
            self._active = True
            self._prebuffering = True
            self._prebuf_bytes = prebuf_bytes
            self._reprebuf_bytes = reprebuf_bytes
            self._in_underrun = False
            self._underrun_count = 0

    def write(self, data: bytes) -> bool:
        """Write PCM data. Returns True if prebuffering just completed."""
        with self._lock:
            self._buf.extend(data)
            if self._prebuffering and len(self._buf) >= self._prebuf_bytes:
                self._prebuffering = False
                return True
            return False

    def release_prebuffer(self):
        with self._lock:
            self._prebuffering = False

    @property
    def is_prebuffering(self) -> bool:
        return self._prebuffering

    @property
    def underrun_count(self) -> int:
        return self._underrun_count

    @property
    def buffered_ms(self) -> float:
        with self._lock:
            return len(self._buf) / (SAMPLE_RATE * 2) * 1000

    @property
    def is_outputting(self) -> bool:
        """AI 音频正在播放 (active + 非预缓冲中)。用于回声门控。"""
        with self._lock:
            return self._active and not self._prebuffering

    def read(self, frames: int) -> np.ndarray:
        needed = frames * 2
        with self._lock:
            if not self._active or self._prebuffering:
                return np.zeros(frames, dtype=np.int16)

            avail = len(self._buf)
            if avail >= needed:
                out = np.frombuffer(bytes(self._buf[:needed]), dtype=np.int16).copy()
                del self._buf[:needed]
                tail_n = min(self._FADE_SAMPLES, len(out))
                self._last_good[-tail_n:] = out[-tail_n:]
                if self._in_underrun:
                    self._in_underrun = False
                    fade_n = min(self._FADE_SAMPLES, len(out))
                    ramp = np.linspace(0.0, 1.0, fade_n, dtype=np.float32)
                    out[:fade_n] = (out[:fade_n].astype(np.float32) * ramp).astype(np.int16)
                return out

            # ── UNDERRUN ──
            self._underrun_count += 1
            self._in_underrun = True

            # 重新预缓冲: 保留已有数据，等待积累足够才恢复播放
            if self._reprebuf_bytes > 0:
                self._prebuffering = True
                self._prebuf_bytes = self._reprebuf_bytes
                # 不清空缓冲区 — 已有数据保留，write() 继续追加
                return np.zeros(frames, dtype=np.int16)

            # 无二次预缓冲: 播放残余数据 + 淡出
            if avail > 0:
                partial = np.frombuffer(bytes(self._buf[:avail]), dtype=np.int16).copy()
                self._buf.clear()
                tail_n = min(self._FADE_SAMPLES, len(partial))
                self._last_good[-tail_n:] = partial[-tail_n:]
                fade_n = min(self._FADE_SAMPLES, len(partial))
                ramp = np.linspace(1.0, 0.0, fade_n, dtype=np.float32)
                partial[-fade_n:] = (partial[-fade_n:].astype(np.float32) * ramp).astype(np.int16)
                out = np.zeros(frames, dtype=np.int16)
                out[:len(partial)] = partial
                return out
            else:
                fade = self._last_good.copy()
                ramp = np.linspace(1.0, 0.0, len(fade), dtype=np.float32)
                fade = (fade.astype(np.float32) * ramp).astype(np.int16)
                out = np.zeros(frames, dtype=np.int16)
                out[:len(fade)] = fade
                self._last_good[:] = 0
                return out

    def clear(self):
        with self._lock:
            self._buf.clear()
            self._active = False
            self._prebuffering = False
            self._in_underrun = False


def build_realtime_tab(page: ft.Page):
    """构建「Voice Live 实时语音对话」Tab 的全部 UI 和逻辑。"""

    # ══════════════════════════════════════════════════════════════
    # 共享状态
    # ══════════════════════════════════════════════════════════════
    vl_state = {
        "connection": None,
        "loop": None,
        "stop": threading.Event(),
        "thread": None,
    }
    audio_state = {
        "stream_in": None,
        "stream_out": None,
        "capturing": False,
    }
    audio_buf = _AudioBuffer()

    # ── 自适应抖动缓冲 (Adaptive Jitter Buffer) ──────────────
    # 解决网络抖动（如 VPN 切换后）导致的 AI 语音逐字卡顿
    _PREBUF_MS_MIN = 400          # 最小预缓冲 (ms)
    _PREBUF_MS_MAX = 2000         # 最大预缓冲 (ms)
    _PREBUF_MS_DEFAULT = 1000     # 默认预缓冲 (ms)  ↑ v3 提高默认值
    _REPREBUF_MS = 400            # 二次预缓冲 (ms)  ← v3 新增
    _JITTER_WINDOW = 20           # 抖动计算滑动窗口
    _UNDERRUN_WINDOW_SEC = 15     # underrun 统计窗口 (秒)
    _ECHO_GATE_RMS = 800          # 回声门控 RMS 阈值 (int16 量级)
    _ECHO_COOLDOWN_SEC = 0.6      # AI 停播后继续门控的冷却时间 (秒)

    def _ms_to_bytes(ms: float) -> int:
        return int(ms / 1000 * SAMPLE_RATE * 2)

    buf_ctl = {
        "prebuf_ms": _PREBUF_MS_DEFAULT,    # 当前预缓冲时长 (ms)
        "chunks_in": 0,                     # 当前响应已收到 chunk 数
        "delta_bytes_total": 0,              # 当前响应总字节数
        "underruns": 0,                      # 总 underrun 次数
        "underrun_ts": [],                   # underrun 时间戳
        "arrivals": [],                      # 包间到达时间差 (ms)
        "last_arrival_t": 0.0,
        "jitter_ms": 0.0,
        "last_adjust_t": 0.0,
    }
    echo_gate = {
        "cooldown_until": 0.0,               # 回声门控冷却截止时间
        "suppressed": 0,                     # 已抑制的帧数（调试用）
    }

    # ── 性能指标 ─────────────────────────────────────────────
    perf = {
        "response_created_t": 0,       # RESPONSE_CREATED 时间戳
        "first_audio_t": 0,            # 首个 RESPONSE_AUDIO_DELTA 时间戳
        "speech_stopped_t": 0,         # 用户停止说话时间戳
        "ttft_list": [],               # TTFT 历史记录 (ms)
        "e2e_list": [],                # 端到端延迟历史 (ms)
        "total_input_tokens": 0,
        "total_output_tokens": 0,
    }

    # UI 更新机制: 通过 page.run_task() 将更新调度到 Flet 事件循环
    _update_pending = [False]

    async def _async_update():
        """Flet 事件循环上执行的 UI 更新。"""
        _update_pending[0] = False
        try:
            page.update()
        except Exception:
            pass

    def _mark_dirty():
        """将 UI 更新调度到 Flet 事件循环 (线程安全)。"""
        if _update_pending[0]:
            return
        _update_pending[0] = True
        try:
            page.run_task(_async_update)
        except Exception:
            _update_pending[0] = False

    def _flush_ui():
        """强制立即刷新 (仅在 Flet 事件回调线程中使用)。"""
        try:
            page.update()
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════════
    # 顶部状态
    # ══════════════════════════════════════════════════════════════
    conn_icon = ft.Icon(ft.Icons.CIRCLE, color=ft.Colors.RED, size=12)
    conn_text = ft.Text("未连接", size=12)
    model_text = ft.Text("", size=12, opacity=0.6)

    ai_status_icon = ft.Icon(ft.Icons.HEARING, color=ft.Colors.GREY, size=16)
    ai_status_text = ft.Text("空闲", size=13, color=ft.Colors.GREY)
    ai_status_row = ft.Row(
        [ai_status_icon, ai_status_text], spacing=6,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    def _set_ai_status(status: str):
        if status == "listening":
            ai_status_icon.name = ft.Icons.HEARING
            ai_status_icon.color = "#00E676"
            ai_status_text.value = "正在收听"
            ai_status_text.color = "#00E676"
        elif status == "speaking":
            ai_status_icon.name = ft.Icons.RECORD_VOICE_OVER
            ai_status_icon.color = "#40C4FF"
            ai_status_text.value = "AI 说话中"
            ai_status_text.color = "#40C4FF"
        else:
            ai_status_icon.name = ft.Icons.HEARING
            ai_status_icon.color = ft.Colors.GREY
            ai_status_text.value = "空闲"
            ai_status_text.color = ft.Colors.GREY

    # ══════════════════════════════════════════════════════════════
    # 设置控件
    # ══════════════════════════════════════════════════════════════
    model_dropdown = ft.Dropdown(
        label="模型", value="gpt-realtime",
        options=[ft.dropdown.Option(k, v) for k, v in MODEL_OPTIONS], width=220,
        dense=True, text_size=13,
    )
    voice_dropdown = ft.Dropdown(
        label="语音", value="zh-CN-XiaoxiaoNeural",
        options=[ft.dropdown.Option(k, v) for k, v in VOICE_OPTIONS], width=240,
        dense=True, text_size=13,
    )
    role_dropdown = ft.Dropdown(
        label="AI 角色", value="玩具儿童助手",
        options=[ft.dropdown.Option(k, k) for k in ROLE_PRESETS], width=200,
        dense=True, text_size=13,
    )
    voice_temp_value_text = ft.Text("1.0", size=12, weight=ft.FontWeight.BOLD, width=30)
    voice_temp_slider = ft.Slider(
        min=0, max=1, value=1.0, divisions=10, label="{value}", width=140,
        on_change=lambda e: _on_temp_change(e),
    )
    voice_rate_dropdown = ft.Dropdown(
        label="速率", value="medium",
        options=[ft.dropdown.Option(k, v) for k, v in RATE_OPTIONS], width=100,
        dense=True, text_size=13,
    )
    noise_switch = ft.Switch(label="降噪", value=True, label_text_style=ft.TextStyle(size=12))
    echo_switch = ft.Switch(label="回声消除", value=True, label_text_style=ft.TextStyle(size=12))
    proactive_switch = ft.Switch(label="主动参与", value=False, label_text_style=ft.TextStyle(size=12))

    def _on_temp_change(e):
        val = round(voice_temp_slider.value, 1)
        voice_temp_value_text.value = f"{val:.1f}"
        _notify_setting_changed()
        _flush_ui()

    def _notify_setting_changed():
        """设置变更时通知用户生效时机。"""
        if is_active[0]:
            msg = "设置已更新，将在下次对话时生效"
        else:
            msg = "设置已更新，开始对话后生效"
        page.show_dialog(ft.SnackBar(content=ft.Text(msg), duration=2000))

    # 为各设置控件添加变更通知
    # Flet 0.82: Dropdown 事件是 on_select（不是 on_change）
    def _on_setting_dropdown_select(e):
        _notify_setting_changed()

    def _on_setting_switch_change(e):
        _notify_setting_changed()

    model_dropdown.on_select = _on_setting_dropdown_select
    voice_dropdown.on_select = _on_setting_dropdown_select
    role_dropdown.on_select = _on_setting_dropdown_select
    voice_rate_dropdown.on_select = _on_setting_dropdown_select

    noise_switch.on_change = _on_setting_switch_change
    echo_switch.on_change = _on_setting_switch_change
    proactive_switch.on_change = _on_setting_switch_change
    vad_dropdown = ft.Dropdown(
        label="VAD", value="azure_semantic_vad",
        options=[
            ft.dropdown.Option("azure_semantic_vad", "语义 VAD"),
            ft.dropdown.Option("server_vad", "标准 VAD"),
        ],
        width=130, dense=True, text_size=13,
    )
    vad_dropdown.on_select = _on_setting_dropdown_select

    # ══════════════════════════════════════════════════════════════
    # 对话区
    # ══════════════════════════════════════════════════════════════
    CONNECTING_TAG = "__connecting__"

    chat_list = ft.ListView(expand=True, spacing=8, auto_scroll=True)
    chat_list.controls.append(
        ft.Container(
            content=ft.Text("点击下方麦克风按钮开始对话", opacity=0.4, italic=True),
            alignment=ft.Alignment(0, 0), padding=40,
        )
    )

    def _show_connecting():
        chat_list.controls.append(ft.Container(
            content=ft.Row([
                ft.ProgressRing(width=18, height=18, stroke_width=2.5, color="#0078D4"),
                ft.Text("正在设置连接，请稍候...", size=14, color="#90CAF9"),
            ], spacing=10, alignment=ft.MainAxisAlignment.CENTER),
            alignment=ft.Alignment(0, 0), padding=16, data=CONNECTING_TAG,
        ))

    def _remove_connecting():
        chat_list.controls = [
            c for c in chat_list.controls if getattr(c, "data", None) != CONNECTING_TAG
        ]

    def _add_system_msg(text: str):
        chat_list.controls.append(ft.Container(
            content=ft.Text(text, size=13, color="#81C784", text_align=ft.TextAlign.CENTER),
            alignment=ft.Alignment(0, 0), padding=8,
        ))

    def _add_error_msg(text: str):
        chat_list.controls.append(ft.Container(
            content=ft.Text(text, size=13, color=ft.Colors.AMBER, text_align=ft.TextAlign.CENTER),
            alignment=ft.Alignment(0, 0), padding=8,
        ))

    # ── 用户气泡 (在 SPEECH_STOPPED 时占位, TRANSCRIPTION_COMPLETED 时填充) ─
    _pending_user = {"text_ctrl": None}

    def _create_pending_user_bubble():
        """用户停止说话后立即创建占位气泡 (显示 '...')。"""
        text_ctrl = ft.Text("...", size=14, italic=True, opacity=0.5, selectable=True)
        _pending_user["text_ctrl"] = text_ctrl
        bubble = ft.Container(
            content=ft.Column([
                ft.Row([ft.Container(
                    content=ft.Text("👤 我", size=11, weight=ft.FontWeight.BOLD, color=ft.Colors.ON_PRIMARY),
                    bgcolor=ft.Colors.PRIMARY, border_radius=4,
                    padding=ft.Padding.symmetric(horizontal=8, vertical=2),
                )], spacing=8),
                text_ctrl,
            ], spacing=4),
            bgcolor=ft.Colors.PRIMARY_CONTAINER, border_radius=12, padding=12, width=450,
        )
        chat_list.controls.append(
            ft.Row([bubble], alignment=ft.MainAxisAlignment.END)
        )

    def _fill_pending_user_bubble(transcript: str):
        """填充已占位的用户气泡文本。"""
        ctrl = _pending_user.get("text_ctrl")
        if ctrl is not None:
            ctrl.value = transcript
            ctrl.italic = False
            ctrl.opacity = 1.0
            _pending_user["text_ctrl"] = None
        else:
            _add_user_bubble(transcript)

    def _add_user_bubble(text: str):
        bubble = ft.Container(
            content=ft.Column([
                ft.Row([ft.Container(
                    content=ft.Text("👤 我", size=11, weight=ft.FontWeight.BOLD, color=ft.Colors.ON_PRIMARY),
                    bgcolor=ft.Colors.PRIMARY, border_radius=4,
                    padding=ft.Padding.symmetric(horizontal=8, vertical=2),
                )], spacing=8),
                ft.Text(text, size=14, selectable=True),
            ], spacing=4),
            bgcolor=ft.Colors.PRIMARY_CONTAINER, border_radius=12, padding=12, width=450,
        )
        chat_list.controls.append(
            ft.Row([bubble], alignment=ft.MainAxisAlignment.END)
        )

    # ── AI 气泡 (流式文本) ────────────────────────────────────────
    _ai_buf = {"text": "", "ctrl": None}

    def _start_ai_bubble():
        _ai_buf["text"] = ""
        text_ctrl = ft.Text("...", size=14, selectable=True, italic=True, opacity=0.5)
        _ai_buf["ctrl"] = text_ctrl
        bubble = ft.Container(
            content=ft.Column([
                ft.Row([ft.Container(
                    content=ft.Text("🤖 AI", size=11, weight=ft.FontWeight.BOLD, color=ft.Colors.ON_TERTIARY_CONTAINER),
                    bgcolor=ft.Colors.TERTIARY, border_radius=4,
                    padding=ft.Padding.symmetric(horizontal=8, vertical=2),
                )], spacing=8),
                text_ctrl,
            ], spacing=4),
            bgcolor=ft.Colors.TERTIARY_CONTAINER, border_radius=12, padding=12, width=450,
            border=ft.Border(left=ft.BorderSide(3, ft.Colors.TERTIARY)),
        )
        chat_list.controls.append(
            ft.Row([bubble], alignment=ft.MainAxisAlignment.START)
        )

    def _append_ai_text(delta: str):
        _ai_buf["text"] += delta
        ctrl = _ai_buf.get("ctrl")
        if ctrl:
            ctrl.value = _ai_buf["text"]
            ctrl.italic = False
            ctrl.opacity = 1.0

    # ══════════════════════════════════════════════════════════════
    # 音频播放 (连续字节缓冲 + 平滑淡出)
    # ══════════════════════════════════════════════════════════════
    def _write_audio(pcm_bytes: bytes):
        """Write PCM data into the audio buffer."""
        released = audio_buf.write(pcm_bytes)
        if released:
            buf_ms = audio_buf.buffered_ms + buf_ctl["prebuf_ms"]
            log.info("预缓冲完成: %d chunks / %d bytes / ≈%.0fms (阈值=%dms)",
                     buf_ctl["chunks_in"], buf_ctl["delta_bytes_total"],
                     buf_ms, buf_ctl["prebuf_ms"])

    def _skip_pending_audio():
        audio_buf.clear()
        audio_buf.release_prebuffer()

    def _playback_callback(outdata, frames, _time_info, _status):
        """sounddevice output callback — reads from _AudioBuffer."""
        samples = audio_buf.read(frames)
        outdata[:] = samples.reshape(-1, 1)

    def _start_audio_playback():
        if audio_state["stream_out"] is not None:
            return
        audio_state["stream_out"] = sd.OutputStream(
            samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="int16",
            callback=_playback_callback, blocksize=OUT_BLOCKSIZE,
        )
        audio_state["stream_out"].start()
        log.info("音频播放已启动 (blocksize=%d = %dms)", OUT_BLOCKSIZE,
                 int(OUT_BLOCKSIZE / SAMPLE_RATE * 1000))

    def _stop_audio_playback():
        s = audio_state["stream_out"]
        audio_state["stream_out"] = None
        if s:
            try:
                s.stop()
                s.close()
            except Exception:
                pass
        audio_buf.clear()
        log.info("音频播放已停止")

    # ══════════════════════════════════════════════════════════════
    # 麦克风采集
    # ══════════════════════════════════════════════════════════════
    def _start_mic_capture():
        if audio_state["capturing"]:
            return

        def _mic_cb(indata, _frames, _time_info, _status):
            conn = vl_state["connection"]
            loop = vl_state["loop"]
            if conn is None or loop is None or not audio_state["capturing"]:
                return

            # ── 客户端回声门控 ──
            # AI 音频播放期间 + 冷却期内，仅放行高能量信号（真正的用户说话）
            now_t = time.time()
            ai_playing = audio_buf.is_outputting
            if ai_playing:
                echo_gate["cooldown_until"] = now_t + _ECHO_COOLDOWN_SEC
            if ai_playing or now_t < echo_gate["cooldown_until"]:
                samples = np.frombuffer(indata, dtype=np.int16)
                rms = np.sqrt(np.mean(samples.astype(np.float32) ** 2))
                if rms < _ECHO_GATE_RMS:
                    echo_gate["suppressed"] += 1
                    return  # 抑制回声

            audio_b64 = base64.b64encode(indata.tobytes()).decode("ascii")
            asyncio.run_coroutine_threadsafe(
                conn.input_audio_buffer.append(audio=audio_b64), loop
            )

        audio_state["stream_in"] = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="int16",
            callback=_mic_cb, blocksize=CHUNK_SIZE,
        )
        audio_state["stream_in"].start()
        audio_state["capturing"] = True
        log.info("麦克风采集已启动 (回声门控 RMS阈值=%d, 冷却=%.1fs)",
                 _ECHO_GATE_RMS, _ECHO_COOLDOWN_SEC)

    def _stop_mic_capture():
        audio_state["capturing"] = False
        s = audio_state["stream_in"]
        audio_state["stream_in"] = None
        if s:
            try:
                s.stop()
                s.close()
            except Exception:
                pass
        log.info("麦克风采集已停止")

    # ── 自适应缓冲调整 ─────────────────────────────────────────
    def _adjust_prebuffer():
        """根据网络抖动和 underrun 频率自适应调整预缓冲时长。"""
        now = time.time()
        if now - buf_ctl["last_adjust_t"] < 3:
            return
        buf_ctl["last_adjust_t"] = now

        # 计算包间到达时间的标准差 (jitter)
        arrivals = buf_ctl["arrivals"]
        if len(arrivals) >= 5:
            mean_arr = sum(arrivals) / len(arrivals)
            variance = sum((a - mean_arr) ** 2 for a in arrivals) / len(arrivals)
            jitter = variance ** 0.5
            buf_ctl["jitter_ms"] = jitter
        else:
            jitter = buf_ctl["jitter_ms"]

        # 统计最近窗口内的 underrun 次数
        cutoff = now - _UNDERRUN_WINDOW_SEC
        buf_ctl["underrun_ts"] = [t for t in buf_ctl["underrun_ts"] if t > cutoff]
        recent_underruns = len(buf_ctl["underrun_ts"])

        old_ms = buf_ctl["prebuf_ms"]

        # 自适应策略: 基于 3×jitter + underrun 惩罚
        # 目标: prebuf_ms ≥ 3 × jitter (覆盖 ~99% 的延迟波动)
        target = max(_PREBUF_MS_MIN, jitter * 3.0)
        if recent_underruns > 3:
            target = max(target, old_ms + 300)  # 频繁 underrun → 大幅增加
        elif recent_underruns > 0:
            target = max(target, old_ms + 150)  # 偶尔 underrun → 中幅增加
        elif jitter < 30 and recent_underruns == 0:
            target = min(target, old_ms - 50)   # 网络良好 → 缓降

        new_ms = int(max(_PREBUF_MS_MIN, min(_PREBUF_MS_MAX, target)))
        buf_ctl["prebuf_ms"] = new_ms

        if new_ms != old_ms:
            log.info("自适应缓冲: %dms→%dms (jitter=%.1fms, underruns=%d)",
                     old_ms, new_ms, jitter, recent_underruns)
            _update_buffer_display()
            _mark_dirty()

    def _update_buffer_display():
        """更新缓冲健康指标 UI。"""
        prebuf_ms = buf_ctl["prebuf_ms"]
        jitter = buf_ctl["jitter_ms"]
        if jitter > 80:
            _perf_buf_value.value = f"{prebuf_ms}ms"
            _perf_buf_value.color = "#FF7043"  # 橙红 — 网络差
            _perf_buf_sub.value = f"jitter {jitter:.0f}ms"
        elif jitter > 30:
            _perf_buf_value.value = f"{prebuf_ms}ms"
            _perf_buf_value.color = "#FFB74D"  # 橙色 — 一般
            _perf_buf_sub.value = f"jitter {jitter:.0f}ms"
        else:
            _perf_buf_value.value = f"{prebuf_ms}ms"
            _perf_buf_value.color = "#00E676"  # 绿色 — 良好
            _perf_buf_sub.value = f"jitter {jitter:.0f}ms" if jitter > 0 else ""

    # ══════════════════════════════════════════════════════════════
    # Voice Live 事件处理
    # 关键: 绝不调用 page.update(), 只设 _mark_dirty()
    # ══════════════════════════════════════════════════════════════
    def _handle_event(event):
        from azure.ai.voicelive.models import ServerEventType
        etype = event.type

        if etype == ServerEventType.SESSION_UPDATED:
            _start_mic_capture()
            _remove_connecting()
            _add_system_msg("连接已建立，请开始说话")
            _set_ai_status("listening")
            _mark_dirty()

        elif etype == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STARTED:
            log.info("用户开始说话 → 打断 AI")
            _skip_pending_audio()
            _set_ai_status("listening")
            _mark_dirty()

        elif etype == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STOPPED:
            log.info("用户停止说话")
            perf["speech_stopped_t"] = time.time()
            _create_pending_user_bubble()
            _mark_dirty()

        elif etype == ServerEventType.RESPONSE_CREATED:
            log.info("AI 开始回复")
            perf["response_created_t"] = time.time()
            perf["first_audio_t"] = 0
            # 启动预缓冲: 积累足够音频数据后再开始播放
            prebuf_bytes = _ms_to_bytes(buf_ctl["prebuf_ms"])
            reprebuf_bytes = _ms_to_bytes(_REPREBUF_MS)
            audio_buf.start_response(prebuf_bytes, reprebuf_bytes)
            buf_ctl["chunks_in"] = 0
            buf_ctl["delta_bytes_total"] = 0
            buf_ctl["arrivals"] = []
            buf_ctl["last_arrival_t"] = 0.0
            _start_ai_bubble()
            _set_ai_status("speaking")
            _mark_dirty()

        elif etype == ServerEventType.RESPONSE_AUDIO_DELTA:
            if event.delta:
                now = time.time()
                delta_data = event.delta
                delta_len = len(delta_data) if isinstance(delta_data, (bytes, bytearray)) else 0
                # 追踪包间到达时间
                if buf_ctl["last_arrival_t"] > 0:
                    delta_ms = (now - buf_ctl["last_arrival_t"]) * 1000
                    buf_ctl["arrivals"].append(delta_ms)
                    if len(buf_ctl["arrivals"]) > _JITTER_WINDOW:
                        buf_ctl["arrivals"] = buf_ctl["arrivals"][-_JITTER_WINDOW:]
                buf_ctl["last_arrival_t"] = now
                buf_ctl["chunks_in"] += 1
                buf_ctl["delta_bytes_total"] += delta_len

                # 记录首个音频的时间戳（TTFT）
                if perf["first_audio_t"] == 0:
                    perf["first_audio_t"] = now
                    if perf["response_created_t"] > 0:
                        ttft_ms = (now - perf["response_created_t"]) * 1000
                        perf["ttft_list"].append(ttft_ms)
                        _update_perf_display(ttft_ms=ttft_ms)
                        log.info("首个音频包: %d bytes, TTFT=%.0fms", delta_len, ttft_ms)
                        _mark_dirty()

                _write_audio(delta_data)

        elif etype == ServerEventType.RESPONSE_AUDIO_TRANSCRIPT_DELTA:
            if event.delta:
                _append_ai_text(event.delta)
                _mark_dirty()

        elif etype == ServerEventType.RESPONSE_AUDIO_DONE:
            if audio_buf.is_prebuffering:
                audio_buf.release_prebuffer()
                log.info("短回复释放预缓冲: %d chunks / %d bytes (阈值=%dms)",
                         buf_ctl["chunks_in"], buf_ctl["delta_bytes_total"],
                         buf_ctl["prebuf_ms"])
            # 记录本轮 underrun 数据到 buf_ctl
            resp_underruns = audio_buf.underrun_count
            if resp_underruns > 0:
                buf_ctl["underruns"] += resp_underruns
                now = time.time()
                buf_ctl["underrun_ts"].extend([now] * resp_underruns)
            log.info("AI 音频播放完毕 (总计 %d chunks, %d bytes, underruns=%d, 回声抑制=%d帧)",
                     buf_ctl["chunks_in"], buf_ctl["delta_bytes_total"],
                     resp_underruns, echo_gate["suppressed"])
            echo_gate["suppressed"] = 0

        elif etype == ServerEventType.RESPONSE_DONE:
            log.info("AI 回复完成")
            # 计算端到端延迟
            if perf["speech_stopped_t"] > 0 and perf["first_audio_t"] > 0:
                e2e_ms = (perf["first_audio_t"] - perf["speech_stopped_t"]) * 1000
                if e2e_ms > 0:
                    perf["e2e_list"].append(e2e_ms)
                    _update_perf_display(e2e_ms=e2e_ms)
            # 提取 token 用量
            resp = getattr(event, "response", None)
            if resp:
                usage = getattr(resp, "usage", None)
                if usage:
                    inp = getattr(usage, "input_tokens", 0) or 0
                    out = getattr(usage, "output_tokens", 0) or 0
                    perf["total_input_tokens"] += inp
                    perf["total_output_tokens"] += out
                    _update_perf_display(input_tok=inp, output_tok=out)
            # 自适应调整预缓冲阈值
            _adjust_prebuffer()
            _update_buffer_display()
            _set_ai_status("listening")
            _mark_dirty()

        elif etype == ServerEventType.CONVERSATION_ITEM_INPUT_AUDIO_TRANSCRIPTION_COMPLETED:
            transcript = getattr(event, "transcript", "") or ""
            if transcript.strip():
                _fill_pending_user_bubble(transcript.strip())
                _mark_dirty()

        elif etype == ServerEventType.ERROR:
            err = getattr(event, "error", None)
            msg = getattr(err, "message", str(err)) if err else "未知错误"
            if "Cancellation failed" not in msg:
                log.error("Voice Live 错误: %s", msg)
                _add_error_msg(f"{msg}")
                # 出错时中断连接
                vl_state["stop"].set()
                _mark_dirty()

    # ══════════════════════════════════════════════════════════════
    # Voice Live 异步连接
    # ══════════════════════════════════════════════════════════════
    async def _async_connect(endpoint: str, api_key: str, model: str):
        from azure.core.credentials import AzureKeyCredential
        from azure.ai.voicelive.aio import connect
        from azure.ai.voicelive.models import (
            AudioEchoCancellation, AudioNoiseReduction, AzureStandardVoice,
            InputAudioFormat, Modality, OutputAudioFormat, RequestSession, ServerVad,
        )

        vl_state["loop"] = asyncio.get_event_loop()
        vl_state["stop"].clear()
        log.info("连接: endpoint=%s, model=%s", endpoint, model)

        try:
            async with connect(
                endpoint=endpoint,
                credential=AzureKeyCredential(api_key),
                model=model,
            ) as connection:
                vl_state["connection"] = connection
                conn_icon.color = ft.Colors.GREEN
                conn_text.value = "已连接"
                model_text.value = model
                _mark_dirty()

                voice_name = voice_dropdown.value or "zh-CN-XiaoxiaoNeural"
                voice_kwargs = {"name": voice_name}
                # 声音温度
                voice_temp = voice_temp_slider.value
                if voice_temp is not None:
                    voice_kwargs["temperature"] = float(voice_temp)
                # 说话速率
                voice_rate = voice_rate_dropdown.value
                if voice_rate and voice_rate != "medium":
                    voice_kwargs["rate"] = voice_rate
                voice_config = AzureStandardVoice(**voice_kwargs)

                role = role_dropdown.value or "玩具儿童助手"
                instructions = ROLE_PRESETS.get(role, "")

                vad_type = vad_dropdown.value or "azure_semantic_vad"
                turn_detection = ServerVad(
                    type=vad_type, threshold=0.5,
                    prefix_padding_ms=300, silence_duration_ms=500,
                )

                session_kwargs = dict(
                    modalities=[Modality.TEXT, Modality.AUDIO],
                    instructions=instructions,
                    voice=voice_config,
                    input_audio_format=InputAudioFormat.PCM16,
                    output_audio_format=OutputAudioFormat.PCM16,
                    turn_detection=turn_detection,
                    input_audio_transcription={"model": "whisper-1"},
                )
                if noise_switch.value:
                    session_kwargs["input_audio_noise_reduction"] = AudioNoiseReduction(
                        type="azure_deep_noise_suppression"
                    )
                if echo_switch.value:
                    session_kwargs["input_audio_echo_cancellation"] = AudioEchoCancellation(
                        type="server_echo_cancellation"
                    )

                await connection.session.update(session=RequestSession(**session_kwargs))

                _start_audio_playback()

                # 主动参与: 连接建立后让 AI 先开口打招呼
                if proactive_switch.value:
                    log.info("主动参与已启用，触发 AI 初始问候")
                    await connection.response.create(
                        additional_instructions="请主动向用户打招呼，简短友好地介绍你自己，并询问用户需要什么帮助。"
                    )

                async for event in connection:
                    if vl_state["stop"].is_set():
                        break
                    _handle_event(event)

        except Exception as ex:
            log.exception("Voice Live 连接异常")
            conn_icon.color = ft.Colors.RED
            conn_text.value = f"连接失败: {str(ex)[:80]}"
            _mark_dirty()
        finally:
            vl_state["connection"] = None
            vl_state["loop"] = None
            _stop_mic_capture()
            _stop_audio_playback()
            _remove_connecting()
            # 仅在非主动停止时更新状态（主动停止已在 _on_stop 中更新）
            if is_active[0]:
                if not conn_text.value.startswith("连接失败"):
                    conn_icon.color = ft.Colors.RED
                    conn_text.value = "已断开"
                is_active[0] = False
                mic_btn_text.value = "开始对话"
                mic_btn_icon.name = ft.Icons.MIC
                mic_btn_container.bgcolor = "#0078D4"
                _set_ai_status("idle")
            _mark_dirty()

    def _connect_thread(endpoint, api_key, model):
        asyncio.run(_async_connect(endpoint, api_key, model))

    # ══════════════════════════════════════════════════════════════
    # 麦克风启停按钮 (Container + Text 确保文本可更新)
    # ══════════════════════════════════════════════════════════════
    is_active = [False]

    mic_btn_text = ft.Text(
        "开始对话", size=15, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE,
    )
    mic_btn_icon = ft.Icon(ft.Icons.MIC, size=20, color=ft.Colors.WHITE)
    mic_btn_container = ft.Container(
        content=ft.Row([mic_btn_icon, mic_btn_text], spacing=6),
        bgcolor="#0078D4",
        border_radius=25,
        padding=ft.Padding.symmetric(horizontal=32, vertical=12),
        on_click=lambda e: _on_mic_toggle(),
        ink=True,
    )

    def _on_mic_toggle():
        if is_active[0]:
            _on_stop()
        else:
            _on_start()

    def _on_start():
        cfg = load_config()
        endpoint_raw = cfg.get("voicelive_endpoint", "").strip()
        api_key = cfg.get("voicelive_api_key", "").strip()
        model = model_dropdown.value or "gpt-realtime"

        if not endpoint_raw or not api_key:
            conn_icon.color = ft.Colors.RED
            conn_text.value = "未配置 Voice Live"
            _flush_ui()
            return

        endpoint = _normalize_endpoint(endpoint_raw)
        log.info("启动: endpoint=%s, model=%s", endpoint, model)

        is_active[0] = True
        mic_btn_text.value = "停止"
        mic_btn_icon.name = ft.Icons.STOP
        mic_btn_container.bgcolor = "#D32F2F"
        conn_icon.color = ft.Colors.YELLOW
        conn_text.value = "连接中..."
        _show_connecting()
        _flush_ui()

        t = threading.Thread(
            target=_connect_thread, args=(endpoint, api_key, model), daemon=True,
        )
        vl_state["thread"] = t
        t.start()

    def _on_stop():
        vl_state["stop"].set()
        _stop_mic_capture()
        _stop_audio_playback()
        # 立即更新连接状态
        conn_icon.color = ft.Colors.RED
        conn_text.value = "已断开"
        _remove_connecting()
        is_active[0] = False
        mic_btn_text.value = "开始对话"
        mic_btn_icon.name = ft.Icons.MIC
        mic_btn_container.bgcolor = "#0078D4"
        _set_ai_status("idle")
        # 尝试关闭 WebSocket 连接
        conn = vl_state.get("connection")
        loop = vl_state.get("loop")
        if conn and loop:
            try:
                asyncio.run_coroutine_threadsafe(conn.close(), loop)
            except Exception:
                pass
        _flush_ui()

    # ══════════════════════════════════════════════════════════════
    # 配置 Banner
    # ══════════════════════════════════════════════════════════════
    config_banner_icon = ft.Icon(ft.Icons.WARNING_ROUNDED, color=ft.Colors.AMBER, size=18)
    config_banner_text = ft.Text("", size=13)
    config_banner_btn = ft.TextButton(
        "前往设置",
        on_click=lambda e: page.pubsub.send_all("open_settings"),
        style=ft.ButtonStyle(color=ft.Colors.AMBER),
    )
    config_banner_row = ft.Row(
        [config_banner_icon, config_banner_text, config_banner_btn],
        spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
    config_banner = ft.Container(
        content=config_banner_row, border_radius=8,
        padding=ft.Padding.symmetric(horizontal=14, vertical=8), bgcolor=ft.Colors.SECONDARY_CONTAINER,
    )

    def _refresh_config_banner():
        cfg = load_config()
        has_vl = bool(cfg.get("voicelive_endpoint", "").strip()) and bool(cfg.get("voicelive_api_key", "").strip())
        if has_vl:
            config_banner.visible = False
        else:
            config_banner.visible = True
            config_banner_row.controls[0] = ft.Icon(ft.Icons.ERROR_OUTLINE, color=ft.Colors.RED_400, size=18)
            config_banner_text.value = "请先在设置中配置 Voice Live Endpoint 和 API Key"
            config_banner_btn.visible = True
            config_banner.bgcolor = ft.Colors.ERROR_CONTAINER
        _flush_ui()

    _refresh_config_banner()

    # ══════════════════════════════════════════════════════════════
    # 清除对话
    # ══════════════════════════════════════════════════════════════
    def _clear_chat(e):
        chat_list.controls.clear()
        chat_list.controls.append(ft.Container(
            content=ft.Text("点击下方麦克风按钮开始对话", opacity=0.4, italic=True),
            alignment=ft.Alignment(0, 0), padding=40,
        ))
        # 重置性能指标
        perf["ttft_list"].clear()
        perf["e2e_list"].clear()
        perf["total_input_tokens"] = 0
        perf["total_output_tokens"] = 0
        _perf_ttft_value.value = "--"
        _perf_ttft_avg.value = ""
        _perf_e2e_value.value = "--"
        _perf_e2e_avg.value = ""
        _perf_token_value.value = "0"
        # 重置缓冲指标 (保留自适应阈值)
        buf_ctl["underruns"] = 0
        buf_ctl["underrun_ts"].clear()
        buf_ctl["arrivals"].clear()
        buf_ctl["jitter_ms"] = 0.0
        _perf_buf_value.value = f"{buf_ctl['prebuf_ms']}ms"
        _perf_buf_value.color = "#00E676"
        _perf_buf_sub.value = ""
        _flush_ui()

    # ══════════════════════════════════════════════════════════════
    # 布局: 对话区为主体, 设置可折叠
    # ══════════════════════════════════════════════════════════════

    # ── 顶部 hero 栏（按钮 + 状态，无标题）──
    hero_bar = ft.Container(
        content=ft.Row(
            [
                mic_btn_container,
                ft.Container(width=12),
                ai_status_row,
                ft.Container(expand=True),
                ft.Container(
                    content=ft.Row([conn_icon, conn_text, model_text], spacing=4),
                    border_radius=12,
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
                    padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                ),
            ],
            spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding.symmetric(horizontal=4, vertical=0),
    )

    # ── 可折叠设置面板 ──
    _settings_visible = [True]
    _settings_toggle_icon = ft.Icon(ft.Icons.EXPAND_LESS, size=18)
    _settings_toggle_text = ft.Text("收起设置", size=11, opacity=0.6)

    settings_content = ft.Column([
        # 第一行: 模型 + 语音 + 角色
        ft.Row([model_dropdown, voice_dropdown, role_dropdown], spacing=8, wrap=True),
        # 第二行: 温度 + 速率 + 开关组
        ft.Row([
            ft.Row([
                ft.Text("温度", size=11, opacity=0.5),
                voice_temp_slider,
                voice_temp_value_text,
            ], spacing=2, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            voice_rate_dropdown,
            ft.Container(width=8),
            noise_switch, echo_switch, proactive_switch,
            ft.Container(width=4),
            vad_dropdown,
        ], spacing=6, wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER),
    ], spacing=8, visible=True)

    def _toggle_settings(e):
        _settings_visible[0] = not _settings_visible[0]
        settings_content.visible = _settings_visible[0]
        _settings_toggle_icon.name = ft.Icons.EXPAND_LESS if _settings_visible[0] else ft.Icons.EXPAND_MORE
        _settings_toggle_text.value = "收起设置" if _settings_visible[0] else "展开设置"
        _flush_ui()

    settings_panel = ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Text("对话设置", size=12, weight=ft.FontWeight.BOLD, opacity=0.7),
                ft.Container(expand=True),
                ft.Container(
                    content=ft.Row([_settings_toggle_icon, _settings_toggle_text], spacing=2),
                    on_click=_toggle_settings, ink=True,
                    border_radius=12, padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                ),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            settings_content,
        ], spacing=6),
        bgcolor=ft.Colors.SURFACE_CONTAINER, border_radius=10,
        padding=ft.Padding.symmetric(horizontal=14, vertical=10),
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
    )

    # ── 性能指标（紧凑 pill 标签式，对齐 Phase 3 设计） ────────
    _perf_ttft_value = ft.Text("--", size=13, weight=ft.FontWeight.BOLD, color="#00E676")
    _perf_ttft_avg = ft.Text("", size=11, opacity=0.5)
    _perf_e2e_value = ft.Text("--", size=13, color="#90CAF9")
    _perf_e2e_avg = ft.Text("", size=11, opacity=0.5)
    _perf_token_value = ft.Text("0", size=13, weight=ft.FontWeight.BOLD, color="#FFB74D")

    def _fmt_ms(ms: float) -> str:
        if ms < 1000:
            return f"{int(ms)}ms"
        return f"{ms / 1000:.1f}s"

    def _update_perf_display(ttft_ms: float = 0, e2e_ms: float = 0,
                             input_tok: int = 0, output_tok: int = 0):
        if ttft_ms > 0:
            _perf_ttft_value.value = _fmt_ms(ttft_ms)
            if perf["ttft_list"]:
                avg = sum(perf["ttft_list"]) / len(perf["ttft_list"])
                _perf_ttft_avg.value = f"avg {_fmt_ms(avg)}"
        if e2e_ms > 0:
            _perf_e2e_value.value = _fmt_ms(e2e_ms)
            if perf["e2e_list"]:
                avg = sum(perf["e2e_list"]) / len(perf["e2e_list"])
                _perf_e2e_avg.value = f"avg {_fmt_ms(avg)}"
        total = perf["total_input_tokens"] + perf["total_output_tokens"]
        _perf_token_value.value = f"{total:,}"

    def _build_perf_pill(icon_text: str, value_ctrl, sub_ctrl=None):
        children = [ft.Text(icon_text, size=12, opacity=0.7), value_ctrl]
        if sub_ctrl:
            children.append(sub_ctrl)
        return ft.Container(
            content=ft.Row(children, spacing=4,
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
            border_radius=14,
            padding=ft.Padding.symmetric(horizontal=10, vertical=5),
        )

    perf_ttft_pill = _build_perf_pill("TTFT", _perf_ttft_value, _perf_ttft_avg)
    perf_e2e_pill = _build_perf_pill("E2E", _perf_e2e_value, _perf_e2e_avg)
    perf_token_pill = _build_perf_pill("Token", _perf_token_value)

    # ── 缓冲健康指标 pill ──
    _perf_buf_value = ft.Text("--", size=13, weight=ft.FontWeight.BOLD, color="#00E676")
    _perf_buf_sub = ft.Text("", size=11, opacity=0.5)
    perf_buf_pill = _build_perf_pill("Buf", _perf_buf_value, _perf_buf_sub)

    # ── 底部信息条：性能指标 pill + 清除按钮（对齐 Phase 3 布局）──
    bottom_bar = ft.Container(
        content=ft.Row(
            [
                perf_ttft_pill,
                perf_e2e_pill,
                perf_token_pill,
                perf_buf_pill,
                ft.Container(expand=True),
                ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, tooltip="清除对话",
                              on_click=_clear_chat, icon_size=18,
                              icon_color=ft.Colors.ON_SURFACE_VARIANT),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding.symmetric(horizontal=4, vertical=4),
    )

    # ── 对话主体区域 (占据大部分空间) ──
    chat_panel = ft.Container(
        content=chat_list,
        expand=True,
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        border_radius=12, padding=10,
        bgcolor=ft.Colors.SURFACE_CONTAINER_LOWEST,
    )

    tab_content = ft.Container(
        content=ft.Column([
            config_banner,
            hero_bar,
            settings_panel,
            chat_panel,
            bottom_bar,
        ], spacing=6, expand=True),
        padding=ft.Padding(left=16, right=16, top=10, bottom=6), expand=True,
    )

    return tab_content, _refresh_config_banner
