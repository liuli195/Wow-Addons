const {load,vm,assert}=require('./test-page.cjs');
for(const id of ['','a']){
 const els={buildName:{value:'新名称',focus(){}},saveBtn:{}};let fail=true,persisted;
 const ctx=vm.createContext({$:k=>els[k],model:{name:'原名称',gear:{head:'new'}},builds:[{id:'a',model:{name:'原名称',gear:{head:'old'}}}],saveId:id,busy:false,dirty:true,clone:structuredClone,crypto:{randomUUID:()=> 'b'},boot:{version:'v'},STORE:'test',banner(){},toast(){},rememberSavedLevels(){},rememberOriginalItems(){},drawGear(){},drawEditor(){},refreshMenus(){},drawStats(){},localStorage:{setItem(k,v){if(fail)throw Error('quota');persisted=JSON.parse(v)}}});
 load(ctx,'function nameTaken(',"$('deleteBtn').onclick=");
 els.saveBtn.onclick();assert.equal(ctx.builds.length,1);assert.equal(ctx.builds[0].model.gear.head,'old');assert.equal(ctx.saveId,id);assert(ctx.dirty);assert.equal(ctx.model.name,'原名称');
 fail=false;els.saveBtn.onclick();assert.equal(persisted.length,id?1:2);assert.equal(ctx.saveId,id||'b');assert(!ctx.dirty);assert.equal(persisted.at(-1).model.gear.head,'new');
}
const ctx=vm.createContext({busy:false,result:{complete:true,version:'v',values:{armor:3449.028}},currentCompare:()=>({complete:true,version:'v',values:{armor:3347.586}})});
load(ctx,'const fmt=', 'function drawCharacter(');
load(ctx,'const panelValue=', 'function drawStats(');
vm.runInContext("globalThis.display=n=>fmt(panelValue('armor',n));globalThis.unrounded=panelValue('crit',1.8)",ctx);
assert.equal(ctx.display(3347.586),'3,347');assert.equal(ctx.display(3449.028),'3,449');assert.equal(ctx.display(3398.307),'3,398');assert.equal(ctx.display(null),'—');assert.equal(ctx.unrounded,1.8);assert(ctx.diff('armor').includes('+102'));assert.equal(ctx.result.values.armor,3449.028);
console.log('PASS: atomic save/create, armor samples and difference of displayed values; native data retained');
