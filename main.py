"""
Azure AI 语音演示台 — 主应用壳层（Phase 0）
Flet Material Design 3 · 暗色主题 · Azure 蓝 #0078D4
"""

import threading
import urllib.error
import urllib.request

import flet as ft

# ── Flet 0.28 + Python 3.9 兼容性修复 ──────────────────────────
# Tab.before_update 中 isinstance(x, IconValue) 在 Python 3.9 下会报错
# 因为 IconValue = Union[str, Icons, CupertinoIcons] 是 subscripted generic
import sys
if sys.version_info < (3, 10):
    from flet.core import tabs as _tabs_mod
    _original_before_update = _tabs_mod.Tab.before_update

    def _patched_before_update(self):
        try:
            _original_before_update(self)
        except TypeError:
            # 跳过 isinstance 检查，直接用 str 处理 icon
            super(_tabs_mod.Tab, self).before_update()
            self._set_attr_json("iconMargin", self._Tab__icon_margin)
            icon = self._Tab__icon
            if icon is not None:
                self._set_enum_attr("icon", icon, _tabs_mod.IconEnums)

    _tabs_mod.Tab.before_update = _patched_before_update
# ────────────────────────────────────────────────────────────────

from config_manager import load_config, save_config
from transcription_tab import build_transcription_tab

VERSION = "v2.0"


