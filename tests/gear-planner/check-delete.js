const {load,vm,assert}=require('./test-page.cjs');
const els={deleteBtn:{},compare:{value:'a'}};let approve=false,fail=false,stored;
const ctx=vm.createContext({$:id=>els[id],busy:false,saveId:'a',dirty:false,builds:[{id:'a',model:{name:'一'}},{id:'b',model:{name:'二'}}],compareResult:{},STORE:'test',confirm:()=>approve,toast(){},banner(){},refreshMenus(){},drawStats(){},buildLabel:b=>b.model.name,clearEditor(){ctx.cleared=true;ctx.model=null},localStorage:{setItem(k,v){if(fail)throw Error('quota');stored=JSON.parse(v)}}});
load(ctx,"$('deleteBtn').onclick=","$('copyBtn').onclick=");
els.deleteBtn.onclick();assert.equal(ctx.builds.length,2);
approve=true;fail=true;els.deleteBtn.onclick();assert.equal(ctx.builds.length,2);assert.equal(ctx.saveId,'a');
fail=false;els.deleteBtn.onclick();assert.equal(stored.length,1);assert.equal(ctx.builds[0].id,'b');assert.equal(ctx.compareResult,null);assert.equal(ctx.saveId,'');assert(!ctx.cleared);
ctx.saveId='b';els.deleteBtn.onclick();assert.equal(stored.length,0);assert.equal(ctx.builds.length,0);assert(ctx.cleared);
console.log('PASS: actual delete cancellation, failed persistence, ordinary and last build');
