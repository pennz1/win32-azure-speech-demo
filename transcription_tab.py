"""
会议转写 & AI 纪要生成 Tab
功能：实时麦克风流式转写(Diarization) + 音频文件转写 → GPT-4o 流式生成纪要
UI 更新：page.run_task() 调度到 Flet 事件循环（线程安全）
"""

import datetime
import os
import threading
import time

import flet as ft
from openai import AzureOpenAI

from config_manager import load_config

# Speaker 颜色映射（最多 10 个说话人）
SPEAKER_COLORS = [
    "#1565C0",  # Blue
    "#2E7D32",  # Green
    "#C62828",  # Red
    "#6A1B9A",  # Purple
    "#E65100",  # Orange
    "#00838F",  # Teal
    "#AD1457",  # Pink
    "#4E342E",  # Brown
    "#283593",  # Indigo
    "#558B2F",  # Light Green
]

# 纪要结构 Prompt (F1-08)
SUMMARY_SYSTEM_PROMPT = """你是专业的会议纪要助手。请根据以下转写文本，生成结构化的会议纪要。

要求格式如下（使用 Markdown）：

## 会议主题
（一句话概括会议主题）

## 参与人
（列出所有识别到的说话人）

## 核心议题
1. （议题 1 及要点）
2. （议题 2 及要点）

## 决策事项
- （决策 1）
- （决策 2）

## 待办事项
- ☐ （待办 1，标注负责人如有）
- ☐ （待办 2）

请用中文输出。如果内容是英文对话，也用中文总结。"""


