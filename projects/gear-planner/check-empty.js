const {load,vm,assert,html}=require('./test-page.cjs');
const els={buildName:{value:'old'},statMatch:{value:'all'},compare:{value:'old'}};
const ctx=vm.createContext({$:id=>els[id],compareRequest:0,drawCharacter(){},banner(){},refreshMenus(){},drawGear(){},drawStats(){},drawEditor(){},model:{},result:{},originalItems:{head:{}},originalMatches:{head:[1]},savedLevels:{}});
load(ctx,'function clearEditor(', '(async()=>');ctx.clearEditor();
for(const key of ['model','result','compareResult','selected'])assert.equal(ctx[key],null);
assert.equal(ctx.saveId,'');assert(!ctx.dirty);assert.equal(Object.keys(ctx.originalItems).length,0);assert.equal(ctx.originalMatchKey,'');assert.equal(ctx.compareRequest,1);assert.equal(els.compare.value,'');assert.equal(els.statMatch.value,'any');
assert(!html.includes('boot.model'));assert(!html.includes('value="baseline"'));assert(!html.includes('resetBtn'));
console.log('PASS: actual empty state resets originals, comparison and filters; no automatic sample');
