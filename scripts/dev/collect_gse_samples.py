"""下载公开 GSE 帖子中的导入串到 Git 忽略的本机目录，并记录覆盖元数据。"""

import argparse
import html
import json
from pathlib import Path
import re
import sys
from urllib.request import Request, urlopen


TOPICS = {
    "sol-unholy-12-1": "https://wowlazymacros.com/t/64010.json",
    "flip-unholy-archive": "https://gseunited.com/t/669.json",
    "mob-unholy": "https://gseunited.com/t/270.json",
    "mob-blood": "https://gseunited.com/t/273.json",
    "mob-guardian": "https://gseunited.com/t/271.json",
    "mob-shadow": "https://gseunited.com/t/277.json",
    "oak-discipline": "https://gseunited.com/t/486.json",
    "demon-hunter-examples": "https://gseunited.com/t/29.json",
    "shadow-priest-examples": "https://gseunited.com/t/768.json",
    "survival-hunter": "https://gseunited.com/t/701.json",
    "beast-hunter": "https://gseunited.com/t/700.json",
    "violent-benediction-if": "https://wowlazymacros.com/t/64007.json",
    "karens-unholy": "https://wowlazymacros.com/t/62253.json",
    "kims-unholy": "https://wowlazymacros.com/t/62086.json",
}
PATTERN = re.compile(r"!GSE3!(?:\+)?[A-Za-z0-9+/=]+")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "projects" / "sim2gse"))
from gse_import import decode_import  # noqa: E402


def features(value, result):
    if isinstance(value, dict):
        if isinstance(value.get("Type"), str):
            result.add(value["Type"])
        for item in value.values():
            features(item, result)
    elif isinstance(value, list):
        for item in value:
            features(item, result)


def describe(value, slug, url, index, *, cached=False):
    decoded = decode_import(value)
    kinds = set()
    features(decoded["payload"], kinds)
    names = list(decoded["sequences"])
    sequences = list(decoded["sequences"].values())
    return dict(source=url, slug=slug, index=index, file=f"{slug}-{index:02}.txt",
                sha256=decoded["sha256"],
                names=names, versions=[len(seq.get("Versions", [])) for seq in sequences],
                gse_versions=[seq.get("MetaData", {}).get("GSEVersion") for seq in sequences],
                syntax=sorted(kinds), format=decoded["envelope"],
                **({"cached": True} if cached else {}))


def collect(directory, slugs=None):
    directory.mkdir(parents=True, exist_ok=True)
    manifest = []
    selected = TOPICS if slugs is None else {slug: TOPICS[slug] for slug in slugs}
    for slug, url in selected.items():
        try:
            with urlopen(Request(url, headers={"User-Agent": "Sim2GSE corpus collector"}), timeout=25) as response:
                topic = json.load(response)
            source = html.unescape(topic["post_stream"]["posts"][0]["cooked"])
            found = list(dict.fromkeys(PATTERN.findall(source)))
            for index, value in enumerate(found, 1):
                if value.startswith("!GSE3!+"):
                    manifest.append(dict(source=url, slug=slug, index=index, format="protected", status="not_decoded"))
                    continue
                key = f"{slug}-{index:02}"
                (directory / f"{key}.txt").write_text(value, encoding="ascii")
                manifest.append(describe(value, slug, url, index))
        except Exception as error:
            cached = sorted(directory.glob(f"{slug}-*.txt"))
            for path in cached:
                index = int(path.stem.rsplit("-", 1)[1])
                manifest.append(describe(path.read_text(encoding="ascii"), slug, url, index, cached=True))
            manifest.append(dict(source=url, slug=slug, error=f"{type(error).__name__}: {error}",
                                 cached_samples=len(cached)))
    (directory / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--topic", dest="topics", action="append", choices=TOPICS,
                        help="只收集指定主题；可重复传入多个主题")
    args = parser.parse_args()
    for row in collect(args.directory, args.topics):
        print(json.dumps(row, ensure_ascii=False))
