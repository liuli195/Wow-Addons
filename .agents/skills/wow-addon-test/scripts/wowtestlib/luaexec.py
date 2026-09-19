"""Execute trusted Lua in a disposable process. Not a security sandbox."""
from __future__ import annotations
import ctypes, ctypes.util, importlib.util, json, os, pathlib, shutil, subprocess, sys, tempfile

class LuaExecutionError(RuntimeError):
    pass

def backend() -> dict:
    choice = os.environ.get('WOWTEST_LUA_BACKEND', '')
    exe = os.environ.get('WOWTEST_LUA')
    if exe:
        found = shutil.which(exe) or (exe if pathlib.Path(exe).is_file() else None)
        if not found:
            return {'available': False, 'reason': 'WOWTEST_LUA 指定的程序不存在'}
        return {'available': True, 'kind': 'executable', 'path': found}
    if choice in ('', 'lupa'):
        try:
            if importlib.util.find_spec('lupa.lua51'):
                return {'available': True, 'kind': 'lupa.lua51'}
        except (ImportError, ModuleNotFoundError):
            pass
        if choice == 'lupa':
            return {'available': False, 'reason': '未安装 lupa.lua51'}
    if choice in ('', 'library'):
        for name in ('lua5.4', 'lua54', 'lua5.3', 'lua53'):
            path = ctypes.util.find_library(name)
            if path:
                return {'available': True, 'kind': 'library', 'path': path, 'version': name}
    if choice == '':
        for name in ('lua5.1', 'lua51', 'lua', 'lua5.4', 'lua5.3'):
            path = shutil.which(name)
            if path:
                return {'available': True, 'kind': 'executable', 'path': path}
    return {'available': False,
            'reason': '未找到可用的 Lua 后端：设置 WOWTEST_LUA 指向 Lua 程序或共享库，'
                      '或安装 lupa.lua51。本技能不修改系统与用户级环境。'}

def _library_eval(source: str, path: str) -> str:
    lib = ctypes.CDLL(path)
    P = ctypes.c_void_p
    lib.luaL_newstate.restype = P
    lib.luaL_openlibs.argtypes = [P]
    lib.luaL_loadbufferx.argtypes = [P, ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p, ctypes.c_char_p]
    lib.luaL_loadbufferx.restype = ctypes.c_int
    lib.lua_pcallk.argtypes = [P, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_ssize_t, P]
    lib.lua_pcallk.restype = ctypes.c_int
    lib.lua_tolstring.argtypes = [P, ctypes.c_int, ctypes.POINTER(ctypes.c_size_t)]
    lib.lua_tolstring.restype = P
    lib.lua_close.argtypes = [P]
    L = lib.luaL_newstate()
    if not L:
        raise LuaExecutionError('Lua allocation failed')
    try:
        lib.luaL_openlibs(L)
        raw = source.encode('utf-8')
        code = lib.luaL_loadbufferx(L, raw, len(raw), b'@wowtest-worker', b't')
        if not code:
            code = lib.lua_pcallk(L, 0, 1, 0, 0, None)
        n = ctypes.c_size_t()
        value = lib.lua_tolstring(L, -1, ctypes.byref(n))
        result = ctypes.string_at(value, n.value).decode('utf-8') if value else ''
        if code:
            raise LuaExecutionError(result or f'Lua error {code}')
        if not value:
            raise LuaExecutionError('Lua worker must return JSON text')
        return result
    finally:
        lib.lua_close(L)

def evaluate(source: str, timeout: float = 30) -> dict | list:
    """Evaluate source returning JSON. A process wall timeout also covers infinite Lua loops."""
    b = backend()
    if not b['available']:
        raise LuaExecutionError(b['reason'])
    with tempfile.TemporaryDirectory(prefix='wowtest-') as tmp:
        src = pathlib.Path(tmp)/'job.lua'
        out = pathlib.Path(tmp)/'result.json'
        src.write_text(source, encoding='utf-8')
        if b['kind'] == 'executable':
            wrapper = pathlib.Path(tmp)/'wrapper.lua'
            wrapper.write_text('local result = assert(loadfile(arg[1]))(); local f=assert(io.open(arg[2], "wb")); f:write(result); f:close()\n', encoding='utf-8')
            args = [b['path'], str(wrapper), str(src), str(out)]
        else:
            args = [sys.executable, str(pathlib.Path(__file__).resolve()), str(src), str(out)]
        try:
            p = subprocess.run(args, capture_output=True, timeout=timeout, encoding='utf-8', errors='replace', shell=False)
        except subprocess.TimeoutExpired as exc:
            raise LuaExecutionError(f'执行超过 {timeout} 秒，已终止测试进程') from exc
        if p.returncode:
            raise LuaExecutionError((p.stderr or p.stdout).strip()[-12000:] or f'worker exit {p.returncode}')
        if not out.is_file():
            raise LuaExecutionError('worker did not produce output')
        if out.stat().st_size > 64*1024*1024:
            raise LuaExecutionError('output exceeds 64 MiB')
        try:
            return json.loads(out.read_text('utf-8'))
        except (ValueError, OSError) as exc:
            raise LuaExecutionError(f'无效 JSON 输出: {exc}') from exc

def literal(value):
    if value is None: return 'nil'
    if value is True: return 'true'
    if value is False: return 'false'
    if isinstance(value, (int,float)):
        import math
        if not math.isfinite(value): raise ValueError('non-finite number')
        return repr(value)
    if isinstance(value, str):
        # JSON \u escapes are not Lua escapes; encode controls using 3 digit decimal escapes.
        return '"'+''.join('\\"' if c=='"' else '\\\\' if c=='\\' else ('\\%03d'%ord(c)) if ord(c)<32 else c for c in value)+'"'
    if isinstance(value,list): return '{'+','.join(literal(v) for v in value)+'}'
    if isinstance(value,dict): return '{'+','.join('['+literal(str(k))+']='+literal(v) for k,v in value.items())+'}'
    raise TypeError(type(value))

if __name__ == '__main__':
    try:
        source = pathlib.Path(sys.argv[1]).read_text('utf-8')
        b = backend()
        if b['kind']=='lupa.lua51':
            from lupa.lua51 import LuaRuntime
            runtime=LuaRuntime(unpack_returned_tuples=True,register_eval=False,register_builtins=False)
            result=runtime.execute(source)
        elif b['kind']=='library':
            result=_library_eval(source,b['path'])
        else: raise LuaExecutionError('invalid worker backend')
        json.loads(result)
        pathlib.Path(sys.argv[2]).write_text(result,encoding='utf-8')
    except Exception as exc:
        sys.stderr.write(str(exc)+'\n'); sys.exit(1)
