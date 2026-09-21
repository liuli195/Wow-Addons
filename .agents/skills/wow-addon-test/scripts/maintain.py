"""维护入口：重生成用例与基线，并重算清单摘要。

**这是显式的维护动作，正常测试命令不会调用它。** 数据或基线要变，必须走这里：
先有独立理由，再重生成，再核对打印出来的差异。测试失败时**不得**自动重写期望或清单。

用法：
    python scripts/maintain.py --reason "<为什么改>" --dry-run
    python scripts/maintain.py --reason "<为什么改>"
"""
from __future__ import annotations
import argparse, gzip, hashlib, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
sys.path.insert(0, str(ROOT / "scripts"))

from wowtestlib import core  # noqa: E402
from reference import build_cases, generate  # noqa: E402


def _read_json(asset_name):
    return core.load_json(ASSETS / asset_name)


def _write_json_gz(asset_name, data):
    target = ASSETS / (asset_name + ".gz")
    target.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    with gzip.GzipFile(target, "wb", compresslevel=9, mtime=0) as handle:
        handle.write(text.encode("utf-8"))
    (ASSETS / asset_name).unlink(missing_ok=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _summary(old, new, label):
    if old == new:
        return f"{label}: 无变化"
    if isinstance(old, list) and isinstance(new, list):
        return f"{label}: 条数 {len(old)} → {len(new)}"
    return f"{label}: 有变化"


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--reason", required=True, help="变更理由：必须有独立依据，不能是「这样测试就通过」")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    before_cases = _read_json("data/cases.json")
    before_baselines = _read_json("data/baselines.json")
    before_profiles = _read_json("data/profiles.json")

    profiles, cases = build_cases.cases()
    baselines = generate.generate(cases, profiles)

    gaps = core.discriminating_gaps(cases, baselines)
    print(f"数据检查规则：无判别力处 {len(gaps)}")
    for gap in gaps[:5]:
        print("  ", json.dumps(gap, ensure_ascii=False))
    if gaps:
        print("存在无判别力的用例，拒绝写入。请先把这些场景的数据改成可区分。")
        return 1

    print(_summary(before_profiles, profiles, "profiles"))
    print(_summary(before_cases, cases, "cases"))
    print(_summary(before_baselines, baselines, "baselines"))
    print(f"理由：{args.reason}")
    if args.dry_run:
        print("dry-run：未写入")
        return 0

    digests = {
        "data/profiles.json": _write_json_gz("data/profiles.json", profiles),
        "data/cases.json": _write_json_gz("data/cases.json", cases),
        "data/baselines.json": _write_json_gz("data/baselines.json", baselines),
    }
    # 清单保持明文：它是索引而不是大体积载荷，明文便于人工核对。
    # 这里重算**清单自己列出的每一个**文件——数据、参照、运行时都算，
    # 否则改一次运行时摘要就对不上，而清单又会显得"没人负责更新"。
    manifest = json.loads((ASSETS / "data/manifest.json").read_text(encoding="utf-8"))
    for name in sorted(manifest["sha256"]):
        digest = digests.get(name) or hashlib.sha256(
            core.read_asset_bytes(ASSETS / name)).hexdigest()
        previous = manifest["sha256"].get(name)
        if previous != digest:
            print(f"清单更新 {name}: {str(previous)[:12]}… → {digest[:12]}…")
        manifest["sha256"][name] = digest
    (ASSETS / "data/manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("已写入；请核对差异后再提交。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
