"""把已人工审核的爆发定义发布到明确指定的既有共享中心。"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'projects/sim2gse'))
import result_store
from burst import publish


def main():
    parser = argparse.ArgumentParser(description='显式发布已审核的专精爆发定义')
    parser.add_argument('definition', type=Path, help='已审核定义文件')
    parser.add_argument('--project', type=Path, required=True, help='已接入的共享数据中心所属项目')
    args = parser.parse_args()
    try:
        result_store.bind_project(args.project)
        definition = publish(json.loads(args.definition.read_text(encoding='utf-8')))
        print(json.dumps(dict(spec_id=definition['spec_id'], version=definition['version'],
                              definition_id=definition['definition_id']), ensure_ascii=False))
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
