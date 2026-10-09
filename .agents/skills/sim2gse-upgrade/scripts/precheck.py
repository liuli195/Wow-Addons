"""只读核对指定仓库的构建、标准角色及既有共享中心。"""
import argparse
import json
from pathlib import Path
import sys


def prepare(project, data_project):
    project = project.resolve()
    if not project.is_dir():
        raise ValueError('项目目录不存在: ' + str(project))
    if not (project / 'projects/sim2gse/seed_training.py').is_file():
        raise ValueError('指定项目不是本仓库的模拟器')
    if not data_project.is_dir() or not (data_project / 'data').is_dir():
        raise ValueError('共享数据项目或数据目录不存在')
    sys.path.insert(0, str(project / 'projects/sim2gse'))
    import result_store
    result_store.bind_project(data_project)
    result_store.ensure_available()
    return project


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--data-project', type=Path, required=True)
    args = parser.parse_args()
    try:
        prepare(args.project, args.data_project)
        from seed_training import check_training
        result = check_training()
        result['data_project'] = str(args.data_project.resolve())
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
