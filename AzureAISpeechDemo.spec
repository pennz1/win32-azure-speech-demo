# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
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
    version='C:\\Users\\Penn\\AppData\\Local\\Temp\\358e0335-db14-4462-b26f-c7227bed0de8',
    icon=['app.ico'],
)
