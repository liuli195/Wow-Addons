"""验证真实检查器能区分正确输入和错误输入，不模拟游戏运行时。"""
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def invoke(check, folder, expected):
    result = subprocess.run([sys.executable, str(ROOT / "tools/check.py"), check,
                             "--source", str(folder)], cwd=ROOT,
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert (result.returncode == 0) == expected, result.stdout + result.stderr
    return result.stdout + result.stderr


def main():
    with tempfile.TemporaryDirectory(prefix="wow-checks-") as temporary:
        folder = Path(temporary)
        source = folder / "Core.lua"
        toc = folder / "Example.toc"
        toc.write_text("## Interface: 120100\nCore.lua\n", encoding="utf-8")
        source.write_text('C_Timer.After(0, function() print("ok") end)\n', encoding="utf-8")
        for check in ("toc", "luacheck", "luals"):
            invoke(check, folder, True)
        source.write_text('C_Timer.After("wrong", function() MissingWoWFunction() end)\n', encoding="utf-8")
        invoke("luacheck", folder, False)
        diagnostic = invoke("luals", folder, False)
        assert "param-type-mismatch" in diagnostic and "undefined-global" in diagnostic, diagnostic
        source.write_text("local =\n", encoding="utf-8")
        invoke("toc", folder, False)
        toc.write_text("## Interface: 120100\nMissing.lua\n", encoding="utf-8")
        invoke("toc", folder, False)
    print("PASS: 正确代码通过；错误接口名、参数、语法及缺失加载文件均被拦截")


if __name__ == "__main__":
    main()
