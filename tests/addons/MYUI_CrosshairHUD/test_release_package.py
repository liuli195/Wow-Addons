"""从正式打包和部署入口检查文件边界、备份及个人设置保护。"""
import importlib.util
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[3]


def tool():
    spec = importlib.util.spec_from_file_location('hud_package', ROOT / 'scripts/dev/package_crosshair_hud.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_package_contains_only_runtime(tmp_path):
    module = tool()
    package = module.build(ROOT, tmp_path / 'packages')
    manifest = module.validate(package)
    assert len(manifest['files']) == 32
    paths = [entry['path'] for entry in manifest['files']]
    assert not any('Debug.lua' in p or p.endswith('.png') or 'EdgeTest' in p for p in paths)
    assert 'MYUI_CrosshairHUD/Diagnostics.lua' in paths
    for entry in manifest['files']:
        p = entry['path']
        if p.endswith('.blp'):
            assert (package / 'AddOns' / p).read_bytes() == (ROOT / 'addons' / p).read_bytes()


def test_deploy_backs_up_exact_scopes_and_preserves_settings(tmp_path):
    module = tool()
    package = module.build(ROOT, tmp_path / 'packages')
    game = tmp_path / '_retail_'
    addons = game / 'Interface/AddOns'
    old = {
        'MYUI_CrosshairHUD/old.bak': b'old hud',
        'MYUI/Media/CrosshairHUD/old.png': b'old media',
        'MYUI_CrosshairHUDEdgeTest/test.lua': b'old test',
        'MYUI/Series.lua': b'old series',
    }
    for name, content in old.items():
        p = addons / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
    keep = addons / 'MYUI/Media/Other/keep.txt'
    keep.parent.mkdir(parents=True)
    keep.write_bytes(b'other material')
    settings = game / 'WTF/Account/example/SavedVariables/MYUI_CrosshairHUD.lua'
    settings.parent.mkdir(parents=True)
    settings.write_bytes(b'personal configuration')
    backup = module.deploy(package, addons, tmp_path / 'backups')
    for name, content in old.items():
        assert (backup / name).read_bytes() == content
    assert keep.read_bytes() == b'other material'
    assert settings.read_bytes() == b'personal configuration'
    assert not (addons / 'MYUI_CrosshairHUDEdgeTest').exists()
    assert not (addons / 'MYUI_CrosshairHUD/old.bak').exists()
    assert not list((addons / 'MYUI/Media/CrosshairHUD').glob('*.png'))
    assert (addons / 'MYUI_CrosshairHUD/Diagnostics.lua').is_file()


def test_corrupt_package_stops_before_deployment(tmp_path):
    module = tool()
    package = module.build(ROOT, tmp_path / 'packages')
    (package / 'AddOns/MYUI_CrosshairHUD/Core.lua').write_bytes(b'corrupt')
    addons = tmp_path / '_retail_/Interface/AddOns'
    addons.mkdir(parents=True)
    with pytest.raises(ValueError):
        module.deploy(package, addons, tmp_path / 'backups')
    assert list(addons.iterdir()) == []
    assert not (tmp_path / 'backups').exists()


def test_packaged_core_still_draws_real_readings(tmp_path, monkeypatch):
    package = tool().build(ROOT, tmp_path / 'packages')
    spec = importlib.util.spec_from_file_location('packaged_core_check', Path(__file__).with_name('test_core_readings.py'))
    checks = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checks)
    monkeypatch.setattr(checks, 'ADDON', package / 'AddOns/MYUI_CrosshairHUD')
    checks.test_arc_rotation_chain()


