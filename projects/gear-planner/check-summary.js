const {load,vm,assert}=require('./test-page.cjs');
const ctx=vm.createContext({result:{complete:true},boot:{gems:[{id:1,label:'测试宝石 · 品质 2'}]},esc:String,fmt:String});
load(ctx,'function gearSummary(', 'function updateOriginalMatches(');
const gearSummary=ctx.gearSummary;
let text=gearSummary({fields:{},raw:{},gemSlots:[],enchantOptions:[]});assert(!text.includes('宝石：'));assert(!text.includes('附魔：'));
text=gearSummary({fields:{},raw:{},gemSlots:['PRISMATIC'],enchantOptions:[{id:'2',label:'测试附魔'}]});assert(text.includes('宝石：</span><strong class="missing-config">缺失</strong>'));assert(text.includes('附魔：</span><strong class="missing-config">缺失</strong>'));
text=gearSummary({fields:{gem_id:'1',enchant_id:'2'},raw:{},gemSlots:['PRISMATIC'],enchantOptions:[{id:'2',label:'测试附魔'}]});assert(text.includes('测试宝石'));assert(text.includes('测试附魔'));assert(!text.includes('缺失'));
console.log('PASS: unsupported summaries hidden; supported empty marked missing; configured labels retained');
