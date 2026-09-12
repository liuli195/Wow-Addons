const {load,vm,assert}=require('./test-page.cjs');
const ctx=vm.createContext({builds:[{id:'a',model:{name:'当前装备'}},{id:'b',model:{name:'其他方案'}}]});
load(ctx,'function nameTaken(',"$('saveBtn').onclick=");load(ctx,'function buildLabel(', 'function rememberOriginalItems(');
assert(ctx.nameTaken(' 当前装备 '));assert(!ctx.nameTaken('当前装备','a'));assert(!ctx.nameTaken('新方案'));
ctx.builds.push({id:'c',model:{name:'当前装备'}});assert.equal(ctx.buildLabel(ctx.builds[0]),'当前装备【同名 1】');assert.equal(ctx.buildLabel(ctx.builds[2]),'当前装备【同名 2】');
console.log('PASS: current name validation and legacy duplicate labels');
