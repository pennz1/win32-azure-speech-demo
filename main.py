"""
Azure AI 语音演示台 — 主应用壳层
Flet Material Design 3 · 暗色主题 · Azure 蓝 #0078D4
"""

import ctypes
import os
import sys
import threading
import urllib.error
import urllib.request

# ── DLL 依赖检查（打包 exe 运行时可能缺少 VC++ 运行库）──────────
def _check_dll_dependencies():
    """检查关键 DLL 是否存在，缺失时弹出提示并退出。"""
    required_dlls = [
        ("MSVCP140.dll", "Microsoft Visual C++ Redistributable"),
        ("VCRUNTIME140.dll", "Microsoft Visual C++ Redistributable"),
        ("VCRUNTIME140_1.dll", "Microsoft Visual C++ Redistributable (x64)"),
    ]
    missing = []
    for dll_name, desc in required_dlls:
        try:
            ctypes.WinDLL(dll_name)
        except OSError:
            missing.append((dll_name, desc))

    if missing:
        dll_list = "\n".join(f"  - {name} ({desc})" for name, desc in missing)
        msg = (
            "Azure AI 语音演示台 无法启动\n\n"
            f"缺少以下系统组件：\n{dll_list}\n\n"
            "请安装 Microsoft Visual C++ Redistributable (x64)：\n"
            "https://aka.ms/vs/17/release/vc_redist.x64.exe\n\n"
            "安装完成后重新运行本程序。"
        )
        ctypes.windll.user32.MessageBoxW(0, msg, "缺少运行库", 0x10)
        sys.exit(1)

if sys.platform == "win32":
    _check_dll_dependencies()

import flet as ft

from config_manager import load_config, save_config
from transcription_tab import build_transcription_tab
from realtime_tab import build_realtime_tab
from interpreter_tab import build_interpreter_tab

VERSION = "v2.0.0322.14"