def _format_time(seconds: float) -> str:
    """将秒数格式化为 mm:ss。"""
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def build_transcription_tab(page: ft.Page) -> ft.Control:
    """构建「会议转写 & AI 纪要」Tab 的全部 UI 和逻辑。"""

    config = load_config()

    # ── 状态变量 ─────────────────────────────────────────────────
    selected_file = {"path": None, "source": None}
    transcription_results = {"segments": [], "full_text": ""}
    summary_text = {"value": ""}
    live_state = {
        "transcriber": None,
        "running": False,
    }

    # ── 性能指标 ──────────────────────────────────────
    perf = {
        "last_recognizing_t": 0,      # 最后一次 recognizing 事件时间戳
        "latency_list": [],           # 识别延迟历史 (ms)
        "speakers": set(),            # 唯一说话人集合
        "word_count": 0,              # 总词数
        "audio_duration_s": 0,        # 音频总时长 (s)
        "start_time": 0,              # 转录开始时间
    }

    # ── UI 更新机制 (同 Phase 2/3): page.run_task() 调度到 Flet 事件循环 ──
    _update_pending = [False]

    async def _async_update():
        _update_pending[0] = False
        try:
            page.update()
        except Exception:
            pass

    def _mark_dirty():
        if _update_pending[0]:
            return
        _update_pending[0] = True
        try:
            page.run_task(_async_update)
        except Exception:
            _update_pending[0] = False

    def _flush_ui():
        try:
            page.update()
        except Exception:
            pass

    # ── F1-11 配置状态 Banner ────────────────────────────────────
    config_banner_icon = ft.Icon(ft.Icons.WARNING_ROUNDED, color=ft.Colors.AMBER, size=18)
    config_banner_text = ft.Text("", size=13)
    config_banner_btn = ft.TextButton(
        "前往设置",
        on_click=lambda e: page.pubsub.send_all("open_settings"),
        style=ft.ButtonStyle(color=ft.Colors.AMBER),
    )
    config_banner_row = ft.Row(
        [config_banner_icon, config_banner_text, config_banner_btn],
        spacing=10,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
    config_banner = ft.Container(
        content=config_banner_row,
        border_radius=8,
        padding=ft.Padding.symmetric(horizontal=14, vertical=8),
        bgcolor=ft.Colors.SECONDARY_CONTAINER,
    )

    def _set_banner_icon(icon_name: str, color: str):
        config_banner_row.controls[0] = ft.Icon(icon_name, color=color, size=18)

    def _refresh_config_banner():
        cfg = load_config()
        has_speech = bool(cfg.get("speech_api_key", "").strip())
        has_openai = bool(cfg.get("openai_api_key", "").strip()) and bool(cfg.get("openai_endpoint", "").strip())

        if has_speech and has_openai:
            config_banner.visible = False
        elif has_speech and not has_openai:
            config_banner.visible = True
            _set_banner_icon(ft.Icons.WARNING_AMBER_ROUNDED, ft.Colors.AMBER)
            config_banner_text.value = "Azure Speech 已配置，OpenAI 未配置（AI 纪要不可用）"
            config_banner_btn.visible = True
            config_banner.bgcolor = ft.Colors.SECONDARY_CONTAINER
        elif not has_speech and has_openai:
            config_banner.visible = True
            _set_banner_icon(ft.Icons.WARNING_AMBER_ROUNDED, ft.Colors.AMBER)
            config_banner_text.value = "Azure OpenAI 已配置，Speech 未配置（转写不可用）"
            config_banner_btn.visible = True
            config_banner.bgcolor = ft.Colors.SECONDARY_CONTAINER
        else:
            config_banner.visible = True
            _set_banner_icon(ft.Icons.ERROR_OUTLINE, ft.Colors.RED_400)
            config_banner_text.value = "尚未配置 Azure API Key，请先在设置中填写配置"
            config_banner_btn.visible = True
            config_banner.bgcolor = ft.Colors.ERROR_CONTAINER
        _flush_ui()

    _refresh_config_banner()

    # ── 文件选择 (F1-01) ─────────────────────────────────────────
    file_info_text = ft.Text("未选择文件", size=13, italic=True, opacity=0.35)

    file_picker = ft.FilePicker()
    page.services.append(file_picker)

    async def pick_file(e):
        if live_state["running"]:
            _show_snackbar("请先停止实时转录")
            return
        result = await file_picker.pick_files(
            dialog_title="选择音频文件",
            allowed_extensions=["wav", "mp3", "m4a"],
            allow_multiple=False,
        )
        if result:
            selected_file["path"] = result[0].path
            selected_file["source"] = "uploaded"
            file_info_text.value = f"已选：{result[0].name}"
            file_info_text.opacity = 1.0
            file_info_text.visible = True
            file_transcribe_btn.disabled = False
            clear_file_btn.visible = True
            # 选择文件后禁用实时转录
            live_btn.disabled = True
            live_btn.bgcolor = ft.Colors.OUTLINE
            live_btn.opacity = 0.5
            _flush_ui()

    def _clear_selected_file(e):
        """清除已选择的音频文件，恢复实时转录可用。若已有转写结果则一并清除。"""
        selected_file["path"] = None
        selected_file["source"] = None
        file_info_text.value = "未选择文件"
        file_info_text.opacity = 0.35
        file_transcribe_btn.disabled = True
        clear_file_btn.visible = False
        # 恢复实时转录按钮
        live_btn.disabled = False
        live_btn.bgcolor = "#0078D4"
        live_btn.opacity = 1.0
        # 清除已有转写/纪要结果和按钮状态
        transcription_results["segments"] = []
        transcription_results["full_text"] = ""
        summary_text["value"] = ""
        transcript_list.controls.clear()
        transcript_list.controls.append(_transcript_placeholder)
        summary_list_view.controls.clear()
        summary_list_view.controls.append(summary_placeholder)
        summary_markdown.value = ""
        _set_summary_enabled(False)
        copy_btn.disabled = True
        copy_summary_btn.disabled = True
        export_btn.disabled = True
        clear_results_btn.visible = False
        progress_bar.visible = False
        progress_text.visible = False
        # 重置性能指标
        perf["latency_list"].clear()
        perf["speakers"].clear()
        perf["word_count"] = 0
        perf["audio_duration_s"] = 0
        _perf_latency_value.value = "--"
        _perf_latency_avg.value = ""
        _perf_speaker_value.value = "0"
        _perf_word_value.value = "0"
        _perf_duration_value.value = "00:00"
        _flush_ui()

    # ── 转写结果列表 ─────────────────────────────────────────────
    transcript_list = ft.ListView(expand=True, spacing=6, auto_scroll=True)
    # 中间结果（实时转录 recognizing 事件）
    _interim_text = ft.Text("", size=15, italic=True, opacity=0.45)
    _interim_container = ft.Container(
        content=_interim_text,
        visible=False,
        padding=ft.Padding.symmetric(horizontal=10, vertical=4),
    )

    # 默认占位
    _transcript_placeholder = ft.Container(
        content=ft.Column([
            ft.Icon(ft.Icons.SUBTITLES_OFF, size=32, opacity=0.12),
            ft.Text("转写结果将显示在此处", opacity=0.25, italic=True, size=12),
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
        alignment=ft.Alignment(0, 0),
        padding=40,
    )
    transcript_list.controls.append(_transcript_placeholder)

    # ── 进度指示 ─────────────────────────────────────────────────
    progress_bar = ft.ProgressBar(visible=False)
    progress_text = ft.Text("", size=12, visible=False, opacity=0.7)

    # ── 录制状态指示（红点，无 LIVE 文本）─────────────────
    live_indicator = ft.Container(
        content=ft.Icon(ft.Icons.FIBER_MANUAL_RECORD, color=ft.Colors.RED, size=12),
        visible=False,
    )
    segment_count_text = ft.Text("", size=12, opacity=0.5)

    def _add_transcript_bubble(seg: dict):
        """向转写列表添加一条 Speaker 气泡卡片。"""
        # 移除占位
        if _transcript_placeholder in transcript_list.controls:
            transcript_list.controls.remove(_transcript_placeholder)

        speaker = seg["speaker"]
        try:
            speaker_idx = int(speaker.replace("Guest-", "").replace("Speaker-", "").replace("Unknown", "0")) % len(SPEAKER_COLORS)
        except (ValueError, AttributeError):
            speaker_idx = hash(speaker) % len(SPEAKER_COLORS)
        color = SPEAKER_COLORS[speaker_idx]

        bubble = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Container(
                                content=ft.Text(
                                    speaker, size=10, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE
                                ),
                                bgcolor=color,
                                border_radius=4,
                                padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                            ),
                            ft.Text(
                                _format_time(seg["offset"]),
                                size=10,
                                opacity=0.4,
                            ),
                        ],
                        spacing=6,
                    ),
                    ft.Text(seg["text"], size=13, selectable=True, opacity=0.9),
                ],
                spacing=3,
            ),
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            border_radius=8,
            padding=10,
        )
        transcript_list.controls.append(bubble)

    # ══════════════════════════════════════════════════════════════
    # 实时麦克风转录（ConversationTranscriber + Diarization）
    # ══════════════════════════════════════════════════════════════

    def _start_live_transcription(e):
        """启动实时麦克风转录。"""
        if live_state["running"]:
            return

        cfg = load_config()
        speech_key = cfg.get("speech_api_key", "")
        region = cfg.get("region", "eastasia")

        if not speech_key:
            _show_snackbar("请先在设置中配置 Azure Speech API Key")
            return

        live_state["running"] = True
        # 清空旧结果
        transcript_list.controls.clear()
        transcript_list.controls.append(_transcript_placeholder)
        transcription_results["segments"] = []
        transcription_results["full_text"] = ""
        _set_summary_enabled(False)
        copy_btn.disabled = True
        copy_summary_btn.disabled = True
        export_btn.disabled = True
        clear_results_btn.visible = False
        # 重置性能指标
        perf["last_recognizing_t"] = 0
        perf["latency_list"].clear()
        perf["speakers"].clear()
        perf["word_count"] = 0
        perf["audio_duration_s"] = 0
        perf["start_time"] = time.time()
        _perf_latency_value.value = "--"
        _perf_latency_avg.value = ""
        _perf_speaker_value.value = "0"
        _perf_word_value.value = "0"
        _perf_duration_value.value = "00:00"

        # UI 切换
        live_btn.visible = False
        stop_live_btn.visible = True
        live_indicator.visible = True
        segment_count_text.value = "0 段"
        file_transcribe_btn.disabled = True
        _flush_ui()

        threading.Thread(target=_live_transcription_worker, args=(speech_key, region), daemon=True).start()

    def _live_transcription_worker(speech_key: str, region: str):
        """后台线程运行实时转录。"""
        try:
            import azure.cognitiveservices.speech as speechsdk

            speech_config = speechsdk.SpeechConfig(
                subscription=speech_key, region=region
            )
            speech_config.speech_recognition_language = "zh-CN"
            speech_config.set_property(
                speechsdk.PropertyId.SpeechServiceResponse_DiarizeIntermediateResults,
                "true",
            )
            # 启用词级时间戳（用于精确延迟计算）
            speech_config.request_word_level_timestamps()
            # 语义分段策略（更智能的断句，减少过度分段）
            speech_config.set_property(
                speechsdk.PropertyId.Speech_SegmentationStrategy, "Semantic"
            )
            auto_detect_config = speechsdk.languageconfig.AutoDetectSourceLanguageConfig(
                languages=["zh-CN", "en-US"]
            )

            # 使用默认麦克风
            audio_config = speechsdk.audio.AudioConfig(use_default_microphone=True)
            transcriber = speechsdk.transcription.ConversationTranscriber(
                speech_config=speech_config,
                audio_config=audio_config,
                auto_detect_source_language_config=auto_detect_config,
            )
            live_state["transcriber"] = transcriber

            segments = transcription_results["segments"]

            def on_transcribing(evt):
                """中间结果 — 流式显示正在说的话。"""
                if evt.result.text:
                    perf["last_recognizing_t"] = time.time()
                    speaker_id = getattr(evt.result, "speaker_id", "")
                    prefix = f"[{speaker_id}] " if speaker_id else ""
                    _interim_text.value = f"{prefix}{evt.result.text}"
                    _interim_container.visible = True
                    _mark_dirty()

            def on_transcribed(evt):
                """最终结果 — 固化为气泡。"""
                if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech and evt.result.text:
                    # 计算识别延迟（最后 recognizing → recognized）
                    if perf["last_recognizing_t"] > 0:
                        latency_ms = (time.time() - perf["last_recognizing_t"]) * 1000
                        perf["latency_list"].append(latency_ms)
                        _update_perf_latency(latency_ms)
                    perf["last_recognizing_t"] = 0

                    speaker_id = getattr(evt.result, "speaker_id", "Unknown") or "Unknown"
                    offset_ticks = getattr(evt.result, "offset", 0)
                    duration_ticks = getattr(evt.result, "duration", 0)
                    offset_sec = offset_ticks / 10_000_000

                    # 更新性能指标
                    perf["speakers"].add(speaker_id)
                    words = len(evt.result.text.split())
                    perf["word_count"] += words
                    end_sec = (offset_ticks + duration_ticks) / 10_000_000
                    if end_sec > perf["audio_duration_s"]:
                        perf["audio_duration_s"] = end_sec
                    _update_perf_counters()

                    seg = {
                        "speaker": speaker_id,
                        "text": evt.result.text,
                        "offset": offset_sec,
                    }
                    segments.append(seg)
                    _add_transcript_bubble(seg)
                    _interim_container.visible = False
                    segment_count_text.value = f"{len(segments)} 段"
                    _mark_dirty()

            def on_canceled(evt):
                details = evt.cancellation_details
                if details.reason == speechsdk.CancellationReason.Error:
                    _show_snackbar(f"转写错误: {details.error_details[:80]}")
                _stop_live_transcription(None)

            def on_session_stopped(evt):
                pass

            transcriber.transcribing.connect(on_transcribing)
            transcriber.transcribed.connect(on_transcribed)
            transcriber.canceled.connect(on_canceled)
            transcriber.session_stopped.connect(on_session_stopped)

            transcriber.start_transcribing_async().get()

        except ImportError:
            _show_snackbar("错误: 未安装 azure-cognitiveservices-speech")
            _stop_live_transcription(None)
        except Exception as ex:
            _show_snackbar(f"实时转录启动失败: {str(ex)[:100]}")
            _stop_live_transcription(None)

    def _stop_live_transcription(e):
        """停止实时麦克风转录。"""
        if not live_state["running"] and live_state["transcriber"] is None:
            return

        live_state["running"] = False
        transcriber = live_state["transcriber"]
        live_state["transcriber"] = None

        if transcriber:
            try:
                transcriber.stop_transcribing_async().get()
            except Exception:
                pass

        # 汇总结果
        segments = transcription_results["segments"]
        if segments:
            full = "\n".join(
                f"[{s['speaker']}] ({_format_time(s['offset'])}) {s['text']}"
                for s in segments
            )
            transcription_results["full_text"] = full
            _set_summary_enabled(True)
            copy_btn.disabled = False
            copy_summary_btn.disabled = False
            export_btn.disabled = False
            clear_results_btn.visible = True

        # UI 复原
        live_btn.visible = True
        stop_live_btn.visible = False
        live_indicator.visible = False
        _interim_container.visible = False
        # 如果有已选文件，保持实时转录按钮禁用
        if selected_file["path"]:
            live_btn.disabled = True
            live_btn.bgcolor = ft.Colors.OUTLINE
            live_btn.opacity = 0.5
            file_transcribe_btn.disabled = False
        else:
            file_transcribe_btn.disabled = False
        _mark_dirty()

    # ── 实时转录按钮 ─────────────────────────────────────────────
    live_btn = ft.Container(
        content=ft.Row([
            ft.Icon(ft.Icons.MIC, size=20, color=ft.Colors.WHITE),
            ft.Text("实时转录", size=15, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
        ], spacing=6),
        bgcolor="#0078D4", border_radius=25,
        padding=ft.Padding.symmetric(horizontal=32, vertical=12),
        on_click=_start_live_transcription, ink=True,
    )
    stop_live_btn = ft.Container(
        content=ft.Row([
            ft.Icon(ft.Icons.STOP, size=20, color=ft.Colors.WHITE),
            ft.Text("停止转录", size=15, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
        ], spacing=6),
        bgcolor="#D32F2F", border_radius=25,
        padding=ft.Padding.symmetric(horizontal=32, vertical=12),
        on_click=_stop_live_transcription, ink=True, visible=False,
    )

    # ══════════════════════════════════════════════════════════════
    # 文件转写（上传音频文件 → Azure Speech 转写 + Diarization）
    # ══════════════════════════════════════════════════════════════

    def _do_file_transcription():
        """后台线程执行文件转写。"""
        filepath = selected_file["path"]
        if not filepath:
            return

        cfg = load_config()
        speech_key = cfg.get("speech_api_key", "")
        region = cfg.get("region", "eastasia")

        if not speech_key:
            _show_snackbar("请先在设置中配置 Azure Speech API Key")
            return

        # UI
        progress_bar.visible = True
        progress_bar.value = None
        progress_text.visible = True
        progress_text.value = "正在初始化 Azure Speech 服务..."
        file_transcribe_btn.disabled = True
        live_btn.disabled = True
        transcript_list.controls.clear()
        # 重置性能指标
        perf["last_recognizing_t"] = 0
        perf["latency_list"].clear()
        perf["speakers"].clear()
        perf["word_count"] = 0
        perf["audio_duration_s"] = 0
        perf["start_time"] = time.time()
        _perf_latency_value.value = "--"
        _perf_latency_avg.value = ""
        _perf_speaker_value.value = "0"
        _perf_word_value.value = "0"
        _perf_duration_value.value = "00:00"
        _flush_ui()

        try:
            import azure.cognitiveservices.speech as speechsdk

            speech_config = speechsdk.SpeechConfig(
                subscription=speech_key, region=region
            )
            speech_config.speech_recognition_language = "zh-CN"
            speech_config.set_property(
                speechsdk.PropertyId.SpeechServiceResponse_DiarizeIntermediateResults,
                "true",
            )
            speech_config.request_word_level_timestamps()
            speech_config.set_property(
                speechsdk.PropertyId.Speech_SegmentationStrategy, "Semantic"
            )
            auto_detect_config = speechsdk.languageconfig.AutoDetectSourceLanguageConfig(
                languages=["zh-CN", "en-US"]
            )
            audio_config = speechsdk.audio.AudioConfig(filename=filepath)
            transcriber = speechsdk.transcription.ConversationTranscriber(
                speech_config=speech_config,
                audio_config=audio_config,
                auto_detect_source_language_config=auto_detect_config,
            )

            segments = []
            done_event = threading.Event()

            def handle_transcribed(evt):
                if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech and evt.result.text:
                    speaker_id = getattr(evt.result, "speaker_id", "Unknown") or "Unknown"
                    offset_ticks = getattr(evt.result, "offset", 0)
                    duration_ticks = getattr(evt.result, "duration", 0)
                    offset_sec = offset_ticks / 10_000_000

                    # 性能指标
                    perf["speakers"].add(speaker_id)
                    perf["word_count"] += len(evt.result.text.split())
                    end_sec = (offset_ticks + duration_ticks) / 10_000_000
                    if end_sec > perf["audio_duration_s"]:
                        perf["audio_duration_s"] = end_sec
                    _update_perf_counters()

                    seg = {
                        "speaker": speaker_id,
                        "text": evt.result.text,
                        "offset": offset_sec,
                    }
                    segments.append(seg)
                    _add_transcript_bubble(seg)
                    progress_text.value = f"已识别 {len(segments)} 段..."
                    _mark_dirty()

            def handle_canceled(evt):
                if evt.cancellation_details.reason == speechsdk.CancellationReason.Error:
                    progress_text.value = f"转写错误: {evt.cancellation_details.error_details}"
                    _mark_dirty()
                done_event.set()

            def handle_stopped(evt):
                done_event.set()

            transcriber.transcribed.connect(handle_transcribed)
            transcriber.canceled.connect(handle_canceled)
            transcriber.session_stopped.connect(handle_stopped)

            progress_text.value = "转写进行中..."
            _mark_dirty()

            transcriber.start_transcribing_async().get()
            done_event.wait(timeout=300)
            transcriber.stop_transcribing_async().get()

            # 保存结果
            transcription_results["segments"] = segments
            full = "\n".join(
                f"[{s['speaker']}] ({_format_time(s['offset'])}) {s['text']}"
                for s in segments
            )
            transcription_results["full_text"] = full

            _set_summary_enabled(True)
            copy_btn.disabled = False
            copy_summary_btn.disabled = False
            export_btn.disabled = False
            clear_results_btn.visible = True
            progress_text.value = f"转写完成，共 {len(segments)} 段"
            progress_bar.value = 1.0

        except ImportError:
            progress_text.value = "错误: 未安装 azure-cognitiveservices-speech"
        except Exception as ex:
            progress_text.value = f"转写失败: {str(ex)[:100]}"
        finally:
            file_transcribe_btn.disabled = False
            live_btn.disabled = False
            _mark_dirty()

    def _start_file_transcription(e):
        if live_state["running"]:
            _show_snackbar("请先停止实时转录")
            return
        if not selected_file["path"]:
            _show_snackbar("请先选择音频文件")
            return
        threading.Thread(target=_do_file_transcription, daemon=True).start()

    file_transcribe_btn = ft.Container(
        content=ft.Row([
            ft.Icon(ft.Icons.PLAY_ARROW, size=16, color=ft.Colors.ON_SURFACE),
            ft.Text("转写文件", size=13, weight=ft.FontWeight.W_500, color=ft.Colors.ON_SURFACE),
        ], spacing=6),
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH, border_radius=8,
        padding=ft.Padding.symmetric(horizontal=16, vertical=10),
        on_click=_start_file_transcription, ink=True, disabled=True,
    )
    clear_file_btn = ft.IconButton(
        icon=ft.Icons.CLOSE, icon_size=16, tooltip="清除选择",
        on_click=_clear_selected_file, visible=False,
    )

    # ── GPT-4o 纪要生成 (F1-07/08) ──────────────────────────────
    summary_markdown = ft.Markdown(
        "",
        selectable=True,
        extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
        auto_follow_links=False,
    )
    summary_placeholder = ft.Container(
        content=ft.Column([
            ft.Icon(ft.Icons.AUTO_AWESOME, size=40, opacity=0.08, color="#0078D4"),
            ft.Text("AI 会议纪要将在此处生成", opacity=0.25, italic=True, size=14),
            ft.Text("完成转写后，点击下方「生成纪要」", opacity=0.18, size=12),
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
        alignment=ft.Alignment(0, 0),
        padding=60,
    )
    summary_list_view = ft.ListView(
        controls=[summary_placeholder],
        expand=True,
        auto_scroll=True,
    )
    summary_container = ft.Container(
        content=summary_list_view,
        expand=True,
    )

    def _do_summary():
        full_text = transcription_results.get("full_text", "")
        if not full_text:
            _show_snackbar("转写内容为空，请先完成转写")
            return

        cfg = load_config()
        openai_endpoint = cfg.get("openai_endpoint", "")
        openai_key = cfg.get("openai_api_key", "")
        openai_deployment = cfg.get("openai_deployment", "gpt-4o") or "gpt-4o"

        if not openai_endpoint or not openai_key:
            _show_snackbar("请先在设置中配置 Azure OpenAI Endpoint 和 API Key")
            return

        _set_summary_enabled(False)
        summary_list_view.controls.clear()
        summary_list_view.controls.append(summary_markdown)
        summary_markdown.value = "正在生成纪要..."
        _flush_ui()

        try:
            client = AzureOpenAI(
                azure_endpoint=openai_endpoint,
                api_key=openai_key,
                api_version="2024-06-01",
            )

            response = client.chat.completions.create(
                model=openai_deployment,
                messages=[
                    {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                    {"role": "user", "content": f"以下是会议转写文本：\n\n{full_text}"},
                ],
                stream=True,
                temperature=0.3,
                max_tokens=4096,
            )

            result_chunks = []
            for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    text = chunk.choices[0].delta.content
                    result_chunks.append(text)
                    summary_markdown.value = "".join(result_chunks)
                    _mark_dirty()

            summary_text["value"] = "".join(result_chunks)

        except Exception as ex:
            summary_markdown.value = f"生成失败: {str(ex)[:200]}"
        finally:
            _set_summary_enabled(True)
            copy_summary_btn.disabled = False
            _mark_dirty()

    summary_btn = ft.Container(
        content=ft.Row([
            ft.Icon(ft.Icons.AUTO_AWESOME, size=16, color=ft.Colors.WHITE),
            ft.Text("生成纪要", size=13, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
        ], spacing=6),
        bgcolor=ft.Colors.OUTLINE, border_radius=8,
        padding=ft.Padding.symmetric(horizontal=20, vertical=10),
        on_click=lambda e: threading.Thread(target=_do_summary, daemon=True).start(),
        ink=True, disabled=True, tooltip="请先完成转写",
        opacity=0.5,
    )

    def _set_summary_enabled(enabled: bool):
        summary_btn.disabled = not enabled
        summary_btn.bgcolor = "#0078D4" if enabled else ft.Colors.OUTLINE
        summary_btn.opacity = 1.0 if enabled else 0.5
        summary_btn.tooltip = None if enabled else "请先完成转写"

    # ── 复制 & 导出 (F1-09/10) ───────────────────────────────────
    _clipboard = ft.Clipboard()
    _export_picker = ft.FilePicker()
    page.services.append(_clipboard)
    page.services.append(_export_picker)

    async def _copy_transcript(e):
        text = transcription_results.get("full_text", "")
        if text:
            await _clipboard.set(text)
            _show_snackbar("已复制转写原文")
        else:
            _show_snackbar("暂无转写内容")

    async def _copy_summary(e):
        text = summary_text.get("value", "")
        if text:
            await _clipboard.set(text)
            _show_snackbar("已复制会议纪要")
        else:
            _show_snackbar("暂无纪要内容")

    async def export_txt(e):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"meeting_notes_{timestamp}.txt"

        content = "=" * 60 + "\n"
        content += "  Azure AI 语音演示台 — 会议纪要导出\n"
        content += f"  导出时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        content += "=" * 60 + "\n\n"
        content += "【转写原文】\n"
        content += "-" * 40 + "\n"
        content += transcription_results.get("full_text", "无") + "\n\n"
        content += "【AI 会议纪要】\n"
        content += "-" * 40 + "\n"
        content += summary_text.get("value", "未生成") + "\n"

        save_path = await _export_picker.save_file(
            dialog_title="导出会议纪要",
            file_name=default_name,
            allowed_extensions=["txt"],
        )
        if save_path:
            from pathlib import Path
            Path(save_path).write_text(content, encoding="utf-8")
            _show_snackbar(f"已导出: {Path(save_path).name}")
        else:
            _show_snackbar("已取消导出")

    copy_btn = ft.Container(
        content=ft.Row([
            ft.Icon(ft.Icons.CONTENT_COPY, size=14, color=ft.Colors.ON_SURFACE),
            ft.Text("复制原文", size=13, weight=ft.FontWeight.W_500, color=ft.Colors.ON_SURFACE),
        ], spacing=6),
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH, border_radius=8,
        padding=ft.Padding.symmetric(horizontal=16, vertical=10),
        on_click=_copy_transcript, ink=True, disabled=True,
    )
    copy_summary_btn = ft.Container(
        content=ft.Row([
            ft.Icon(ft.Icons.CONTENT_COPY, size=14, color=ft.Colors.ON_SURFACE),
            ft.Text("复制纪要", size=13, weight=ft.FontWeight.W_500, color=ft.Colors.ON_SURFACE),
        ], spacing=6),
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH, border_radius=8,
        padding=ft.Padding.symmetric(horizontal=16, vertical=10),
        on_click=_copy_summary, ink=True, disabled=True,
    )
    export_btn = ft.Container(
        content=ft.Row([
            ft.Icon(ft.Icons.DOWNLOAD, size=14, color=ft.Colors.ON_SURFACE),
            ft.Text("导出 .txt", size=13, weight=ft.FontWeight.W_500, color=ft.Colors.ON_SURFACE),
        ], spacing=6),
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH, border_radius=8,
        padding=ft.Padding.symmetric(horizontal=16, vertical=10),
        on_click=export_txt, ink=True, disabled=True,
    )

    def _clear_all_results(e):
        """清除所有转写和纪要结果。"""
        transcription_results["segments"] = []
        transcription_results["full_text"] = ""
        summary_text["value"] = ""
        transcript_list.controls.clear()
        transcript_list.controls.append(_transcript_placeholder)
        summary_list_view.controls.clear()
        summary_list_view.controls.append(summary_placeholder)
        summary_markdown.value = ""
        _set_summary_enabled(False)
        copy_btn.disabled = True
        copy_summary_btn.disabled = True
        export_btn.disabled = True
        clear_results_btn.visible = False
        progress_bar.visible = False
        progress_text.visible = False
        # 重置性能指标
        perf["latency_list"].clear()
        perf["speakers"].clear()
        perf["word_count"] = 0
        perf["audio_duration_s"] = 0
        _perf_latency_value.value = "--"
        _perf_latency_avg.value = ""
        _perf_speaker_value.value = "0"
        _perf_word_value.value = "0"
        _perf_duration_value.value = "00:00"
        _flush_ui()

    clear_results_btn = ft.Container(
        content=ft.Row([
            ft.Icon(ft.Icons.DELETE_OUTLINE, size=14, color=ft.Colors.ON_SURFACE),
            ft.Text("清除", size=13, weight=ft.FontWeight.W_500, color=ft.Colors.ON_SURFACE),
        ], spacing=6),
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH, border_radius=8,
        padding=ft.Padding.symmetric(horizontal=16, vertical=10),
        on_click=_clear_all_results, ink=True, visible=False,
    )

    # ── 工具函数 ─────────────────────────────────────────────────
    def _show_snackbar(msg: str):
        page.show_dialog(ft.SnackBar(content=ft.Text(msg)))
        _flush_ui()

    def _fmt_ms(ms: float) -> str:
        if ms < 1000:
            return f"{int(ms)}ms"
        return f"{ms / 1000:.1f}s"

    # ── 性能指标（紧凑 pill 标签式，对齐 Phase 2/3）──────────────
    _perf_latency_value = ft.Text("--", size=13, weight=ft.FontWeight.BOLD, color="#00E676")
    _perf_latency_avg = ft.Text("", size=11, opacity=0.5)
    _perf_speaker_value = ft.Text("0", size=13, weight=ft.FontWeight.BOLD, color="#90CAF9")
    _perf_word_value = ft.Text("0", size=13, weight=ft.FontWeight.BOLD, color="#FFB74D")
    _perf_duration_value = ft.Text("00:00", size=13, color=ft.Colors.ON_SURFACE_VARIANT)

    def _update_perf_latency(latency_ms: float):
        _perf_latency_value.value = _fmt_ms(latency_ms)
        if perf["latency_list"]:
            avg = sum(perf["latency_list"]) / len(perf["latency_list"])
            _perf_latency_avg.value = f"avg {_fmt_ms(avg)}"

    def _update_perf_counters():
        _perf_speaker_value.value = str(len(perf["speakers"]))
        _perf_word_value.value = f"{perf['word_count']:,}"
        # 实时转录用 elapsed time，文件转录用 audio offset
        if live_state["running"] and perf["start_time"] > 0:
            elapsed = time.time() - perf["start_time"]
            m, s = divmod(int(elapsed), 60)
            _perf_duration_value.value = f"{m:02d}:{s:02d}"
        elif perf["audio_duration_s"] > 0:
            m, s = divmod(int(perf["audio_duration_s"]), 60)
            _perf_duration_value.value = f"{m:02d}:{s:02d}"

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

    perf_latency_pill = _build_perf_pill("延迟", _perf_latency_value, _perf_latency_avg)
    perf_speaker_pill = _build_perf_pill("说话人", _perf_speaker_value)
    perf_word_pill = _build_perf_pill("词数", _perf_word_value)
    perf_duration_pill = _build_perf_pill("时长", _perf_duration_value)

    # ══════════════════════════════════════════════════════════════
    # 布局
    # ══════════════════════════════════════════════════════════════

    # 输入区 Card：实时转录（主按钮）+ 文件上传（次按钮）
    input_card = ft.Container(
        content=ft.Column([
            ft.Row([
                live_btn,
                stop_live_btn,
                live_indicator,
                segment_count_text,
                ft.Container(width=1, height=28, bgcolor=ft.Colors.OUTLINE_VARIANT),
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.UPLOAD_FILE, size=16, color=ft.Colors.ON_SURFACE),
                        ft.Text("选择文件", size=13, weight=ft.FontWeight.W_500, color=ft.Colors.ON_SURFACE),
                    ], spacing=6),
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH, border_radius=8,
                    padding=ft.Padding.symmetric(horizontal=16, vertical=10),
                    on_click=pick_file, ink=True,
                ),
                file_info_text,
                clear_file_btn,
                file_transcribe_btn,
            ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            progress_bar,
            progress_text,
        ], spacing=8),
        bgcolor=ft.Colors.SURFACE_CONTAINER,
        border_radius=12,
        padding=ft.Padding(left=24, top=16, right=24, bottom=12),
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
    )

    # 转写原文（副区，expand=1），含中间结果
    transcript_panel = ft.Container(
        content=ft.Column([
            ft.Text("转写原文", size=13, weight=ft.FontWeight.W_500, opacity=0.5),
            ft.Container(
                content=ft.Column([
                    transcript_list,
                    _interim_container,
                ], expand=True, spacing=0),
                expand=True,
                border_radius=8,
                bgcolor=ft.Colors.SURFACE_CONTAINER_LOWEST,
                padding=8,
            ),
        ], spacing=8),
        bgcolor=ft.Colors.SURFACE_CONTAINER,
        border_radius=12,
        padding=16,
        expand=1,
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
    )

    # AI 会议纪要（主区，expand=2）
    summary_panel = ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.AUTO_AWESOME, color=ft.Colors.PRIMARY, size=18),
                ft.Text("AI 会议纪要", size=15, weight=ft.FontWeight.BOLD),
            ], spacing=8),
            ft.Container(
                content=summary_container,
                expand=True,
                border_radius=8,
                bgcolor=ft.Colors.SURFACE_CONTAINER_LOWEST,
                padding=16,
                border=ft.Border(left=ft.BorderSide(3, ft.Colors.PRIMARY)),
            ),
        ], spacing=10),
        bgcolor=ft.Colors.SURFACE_CONTAINER,
        border_radius=12,
        padding=20,
        expand=2,
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
    )

    result_area = ft.Row(
        [transcript_panel, summary_panel],
        expand=True,
        spacing=16,
    )

    # 底部操作栏（性能指标 + 操作按钮）
    bottom_bar = ft.Container(
        content=ft.Row(
            [
                perf_latency_pill,
                perf_speaker_pill,
                perf_word_pill,
                perf_duration_pill,
                ft.Container(expand=True),
                clear_results_btn,
                summary_btn,
                copy_btn,
                copy_summary_btn,
                export_btn,
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding.symmetric(horizontal=0, vertical=4),
    )

    # 最终布局
    tab_content = ft.Container(
        content=ft.Column(
            [
                config_banner,
                input_card,
                result_area,
                bottom_bar,
            ],
            spacing=8,
            expand=True,
        ),
        padding=ft.Padding(left=16, top=12, right=16, bottom=8),
        expand=True,
    )

    return tab_content, _refresh_config_banner
