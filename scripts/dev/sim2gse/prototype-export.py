"""Task 7 throwaway export probe. Uses Python stdlib + cached upstream Lua 5.1.

Run: .venv/Scripts/python.exe scripts/dev/sim2gse/prototype-export.py
Candidate strings use a zlib wrapper hypothesis, NOT verified client encoding.
"""
import base64
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import zlib

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / ".tools/sim2gse-research/gse-f225d4c"
OUT = ROOT / ".local/sim2gse/export-prototype"
LUA = ROOT / ".tools/lua-5.1.5/src/lua.exe"


def cbor(value):
    # ponytail: fixture-only types; production must use a maintained CBOR library.
    def head(major, n):
        if n < 24:
            return bytes([major * 32 + n])
        for code, width in ((24, 1), (25, 2), (26, 4)):
            if n < 1 << (8 * width):
                return bytes([major * 32 + code]) + n.to_bytes(width, "big")
        raise ValueError("fixture integer/length out of range")
    if type(value) is bool:
        return b"\xf5" if value else b"\xf4"
    if type(value) is int:
        return head(0, value) if value >= 0 else head(1, -1 - value)
    if isinstance(value, str):
        raw = value.encode("utf-8")
        return head(3, len(raw)) + raw
    if isinstance(value, list):
        return head(4, len(value)) + b"".join(map(cbor, value))
    if isinstance(value, dict):
        return head(5, len(value)) + b"".join(cbor(k) + cbor(v) for k, v in value.items())
    raise TypeError("unsupported fixture CBOR type")


def lua_literal(value):
    if isinstance(value, str):
        return '"' + ''.join(f"\\{b:03d}" for b in value.encode("utf-8")) + '"'
    if type(value) is bool:
        return str(value).lower()
    if type(value) is int:
        return str(value)
    items = enumerate(value, 1) if isinstance(value, list) else value.items()
    return "{" + ",".join(f"[{lua_literal(k)}]={lua_literal(v)}" for k, v in items) + "}"


def spell(number):
    return {"Type": "Action", "type": "spell", "spell": number}


def macro(text):
    if len(text.encode("utf-8")) > 255:
        raise ValueError("fixture macro exceeds conservative 255 UTF-8 byte cap")
    return {"Type": "Action", "type": "macro", "macro": text}


