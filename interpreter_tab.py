"""
同声传译 Live Interpreter Tab
功能：麦克风实时采集 → Azure Speech Translation（自动语言检测）→ 双栏字幕 + TTS 播放
"""

import datetime
import threading
import time
from pathlib import Path

import flet as ft

from config_manager import load_config

# 支持的目标语言
TARGET_LANGUAGES = {
    "zh-Hans": "🇨🇳 中文",
    "en": "🇺🇸 English",
    "ja": "🇯🇵 日本語",
    "ko": "🇰🇷 한국어",
    "de": "🇩🇪 Deutsch",
    "fr": "🇫🇷 Français",
}

# 自动检测的源语言候选（At-start LID 模式最多支持 4 种）
# Continuous LID 支持更多但不适用于 TranslationRecognizer
SOURCE_LANGUAGES = ["zh-CN", "en-US", "ja-JP", "ko-KR"]

# 语言代码→显示名映射
LANG_DISPLAY = {
    "zh-CN": "🇨🇳 中文 (zh-CN)",
    "en-US": "🇺🇸 English (en-US)",
    "ja-JP": "🇯🇵 日本語 (ja-JP)",
    "ko-KR": "🇰🇷 한국어 (ko-KR)",
    "de-DE": "🇩🇪 Deutsch (de-DE)",
    "fr-FR": "🇫🇷 Français (fr-FR)",
}

# 简短语言显示（用于检测标签）
LANG_SHORT = {
    "zh-CN": "🇨🇳 中文",
    "en-US": "🇺🇸 EN",
    "ja-JP": "🇯🇵 JA",
    "ko-KR": "🇰🇷 KO",
}

# 分段静音超时（ms）—— 控制端点检测灵敏度，越小翻译越快但可能打断长句
SEGMENTATION_SILENCE_MS = "300"

# TTS 语音映射：target_lang → gender → [(voice_id, display_name), ...]
TTS_VOICE_OPTIONS = {
    "zh-Hans": {
        "female": [("zh-CN-XiaoxiaoNeural", "晓晓"), ("zh-CN-XiaoyiNeural", "晓伊"), ("zh-CN-XiaochenNeural", "晓辰")],
        "male": [("zh-CN-YunxiNeural", "云希"), ("zh-CN-YunjianNeural", "云健"), ("zh-CN-YunyangNeural", "云扬")],
    },
    "en": {
        "female": [("en-US-JennyNeural", "Jenny"), ("en-US-AriaNeural", "Aria"), ("en-US-AvaNeural", "Ava")],
        "male": [("en-US-GuyNeural", "Guy"), ("en-US-DavisNeural", "Davis"), ("en-US-BrianNeural", "Brian")],
    },
    "ja": {
        "female": [("ja-JP-NanamiNeural", "七海"), ("ja-JP-AoiNeural", "葵"), ("ja-JP-MayuNeural", "まゆ")],
        "male": [("ja-JP-KeitaNeural", "圭太"), ("ja-JP-DaichiNeural", "大智"), ("ja-JP-NaokiNeural", "直紀")],
    },
    "ko": {
        "female": [("ko-KR-SunHiNeural", "선히"), ("ko-KR-JiMinNeural", "지민"), ("ko-KR-YuJinNeural", "유진")],
        "male": [("ko-KR-InJoonNeural", "인준"), ("ko-KR-BongJinNeural", "봉진"), ("ko-KR-GookMinNeural", "국민")],
    },
    "de": {
        "female": [("de-DE-KatjaNeural", "Katja"), ("de-DE-AmalaNeural", "Amala"), ("de-DE-KlarissaNeural", "Klarissa")],
        "male": [("de-DE-ConradNeural", "Conrad"), ("de-DE-BerndNeural", "Bernd"), ("de-DE-KasperNeural", "Kasper")],
    },
    "fr": {
        "female": [("fr-FR-DeniseNeural", "Denise"), ("fr-FR-CoralieNeural", "Coralie"), ("fr-FR-BrigitteNeural", "Brigitte")],
        "male": [("fr-FR-HenriNeural", "Henri"), ("fr-FR-ClaudeNeural", "Claude"), ("fr-FR-AlainNeural", "Alain")],
    },
}