def main(page: ft.Page):
    # ── 主题 & 窗口 ──────────────────────────────────────────────
    page.title = "Azure AI 语音演示台"
    page.theme = ft.Theme(color_scheme_seed="#0078D4")
    page.theme_mode = ft.ThemeMode.DARK
    page.window.width = 1200
    page.window.height = 800
    page.padding = 0

    # ── 加载配置 ─────────────────────────────────────────────────
    config = load_config()

    # ── 状态栏组件 ───────────────────────────────────────────────
    status_icon = ft.Icon(ft.Icons.CIRCLE, color=ft.Colors.GREY, size=12)
    status_text = ft.Text("未连接", size=12)
    region_text = ft.Text(f"区域: {config.get('region', 'eastasia')}", size=12)
    version_text = ft.Text(f"版本: {VERSION}", size=12)

    # ── Azure 连接检测 ───────────────────────────────────────────
    def check_azure_connection():
        """后台线程检测 Azure Speech 服务连通性。"""

        def _check():
            key = config.get("speech_api_key", "")
            region = config.get("region", "eastasia")

            if not key:
                status_icon.color = ft.Colors.GREY
                status_text.value = "未配置"
                page.update()
                return

            status_icon.color = ft.Colors.YELLOW
            status_text.value = "检测中..."
            page.update()

            try:
                url = f"https://{region}.api.cognitive.microsoft.com/sts/v1.0/issueToken"
                req = urllib.request.Request(url, data=b"", method="POST")
                req.add_header("Ocp-Apim-Subscription-Key", key)
                req.add_header("Content-Length", "0")
                urllib.request.urlopen(req, timeout=10)
                status_icon.color = ft.Colors.GREEN
                status_text.value = "Azure 连接正常"
            except urllib.error.HTTPError as he:
                if he.code == 401:
                    status_icon.color = ft.Colors.YELLOW
                    status_text.value = "API Key 无效"
                else:
                    # 其他 HTTP 错误也说明端点可达
                    status_icon.color = ft.Colors.GREEN
                    status_text.value = "Azure 连接正常"
            except Exception:
                status_icon.color = ft.Colors.RED
                status_text.value = "连接失败"
            page.update()

        threading.Thread(target=_check, daemon=True).start()

    # ── 设置弹窗 ─────────────────────────────────────────────────
    speech_key_field = ft.TextField(
        label="Azure Speech API Key",
        value=config.get("speech_api_key", ""),
        password=True,
        can_reveal_password=True,
    )
    openai_endpoint_field = ft.TextField(
        label="Azure OpenAI Endpoint",
        value=config.get("openai_endpoint", ""),
        hint_text="https://<resource>.openai.azure.com/",
    )
    openai_key_field = ft.TextField(
        label="Azure OpenAI API Key",
        value=config.get("openai_api_key", ""),
        password=True,
        can_reveal_password=True,
    )
    openai_deployment_field = ft.TextField(
        label="GPT 部署名称 (Deployment Name)",
        value=config.get("openai_deployment", "gpt-4o"),
        hint_text="例: gpt-4o 或你的自定义部署名",
    )
    region_field = ft.Dropdown(
        label="部署区域 (Region)",
        value=config.get("region", "eastasia"),
        options=[
            ft.dropdown.Option("eastasia", "East Asia (东亚)"),
            ft.dropdown.Option("southeastasia", "Southeast Asia (东南亚)"),
            ft.dropdown.Option("eastus", "East US (美国东部)"),
            ft.dropdown.Option("eastus2", "East US 2 (美国东部2)"),
            ft.dropdown.Option("westus2", "West US 2 (美国西部2)"),
            ft.dropdown.Option("westeurope", "West Europe (西欧)"),
            ft.dropdown.Option("northeurope", "North Europe (北欧)"),
        ],
    )

    _on_settings_saved_callbacks = []

    def _close_settings(e):
        page.close(settings_dialog)

    def _save_settings(e):
        new_config = {
            "speech_api_key": speech_key_field.value.strip(),
            "openai_endpoint": openai_endpoint_field.value.strip(),
            "openai_api_key": openai_key_field.value.strip(),
            "openai_deployment": openai_deployment_field.value.strip() or "gpt-4o",
            "region": region_field.value,
        }
        save_config(new_config)
        config.update(new_config)
        region_text.value = f"区域: {new_config['region']}"
        page.close(settings_dialog)
        check_azure_connection()
        # 通知各 Tab 页刷新配置状态 Banner
        for _cb in _on_settings_saved_callbacks:
            _cb()
        page.snack_bar = ft.SnackBar(content=ft.Text("设置已保存 ✅"))
        page.snack_bar.open = True
        page.update()

    settings_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("⚙️ Azure 服务设置"), 
        content=ft.Container(
            content=ft.Column(
                [
                    ft.Text("Azure Speech 服务", weight=ft.FontWeight.BOLD),
                    speech_key_field,
                    ft.Text("💡 区域选择即可，无需填写 Endpoint", size=11, opacity=0.5),
                    ft.Divider(),
                    ft.Text("Azure OpenAI 服务", weight=ft.FontWeight.BOLD),
                    openai_endpoint_field,
                    openai_key_field,
                    openai_deployment_field,
                    ft.Divider(),
                    region_field,
                ],
                spacing=12,
                scroll=ft.ScrollMode.AUTO,
            ),
            width=500,
            height=480,
        ),
        actions=[
            ft.TextButton("取消", on_click=_close_settings),
            ft.ElevatedButton("保存", on_click=_save_settings),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    def _open_settings(e):
        speech_key_field.value = config.get("speech_api_key", "")
        openai_endpoint_field.value = config.get("openai_endpoint", "")
        openai_key_field.value = config.get("openai_api_key", "")
        openai_deployment_field.value = config.get("openai_deployment", "gpt-4o")
        region_field.value = config.get("region", "eastasia")
        page.open(settings_dialog)

    # Banner 里的「前往设置」按鈕通过 pubsub 触发打开设置弹窗
    def _on_open_settings(message):
        if message == "open_settings":
            _open_settings(None)

    page.pubsub.subscribe(_on_open_settings)

    # ── Tab 占位内容 ─────────────────────────────────────────────
    def _placeholder(icon, title, phase_label):
        return ft.Container(
            content=ft.Column(
                [
                    ft.Icon(icon, size=64, opacity=0.3),
                    ft.Text(title, size=24, weight=ft.FontWeight.BOLD),
                    ft.Text(phase_label, size=14, opacity=0.5),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=16,
            ),
            alignment=ft.alignment.center,
            expand=True,
        )

    # ── Tabs 导航 ────────────────────────────────────────────────
    _transcription_content, _refresh_transcription_banner = build_transcription_tab(page)
    _on_settings_saved_callbacks.append(_refresh_transcription_banner)

    tabs = ft.Tabs(
        selected_index=0,
        animation_duration=300,
        tabs=[
            ft.Tab(
                text="📝 会议转写 & 总结",
                content=_transcription_content,
            ),
            ft.Tab(
                text="🤖 实时对话 GPT-4o",
                content=_placeholder(
                    ft.Icons.SMART_TOY,
                    "GPT-4o Realtime 实时语音对话",
                    "Phase 2 — 即将开发",
                ),
            ),
            ft.Tab(
                text="🌐 同声传译",
                content=_placeholder(
                    ft.Icons.TRANSLATE,
                    "同声传译 Live Interpreter",
                    "Phase 3 — 即将开发",
                ),
            ),
        ],
        expand=True,
    )

    # ── 顶部标题栏 ──────────────────────────────────────────────
    title_bar = ft.Container(
        content=ft.Row(
            [
                ft.Row(
                    [
                        ft.Icon(ft.Icons.RECORD_VOICE_OVER, color="#0078D4", size=28),
                        ft.Text(
                            "Azure AI 语音演示台",
                            size=20,
                            weight=ft.FontWeight.BOLD,
                        ),
                    ],
                    spacing=12,
                ),
                ft.IconButton(
                    icon=ft.Icons.SETTINGS,
                    tooltip="设置",
                    on_click=_open_settings,
                    icon_size=24,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        ),
        padding=ft.padding.symmetric(horizontal=20, vertical=12),
    )

    # ── 底部状态栏 ──────────────────────────────────────────────
    status_bar = ft.Container(
        content=ft.Row(
            [
                ft.Row([status_icon, status_text], spacing=6),
                region_text,
                version_text,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        ),
        padding=ft.padding.symmetric(horizontal=20, vertical=8),
        bgcolor="#1e1e2e",
    )

    # ── 页面布局 ─────────────────────────────────────────────────
    page.add(
        ft.Column(
            [
                title_bar,
                ft.Divider(height=1),
                tabs,
                ft.Divider(height=1),
                status_bar,
            ],
            expand=True,
            spacing=0,
        )
    )

    # 启动时自动检测连接
    check_azure_connection()


ft.app(target=main)
