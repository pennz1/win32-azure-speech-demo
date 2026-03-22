# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

# ── 原生 DLL 手动包含 ──────────────────────────────────────────────────────
# 问题: Azure Speech SDK 和 sounddevice 通过 ctypes.LoadLibrary 加载 DLL，
#       路径基于 os.path.dirname(__file__)。PyInstaller onefile 模式下如果
#       不显式列出这些 DLL，它们不会被打包到 _MEI* 临时目录中。
_sp = Path(SPECPATH) / '.venv' / 'Lib' / 'site-packages'

# Azure Speech SDK DLLs → 必须放在 azure/cognitiveservices/speech/ 子目录
# 以匹配 interop.py 中的 os.path.join(os.path.dirname(__file__), library_name)
_speech_dir = _sp / 'azure' / 'cognitiveservices' / 'speech'
_speech_bins = [(str(f), 'azure/cognitiveservices/speech')
                for f in _speech_dir.glob('*.dll')]

# sounddevice portaudio DLLs
_sd_dir = _sp / '_sounddevice_data' / 'portaudio-binaries'
_sd_bins = [(str(f), '_sounddevice_data/portaudio-binaries')
             for f in _sd_dir.glob('*.dll')]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=_speech_bins + _sd_bins,
    datas=[('app.ico', '.')],
    hiddenimports=['azure.cognitiveservices.speech', 'openai', 'sounddevice', 'scipy.io.wavfile', 'cryptography.fernet', 'azure.ai.voicelive', 'azure.ai.voicelive.aio', 'azure.ai.voicelive.models', 'numpy', 'azure.core.credentials', 'aiohttp'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'PIL', 'cv2', 'torch', 'tensorflow', 'pytest'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='AzureAISpeechDemo',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['app.ico'],
)