def _format_ms(ms: float) -> str:
    if ms < 1000:
        return f"{int(ms)}ms"
    return f"{ms / 1000:.1f}s"


def build_interpreter_tab(page: ft.Page):
    """构建「同声传译 Live Interpreter」Tab 的全部 UI 和逻辑。"""

    # ── 状态 ─────────────────────────────────────────────────────
    state = {
        "recognizer": None,
        "running": False,
        "detected_lang": "",
        "tts_enabled": True,
        "synthesizer": None,       # 复用 TTS synthesizer 降低延迟
        "synth_lock": threading.Lock(),
        "voice_gender": "female",   # 默认女声
        "current_tts_future": None, # 当前 TTS 播放句柄，用于取消
    }
    history = {"source": [], "target": []}
    metrics = {
        "latency_ms": 0,
        "confidence": 0.0,
        "latency_history": [],
        "sentence_start": 0,
    }

    # ── UI 更新机制 (与 Phase 2 一致): page.run_task() 调度到 Flet 事件循环 ───
    _update_pending = [False]

    async def _async_update():
        """在 Flet 事件循环上执行 UI 更新。"""
        _update_pending[0] = False
        try:
            page.update()
        except Exception:
            pass

    def _mark_dirty():
        """将 UI 更新调度到 Flet 事件循环 (线程安全，用于 SDK 回调线程)。"""
        if _update_pending[0]:
            return
        _update_pending[0] = True
        try:
            page.run_task(_async_update)
        except Exception:
            _update_pending[0] = False

    def _flush_ui():
        """强制立即刷新 (仅在 Flet UI 事件回调线程中使用)。"""
        try:
            page.update()
        except Exception:
            pass

    # ── 配置 Banner ──────────────────────────────────────────────
    config_banner_icon = ft.Icon(ft.Icons.WARNING_ROUNDED, color=ft.Colors.AMBER, size=18)
    config_banner_text = ft.Text("", size=13)
    config_banner_btn = ft.TextButton(
        "前往设置",
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
        padding=ft.Padding.symmetric(horizontal=14, vertical=8),
        bgcolor=ft.Colors.SECONDARY_CONTAINER,
        visible=True,
    )

    def _refresh_config_banner():
        cfg = load_config()
        has_speech = bool(cfg.get("speech_api_key", "").strip())
        if has_speech:
            config_banner.visible = False
        else:
            config_banner.visible = True
            config_banner_icon.name = ft.Icons.ERROR_OUTLINE
            config_banner_icon.color = ft.Colors.RED_400
            config_banner_text.value = "请先在设置中配置 Azure Speech API Key"
            config_banner_btn.visible = True
            config_banner.bgcolor = ft.Colors.ERROR_CONTAINER
        _flush_ui()

    _refresh_config_banner()

    # ── 目标语言选择 ─────────────────────────────────────────────
    target_lang_dropdown = ft.Dropdown(
        value="en",
        options=[ft.dropdown.Option(k, v) for k, v in TARGET_LANGUAGES.items()],
        width=150,
        border_color="transparent",
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
        border_radius=12,
        content_padding=ft.Padding.symmetric(horizontal=12, vertical=4),
        text_size=13,
    )

    # ── 原文字幕列表 ─────────────────────────────────────────────
    source_list = ft.ListView(expand=True, spacing=8, auto_scroll=True, padding=ft.Padding.symmetric(horizontal=16, vertical=12))

    # ── 译文字幕列表 ─────────────────────────────────────────────
    target_list = ft.ListView(expand=True, spacing=8, auto_scroll=True, padding=ft.Padding.symmetric(horizontal=16, vertical=12))

    # ── 延迟指标（紧凑标签式） ───────────────────────────────────
    latency_value = ft.Text("--", size=13, weight=ft.FontWeight.BOLD, color="#00E676")
    sentence_count_value = ft.Text("0", size=13, weight=ft.FontWeight.BOLD, color="#B0BEC5")
    detected_lang_text = ft.Text("自动检测", size=12, color="#90CAF9")

    def _build_pill(icon_text: str, value_ctrl, bg: str = None):
        return ft.Container(
            content=ft.Row([ft.Text(icon_text, size=12, opacity=0.7), value_ctrl], spacing=4,
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
            bgcolor=bg or ft.Colors.SURFACE_CONTAINER_HIGH,
            border_radius=14,
            padding=ft.Padding.symmetric(horizontal=10, vertical=5),
        )

    latency_pill = _build_pill("延迟", latency_value)
    count_pill = _build_pill("句数", sentence_count_value)
    lang_pill = _build_pill("语言", detected_lang_text)

    # ── 延迟趋势 ─────────────────────────────────────────────────
    latency_history_text = ft.Text("", size=11, opacity=0.4)

    def _update_latency_display():
        hist = metrics["latency_history"][-10:]
        if not hist:
            latency_history_text.value = ""
            return
        max_val = max(hist) if hist else 1
        blocks = "▁▂▃▄▅▆▇█"
        bars = ""
        for v in hist:
            level = min(int(v / max_val * 7), 7) if max_val > 0 else 0
            bars += blocks[level]
        avg = sum(hist) / len(hist)
        latency_history_text.value = f"{bars} avg {_format_ms(avg)}"

    # ── TTS 开关 ─────────────────────────────────────────────────
    tts_switch = ft.Switch(
        label="播报",
        value=True,
        on_change=lambda e: _toggle_tts(),
        scale=0.8,
    )

    def _toggle_tts():
        state["tts_enabled"] = tts_switch.value
        _notify_setting_changed()

    # ── 音色选择 ─────────────────────────────────────────────────
    voice_gender_dropdown = ft.Dropdown(
        value="female",
        options=[
            ft.dropdown.Option("female", "♀ 女声"),
            ft.dropdown.Option("male", "♂ 男声"),
        ],
        width=100,
        border_color="transparent",
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
        border_radius=12,
        content_padding=ft.Padding.symmetric(horizontal=8, vertical=4),
        text_size=12,
    )

    voice_dropdown = ft.Dropdown(
        width=130,
        border_color="transparent",
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
        border_radius=12,
        content_padding=ft.Padding.symmetric(horizontal=8, vertical=4),
        text_size=12,
    )

    def _get_voice_options():
        target_lang = target_lang_dropdown.value or "en"
        gender = voice_gender_dropdown.value or "female"
        lang_voices = TTS_VOICE_OPTIONS.get(target_lang, TTS_VOICE_OPTIONS["en"])
        return lang_voices.get(gender, lang_voices["female"])

    def _update_voice_options():
        voices = _get_voice_options()
        voice_dropdown.options = [ft.dropdown.Option(v[0], v[1]) for v in voices]
        valid_values = [v[0] for v in voices]
        if voice_dropdown.value not in valid_values:
            voice_dropdown.value = voices[0][0] if voices else None

    _update_voice_options()

    def _notify_setting_changed():
        """设置变更时通知用户生效时机。"""
        if state["running"]:
            msg = "设置已更新，下一句传译时生效"
        else:
            msg = "设置已更新"
        page.show_dialog(ft.SnackBar(content=ft.Text(msg), duration=2000))

    def _on_voice_gender_changed(e):
        state["voice_gender"] = voice_gender_dropdown.value or "female"
        _update_voice_options()
        _invalidate_synthesizer()
        _notify_setting_changed()
        _flush_ui()

    def _on_voice_changed(e):
        _invalidate_synthesizer()
        _notify_setting_changed()

    voice_gender_dropdown.on_select = _on_voice_gender_changed
    voice_dropdown.on_select = _on_voice_changed

    # ── 字幕样式（沉浸式，非日志风） ─────────────────────────────
    def _add_source_bubble(timestamp: str, text: str):
        bubble = ft.Container(
            content=ft.Text(text, size=17, selectable=True),
            padding=ft.Padding.symmetric(horizontal=0, vertical=4),
        )
        source_list.controls.append(bubble)

    def _add_target_bubble(timestamp: str, text: str):
        bubble = ft.Container(
            content=ft.Text(text, size=17, selectable=True, weight=ft.FontWeight.W_500,
                            color="#00C853"),
            padding=ft.Padding.symmetric(horizontal=0, vertical=4),
        )
        target_list.controls.append(bubble)

    # ── 句子计时器 ──────────────────────────────────────────────
    _sentence_timer = {"start": 0, "last_recognizing": 0}

    # ── 流式字幕 (Live bubble) ────────────────────────────────────
    _live = {"src_bubble": None, "src_text": None, "tgt_bubble": None, "tgt_text": None, "placeholder_cleared": False}

    def _clear_placeholder():
        if not _live["placeholder_cleared"]:
            if source_list.controls and len(source_list.controls) == 1:
                first = source_list.controls[0]
                if hasattr(first, 'content') and hasattr(first.content, 'opacity') and first.content.opacity == 0.3:
                    source_list.controls.clear()
                    target_list.controls.clear()
            _live["placeholder_cleared"] = True

    def _finalize_live_source(final_text):
        if _live["src_text"]:
            _live["src_text"].value = final_text
            _live["src_text"].italic = False
            _live["src_text"].opacity = 1.0
        if _live["src_bubble"]:
            _live["src_bubble"].border = None
        _live["src_bubble"] = _live["src_text"] = None

    def _finalize_live_target(final_text):
        if _live["tgt_text"]:
            _live["tgt_text"].value = final_text
            _live["tgt_text"].italic = False
            _live["tgt_text"].opacity = 1.0
            _live["tgt_text"].weight = ft.FontWeight.W_500
        if _live["tgt_bubble"]:
            _live["tgt_bubble"].border = None
        _live["tgt_bubble"] = _live["tgt_text"] = None

    def _cleanup_live_bubbles():
        if _live["src_bubble"] and _live["src_bubble"] in source_list.controls:
            source_list.controls.remove(_live["src_bubble"])
        if _live["tgt_bubble"] and _live["tgt_bubble"] in target_list.controls:
            target_list.controls.remove(_live["tgt_bubble"])
        _live["src_bubble"] = _live["src_text"] = None
        _live["tgt_bubble"] = _live["tgt_text"] = None

    # ── Azure Speech Translation 核心 ───────────────────────────
    def _on_recognizing(evt):
        """中间结果回调 — 流式更新字幕（边说边译）。"""
        result = evt.result
        if not result.text:
            return

        _clear_placeholder()

        if _sentence_timer["start"] == 0:
            _sentence_timer["start"] = time.time()
        _sentence_timer["last_recognizing"] = time.time()

        if hasattr(result, 'properties'):
            import azure.cognitiveservices.speech as speechsdk
            lang_key = speechsdk.PropertyId.SpeechServiceConnection_AutoDetectSourceLanguageResult
            detected = result.properties.get(lang_key, "")
            if detected and detected != state["detected_lang"]:
                state["detected_lang"] = detected
                detected_lang_text.value = LANG_SHORT.get(detected, detected)

        target_lang = target_lang_dropdown.value or "en"
        translation_text = ""
        if result.translations:
            translation_text = result.translations.get(target_lang, "")

        # 创建或更新 live 原文气泡
        if _live["src_text"] is None:
            src_text_ctrl = ft.Text(result.text, size=17, selectable=True, opacity=0.6, italic=True)
            src_bubble = ft.Container(
                content=src_text_ctrl,
                padding=ft.Padding.symmetric(horizontal=0, vertical=4),
                border=ft.Border(left=ft.BorderSide(2, "#0078D4")),
            )
            source_list.controls.append(src_bubble)
            _live["src_bubble"] = src_bubble
            _live["src_text"] = src_text_ctrl
        else:
            _live["src_text"].value = result.text

        # 创建或更新 live 译文气泡
        if translation_text:
            if _live["tgt_text"] is None:
                tgt_text_ctrl = ft.Text(translation_text, size=17, selectable=True, color="#00C853", opacity=0.6, italic=True)
                tgt_bubble = ft.Container(
                    content=tgt_text_ctrl,
                    padding=ft.Padding.symmetric(horizontal=0, vertical=4),
                    border=ft.Border(left=ft.BorderSide(2, "#00E676")),
                )
                target_list.controls.append(tgt_bubble)
                _live["tgt_bubble"] = tgt_bubble
                _live["tgt_text"] = tgt_text_ctrl
            else:
                _live["tgt_text"].value = translation_text

        _mark_dirty()

    def _on_recognized(evt):
        """最终结果回调 — 定稿字幕。"""
        result = evt.result
        import azure.cognitiveservices.speech as speechsdk

        if result.reason == speechsdk.ResultReason.TranslatedSpeech:
            if _sentence_timer.get("last_recognizing", 0) > 0:
                latency = (time.time() - _sentence_timer["last_recognizing"]) * 1000
                metrics["latency_ms"] = latency
                metrics["latency_history"].append(latency)
                latency_value.value = _format_ms(latency)
                _update_latency_display()
            _sentence_timer["start"] = 0
            _sentence_timer["last_recognizing"] = 0

            offset_s = result.offset / 10_000_000
            mm, ss = divmod(int(offset_s), 60)
            ts = f"{mm:02d}:{ss:02d}"

            source_text = result.text.strip()
            target_lang = target_lang_dropdown.value or "en"
            translation_text = ""
            if result.translations:
                translation_text = result.translations.get(target_lang, "")

            # 定稿 live 原文气泡（或新建）
            if source_text:
                if _live["src_text"]:
                    _finalize_live_source(source_text)
                else:
                    _clear_placeholder()
                    _add_source_bubble(ts, source_text)
                history["source"].append((ts, source_text))

            # 定稿 live 译文气泡（或新建）
            if translation_text.strip():
                if _live["tgt_text"]:
                    _finalize_live_target(translation_text.strip())
                else:
                    _add_target_bubble(ts, translation_text.strip())
                history["target"].append((ts, translation_text.strip()))
            else:
                # 无译文 — 清理未完成的 live 译文气泡
                if _live["tgt_bubble"] and _live["tgt_bubble"] in target_list.controls:
                    target_list.controls.remove(_live["tgt_bubble"])
                _live["tgt_bubble"] = _live["tgt_text"] = None

            sentence_count_value.value = str(len(history["source"]))

            lang_key = speechsdk.PropertyId.SpeechServiceConnection_AutoDetectSourceLanguageResult
            detected = result.properties.get(lang_key, "")
            if detected:
                state["detected_lang"] = detected
                detected_lang_text.value = LANG_SHORT.get(detected, detected)

            _mark_dirty()

            if state["tts_enabled"] and translation_text.strip():
                threading.Thread(
                    target=_speak_tts, args=(translation_text.strip(),), daemon=True
                ).start()

        elif result.reason == speechsdk.ResultReason.NoMatch:
            _sentence_timer["start"] = 0
            _cleanup_live_bubbles()
            _mark_dirty()

    def _on_canceled(evt):
        """取消/错误回调。"""
        import azure.cognitiveservices.speech as speechsdk
        details = evt.result.cancellation_details
        if details.reason == speechsdk.CancellationReason.Error:
            _add_source_bubble("--:--", f"{details.error_details[:80]}")
            _mark_dirty()
        _stop_translation()

    # ── TTS 播放（复用 synthesizer 降低延迟） ────────────────────
    def _get_or_create_synthesizer():
        """复用 TTS synthesizer，避免每句话重新建立连接。"""
        with state["synth_lock"]:
            if state["synthesizer"] is not None:
                return state["synthesizer"]
            try:
                import azure.cognitiveservices.speech as speechsdk
                cfg = load_config()
                speech_key = cfg.get("speech_api_key", "")
                region = cfg.get("region", "eastasia")
                if not speech_key:
                    return None
                target_lang = target_lang_dropdown.value or "en"
                gender = state["voice_gender"]
                lang_voices = TTS_VOICE_OPTIONS.get(target_lang, TTS_VOICE_OPTIONS["en"])
                gender_voices = lang_voices.get(gender, lang_voices["female"])
                valid_ids = [v[0] for v in gender_voices]
                selected = voice_dropdown.value
                voice = selected if selected in valid_ids else gender_voices[0][0]
                speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=region)
                speech_config.speech_synthesis_voice_name = voice
                audio_config = speechsdk.audio.AudioOutputConfig(use_default_speaker=True)
                synth = speechsdk.SpeechSynthesizer(
                    speech_config=speech_config, audio_config=audio_config
                )
                # Pre-connect 降低首字节延迟
                try:
                    conn = speechsdk.Connection.from_speech_synthesizer(synth)
                    conn.open(True)
                except Exception:
                    pass
                state["synthesizer"] = synth
                return synth
            except Exception:
                return None

    def _invalidate_synthesizer():
        """目标语言变化时重建 synthesizer。"""
        with state["synth_lock"]:
            state["synthesizer"] = None

    def _speak_tts(text: str):
        """使用 Azure Neural TTS 朗读译文（复用连接）。播放期间暂停识别，避免回声循环。"""
        if not state["running"]:
            return
        # 暂停识别器，避免麦克风拾取扬声器声音导致回声循环
        recognizer = state.get("recognizer")
        if recognizer:
            try:
                recognizer.stop_continuous_recognition()
            except Exception:
                pass
        try:
            synth = _get_or_create_synthesizer()
            if synth:
                future = synth.speak_text_async(text)
                state["current_tts_future"] = future
                future.get()
        except Exception:
            _invalidate_synthesizer()
        finally:
            state["current_tts_future"] = None
            # TTS 播完后等待短暂冷却，然后恢复识别
            import time as _time
            _time.sleep(0.3)
            if state["running"] and recognizer:
                try:
                    recognizer.start_continuous_recognition()
                except Exception:
                    pass

    # ── 开始/停止传译 ────────────────────────────────────────────
    def _start_translation():
        if state["running"]:
            return

        cfg = load_config()
        speech_key = cfg.get("speech_api_key", "")
        region = cfg.get("region", "eastasia")
        if not speech_key:
            return

        try:
            import azure.cognitiveservices.speech as speechsdk

            target_lang = target_lang_dropdown.value or "en"

            translation_config = speechsdk.translation.SpeechTranslationConfig(
                subscription=speech_key,
                region=region,
                target_languages=[target_lang],
            )
            translation_config.speech_recognition_language = "zh-CN"
            # 缩短分段静音超时，降低翻译延迟（默认 ~500-2000ms → 300ms）
            translation_config.set_property_by_name(
                "Speech_SegmentationSilenceTimeoutMs", SEGMENTATION_SILENCE_MS
            )

            auto_detect_config = speechsdk.AutoDetectSourceLanguageConfig(
                languages=SOURCE_LANGUAGES
            )

            audio_config = speechsdk.audio.AudioConfig(use_default_microphone=True)

            recognizer = speechsdk.translation.TranslationRecognizer(
                translation_config=translation_config,
                auto_detect_source_language_config=auto_detect_config,
                audio_config=audio_config,
            )

            recognizer.recognizing.connect(_on_recognizing)
            recognizer.recognized.connect(_on_recognized)
            recognizer.canceled.connect(_on_canceled)

            recognizer.start_continuous_recognition()

            state["recognizer"] = recognizer
            state["running"] = True

            # Pre-connect TTS synthesizer 降低首次播报延迟
            threading.Thread(target=_get_or_create_synthesizer, daemon=True).start()

            # UI 切换
            hero_btn_container.content = _build_stop_btn()
            hero_status.value = "● LIVE"
            hero_status.color = "#00E676"
            target_lang_dropdown.disabled = True
            _live["placeholder_cleared"] = False
            _flush_ui()

        except Exception as ex:
            _add_source_bubble("--:--", f"启动失败: {str(ex)[:80]}")
            _flush_ui()

    def _stop_translation():
        if not state["running"] and state["recognizer"] is None:
            return

        state["running"] = False
        recognizer = state.get("recognizer")
        if recognizer:
            try:
                recognizer.stop_continuous_recognition()
            except Exception:
                pass
            state["recognizer"] = None

        # 停止 TTS 播放
        with state["synth_lock"]:
            synth = state.get("synthesizer")
            if synth:
                try:
                    synth.stop_speaking_async()
                except Exception:
                    pass
            state["synthesizer"] = None
        state["current_tts_future"] = None

        _sentence_timer["start"] = 0
        _sentence_timer["last_recognizing"] = 0
        _cleanup_live_bubbles()
        hero_btn_container.content = _build_start_btn()
        hero_status.value = "已停止"
        hero_status.color = "#666666"
        target_lang_dropdown.disabled = False
        _mark_dirty()

    # ── 目标语言切换 ─────────────────────────────────────────────
    def _on_target_lang_changed(e):
        _invalidate_synthesizer()
        _update_voice_options()
        if state["running"]:
            _stop_translation()
            time.sleep(0.3)
            _start_translation()
        _flush_ui()

    target_lang_dropdown.on_select = _on_target_lang_changed

    # ── 清除记录 ─────────────────────────────────────────────────
    def _clear_history(e):
        source_list.controls.clear()
        target_list.controls.clear()
        source_list.controls.append(
            ft.Container(
                content=ft.Text("等待开始…", opacity=0.3, italic=True, size=16),
                alignment=ft.Alignment(0, 0),
                padding=40,
            )
        )
        target_list.controls.append(
            ft.Container(
                content=ft.Text("等待开始…", opacity=0.3, italic=True, size=16),
                alignment=ft.Alignment(0, 0),
                padding=40,
            )
        )
        history["source"].clear()
        history["target"].clear()
        metrics["latency_history"].clear()
        metrics["latency_ms"] = 0
        latency_value.value = "--"
        sentence_count_value.value = "0"
        detected_lang_text.value = "自动检测"
        _live["placeholder_cleared"] = False
        _update_latency_display()
        _flush_ui()

    # ── 导出记录 ─────────────────────────────────────────────────
    _export_picker = ft.FilePicker()
    page.services.append(_export_picker)

    async def _export_record(e):
        if not history["source"]:
            return
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"translation_{ts}.txt"
        lines = []
        lines.append("=" * 50)
        lines.append("同声传译记录")
        lines.append(f"导出时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        target_lang = target_lang_dropdown.value or "en"
        lines.append(f"目标语言: {TARGET_LANGUAGES.get(target_lang, target_lang)}")
        lines.append("=" * 50)
        lines.append("")
        lines.append("── 原文 ──────────────────────────────────")
        for ts_str, text in history["source"]:
            lines.append(f"[{ts_str}] {text}")
        lines.append("")
        lines.append("── 译文 ──────────────────────────────────")
        for ts_str, text in history["target"]:
            lines.append(f"[{ts_str}] {text}")
        lines.append("")
        if metrics["latency_history"]:
            avg = sum(metrics["latency_history"]) / len(metrics["latency_history"])
            lines.append(f"平均翻译延迟: {_format_ms(avg)}")
            lines.append(f"总翻译句数: {len(history['source'])}")
        content = "\n".join(lines)

        save_path = await _export_picker.save_file(
            dialog_title="导出传译记录",
            file_name=default_name,
            allowed_extensions=["txt"],
        )
        if save_path:
            from pathlib import Path
            Path(save_path).write_text(content, encoding="utf-8")
            page.show_dialog(ft.SnackBar(content=ft.Text(f"已导出: {Path(save_path).name}")))
        else:
            page.show_dialog(ft.SnackBar(content=ft.Text("已取消导出")))

    # ════════════════════════════════════════════════════════════
    #  新 UI 布局 — 三层结构：Hero按钮 → 主舞台字幕 → 底部信息条
    # ════════════════════════════════════════════════════════════

    # ── Hero 区：大按钮 + 状态 ────────────────────────────────────
    hero_status = ft.Text("已停止", size=12, color="#666666")

    def _build_start_btn():
        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.PLAY_ARROW_ROUNDED, color=ft.Colors.WHITE, size=20),
                    ft.Text("开始传译", size=15, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                ],
                spacing=6,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            bgcolor="#0078D4",
            border_radius=25,
            padding=ft.Padding.symmetric(horizontal=32, vertical=12),
            on_click=lambda e: _start_translation(),
            ink=True,
        )

    def _build_stop_btn():
        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.STOP_ROUNDED, color=ft.Colors.WHITE, size=20),
                    ft.Text("停止传译", size=15, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                ],
                spacing=6,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            bgcolor="#D32F2F",
            border_radius=25,
            padding=ft.Padding.symmetric(horizontal=32, vertical=12),
            on_click=lambda e: _stop_translation(),
            ink=True,
        )

    hero_btn_container = ft.Container(content=_build_start_btn())

    hero_bar = ft.Container(
        content=ft.Row(
            [
                hero_btn_container,
                ft.Container(width=16),
                ft.Column(
                    [
                        hero_status,
                        ft.Row([lang_pill, ft.Text("→", size=14, opacity=0.4), target_lang_dropdown],
                               spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    ],
                    spacing=4,
                ),
                ft.Container(expand=True),
                ft.Row(
                    [voice_gender_dropdown, voice_dropdown],
                    spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                tts_switch,
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=8,
        ),
        padding=ft.Padding.symmetric(horizontal=4, vertical=8),
    )

    # ── 主舞台：双栏字幕 ─────────────────────────────────────────
    # 初始占位
    source_list.controls.append(
        ft.Container(
            content=ft.Text("等待开始…", opacity=0.3, italic=True, size=16),
            alignment=ft.Alignment(0, 0),
            padding=40,
        )
    )
    target_list.controls.append(
        ft.Container(
            content=ft.Text("等待开始…", opacity=0.3, italic=True, size=16),
            alignment=ft.Alignment(0, 0),
            padding=40,
        )
    )

    source_panel = ft.Container(
        content=ft.Column(
            [
                ft.Container(
                    content=ft.Text("原文", size=12, opacity=0.5, weight=ft.FontWeight.BOLD),
                    padding=ft.Padding(left=16, top=10, right=0, bottom=0),
                ),
                ft.Container(
                    content=source_list,
                    expand=True,
                ),
            ],
            spacing=0,
            expand=True,
        ),
        bgcolor=ft.Colors.SURFACE_CONTAINER,
        border_radius=16,
        expand=True,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
    )

    target_panel = ft.Container(
        content=ft.Column(
            [
                ft.Container(
                    content=ft.Text("译文", size=12, opacity=0.5, weight=ft.FontWeight.BOLD),
                    padding=ft.Padding(left=16, top=10, right=0, bottom=0),
                ),
                ft.Container(
                    content=target_list,
                    expand=True,
                ),
            ],
            spacing=0,
            expand=True,
        ),
        bgcolor=ft.Colors.SURFACE_CONTAINER,
        border_radius=16,
        expand=True,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        border=ft.Border(left=ft.BorderSide(3, "#00C853")),
    )

    stage = ft.Row(
        [source_panel, target_panel],
        expand=True,
        spacing=12,
    )

    # ── 底部信息条：指标 + 工具按钮 ──────────────────────────────
    bottom_bar = ft.Container(
        content=ft.Row(
            [
                latency_pill,
                count_pill,
                latency_history_text,
                ft.Container(expand=True),
                ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, tooltip="清除记录",
                              on_click=_clear_history, icon_size=18),
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.DOWNLOAD, size=14, color=ft.Colors.ON_SURFACE),
                        ft.Text("导出", size=13, weight=ft.FontWeight.W_500, color=ft.Colors.ON_SURFACE),
                    ], spacing=6),
                    border_radius=8,
                    padding=ft.Padding.symmetric(horizontal=16, vertical=8),
                    on_click=_export_record, ink=True,
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
                ),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding.symmetric(horizontal=4, vertical=4),
    )

    # ── 最终布局 ─────────────────────────────────────────────────
    tab_content = ft.Container(
        content=ft.Column(
            [
                config_banner,
                hero_bar,
                stage,
                bottom_bar,
            ],
            spacing=8,
            expand=True,
        ),
        padding=ft.Padding(left=16, top=12, right=16, bottom=8),
        expand=True,
    )

    return tab_content, _refresh_config_banner
