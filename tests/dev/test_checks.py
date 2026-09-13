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
    workflow = (ROOT / ".github/workflows/verify.yml").read_text(encoding="utf-8")
    assert "https://github.com/simulationcraft/simc.git" in setup
    assert "simc-source.zip" not in setup
    assert "projects/sim2gse/requirements.txt" in setup
    assert "mingw-w64-x86_64-make" in workflow
    spec = importlib.util.spec_from_file_location(
        "sim2gse_build", ROOT / "scripts/dev/sim2gse/build.py"
    )
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    prototype_spec = importlib.util.spec_from_file_location(
        "sim2gse_prototype_build", ROOT / "scripts/dev/sim2gse/prototype-engine-build.py"
    )
    prototype_build = importlib.util.module_from_spec(prototype_spec)
    prototype_spec.loader.exec_module(prototype_build)
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
        lf = repository / "lf.patch"
        crlf = repository / "crlf.patch"
        lf.write_bytes(b"one\ntwo\n")
        crlf.write_bytes(b"one\r\ntwo\r\n")
        assert build.patch_digest(lf) == build.patch_digest(crlf)
        assert prototype_build.patch_bytes(lf) == prototype_build.patch_bytes(crlf)
        (repository / "source.cpp").write_text("int changed() {}\n", encoding="utf-8")
        crlf.write_bytes(subprocess.check_output(["git", "diff"], cwd=repository).replace(b"\n", b"\r\n"))
        subprocess.run(["git", "checkout", "--", "source.cpp"], cwd=repository, check=True)
        prototype_build.apply_patch(repository, crlf)
        assert (repository / "source.cpp").read_text(encoding="utf-8") == "int changed() {}\n"
        prototype_build.apply_patch(repository, crlf, reverse=True)
        assert (repository / "source.cpp").read_text(encoding="utf-8") == "int main() {}\n"
        try:
            build.verify_upstream(repository, {"upstream_commit": commit, "upstream_tree": "0" * 40})
        except ValueError:
            pass
        else:
            raise AssertionError("错误源码树必须被拒绝")
        source = repository / "expanded"
        source.mkdir()
        (source / "source.cpp").write_text("original\n", encoding="utf-8")
        prototype_build.verify_source(source, [Path("source.cpp")])
        (source / "source.cpp").write_text("changed\n", encoding="utf-8")
        try:
            prototype_build.verify_source(source, [Path("source.cpp")])
        except AssertionError:
            pass
        else:
            raise AssertionError("修改后的原型源码必须被拒绝")

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
