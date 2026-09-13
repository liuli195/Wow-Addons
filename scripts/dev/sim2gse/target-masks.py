"""将固定 SimC 提取器的客户端 CSV 转为导出所需的原始目标掩码。"""
import argparse
import csv
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv', type=Path)
    parser.add_argument('db2', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--build', required=True)
    args = parser.parse_args()
    rows = list(csv.DictReader(args.csv.open(encoding='utf-8-sig')))
    masks = {}
    for row in rows:
        if int(row['difficulty_id']) != 0:
            continue
        key, mask = str(int(row['id_parent'])), int(row['flags'])
        if key in masks and masks[key] != mask:
            raise ValueError('同一法术的客户端目标记录冲突: ' + key)
        masks[key] = mask
    value = dict(client_build=args.build, source='Blizzard client SpellTargetRestrictions.db2',
                 source_sha256=hashlib.sha256(args.db2.read_bytes()).hexdigest(),
                 extractor_commit='b845947a34429874433d8e9362326894650dd20a', difficulty_id=0,
                 target_masks={key: mask for key, mask in masks.items() if mask})
    args.output.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
