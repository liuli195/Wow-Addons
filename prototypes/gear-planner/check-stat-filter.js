const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync(__dirname+'/index.html','utf8');
new vm.Script(html.match(/<script>([\s\S]*?)<\/script>/)[1]);
const source=html.slice(html.indexOf('function matchesStats('),html.indexOf('function drawLevelControl('));
const ctx=vm.createContext({statFilters:[],statMatch:'any'});vm.runInContext(source,ctx);
assert(ctx.matchesStats({filterStats:[]}));
ctx.statFilters=['crit','haste'];assert(ctx.matchesStats({filterStats:['crit']}));
ctx.statMatch='all';assert(!ctx.matchesStats({filterStats:['crit']}));assert(ctx.matchesStats({filterStats:['crit','haste']}));
assert(ctx.matchesStats({customFilter:true}));ctx.statFilters.push('mastery');assert(!ctx.matchesStats({customFilter:true}));
ctx.statMatch='any';assert(ctx.matchesStats({customFilter:true}));assert(!ctx.matchesStats({filterStats:[]}));
const cache=JSON.parse(fs.readFileSync(__dirname+'/filter-stats.json','utf8'));
assert(!cache['250245'].includes('haste'));assert.deepEqual(cache['251229'],['crit','mastery']);
console.log('PASS: script syntax, no selection, any/all, crafted pairs, native trinket stats');


const matchSource=html.slice(html.indexOf('function matchingLevelChoice('),html.indexOf('function rememberSavedLevels('));
vm.runInContext(matchSource,ctx);
const items={head:{ilevel:311,levels:[305,311,321]},feet:{ilevel:311,levels:[305,311,321]}};
assert.equal(ctx.matchingLevelChoice(items,null,'current'),'311');
assert.equal(ctx.matchingLevelChoice(items,{head:311,feet:311},'current'),'restore');
items.head.ilevel=321;assert.equal(ctx.matchingLevelChoice(items,null,'maximum'),'current');
items.feet.ilevel=321;assert.equal(ctx.matchingLevelChoice(items,null,'current'),'maximum');
items.head.ilevel=305;items.feet.ilevel=305;assert.equal(ctx.matchingLevelChoice(items,null,'current'),'minimum');
assert(html.includes('<option value="current" hidden disabled>保持当前装等</option>'));
console.log('PASS: hidden placeholder, saved levels, uniform levels, min/max and mixed levels');

const dockElement={innerHTML:'',classList:{toggle:(name,value)=>{dockElement.loading=value}}};
const dockCtx=vm.createContext({$:()=>dockElement,result:{complete:true,values:{ilevel:315.75,crit:731,crit_pct:20.89}},busy:false,demo:'',model:{},labels:{crit:'暴击',haste:'急速',mastery:'精通',versatility:'全能'},fmt:n=>n==null?'—':String(n),diff:()=>''});
vm.runInContext(html.slice(html.indexOf('function drawDock('),html.indexOf("const dock=$('plannerDock')")),dockCtx);
dockCtx.drawDock();assert(dockElement.innerHTML.includes('315.75'));assert(dockElement.innerHTML.includes('20.89%'));
dockCtx.busy=true;dockCtx.drawDock();assert(dockElement.loading);assert(dockElement.innerHTML.includes('旧结果待更新'));
dockCtx.busy=false;dockCtx.result={complete:false};dockCtx.drawDock();assert(!dockElement.innerHTML.includes('315.75'));assert(dockElement.innerHTML.includes('未能完整计算'));
console.log('PASS: floating summary values, calculation status and incomplete result handling');

const controls={compare:{value:''}};
const comparisonCtx=vm.createContext({$:id=>controls[id],compareRequest:0,compareResult:null,importComparison:null,result:{complete:true,values:{crit:731}},model:{name:'导入检查'},clone:structuredClone,refreshMenus:()=>{},drawStats:()=>{},rememberOriginalItems:()=>{},drawGear:()=>{},drawEditor:()=>{}});
vm.runInContext(html.slice(html.indexOf('function defaultComparison('),html.indexOf('function currentCompare(')),comparisonCtx);
comparisonCtx.defaultComparison();assert.equal(controls.compare.value,'imported');
comparisonCtx.result.values.crit=800;assert.equal(comparisonCtx.compareResult.values.crit,731);
comparisonCtx.defaultComparison('saved-1');assert.equal(controls.compare.value,'saved-1');assert.equal(comparisonCtx.importComparison,null);
assert(!html.includes('当前未确认可用插槽'));assert(!html.includes('该装备无当前资料片附魔选项'));
console.log('PASS: import/saved default comparison, frozen reference, unsupported field placeholders removed');

const identity={innerHTML:''};const identityCtx=vm.createContext({$:()=>identity,model:null,esc:x=>String(x)});
vm.runInContext(html.slice(html.indexOf('function drawCharacter('),html.indexOf('function toast(')),identityCtx);
identityCtx.drawCharacter();assert(identity.innerHTML.includes('尚未导入角色'));assert(!identity.innerHTML.includes('死亡骑士'));
identityCtx.model={character:{class:'deathknight',spec:'blood',level:90,race:'highmountain_tauren'}};identityCtx.drawCharacter();assert(identity.innerHTML.includes('至高岭牛头人'));assert(!html.includes('<h1>配装工作台</h1>'));assert(html.includes('role="heading" aria-level="1"'));
console.log('PASS: neutral workspace title and character identity derived from loaded model');
