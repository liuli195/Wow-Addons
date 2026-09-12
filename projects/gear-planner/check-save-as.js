const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync(__dirname+'/index.html','utf8');
const source=html.slice(html.indexOf("$('copyBtn').onclick="),html.indexOf("$('saved').onchange="));
function setup(fail=false){
 const els={};const $=id=>els[id]??=( {value:'',textContent:'',focus(){},showModal(){this.open=true},close(){this.open=false}} );
 const current={name:'原方案',gear:{head:',id=123,ilevel=311'},character:{}};
 const ctx=vm.createContext({$,model:structuredClone(current),busy:false,builds:[{id:'old',model:structuredClone(current)}],saveId:'old',dirty:true,result:{complete:true,values:{crit:10}},clone:structuredClone,boot:{version:'v1'},STORE:'builds',crypto:{randomUUID:()=> 'new'},rememberSavedLevels(){},defaultComparison(id){ctx.comparison=id},banner(){},toast(){},localStorage:{setItem(k,v){if(fail)throw Error('disk full');ctx.persisted=JSON.parse(v)}}});
 ctx.nameTaken=name=>ctx.builds.some(b=>b.model.name===name);
 vm.runInContext(source,ctx);return {ctx,$};
}
for(const name of ['','   ','原方案',' 原方案 ']){
 const {ctx,$}=setup();$('copyBtn').onclick();$('saveAsName').value=name;$('saveAsForm').onsubmit({preventDefault(){}});
 assert.equal(ctx.builds.length,1);assert.equal(ctx.saveId,'old');assert.equal(ctx.model.name,'原方案');assert($('saveAsError').textContent);
}
{
 const {ctx,$}=setup(true);$('saveAsName').value='新方案';$('saveAsForm').onsubmit({preventDefault(){}});assert.equal(ctx.saveId,'old');assert.equal(ctx.builds.length,1);assert(ctx.dirty);assert.equal(ctx.model.name,'原方案');
}
{
 const {ctx,$}=setup();$('copyBtn').onclick();$('cancelSaveAs').onclick();assert.equal(ctx.model.name,'原方案');assert.equal(ctx.saveId,'old');
 ctx.model.gear.head=',id=456,ilevel=321';$('saveAsName').value=' 新方案 ';$('saveAsForm').onsubmit({preventDefault(){}});
 assert.equal(ctx.builds.length,2);assert.equal(ctx.persisted.length,2);assert.equal(ctx.saveId,'new');assert.equal(ctx.comparison,'new');assert.equal(ctx.model.name,'新方案');assert(!ctx.dirty);
 assert.equal(ctx.builds[0].model.gear.head,',id=123,ilevel=311');assert.equal(ctx.builds[1].model.gear.head,',id=456,ilevel=321');
 ctx.model.gear.head='later';assert.equal(ctx.builds[1].model.gear.head,',id=456,ilevel=321');
}
console.log('PASS: blank/duplicate validation, cancel, storage failure atomicity, save current edits and switch, independent old/new builds');
