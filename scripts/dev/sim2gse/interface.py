"""启动 Sim2GSE（角色级按键序列优化器）本地三步界面。"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "projects" / "sim2gse"))

from interface import serve  # noqa: E402
from simulation_config import load_config  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="启动本机 Sim2GSE 三步界面")
    parser.add_argument("--output-root", type=Path, default=ROOT / ".local/sim2gse/ui-tasks",
                        help="任务输出根目录")
    parser.add_argument("--host", default="127.0.0.1", choices=("127.0.0.1", "localhost"),
                        help="只允许本机地址")
    parser.add_argument("--port", type=int, default=8780, help="本地端口，0 表示自动选择")
    args = parser.parse_args()
    try:
        simulation_config = load_config()
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    serve(args.output_root, host=args.host, port=args.port,
          task_options={"simulation_config": simulation_config})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