def main(page: ft.Page):
    # ── 主题 & 窗口 ──────────────────────────────────────────────
    page.title = "Azure AI 语音演示台"

    # 设置窗口图标
    import os as _os
    if getattr(sys, "frozen", False):
        _icon_path = _os.path.join(sys._MEIPASS, "app.ico")
    else:
        _icon_path = _os.path.join(_os.path.dirname(__file__), "app.ico")
    if _os.path.isfile(_icon_path):
        page.window.icon = _icon_path
    page.fonts = {
        "MicrosoftYaHei": "C:/Windows/Fonts/msyh.ttc",
    }
    page.theme = ft.Theme(
        color_scheme_seed="#0078D4",
        font_family="MicrosoftYaHei",
        color_scheme=ft.ColorScheme(
            surface="#f5f6fa",
            surface_container_lowest="#ffffff",
            surface_container_low="#f0f1f5",
            surface_container="#eaebf0",
            surface_container_high="#e4e5ea",
            surface_container_highest="#dfe0e5",
            on_surface="#1a1a1a",
            on_surface_variant="#444444",
            outline="#c4c7cc",
            outline_variant="#dde0e4",
            primary="#005EA6",
            on_primary="#ffffff",
            primary_container="#d4e8ff",
            on_primary_container="#001d36",
            secondary_container="#e0e2ec",
            on_secondary_container="#1a1c24",
        ),
    )
    page.dark_theme = ft.Theme(
        color_scheme_seed="#0078D4",
        font_family="MicrosoftYaHei",
    )

    # 加载主题偏好
    _saved_theme = load_config().get("theme_mode", "system")
    _theme_map = {"dark": ft.ThemeMode.DARK, "light": ft.ThemeMode.LIGHT, "system": ft.ThemeMode.SYSTEM}
    page.theme_mode = _theme_map.get(_saved_theme, ft.ThemeMode.SYSTEM)

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
    _KEY_MASK = "•" * 16  # API Key 占位符，不显示明文

    def _mask_key(key: str) -> str:
        """API Key 已保存则显示混淆占位符，不允许复制明文。"""
        if key:
            return _KEY_MASK
        return ""

    speech_key_field = ft.TextField(
        label="Azure Speech API Key",
        value=_mask_key(config.get("speech_api_key", "")),
        password=True,
        can_reveal_password=False,
        hint_text="输入新 Key 替换，留空保持不变",
    )
    openai_endpoint_field = ft.TextField(
        label="Azure OpenAI Endpoint",
        value=config.get("openai_endpoint", ""),
        hint_text="https://<resource>.openai.azure.com/",
    )
    openai_key_field = ft.TextField(
        label="Azure OpenAI API Key",
        value=_mask_key(config.get("openai_api_key", "")),
        password=True,
        can_reveal_password=False,
        hint_text="输入新 Key 替换，留空保持不变",
    )
    openai_deployment_field = ft.TextField(
        label="GPT 部署名称 (Deployment Name)",
        value=config.get("openai_deployment", "gpt-4o"),
        hint_text="例: gpt-4o 或你的自定义部署名",
    )
    voicelive_endpoint_field = ft.TextField(
        label="Voice Live Endpoint",
        value=config.get("voicelive_endpoint", ""),
        hint_text="https://<resource>.services.ai.azure.com（自动去除项目路径）",
    )
    voicelive_key_field = ft.TextField(
        label="Voice Live API Key",
        value=_mask_key(config.get("voicelive_api_key", "")),
        password=True,
        can_reveal_password=False,
        hint_text="输入新 Key 替换，留空保持不变",
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
        page.pop_dialog()

    def _save_settings(e):
        # API Key: 只有用户输入了新值才替换，占位符或空值保持原值
        def _resolve_key(field_value: str, config_key: str) -> str:
            v = field_value.strip()
            if v == _KEY_MASK or v == "":
                return config.get(config_key, "")  # 保持原值
            return v  # 用户输入了新 Key

        new_config = {
            "speech_api_key": _resolve_key(speech_key_field.value, "speech_api_key"),
            "openai_endpoint": openai_endpoint_field.value.strip(),
            "openai_api_key": _resolve_key(openai_key_field.value, "openai_api_key"),
            "openai_deployment": openai_deployment_field.value.strip() or "gpt-4o",
            "voicelive_endpoint": voicelive_endpoint_field.value.strip(),
            "voicelive_api_key": _resolve_key(voicelive_key_field.value, "voicelive_api_key"),
            "region": region_field.value,
        }
        save_config(new_config)
        config.update(new_config)
        region_text.value = f"区域: {new_config['region']}"
        page.pop_dialog()
        check_azure_connection()
        # 通知各 Tab 页刷新配置状态 Banner
        for _cb in _on_settings_saved_callbacks:
            _cb()
        page.show_dialog(ft.SnackBar(content=ft.Text("设置已保存")))
        page.update()

    settings_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Azure 服务设置"), 
        content=ft.Container(
            content=ft.Column(
                [
                    ft.Text("Azure Speech 服务", weight=ft.FontWeight.BOLD),
                    speech_key_field,
                    region_field,
                    ft.Text("区域选择即可，无需填写 Endpoint", size=11, opacity=0.5),
                    ft.Divider(),
                    ft.Text("Azure OpenAI 服务", weight=ft.FontWeight.BOLD),
                    openai_endpoint_field,
                    openai_key_field,
                    openai_deployment_field,
                    ft.Divider(),
                    ft.Text("Azure Voice Live", weight=ft.FontWeight.BOLD),
                    voicelive_endpoint_field,
                    voicelive_key_field,
                    ft.Text("在 Azure Portal → Foundry 资源 → Keys and Endpoint 获取", size=11, opacity=0.5),
                ],
                spacing=12,
                scroll=ft.ScrollMode.AUTO,
            ),
            width=500,
            height=560,
        ),
        actions=[
            ft.TextButton("取消", on_click=_close_settings),
            ft.Container(
                content=ft.Text("保存", size=13, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                bgcolor="#0078D4", border_radius=8,
                padding=ft.Padding.symmetric(horizontal=24, vertical=10),
                on_click=_save_settings, ink=True,
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    def _open_settings(e):
        speech_key_field.value = _mask_key(config.get("speech_api_key", ""))
        openai_endpoint_field.value = config.get("openai_endpoint", "")
        openai_key_field.value = _mask_key(config.get("openai_api_key", ""))
        openai_deployment_field.value = config.get("openai_deployment", "gpt-4o")
        voicelive_endpoint_field.value = config.get("voicelive_endpoint", "")
        voicelive_key_field.value = _mask_key(config.get("voicelive_api_key", ""))
        region_field.value = config.get("region", "eastasia")
        page.show_dialog(settings_dialog)

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
            alignment=ft.Alignment(0, 0),
            expand=True,
        )

    # ── Tabs 导航 ────────────────────────────────────────────────
    _transcription_content, _refresh_transcription_banner = build_transcription_tab(page)
    _on_settings_saved_callbacks.append(_refresh_transcription_banner)

    _realtime_content, _refresh_realtime_banner = build_realtime_tab(page)
    _on_settings_saved_callbacks.append(_refresh_realtime_banner)

    _interpreter_content, _refresh_interpreter_banner = build_interpreter_tab(page)
    _on_settings_saved_callbacks.append(_refresh_interpreter_banner)

    tabs = ft.Tabs(
        content=ft.Column(
            [
                ft.TabBar(
                    tabs=[
                        ft.Tab(label="会议转写 & 总结"),
                        ft.Tab(label="实时对话 VoiceLive"),
                        ft.Tab(label="同声传译"),
                    ],
                ),
                ft.TabBarView(
                    controls=[
                        _transcription_content,
                        _realtime_content,
                        _interpreter_content,
                    ],
                    expand=True,
                ),
            ],
            expand=True,
            spacing=0,
        ),
        length=3,
        selected_index=0,
        animation_duration=300,
        expand=True,
    )

    # ── 主题切换图标 (深色/浅色/跟随系统) ──────────────────
    _theme_modes = [
        ("dark", ft.Icons.DARK_MODE, "深色模式"),
        ("light", ft.Icons.LIGHT_MODE, "浅色模式"),
        ("system", ft.Icons.CONTRAST, "跟随系统"),
    ]

    def _get_current_theme_idx():
        mode_str = {ft.ThemeMode.DARK: "dark", ft.ThemeMode.LIGHT: "light", ft.ThemeMode.SYSTEM: "system"}
        cur = mode_str.get(page.theme_mode, "dark")
        for i, (m, _, _) in enumerate(_theme_modes):
            if m == cur:
                return i
        return 0

    _cur_theme_idx = _get_current_theme_idx()
    theme_btn = ft.IconButton(
        icon=_theme_modes[_cur_theme_idx][1],
        on_click=lambda e: _cycle_theme(e),
        tooltip=_theme_modes[_cur_theme_idx][2],
        icon_size=20,
    )

    def _cycle_theme(e):
        idx = (_get_current_theme_idx() + 1) % len(_theme_modes)
        mode_key, icon, tip = _theme_modes[idx]
        page.theme_mode = _theme_map[mode_key]
        theme_btn.icon = icon
        theme_btn.tooltip = tip
        # 更新状态栏背景（浅色模式→适配）
        _update_status_bar_bg()
        page.update()
        # 持久化
        cfg = load_config()
        cfg["theme_mode"] = mode_key
        save_config(cfg)

    def _update_status_bar_bg():
        status_bar.bgcolor = ft.Colors.SURFACE_CONTAINER

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
                ft.Row(
                    [
                        theme_btn,
                        ft.IconButton(
                            icon=ft.Icons.SETTINGS,
                            tooltip="设置",
                            on_click=_open_settings,
                            icon_size=24,
                        ),
                    ],
                    spacing=0,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        ),
        padding=ft.Padding.symmetric(horizontal=20, vertical=12),
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
        padding=ft.Padding.symmetric(horizontal=20, vertical=8),
        bgcolor=ft.Colors.SURFACE_CONTAINER,
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
    _update_status_bar_bg()


ft.run(main)
