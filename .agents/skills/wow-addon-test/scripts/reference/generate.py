"""Generate candidate observations. Never overwrites bundled baseline by default."""
from __future__ import annotations
import sys,json,pathlib
ROOT=pathlib.Path(__file__).resolve().parents[2]  # 技能根;sys.path.insert(0,str(ROOT))
ASSETS=ROOT/'assets'
from wowtestlib.luaexec import evaluate,literal

def generate(cases,profiles):
 base=(ASSETS/'runtime/base.lua').read_text('utf-8')
 native=(ASSETS/'reference/native.lua').read_text('utf-8')
 driver=(ASSETS/'reference/driver.lua').read_text('utf-8')
 source=f'local M=({basewrap(base)})();local drive=({basewrap(driver)})();return M.json(drive(M,{literal(native)},{literal(cases)},{literal(profiles)}))'
 return evaluate(source,120)
def basewrap(code):return 'function()\n'+code+'\nend'
if __name__=='__main__':
 cs=json.loads((ASSETS/'data/cases.json').read_text('utf-8'));ps=json.loads((ASSETS/'data/profiles.json').read_text('utf-8'))
 path=pathlib.Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'reports/reference-candidate.json'
 if path.exists():raise SystemExit(f'拒绝覆盖已有候选文件: {path}')
 path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(json.dumps(generate(cs,ps),ensure_ascii=False,indent=2)+'\n','utf-8')
 print(path)
