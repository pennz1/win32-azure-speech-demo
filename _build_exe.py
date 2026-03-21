"""PyInstaller 构建脚本 — 由 build_installer.ps1 调用。

用法: python _build_exe.py [--icon app.ico] [--version 2.0.0322.11]
"""

import argparse
import os
import shutil
import sys

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--icon", default="")
    parser.add_argument("--version", default="2.0.0322.11")
    parser.add_argument("--name", default="AzureAISpeechDemo")
    args = parser.parse_args()

    pyi_args = [
        "main.py", "--noconfirm", "--noconsole", "--onefile",
        "--name", args.name,
    ]
    if args.icon and os.path.isfile(args.icon):
        pyi_args += ["--icon", args.icon]
        # 将图标文件打包进 exe，供运行时设置窗口图标
        pyi_args += ["--add-data", args.icon + os.pathsep + "."]

    pyi_args += [
        "--hidden-import", "azure.cognitiveservices.speech",
        "--hidden-import", "openai",
        "--hidden-import", "sounddevice",
        "--hidden-import", "scipy.io.wavfile",
        "--hidden-import", "cryptography.fernet",
        "--hidden-import", "azure.ai.voicelive",
        "--hidden-import", "azure.ai.voicelive.aio",
        "--hidden-import", "azure.ai.voicelive.models",
        "--hidden-import", "numpy",
        "--hidden-import", "azure.core.credentials",
        "--hidden-import", "aiohttp",
        "--exclude-module", "tkinter",
        "--exclude-module", "matplotlib",
        "--exclude-module", "PIL",
        "--exclude-module", "cv2",
        "--exclude-module", "torch",
        "--exclude-module", "tensorflow",
        "--exclude-module", "pytest",
    ]

    import flet_cli.__pyinstaller.config as hook_config
    from flet_cli.__pyinstaller.utils import copy_flet_bin

    hook_config.temp_bin_dir = copy_flet_bin()
    if hook_config.temp_bin_dir:
        fletd = os.path.join(hook_config.temp_bin_dir, "fletd.exe")
        if os.path.exists(fletd):
            os.remove(fletd)
        from flet_cli.__pyinstaller.win_utils import update_flet_view_version_info
        exe_path = os.path.join(hook_config.temp_bin_dir, "flet", "flet.exe")
        if os.path.exists(exe_path):
            vi = update_flet_view_version_info(
                exe_path=exe_path,
                product_name="Azure AI Speech Demo",
                file_description="Azure AI Speech Demo Application",
                product_version=args.version,
                file_version=args.version,
                company_name=None,
                copyright=None,
            )
            pyi_args.extend(["--version-file", vi])

    import PyInstaller.__main__
    PyInstaller.__main__.run(pyi_args)

    if hook_config.temp_bin_dir and os.path.exists(hook_config.temp_bin_dir):
        shutil.rmtree(hook_config.temp_bin_dir, ignore_errors=True)

    print("EXE_BUILD_DONE")


if __name__ == "__main__":
    main()
