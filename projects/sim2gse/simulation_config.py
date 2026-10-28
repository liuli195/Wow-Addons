"""读取并校验 Sim2GSE（角色级按键序列优化器）的本地模拟目标配置。"""

from __future__ import annotations

from pathlib import Path
import tomllib
from typing import BinaryIO, TextIO


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = ROOT / ".local" / "sim2gse" / "config.toml"
DEFAULT_CONFIG = {
    "target_count": 1,
    "scene": None,
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
    if config["scene"] not in (None, "single_target", "aoe"):
        raise ValueError("模拟场景必须为single_target或aoe；未指定时不猜测目标数阈值")
    if type(config["enable_omnium_talents"]) is not bool:
        raise ValueError("万奥宝典开关必须是布尔值")
    return config


def _load_document(path=None):
    stream = path if hasattr(path, 'read') else None
    if stream is None:
        path = DEFAULT_PATH if path is None else Path(path)
        if not path.exists():
            return {}
    try:
        content = stream.read() if stream is not None else path.read_bytes()
        document = tomllib.loads(content.decode("utf-8") if isinstance(content, bytes) else content)
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise ValueError(f"本地模拟配置无效: {path}: {error}") from error
    if not isinstance(document, dict):
        raise ValueError("本地模拟配置必须是 TOML 对象")
    unknown = set(document) - {"simulation", "training", "search"}
    if unknown:
        raise ValueError("未知模拟配置区域: " + ", ".join(sorted(unknown)))
    return document


def load_config(path: str | Path | BinaryIO | TextIO | None = None) -> dict:
    """读取模拟区域；独立训练区域不改变普通模拟。"""
    section = _load_document(path).get("simulation", {})
    if not isinstance(section, dict):
        raise ValueError("[simulation] 必须是 TOML 表")
    return config_for(dict(section))


TRAINING_DEFAULTS = dict(max_processes=5, max_trainings=4, coarse_iterations=32,
    retest_batches=3, retest_iterations=128, stagnation_generations=2, top_k=8,
    tournament_size=3, crossover_probability=0.8, mutation_probability=0.8)


def load_training_config(path: str | Path | BinaryIO | TextIO | None = None, *, max_processes=None, max_trainings=None) -> dict:
    """启动读取的GA白名单；普通搜索的资源和采样上限不变。"""
    import math
    section = _load_document(path).get("training", {})
    if not isinstance(section, dict) or set(section) - set(TRAINING_DEFAULTS):
        raise ValueError("[training] 包含未知GA配置")
    values = dict(TRAINING_DEFAULTS, **section)
    values.update({key: value for key, value in dict(max_processes=max_processes,
        max_trainings=max_trainings).items() if value is not None})
    for key in set(values) - {'crossover_probability', 'mutation_probability'}:
        if type(values[key]) is not int or values[key] < 1:
            raise ValueError('训练配置必须为正整数: ' + key)
    if values['max_processes'] > 16 or values['max_trainings'] > 10:
        raise ValueError('训练并发超出既有范围')
    if values['max_processes'] * values['max_trainings'] > 20:
        raise ValueError('训练并发与评分并发乘积不得超过20')
    if values['top_k'] < 4:
        raise ValueError('训练top_k必须至少为4')
    for key in ('crossover_probability', 'mutation_probability'):
        value = values[key]
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError('训练概率必须为0至1的有限数: ' + key)
    return values


REMOVED_SEARCH_SETTINGS = ('rule_initialization_enabled', 'adaptive_selector_enabled', 'rule_diagnostics_policy')
RETIRED_SEARCH_SETTINGS = ('total_budget_seconds', 'search_budget_seconds', 'candidate_limit',
    'round_candidate_limit', 'no_improvement_rounds', 'batch_targets', 'validation_batches',
    'final_batches', 'final_iterations', 'trace_search', 'scenarios')


def reject_removed_search_settings(values):
    removed = set(REMOVED_SEARCH_SETTINGS) & set(values)
    if removed:
        raise ValueError('搜索能力及开关已移除，请删除旧配置: ' + ', '.join(sorted(removed)))
    retired = set(RETIRED_SEARCH_SETTINGS) & set(values)
    if retired:
        raise ValueError('旧正式搜索参数已退役，请删除旧配置: ' + ', '.join(sorted(retired)))


FORMAL_ALGORITHM_DEFAULTS = dict(max_processes=5, coarse_iterations=32,
    retest_batches=3, retest_iterations=128, stagnation_generations=8, top_k=8,
    tournament_size=3, crossover_probability=0.8, mutation_probability=0.8)
SEARCH_RUNTIME_DEFAULTS = dict(iterations=128, random_seed=20260912, search_timeline=False,
    diagnostic_logging=False, diagnostics='summary', search_observability='full',
    input_interval_ms=300, reset_events=())
SEARCH_DEFAULTS = dict(FORMAL_ALGORITHM_DEFAULTS, **SEARCH_RUNTIME_DEFAULTS)


def _search_values(path, overrides):
    section = _load_document(path).get('search', {})
    if not isinstance(section, dict):
        raise ValueError('[search] 必须是 TOML 表')
    reject_removed_search_settings(section)
    reject_removed_search_settings(overrides)
    if (set(section) | set(overrides)) - set(SEARCH_DEFAULTS):
        raise ValueError('[search] 包含未知配置')
    return dict(section, **{key: value for key, value in overrides.items() if value is not None})


def load_search_config(path=None, *, default_input_interval_ms=300, **overrides):
    """运行参数优先，false有效；default_input_interval_ms=None表示所属入口尚未选内置间隔，缺失时不补齐。"""
    from search import config_for
    if 'input_interval_ms' in overrides and overrides['input_interval_ms'] is None:
        raise ValueError('按键间隔必须为 50 至 2000 毫秒的整数')
    values = _search_values(path, overrides)
    config = config_for({'input_interval_ms': 300 if default_input_interval_ms is None else default_input_interval_ms, **values},
                        _defer_interval_alignment=default_input_interval_ms is None)
    if default_input_interval_ms is None and 'input_interval_ms' not in values:
        config.pop('input_interval_ms')
    config.update({key: values[key] for key in ('diagnostics', 'search_observability') if key in values})
    return config


def load_training_search_config(path=None, **overrides):
    """训练文件仅沿用旧曲线开关，其余运行值只接受训练显式调用。"""
    from search import config_for, TRAINING_SEARCH_DEFAULTS
    section = _search_values(path, {})
    reject_removed_search_settings(overrides)
    unsupported = set(overrides) - {'search_timeline', 'diagnostic_logging', 'diagnostics',
                                    'search_observability', 'input_interval_ms', 'reset_events'}
    if unsupported:
        raise ValueError('预训练不支持搜索参数，请使用专用训练配置: ' + ', '.join(sorted(unsupported)))
    values = {key: value for key, value in section.items() if key == 'search_timeline'}
    values.update({key: value for key, value in overrides.items() if value is not None})
    projected = {key: value for key, value in values.items() if key in TRAINING_SEARCH_DEFAULTS}
    config = config_for(projected, training=True)
    config.update({key: projected[key] for key in ('diagnostics', 'search_observability') if key in projected})
    return config


def _removed_search_argument(value):
    import argparse
    raise argparse.ArgumentTypeError('搜索能力及开关已移除，请删除旧参数')


def add_search_arguments(parser):
    """公开曲线开关，退役参数只保留明确错误而不再提供能力。"""
    import argparse
    parser.add_argument('--search-timeline', action=argparse.BooleanOptionalAction, default=None)
    for name in REMOVED_SEARCH_SETTINGS:
        flag = name.replace('_', '-')
        parser.add_argument('--' + flag, '--no-' + flag, nargs='?', const='removed',
            type=_removed_search_argument, default=argparse.SUPPRESS, help=argparse.SUPPRESS)


def engine_options(config: dict | None = None) -> list[str]:
    """把实际配置转换成两个独立引擎共用的 SimC（战斗模拟器）参数。"""
    config = config_for(config)
    return [f"desired_targets={config['target_count']}"]


__all__ = ["DEFAULT_CONFIG", "DEFAULT_PATH", "config_for", "engine_options", "load_config", "load_training_config"]
