"""验证真实检查器能区分正确输入和错误输入，不模拟游戏运行时。"""
from pathlib import Path
import importlib.util
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def invoke(check, folder, expected):
    result = subprocess.run([sys.executable, str(ROOT / "scripts/dev/check.py"), check,
                             "--source", str(folder)], cwd=ROOT,
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert (result.returncode == 0) == expected, result.stdout + result.stderr
    return result.stdout + result.stderr


def main():
    setup = (ROOT / "scripts/dev/setup.ps1").read_text(encoding="utf-8")
    assert "https://github.com/simulationcraft/simc.git" in setup
    assert "simc-source.zip" not in setup
    spec = importlib.util.spec_from_file_location(
        "sim2gse_build", ROOT / "scripts/dev/sim2gse/build.py"
    )
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    with tempfile.TemporaryDirectory(prefix="sim2gse-source-") as temporary:
        repository = Path(temporary)
        subprocess.run(["git", "init", "--quiet"], cwd=repository, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repository, check=True)
        subprocess.run(["git", "config", "user.name", "test"], cwd=repository, check=True)
        (repository / "source.cpp").write_text("int main() {}\n", encoding="utf-8")
        subprocess.run(["git", "add", "source.cpp"], cwd=repository, check=True)
        subprocess.run(["git", "commit", "--quiet", "-m", "source"], cwd=repository, check=True)
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository, text=True).strip()
        tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=repository, text=True).strip()
        build.verify_upstream(repository, {"upstream_commit": commit, "upstream_tree": tree})
        try:
            build.verify_upstream(repository, {"upstream_commit": commit, "upstream_tree": "0" * 40})
        except ValueError:
            pass
        else:
            raise AssertionError("错误源码树必须被拒绝")

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

    output = ROOT / ".local/tests/build-assets"
    shutil.rmtree(output, ignore_errors=True)
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/media/build_assets.py"), "--output-root", str(output)],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (output / "addons/EUI_FacetedPortrait/Media/CrystalHexagonalBorder.tga").is_file()
    print("PASS: 正确代码通过；错误接口名、参数、语法及缺失加载文件均被拦截")


if __name__ == "__main__":
    main()
