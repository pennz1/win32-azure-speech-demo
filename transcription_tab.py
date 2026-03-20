"""
Phase 1 — 会议转写 & AI 纪要生成 Tab
功能：音频上传/录制 → Azure Speech 转写(Diarization) → GPT-4o 流式生成纪要
"""

import datetime
import os
import threading
import time
from pathlib import Path

import flet as ft
from openai import AzureOpenAI

from audio_recorder import AudioRecorder
from app_paths import get_data_dir
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
    recorder = AudioRecorder(output_dir=str(get_data_dir("recordings")))

    # ── 状态变量 ─────────────────────────────────────────────────
    selected_file = {"path": None}
    transcription_results = {"segments": [], "full_text": ""}
    summary_text = {"value": ""}

    # ── F1-11 配置状态 Banner ────────────────────────────────────
    config_banner_icon = ft.Icon(ft.Icons.WARNING_ROUNDED, color=ft.Colors.AMBER, size=18)
    config_banner_text = ft.Text("", size=13)
    config_banner_btn = ft.TextButton(
        "前往设置 ⚙️",
        on_click=lambda e: page.pubsub.send_all("open_settings"),
        style=ft.ButtonStyle(color=ft.Colors.AMBER),
    )
    config_banner = ft.Container(
        content=ft.Row(
            [config_banner_icon, config_banner_text, config_banner_btn],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        border_radius=8,
        padding=ft.padding.symmetric(horizontal=14, vertical=8),
        bgcolor="#2a2200",
    )

    def _refresh_config_banner():
        """根据当前配置刷新 Banner 的颜色和文字。"""
        cfg = load_config()
        has_speech = bool(cfg.get("speech_api_key", "").strip())
        has_openai = bool(cfg.get("openai_api_key", "").strip()) and bool(cfg.get("openai_endpoint", "").strip())

        if has_speech and has_openai:
            config_banner_icon.name = ft.Icons.CHECK_CIRCLE
            config_banner_icon.color = ft.Colors.GREEN
            config_banner_text.value = "✅  Azure Speech + OpenAI 已配置，可开始使用"
            config_banner_btn.visible = False
            config_banner.bgcolor = "#0a2212"
        elif has_speech and not has_openai:
            config_banner_icon.name = ft.Icons.WARNING_ROUNDED
            config_banner_icon.color = ft.Colors.AMBER
            config_banner_text.value = "⚠️  Azure Speech 已配置，但 OpenAI API Key / Endpoint 未填写（生成纪要功能不可用）"
            config_banner_btn.visible = True
            config_banner.bgcolor = "#2a2200"
        elif not has_speech and has_openai:
            config_banner_icon.name = ft.Icons.WARNING_ROUNDED
            config_banner_icon.color = ft.Colors.AMBER
            config_banner_text.value = "⚠️  Azure OpenAI 已配置，但 Speech API Key 未填写（转写功能不可用）"
            config_banner_btn.visible = True
            config_banner.bgcolor = "#2a2200"
        else:
            config_banner_icon.name = ft.Icons.ERROR_OUTLINE
            config_banner_icon.color = ft.Colors.RED_400
            config_banner_text.value = "❌  尚未配置 Azure API Key，请先在设置中填写 Speech 和 OpenAI 配置"
            config_banner_btn.visible = True
            config_banner.bgcolor = "#2a0a0a"
        try:
            page.update()
        except Exception:
            pass

    # 初始渲染
    _refresh_config_banner()

    # ── 文件选择区 (F1-01) ───────────────────────────────────────
    file_info_text = ft.Text("未选择文件", size=13, italic=True, opacity=0.6)

    def on_file_picked(e: ft.FilePickerResultEvent):
        if e.files and len(e.files) > 0:
            selected_file["path"] = e.files[0].path
            file_info_text.value = f"已选：{e.files[0].name}"
            file_info_text.opacity = 1.0
            start_btn.disabled = False
            page.update()

    file_picker = ft.FilePicker(on_result=on_file_picked)
    page.overlay.append(file_picker)

    def pick_file(e):
        file_picker.pick_files(
            dialog_title="选择音频文件",
            allowed_extensions=["wav", "mp3", "m4a"],
            allow_multiple=False,
        )

    # ── 录音控制 (F1-02) ─────────────────────────────────────────
    recording_timer_text = ft.Text("00:00", size=13, color=ft.Colors.RED)
    recording_timer_text.visible = False
    _timer_running = {"flag": False}

    record_btn = ft.ElevatedButton(
        "🎙️ 开始录制",
        on_click=lambda e: _toggle_recording(e),
        color=ft.Colors.WHITE,
    )
    stop_record_btn = ft.ElevatedButton(
        "⏹ 停止录制",
        on_click=lambda e: _stop_recording(e),
        visible=False,
        bgcolor=ft.Colors.RED_900,
        color=ft.Colors.WHITE,
    )

    def _update_timer():
        while _timer_running["flag"]:
            secs = recorder.elapsed_seconds
            recording_timer_text.value = _format_time(secs)
            try:
                page.update()
            except Exception:
                break
            time.sleep(0.5)

    def _toggle_recording(e):
        recorder.start()
        record_btn.visible = False
        stop_record_btn.visible = True
        recording_timer_text.visible = True
        _timer_running["flag"] = True
        threading.Thread(target=_update_timer, daemon=True).start()
        page.update()

    def _stop_recording(e):
        _timer_running["flag"] = False
        filepath = recorder.stop()
        record_btn.visible = True
        stop_record_btn.visible = False
        recording_timer_text.visible = False
        if filepath:
            selected_file["path"] = filepath
            name = os.path.basename(filepath)
            file_info_text.value = f"已录制：{name}  时长: {_format_time(recorder.elapsed_seconds)}"
            file_info_text.opacity = 1.0
            start_btn.disabled = False
        page.update()

    # ── 转写控制 (F1-03/04/05) ───────────────────────────────────
    progress_bar = ft.ProgressBar(visible=False, width=600)
    progress_text = ft.Text("", size=12, visible=False)
    transcript_list = ft.ListView(expand=True, spacing=8, auto_scroll=True)
    # 默认占位
    transcript_list.controls.append(
        ft.Container(
            content=ft.Text("转写结果将显示在此处", opacity=0.4, italic=True),
            alignment=ft.alignment.center,
            padding=40,
        )
    )

    def _do_transcription():
        """后台线程执行 Azure Speech 转写 + Diarization。"""
        filepath = selected_file["path"]
        if not filepath:
            return

        cfg = load_config()
        speech_key = cfg.get("speech_api_key", "")
        region = cfg.get("region", "eastasia")

        if not speech_key:
            transcript_list.controls.clear()
            transcript_list.controls.append(
                ft.Container(
                    content=ft.Column([
                        ft.Icon(ft.Icons.VPN_KEY_OFF, size=40, color=ft.Colors.RED_400),
                        ft.Text("Azure Speech API Key 未配置",
                                size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.RED_400),
                        ft.Text("请点击右上角 ⚙️ 设置按钮，填写 Speech API Key 后重试",
                                size=13, opacity=0.7, text_align=ft.TextAlign.CENTER),
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
                    alignment=ft.alignment.center,
                    padding=40,
                )
            )
            _show_snackbar("请先在设置中配置 Azure Speech API Key")
            page.update()
            return

        progress_bar.visible = True
        progress_bar.value = None  # indeterminate
        progress_text.visible = True
        progress_text.value = "正在初始化转写..."
        start_btn.disabled = True
        page.update()

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
            # 支持多语言
            auto_detect_config = speechsdk.languageconfig.AutoDetectSourceLanguageConfig(
                languages=["zh-CN", "en-US"]
            )

            audio_config = speechsdk.audio.AudioConfig(filename=filepath)
            conversation_transcriber = speechsdk.transcription.ConversationTranscriber(
                speech_config=speech_config,
                audio_config=audio_config,
                auto_detect_source_language_config=auto_detect_config,
            )

            segments = []
            done_event = threading.Event()

            def handle_transcribed(evt):
                if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
                    speaker_id = getattr(evt.result, "speaker_id", "Unknown")
                    offset_ticks = getattr(evt.result, "offset", 0)
                    offset_sec = offset_ticks / 10_000_000
                    seg = {
                        "speaker": speaker_id or "Unknown",
                        "text": evt.result.text,
                        "offset": offset_sec,
                    }
                    segments.append(seg)
                    # 实时更新 UI
                    _add_transcript_bubble(seg, len(segments))
                    progress_text.value = f"已识别 {len(segments)} 段..."
                    try:
                        page.update()
                    except Exception:
                        pass

            def handle_canceled(evt):
                if evt.cancellation_details.reason == speechsdk.CancellationReason.Error:
                    progress_text.value = f"转写错误: {evt.cancellation_details.error_details}"
                    try:
                        page.update()
                    except Exception:
                        pass
                done_event.set()

            def handle_stopped(evt):
                done_event.set()

            conversation_transcriber.transcribed.connect(handle_transcribed)
            conversation_transcriber.canceled.connect(handle_canceled)
            conversation_transcriber.session_stopped.connect(handle_stopped)

            # 清空旧结果
            transcript_list.controls.clear()
            page.update()

            progress_text.value = "转写进行中..."
            page.update()

            conversation_transcriber.start_transcribing_async().get()
            done_event.wait(timeout=300)  # 最长等 5 分钟
            conversation_transcriber.stop_transcribing_async().get()

            # 保存结果
            transcription_results["segments"] = segments
            full = "\n".join(
                f"[{s['speaker']}] ({_format_time(s['offset'])}) {s['text']}"
                for s in segments
            )
            transcription_results["full_text"] = full

            progress_bar.value = 1.0
            progress_text.value = f"转写完成 ✅  共 {len(segments)} 段"
            summary_btn.disabled = False
            copy_btn.disabled = False
            export_btn.disabled = False

        except ImportError:
            progress_text.value = "错误: 未安装 azure-cognitiveservices-speech"
        except Exception as ex:
            progress_text.value = f"转写失败: {str(ex)[:100]}"
        finally:
            start_btn.disabled = False
            try:
                page.update()
            except Exception:
                pass

    def _add_transcript_bubble(seg: dict, index: int):
        """向转写列表添加一条 Speaker 气泡卡片。"""
        speaker = seg["speaker"]
        # 根据 speaker 分配颜色
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
                                    speaker, size=11, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE
                                ),
                                bgcolor=color,
                                border_radius=4,
                                padding=ft.padding.symmetric(horizontal=8, vertical=2),
                            ),
                            ft.Text(
                                _format_time(seg["offset"]),
                                size=11,
                                opacity=0.5,
                            ),
                        ],
                        spacing=8,
                    ),
                    ft.Text(seg["text"], size=14, selectable=True),
                ],
                spacing=4,
            ),
            bgcolor="#1e1e2e",
            border_radius=10,
            padding=12,
        )
        transcript_list.controls.append(bubble)

    def start_transcription(e):
        if not selected_file["path"]:
            _show_snackbar("请先选择或录制音频文件")
            return
        threading.Thread(target=_do_transcription, daemon=True).start()

    start_btn = ft.ElevatedButton(
        "▶ 开始转写",
        on_click=start_transcription,
        disabled=True,
        style=ft.ButtonStyle(bgcolor="#0078D4", color=ft.Colors.WHITE),
    )

    def _reset_transcription_ui():
        progress_bar.visible = False
        progress_text.visible = False
        start_btn.disabled = False
        page.update()

    # ── GPT-4o 纪要生成 (F1-07/08) ──────────────────────────────
    summary_markdown = ft.Markdown(
        "纪要将在此处生成",
        selectable=True,
        extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
        auto_follow_links=False,
    )
    summary_container = ft.Container(
        content=ft.ListView(
            controls=[summary_markdown],
            expand=True,
            auto_scroll=True,
        ),
        expand=True,
    )

    def _do_summary():
        """后台线程使用 GPT-4o 生成流式纪要。"""
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

        summary_btn.disabled = True
        summary_markdown.value = "⏳ 正在生成纪要..."
        page.update()

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
                    try:
                        page.update()
                    except Exception:
                        pass

            summary_text["value"] = "".join(result_chunks)

        except Exception as ex:
            summary_markdown.value = f"生成失败: {str(ex)[:200]}"
        finally:
            summary_btn.disabled = False
            try:
                page.update()
            except Exception:
                pass

    summary_btn = ft.ElevatedButton(
        "🤖 生成纪要",
        on_click=lambda e: threading.Thread(target=_do_summary, daemon=True).start(),
        disabled=True,
        tooltip="请先完成音频转写",
        style=ft.ButtonStyle(bgcolor="#0078D4", color=ft.Colors.WHITE),
    )

    # ── 复制 & 导出 (F1-09/10) ───────────────────────────────────
    def copy_summary(e):
        text = summary_text.get("value", "") or transcription_results.get("full_text", "")
        if text:
            page.set_clipboard(text)
            _show_snackbar("已复制 ✅")
        else:
            _show_snackbar("暂无内容可复制")

    def export_txt(e):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        export_path = get_data_dir("exports")
        filepath = export_path / f"meeting_notes_{timestamp}.txt"

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

        filepath.write_text(content, encoding="utf-8")
        _show_snackbar(f"已导出: {filepath.name}")

    copy_btn = ft.ElevatedButton("📋 复制纪要", on_click=copy_summary, disabled=True, tooltip="请先完成音频转写")
    export_btn = ft.ElevatedButton("💾 导出 .txt", on_click=export_txt, disabled=True, tooltip="请先完成音频转写")

    # ── 工具函数 ─────────────────────────────────────────────────
    def _show_snackbar(msg: str):
        page.snack_bar = ft.SnackBar(content=ft.Text(msg))
        page.snack_bar.open = True
        try:
            page.update()
        except Exception:
            pass

    # ── 整体布局 ─────────────────────────────────────────────────
    # 顶部：文件选择 / 录制区域
    file_area = ft.Container(
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.ElevatedButton("📂 选择文件", on_click=pick_file),
                        record_btn,
                        stop_record_btn,
                        recording_timer_text,
                    ],
                    spacing=12,
                ),
                ft.Row(
                    [
                        file_info_text,
                        ft.Text(
                            "支持: .wav / .mp3 / .m4a  ≤ 500MB",
                            size=11,
                            opacity=0.4,
                        ),
                    ],
                    spacing=16,
                ),
            ],
            spacing=8,
        ),
        border=ft.border.all(1, ft.Colors.OUTLINE),
        border_radius=12,
        padding=16,
    )

    # 转写按钮 + 进度条
    transcribe_area = ft.Column(
        [
            ft.Row([start_btn], alignment=ft.MainAxisAlignment.START),
            progress_bar,
            progress_text,
        ],
        spacing=6,
    )

    # 左右双栏
    left_panel = ft.Container(
        content=ft.Column(
            [
                ft.Text("📄 转写原文", weight=ft.FontWeight.BOLD, size=15),
                ft.Container(
                    content=transcript_list,
                    expand=True,
                    border=ft.border.all(1, ft.Colors.OUTLINE),
                    border_radius=10,
                    padding=8,
                ),
            ],
            spacing=8,
            expand=True,
        ),
        expand=True,
    )

    right_panel = ft.Container(
        content=ft.Column(
            [
                ft.Text("🤖 AI 会议纪要", weight=ft.FontWeight.BOLD, size=15),
                ft.Container(
                    content=summary_container,
                    expand=True,
                    border=ft.border.all(1, ft.Colors.OUTLINE),
                    border_radius=10,
                    padding=12,
                ),
            ],
            spacing=8,
            expand=True,
        ),
        expand=True,
    )

    content_row = ft.Row(
        [left_panel, right_panel],
        expand=True,
        spacing=16,
    )

    # 底部按钮栏
    bottom_bar = ft.Row(
        [summary_btn, copy_btn, export_btn],
        spacing=12,
    )

    # 最终布局
    tab_content = ft.Container(
        content=ft.Column(
            [
                ft.Text(
                    "📝 会议转写 & AI 纪要生成",
                    size=18,
                    weight=ft.FontWeight.BOLD,
                ),
                config_banner,   # F1-11 配置状态 Banner
                file_area,
                transcribe_area,
                content_row,
                bottom_bar,
            ],
            spacing=12,
            expand=True,
        ),
        padding=20,
        expand=True,
    )

    return tab_content, _refresh_config_banner