def run_lua(payload, expected, mode):
    (OUT / "input.cbor").write_bytes(cbor(payload))
    expected = dict(expected, payload=payload)
    (OUT / "expected.lua").write_text("return " + lua_literal(expected), encoding="utf-8")
    result = subprocess.run(
        [str(LUA), str(Path(__file__).with_suffix(".lua")), str(SOURCE),
         str(OUT / "input.cbor"), str(OUT / "expected.lua"), mode],
        cwd=SOURCE, capture_output=True, timeout=20,
    )
    output = result.stdout.decode("utf-8", errors="replace")
    if result.returncode:
        raise RuntimeError(output + result.stderr.decode("utf-8", errors="replace"))
    return output


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    prior = json.loads((ROOT / ".local/sim2gse/gse-source-review.json").read_text(encoding="utf-8-sig"))
    for entry in prior["files"]:
        assert hashlib.sha256((SOURCE / entry["path"]).read_bytes()).hexdigest() == entry["sha256"], entry["path"]
    # RFC 8949 vectors plus the upstream numeric-map-key fixture.
    vectors = [(0, "00"), (24, "1818"), (1000, "1903e8"), (-100, "3863"),
               ("IETF", "6449455446"), ([1, 2, 3], "83010203"),
               ({1: "x", "Type": "Action"}, "a2016178645479706566416374696f6e"),
               ("水", "63e6b0b4")]
    for value, encoded in vectors:
        assert cbor(value).hex() == encoded
    s1, s2 = {"type": "spell", "spell": 85948}, {"type": "spell", "spell": 55090}
    body = "/use 13\n/use 14\n/cast 脓疮打击"
    reverse = "/use 14\n/use 13\n/cast 脓疮打击"
    cases = [
        ("single", "一个技能", [spell(85948)], [s1]),
        ("ordered", "两步顺序", [spell(85948), spell(55090)], [s1, s2]),
        ("repeated", "保留重复技能", [spell(85948), spell(85948), spell(55090)], [s1, s1, s2]),
        ("multi", "同块多命令", [macro(body)], [{"type": "macro", "macrotext": body}]),
        ("reverse", "饰品反向顺序", [macro(reverse)], [{"type": "macro", "macrotext": reverse}]),
        ("loop", "带数字键的顺序循环", [{1: spell(85948), 2: spell(55090), "Type": "Loop", "Repeat": 2}], [s1, s2, s1, s2]),
    ]
    rows = []
    for key, title, actions, steps in cases:
        for wrapper in ("pair", "collection"):
            name = "S2G_TEST_" + key.upper()
            help_text = "离线结构样例：" + title + "。未经过游戏导入或伤害优化。"
            sequence = {"MetaData": {"Name": name, "SpecID": 252, "GSEVersion": 3332, "Help": help_text},
                        "Default": 1, "Versions": [{"Actions": copy.deepcopy(actions), "InbuiltVariables": {}}]}
            payload = [name, sequence] if wrapper == "pair" else {"type": "COLLECTION", "payload": {"Sequences": {name: sequence}}}
            expected = {"name": name, "help": help_text, "steps": steps}
            checksum_output = run_lua(payload, expected, "checksum")
            sequence["MetaData"]["Checksum"] = next(line.split("\t")[1] for line in checksum_output.splitlines() if line.startswith("CHECKSUM\t"))
            raw = cbor(payload)
            candidate = "!GSE3!" + base64.b64encode(zlib.compress(raw)).decode("ascii")
            recovered = zlib.decompress(base64.b64decode(candidate[6:], validate=True))
            assert recovered == raw
            trace = run_lua(payload, expected, "compile")
            assert "PASS\t" in trace
            stem = key + "-" + wrapper
            (OUT / (stem + ".cbor")).write_bytes(raw)
            (OUT / (stem + ".candidate.txt")).write_text(candidate, encoding="ascii")
            (OUT / (stem + ".trace.txt")).write_text(trace, encoding="utf-8")
            rows.append({"sample": stem, "title": title, "wrapper": wrapper, "steps": steps,
                         "characters": len(candidate), "checksum": sequence["MetaData"]["Checksum"],
                         "decoded_import_route": "passed_with_client_fixtures", "compile": "passed_with_client_fixtures"})
    try:
        macro("水" * 86)
    except ValueError:
        pass
    else:
        raise AssertionError("macro length guard failed")
    sources = {str(p.relative_to(SOURCE)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
               for p in SOURCE.rglob("*.lua")}
    evidence = {"upstream_commit": "f225d4c947d168c63451ef7c567d7063c38cc239", "sources": sources,
                "encoding_vectors": len(vectors), "samples": rows, "client_import": "not_run",
                "native_encoding": "unverified_zlib_wrapper_hypothesis", "combat_simulation": "not_run"}
    (OUT / "evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    data = json.dumps(rows, ensure_ascii=False).replace("<", "\\u003c")
    page = r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>最小序列编译样例</title>
<style>body{font:17px system-ui;max-width:850px;margin:48px auto;padding:0 20px;color:#183040;background:#f6f8fa}button,select{font:inherit;padding:8px;margin:6px}pre{background:white;padding:20px;white-space:pre-wrap;border:1px solid #ccd8df}aside{color:#765716}</style>
<h1>最小序列的导入与编译</h1><p>临时原型：查看固定上游源码实际编译的步骤，检查顺序、重复技能及同块命令。</p>
<aside>这些是已运行的离线结果。演示按钮只浏览编译步骤，不模拟按键成功、伤害、队列或游戏导入。</aside>
<p><label>样例 <select id="cases"></select></label><button id="reset">回到开头</button><button id="next">查看下一步</button></p><p id="state"></p><pre id="steps"></pre>
<details><summary>查看该样例的完整记录</summary><pre id="record"></pre></details><script>
const rows=DATA; let index=0; const select=document.getElementById('cases');
rows.forEach((r,i)=>{const o=document.createElement('option');o.value=i;o.textContent=r.title+' · '+(r.wrapper==='pair'?'单序列外壳':'集合外壳');select.append(o)});
function render(){const r=rows[select.value];document.getElementById('state').textContent='共 '+r.steps.length+' 步；当前查看第 '+(index+1)+' 步。';document.getElementById('steps').textContent=r.steps.map((s,i)=>(i===index?'→ ':'  ')+(i+1)+'. '+(s.macrotext||({85948:'脓疮打击',55090:'天灾打击'}[s.spell]||s.item))).join('\n');document.getElementById('record').textContent=JSON.stringify(r,null,2)}
select.onchange=()=>{index=0;render()};document.getElementById('reset').onclick=()=>{index=0;render()};document.getElementById('next').onclick=()=>{index=(index+1)%rows[select.value].steps.length;render()};render();
</script></html>'''.replace("DATA", data)
    # The page only browses captured outputs; it never replaces the Lua compiler.
    (OUT / "walkthrough.html").write_text(page, encoding="utf-8")
    print(f"PASS: {len(rows)} source-compiled samples, {len(vectors)} encoding vectors; client import NOT RUN")
    print(OUT / "walkthrough.html")


if __name__ == "__main__":
    main()
