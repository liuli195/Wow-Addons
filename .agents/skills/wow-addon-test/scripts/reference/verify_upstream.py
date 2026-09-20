"""Optional pinned-source audit. Read only; never updates baselines or source locks."""
from __future__ import annotations
import hashlib,json,pathlib,re,sys,urllib.request
ROOT=pathlib.Path(__file__).resolve().parents[2]  # 技能根
ASSETS=ROOT/'assets'
sys.path.insert(0,str(ROOT))
from wowtestlib.core import load_json,write_json,ToolError

def tokens(text):
    # Lex Lua before dropping comments. Strings containing -- or end remain intact.
    out=[];i=0;n=len(text)
    def long_at(pos):return re.match(r'\[(=*)\[',text[pos:])
    while i<n:
        c=text[i]
        if c.isspace():i+=1;continue
        if text.startswith('--',i):
            m=long_at(i+2)
            if m:
                end=']'+m.group(1)+']';q=text.find(end,i+2+len(m.group(0)))
                if q<0:raise ToolError('unterminated long comment')
                i=q+len(end)
            else:
                q=text.find('\n',i);i=n if q<0 else q+1
            continue
        if c in ('"',"'"):
            q=i+1
            while q<n:
                if text[q]=='\\':q+=2;continue
                if text[q]==c:break
                q+=1
            if q>=n:raise ToolError('unterminated string')
            out.append(text[i:q+1]);i=q+1;continue
        m=long_at(i)
        if m:
            end=']'+m.group(1)+']';q=text.find(end,i+len(m.group(0)))
            if q<0:raise ToolError('unterminated long string')
            out.append(text[i:q+len(end)]);i=q+len(end);continue
        m=re.match(r'[A-Za-z_][A-Za-z_0-9]*|0[xX][0-9a-fA-F]+(?:\.[0-9a-fA-F]*)?(?:[pP][+-]?\d+)?|(?:\d+\.?(?!\.)\d*|\.\d+)(?:[eE][+-]?\d+)?|\.\.\.|==|~=|<=|>=|\.\.|//|<<|>>',text[i:])
        if m:out.append(m.group(0));i+=len(m.group(0))
        else:out.append(c);i+=1
    return out

def contains(hay,needle):
    # KMP: linear time, no parsing/rewrite of the target function.
    if not needle:return False
    prefix=[0]*len(needle);j=0
    for i in range(1,len(needle)):
        while j and needle[i]!=needle[j]:j=prefix[j-1]
        if needle[i]==needle[j]:j+=1
        prefix[i]=j
    j=0
    for x in hay:
        while j and x!=needle[j]:j=prefix[j-1]
        if x==needle[j]:j+=1
        if j==len(needle):return True
    return False

def verify(cache):
    cfg=load_json(ASSETS/'reference/sources.json');src=(ASSETS/'reference/native.lua').read_text('utf-8');cache=pathlib.Path(cache);cache.mkdir(parents=True,exist_ok=True)
    sections=dict(re.findall(r'-- BEGIN ([^\n]+)\n(.*?)\n-- END \1',src,re.S));report=[]
    for name,record in cfg['files'].items():
        p=cache/name
        if not p.exists():
            url=f"https://raw.githubusercontent.com/{cfg['repository']}/{cfg['commit']}/{cfg['base_path']}{name}"
            req=urllib.request.Request(url,headers={'User-Agent':'wow-addon-test/1.0 source-audit'})
            with urllib.request.urlopen(req,timeout=30)as r:raw=r.read(2_000_000)
        else:raw=p.read_bytes()
        digest=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        if digest!=record['git_blob']:raise ToolError('upstream file hash mismatch: '+name)
        if not p.exists():p.write_bytes(raw)
        ts=tokens(raw.decode('utf-8-sig'))
        for method in record['methods']:
            if method not in sections:raise ToolError('missing marked method '+method)
            ok=contains(ts,tokens(sections[method]));report.append({'file':name,'method':method,'match':ok})
    return {'status':'pass'if all(r['match']for r in report)else'difference','methods':report,'scope':'Token equality of selected method bodies, not complete client execution'}
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--cache',default=str(ROOT/'.upstream-cache'));p.add_argument('--output',default=str(ROOT/'reports/upstream-audit.json'));a=p.parse_args()
    try:r=verify(a.cache);write_json(a.output,r);print(json.dumps(r,ensure_ascii=False,indent=2));raise SystemExit(0 if r['status']=='pass'else 1)
    except (ToolError,OSError,ValueError)as e:print(str(e),file=sys.stderr);raise SystemExit(2)
