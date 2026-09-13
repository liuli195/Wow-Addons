"""使用本次启动的本地服务运行浏览器检查，并在退出时关闭服务。"""
from pathlib import Path
import os
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]


def main():
    test = (ROOT / sys.argv[1]).resolve(strict=True)
    if test.parent != ROOT / 'tests/gear-planner' or test.suffix != '.cjs':
        raise ValueError('仅支持装备规划器浏览器检查')
    env = os.environ.copy()
    bundled = Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'
    if not env.get('NODE_PATH') and bundled.is_dir():
        env['NODE_PATH'] = str(bundled)
    subprocess.run(['node', '-e', "require('playwright')"], cwd=test.parent, env=env, check=True)
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1', 8765)) == 0:
            raise RuntimeError('8765 端口已有服务；请关闭后重跑，避免使用未知服务')
    logs = ROOT / '.local/tests'
    logs.mkdir(parents=True, exist_ok=True)
    with (logs / (test.stem + '-server.log')).open('wb') as log:
        server = subprocess.Popen([sys.executable, str(ROOT / 'projects/gear-planner/server.py')],
                                  cwd=ROOT, stdout=log, stderr=log,
                                  creationflags=subprocess.CREATE_NO_WINDOW)
        browser = None
        try:
            deadline = time.monotonic() + 60
            while True:
                if server.poll() is not None:
                    raise RuntimeError('测试服务启动失败，见 .local/tests/ 服务日志')
                try:
                    with urllib.request.urlopen('http://127.0.0.1:8765/', timeout=1):
                        break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError('测试服务启动超时')
                    time.sleep(0.2)
            browser = subprocess.Popen(['node', str(test), *sys.argv[2:]], cwd=ROOT,
                                       env=env,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
            return browser.wait(timeout=180)
        finally:
            if browser is not None:
                if browser.poll() is None:
                    subprocess.run(['taskkill', '/PID', str(browser.pid), '/T', '/F'],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                browser.wait()
            if server.poll() is None:
                subprocess.run(['taskkill', '/PID', str(server.pid), '/T', '/F'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            server.wait()


if __name__ == '__main__':
    raise SystemExit(main())
