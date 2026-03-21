# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 打包配置文件
#
# ===== 推荐方式（Flet 0.82+）=====
# 使用 flet pack 命令自动处理 Flet 运行时依赖：
#   flet pack main.py -n AzureAISpeechDemo \
#       --product-name "Azure AI Speech Demo" \
#       --product-version "2.0.0" --file-version "2.0.0.0" \
#       --hidden-import azure.cognitiveservices.speech \
#       --hidden-import openai \
#       --hidden-import sounddevice \
#       --hidden-import scipy.io.wavfile \
#       --hidden-import cryptography.fernet -y
# 产出位置：dist/AzureAISpeechDemo.exe
#
# ===== 备用方式（手动 PyInstaller）=====
# 如需自定义打包细节，可直接运行：
#   pyinstaller build.spec
# 注意：需手动包含 flet_desktop 运行时资源

import sys
from pathlib import Path

block_cipher = None

# Flet 需要把自己的 assets 和 core 资源一起打包
import flet
flet_dir = Path(flet.__file__).parent

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        # Flet 运行时资源
        (str(flet_dir / 'flet.exe'), '.') if sys.platform == 'win32' else
        (str(flet_dir / 'flet'), '.'),
    ],
    hiddenimports=[
        # Azure SDK
        'azure.cognitiveservices.speech',
        # OpenAI
        'openai',
        # 音频
        'sounddevice',
        'scipy.io.wavfile',
        # 加密
        'cryptography.fernet',
        'cryptography.hazmat.primitives.kdf.pbkdf2',
        # Flet 内部
        'flet.core',
        'flet.core.tabs',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'PIL',
        'cv2',
        'torch',
        'tensorflow',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='AzureAISpeechDemo',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # 隐藏命令行窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch='x86_64',   # 目标 Windows x86-64
    codesign_identity=None,
    entitlements_file=None,
    icon=None,              # 可替换为 .ico 文件路径
    version_file=None,
)
