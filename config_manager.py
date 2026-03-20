"""
配置管理模块：加载/保存 Azure 服务配置，敏感字段（API Key）使用 Fernet 对称加密。
配置文件：项目目录下 config.json
加密密钥：~/.azure_ai_demo/.encryption_key（仅当前用户可读）
"""

import json
import os
import platform
from pathlib import Path

from cryptography.fernet import Fernet

from app_paths import get_app_dir

APP_DIR = get_app_dir()
CONFIG_FILE = APP_DIR / "config.json"
KEY_DIR = Path.home() / ".azure_ai_demo"
KEY_FILE = KEY_DIR / ".encryption_key"

SENSITIVE_FIELDS = {"speech_api_key", "openai_api_key"}

DEFAULT_CONFIG = {
    "speech_api_key": "",
    "openai_endpoint": "",
    "openai_api_key": "",
    "openai_deployment": "gpt-4o",
    "region": "eastasia",
}


def _get_or_create_key() -> bytes:
    KEY_DIR.mkdir(parents=True, exist_ok=True)
    if KEY_FILE.exists():
        return KEY_FILE.read_bytes()
    key = Fernet.generate_key()
    KEY_FILE.write_bytes(key)
    if platform.system() != "Windows":
        os.chmod(KEY_FILE, 0o600)
    return key


def _get_fernet() -> Fernet:
    return Fernet(_get_or_create_key())


def save_config(config: dict) -> None:
    """将配置保存到 config.json，敏感字段加密。"""
    f = _get_fernet()
    data = {}
    for k, v in config.items():
        if k in SENSITIVE_FIELDS and v:
            data[k] = f.encrypt(v.encode()).decode()
        else:
            data[k] = v
    CONFIG_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def load_config() -> dict:
    """从 config.json 加载配置，敏感字段自动解密。"""
    if not CONFIG_FILE.exists():
        return dict(DEFAULT_CONFIG)
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        f = _get_fernet()
        for k in SENSITIVE_FIELDS:
            if k in data and data[k]:
                try:
                    data[k] = f.decrypt(data[k].encode()).decode()
                except Exception:
                    data[k] = ""
        result = dict(DEFAULT_CONFIG)
        result.update(data)
        return result
    except Exception:
        return dict(DEFAULT_CONFIG)
