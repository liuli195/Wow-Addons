"""读取并校验 Sim2GSE（角色级按键序列优化器）的本地模拟目标配置。"""

from __future__ import annotations

import math
from pathlib import Path
import re
import tomllib


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = ROOT / ".local" / "sim2gse" / "config.toml"
DEFAULT_CONFIG = {
    "target_name": "Damage_Dummy",
    "target_level": 90,
    "armor_coefficient": 4531.03,
    "target_count": 1,
    # 由票据 02 使用；此处先纳入同一份实际生效配置，避免启动时拒绝方案中的合法字段。
    "enable_omnium_talents": False,
}
_CONFIG_KEYS = frozenset(DEFAULT_CONFIG)
_TARGET_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


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
    if (not isinstance(config["target_name"], str)
            or not _TARGET_NAME.fullmatch(config["target_name"])):
        raise ValueError("模拟目标名格式错误")
    if type(config["target_level"]) is not int or config["target_level"] <= 0:
        raise ValueError("模拟目标等级必须是正整数")
    armor = config["armor_coefficient"]
    if type(armor) not in (int, float) or not math.isfinite(armor) or armor <= 0:
        raise ValueError("目标护甲系数必须是有限正数")
    if type(config["target_count"]) is not int or config["target_count"] <= 0:
        raise ValueError("模拟目标数必须是正整数")
    if type(config["enable_omnium_talents"]) is not bool:
        raise ValueError("万奥宝典开关必须是布尔值")
    config["armor_coefficient"] = float(armor)
    return config


def load_config(path: str | Path | None = None) -> dict:
    """从本地 TOML 文件读取配置；文件不存在时返回约定默认值。"""
    path = DEFAULT_PATH if path is None else Path(path)
    if not path.exists():
        return config_for()
    try:
        document = tomllib.loads(path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise ValueError(f"本地模拟配置无效: {path}: {error}") from error
    if not isinstance(document, dict):
        raise ValueError("本地模拟配置必须是 TOML 对象")
    unknown = set(document) - {"simulation"}
    if unknown:
        raise ValueError("未知模拟配置区域: " + ", ".join(sorted(unknown)))
    section = document.get("simulation", {})
    if not isinstance(section, dict):
        raise ValueError("[simulation] 必须是 TOML 表")
    return config_for(dict(section))


def engine_options(config: dict | None = None) -> list[str]:
    """把实际配置转换成两个独立引擎共用的 SimC（战斗模拟器）参数。"""
    config = config_for(config)
    return [
        f"enemy={config['target_name']}",
        f"level={config['target_level']}",
        f"armor_coefficient={config['armor_coefficient']}",
        f"desired_targets={config['target_count']}",
    ]


__all__ = ["DEFAULT_CONFIG", "DEFAULT_PATH", "config_for", "engine_options", "load_config"]
