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
    parser.add_argument("--data-config", type=Path, help="受管任务的绝对机器配置路径")
    parser.add_argument("--reserve-bytes", type=int, help="每次任务载荷预留，不是长期容量限额")
    args = parser.parse_args()
    try:
        simulation_config = load_config()
        task_options = {"simulation_config": simulation_config}
        if args.data_config is not None:
            task_options["data_config"] = args.data_config
        if args.reserve_bytes is not None:
            task_options["reserve_bytes"] = args.reserve_bytes
        serve(args.output_root, host=args.host, port=args.port,
              task_options=task_options)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
