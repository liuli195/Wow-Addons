"""保留真实 LuaLS 与 luacheck 拒绝错误接口和参数的最小反例。"""
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def invoke(check, folder):
    result = subprocess.run([sys.executable, str(ROOT / "scripts/dev/check.py"), check,
                             "--source", str(folder)], cwd=ROOT,
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert result.returncode != 0, result.stdout + result.stderr
    return result.stdout + result.stderr


def main():
    with tempfile.TemporaryDirectory(prefix="wow-checks-") as temporary:
        folder = Path(temporary)
        source = folder / "Core.lua"
        source.write_text('C_Timer.After("wrong", function() MissingWoWFunction() end)\n', encoding="utf-8")
        diagnostic = invoke("luacheck", folder)
        assert "accessing undefined variable 'MissingWoWFunction'" in diagnostic, diagnostic
        diagnostic = invoke("luals", folder)
        assert "param-type-mismatch" in diagnostic and "undefined-global" in diagnostic, diagnostic

    print("PASS: 真实 LuaLS 拦截错误接口名和参数；真实 luacheck 拦截未知全局")


if __name__ == "__main__":
    main()