def test_packaged_diagnostic_command_is_lazy_copyable_and_safe(tmp_path):
    package = tool().build(ROOT, tmp_path / 'packages')
    source = r'''
local frames, notices = {}, {}
local methods = {}
local function object(kind, name)
 local o = {kind=kind, name=name, scripts={}}
 return setmetatable(o, {__index=function(_, key)
  return methods[key] or function() end
 end})
end
function methods:SetScript(name, fn) self.scripts[name]=fn end
function methods:CreateFontString() return object('Font') end
function methods:SetText(text) self.text=text end
function methods:Show() self.shown=true end
function methods:Hide() self.shown=false; if self.scripts.OnHide then self.scripts.OnHide(self) end end
function methods:SetFocus() self.focus=true end
function methods:ClearFocus() self.focus=false end
function methods:HighlightText() self.highlight=true end
function methods:GetWidth() return 1920 end
function methods:GetHeight() return 1080 end
UIParent=object('Frame'); UISpecialFrames={}; SlashCmdList={}
function CreateFrame(kind,name) local o=object(kind,name); frames[#frames+1]=o; return o end
print=function(text) notices[#notices+1]=text end
C_Timer={NewTicker=function() error('诊断不能增加轮询') end, After=function() error('诊断不能增加定时器') end}
SendChatMessage=function() error('不能发送报告') end
local secret=setmetatable({}, {__tostring=function() error('不能转成文本') end})
issecretvalue=function(v) return v==secret end
C_AddOns={GetAddOnMetadata=function(_,key) return key=='Version' and '0.1.0' or 'test-build' end,
 IsAddOnLoaded=function() return true end}
GetBuildInfo=function() return '12.1.0','69933','',120100 end
UnitClass=function() return '死亡骑士','DEATHKNIGHT' end
assert(loadfile(arg[1]..'/Logic.lua'))()
assert(loadfile(arg[1]..'/Config.lua'))()
local NS=MYUI_CHH
NS.Core={GetReadings=function() return {healthRotation=secret, powerRotation=secret,
 healthReadOK=true, powerReadOK=true, hasMarker=true} end, IsHidden=function() return false end}
NS.NativeBlood={ready=true, status='账号名字和本机路径不能出现在报告中'}
assert(loadfile(arg[1]..'/Diagnostics.lua'))()
assert(#frames==0 and #notices==0, '加载不能自动创建窗口或输出')
SlashCmdList.MYUICHH('demo')
assert(#frames==0 and NS.Debug==nil, '正式包不允许启动假数据')
SlashCmdList.MYUICHH('diag')
local win, edit
for _,frame in ipairs(frames) do
 if frame.name=='MYUICHHDiagnosticWindow' then win=frame end
 if frame.kind=='EditBox' then edit=frame end
end
assert(win and win.shown and edit.focus and edit.highlight)
assert(edit.text:find('test%-build') and edit.text:find('受限，交给游戏绘制',1,true))
assert(not edit.text:find('账号名字和本机路径不能出现在报告中',1,true))
assert(#notices==2 and not notices[2]:find('\n'))
local report=edit.text
edit.text='误输入'; edit.scripts.OnTextChanged(edit,true)
assert(edit.text==report)
local count=#frames
SlashCmdList.MYUICHH('report')
assert(#frames==count, '再次生成应复用窗口')
edit.scripts.OnEscapePressed()
assert(not win.shown and not edit.focus)
io.write('PASS diagnostic window\n')
'''
    harness = tmp_path / 'diagnostics.lua'
    harness.write_text(source, encoding='utf-8')
    result = subprocess.run([str(ROOT / '.tools/lua-5.1.5/src/lua.exe'), str(harness),
                             str(package / 'AddOns/MYUI_CrosshairHUD')], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_deployment_rejects_wtf_even_when_suffix_looks_correct(tmp_path):
    module = tool()
    package = module.build(ROOT, tmp_path / 'packages')
    wrong = tmp_path / '_retail_/WTF/Interface/AddOns'
    wrong.mkdir(parents=True)
    with pytest.raises(ValueError, match='WTF'):
        module.deploy(package, wrong, tmp_path / 'backups')
    assert list(wrong.iterdir()) == []
    assert not (tmp_path / 'backups').exists()


@pytest.mark.parametrize('old_build', ['previous-build', None])
def test_backup_identifies_old_install_separately_from_target(tmp_path, old_build):
    module = tool()
    package = module.build(ROOT, tmp_path / 'packages')
    addons = tmp_path / '_retail_/Interface/AddOns'
    toc = addons / 'MYUI_CrosshairHUD/MYUI_CrosshairHUD.toc'
    toc.parent.mkdir(parents=True)
    toc.write_text('## Version: 0.1.0\n' + (f'## X-MYUI-Build: {old_build}\n' if old_build else ''), encoding='utf-8')
    backup = module.deploy(package, addons, tmp_path / 'backups')
    import json
    metadata = json.loads((backup / 'backup-manifest.json').read_text(encoding='utf-8'))
    assert metadata['installedBuild'] == (old_build or 'unknown')
    assert metadata['targetBuild'] == module.validate(package)['build']
