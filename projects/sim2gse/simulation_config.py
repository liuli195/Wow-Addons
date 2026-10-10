"""读取并校验 Sim2GSE（角色级按键序列优化器）的本地模拟目标配置。"""

from __future__ import annotations

from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = ROOT / ".local" / "sim2gse" / "config.toml"
DEFAULT_CONFIG = {
    "target_count": 1,
    "enable_omnium_talents": True,
}
_CONFIG_KEYS = frozenset(DEFAULT_CONFIG)


def config_for(values: dict | None = None) -> dict:
    """返回补齐默认值并完成校验的实际模拟配置。"""
    if values is None:
        values = {}
    if not isinstance(values, dict):
        raise ValueError("模拟配置必须是对象")
    unknown = set(values) - _CONFIG_KEYS
    if unknown:
        raise ValueError("未知模拟配置: " + ", ".join(sorted(unknown)))
    config = dict(DEFAULT_CONFIG)
    config.update(values)
    if type(config["target_count"]) is not int or config["target_count"] <= 0:
        raise ValueError("模拟目标数必须是正整数")
    if type(config["enable_omnium_talents"]) is not bool:
        raise ValueError("万奥宝典开关必须是布尔值")
    return config


def _load_document(path=None):
    path = DEFAULT_PATH if path is None else Path(path)
    if not path.exists():
        return {}
    try:
        document = tomllib.loads(path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise ValueError(f"本地模拟配置无效: {path}: {error}") from error
    if not isinstance(document, dict):
        raise ValueError("本地模拟配置必须是 TOML 对象")
    unknown = set(document) - {"simulation", "training"}
    if unknown:
        raise ValueError("未知模拟配置区域: " + ", ".join(sorted(unknown)))
    return document


def load_config(path: str | Path | None = None) -> dict:
    """读取模拟区域；独立训练区域不改变普通模拟。"""
    section = _load_document(path).get("simulation", {})
    if not isinstance(section, dict):
        raise ValueError("[simulation] 必须是 TOML 表")
    return config_for(dict(section))


def load_training_config(path: str | Path | None = None) -> dict:
    """每次人工启动读取一次，只开放既有候选评分并发。"""
    section = _load_document(path).get("training", {})
    if not isinstance(section, dict) or set(section) - {"max_processes"}:
        raise ValueError("[training] 只接受 max_processes（评分并发）")
    from search import config_for as search_config_for
    return {"max_processes": search_config_for(section, training=True)["max_processes"]}


def engine_options(config: dict | None = None) -> list[str]:
    """把实际配置转换成两个独立引擎共用的 SimC（战斗模拟器）参数。"""
    config = config_for(config)
    return [f"desired_targets={config['target_count']}"]


__all__ = ["DEFAULT_CONFIG", "DEFAULT_PATH", "config_for", "engine_options", "load_config", "load_training_config"]
