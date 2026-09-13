"""本地任务命令入口。"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "projects/sim2gse"))
from task import main

if __name__ == "__main__":
    raise SystemExit(main())
