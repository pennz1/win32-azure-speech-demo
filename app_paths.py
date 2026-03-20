"""
app_paths.py — 统一路径解析工具

规则：
  - PyInstaller 打包后（sys.frozen=True）：所有数据目录都在 .exe 所在目录下
  - 开发模式（普通 python 运行）：数据目录在 main.py/config_manager.py 所在的项目根目录下

目录结构（运行时自动创建）：
  <app_dir>/
    config.json          # 加密配置
    recordings/          # 麦克风录音
    exports/             # 纪要导出
"""

import sys
from pathlib import Path


def get_app_dir() -> Path:
    """返回应用根目录：打包后为 .exe 所在目录，开发时为项目根目录。"""
    if getattr(sys, "frozen", False):
        # PyInstaller 打包后 sys.executable = <app_dir>/app.exe
        return Path(sys.executable).parent
    # 开发模式：相对于本文件（app_paths.py 在项目根）
    return Path(__file__).parent


def get_data_dir(subdir: str = "") -> Path:
    """返回数据子目录路径，并确保目录存在。"""
    base = get_app_dir()
    path = base / subdir if subdir else base
    path.mkdir(parents=True, exist_ok=True)
    return path


APP_DIR = get_app_dir()
