const {load,vm,assert}=require('./test-page.cjs');
(async()=>{
 const els={};const pending=[];
 const ctx=vm.createContext({$:id=>els[id]??={value:'当前',disabled:false},model:{name:'当前',gear:{}},result:{complete:true,version:'v',values:{armor:1}},requestId:0,busy:false,performance:{now:()=>0},api:()=>new Promise((resolve,reject)=>pending.push({resolve,reject})),banner(){},drawStats(){},drawEditor(){},drawGear(){},drawCharacter(){},confirm:()=>false});
 load(ctx,'async function runCalc(', 'async function edit(');
 const one=ctx.runCalc({model:ctx.model}),two=ctx.runCalc({model:ctx.model});
 pending[1].resolve({complete:true,values:{armor:2},model:{name:'新',gear:{}}});await two;
 pending[0].resolve({complete:true,values:{armor:1},model:{name:'旧',gear:{}}});await one;
 assert.equal(ctx.result.values.armor,2);assert(!ctx.busy);
 const prior=ctx.result,failed=ctx.runCalc({model:ctx.model,edit:{slot:'head'}});pending[2].reject(Error('timeout'));await failed;assert.equal(ctx.result,prior);assert(!ctx.busy);
 const e={compare:{}};const jobs=[];
 const cmp=vm.createContext({$:id=>e[id],compareRequest:0,compareResult:null,builds:[{id:'a',version:'v',model:{}},{id:'b',version:'v',model:{}}],boot:{version:'v'},api:()=>new Promise(resolve=>jobs.push(resolve)),drawStats(){},toast(){},clone:structuredClone});
 load(cmp,"$('compare').onchange=","$('exportBtn').onclick=");
 const a=e.compare.onchange({target:{value:'a'}}),b=e.compare.onchange({target:{value:'b'}});jobs[1]({complete:true,tag:'new'});await b;jobs[0]({complete:true,tag:'old'});await a;assert.equal(cmp.compareResult.tag,'new');
 const queue=[];const merge=vm.createContext({model:{gear:{head:'a'}},busy:false,originalItems:{head:{value:'original'}},boot:{slots:[['head']]},originalMatchKey:'',originalMatches:{},api:()=>new Promise(resolve=>queue.push(resolve)),drawGear(){},drawEditor(){}});
 load(merge,'function updateOriginalMatches(', 'function drawGear(');merge.updateOriginalMatches();merge.model={gear:{head:'b'}};merge.updateOriginalMatches();queue[1]({head:[2]});await Promise.resolve();queue[0]({head:[1]});await Promise.resolve();assert.equal(merge.originalMatches.head[0],2);
 console.log('PASS: actual calculation, comparison and merge ignore stale replies; failed edit retains previous result');
})().catch(e=>{console.error(e);process.exitCode=1});
