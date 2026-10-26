const {load,vm,assert}=require('./test-page.cjs');
const ctx=vm.createContext({result:{complete:true},boot:{gems:[{id:1,label:'测试宝石 · 品质 2'}]},esc:String,fmt:String});
load(ctx,'function gearSummary(', 'function updateOriginalMatches(');
const gearSummary=ctx.gearSummary;
let text=gearSummary({fields:{},raw:{},gemSlots:[],enchantOptions:[]});assert(!text.includes('宝石：'));assert(!text.includes('附魔：'));
text=gearSummary({fields:{},raw:{},gemSlots:['PRISMATIC'],enchantOptions:[{id:'2',label:'测试附魔'}]});assert(text.includes('宝石：</span><strong class="missing-config">缺失</strong>'));assert(text.includes('附魔：</span><strong class="missing-config">缺失</strong>'));
text=gearSummary({fields:{gem_id:'1',enchant_id:'2'},raw:{},gemSlots:['PRISMATIC'],enchantOptions:[{id:'2',label:'测试附魔'}]});assert(text.includes('测试宝石'));assert(text.includes('测试附魔'));assert(!text.includes('缺失'));
console.log('PASS: unsupported summaries hidden; supported empty marked missing; configured labels retained');

// The former per-class browser matrix exercised these same page functions.
// Keep the class/spec identity checks here, without repeating a native workflow.
const classSpecs={
 deathknight:{blood:250,frost:251,unholy:252},demonhunter:{havoc:577,vengeance:581,devourer:1480},
 rogue:{assassination:259,outlaw:260,subtlety:261},warlock:{affliction:265,demonology:266,destruction:267},
 mage:{arcane:62,fire:63,frost:64},paladin:{holy:65,protection:66,retribution:70},
 hunter:{beast_mastery:253,marksmanship:254,survival:255},shaman:{elemental:262,enhancement:263,restoration:264},
 warrior:{arms:71,fury:72,protection:73},priest:{discipline:256,holy:257,shadow:258},
 druid:{balance:102,feral:103,guardian:104,restoration:105},monk:{brewmaster:268,mistweaver:270,windwalker:269},
 evoker:{devastation:1467,preservation:1468,augmentation:1473}
};
const pageRules=vm.createContext({boot:{classSpecs},model:null});
load(pageRules,'function candidateFits(', 'function drawGear(');
for(const [characterClass,specs] of Object.entries(classSpecs)){
 for(const [spec,id] of Object.entries(specs)){
  const key=characterClass+':'+spec;
  pageRules.model={character:{class:characterClass,spec,specId:999}};
  assert(pageRules.candidateFits({fitReason:'other spec',fitReasonsBySpec:{[key]:''}}),key);
  assert(!pageRules.candidateFits({fitReason:'',fitReasonsBySpec:{[key]:'excluded'}}),key);
  assert(!pageRules.candidateFits({fitReasonsBySpec:{[key]:''},conversion:true}),key);
  assert(!pageRules.candidateFits({fitReason:'excluded'}),key);
  const expected=[key];
  assert.deepEqual([...pageRules.setEffectLines({setEffectsBySpec:{[id]:expected}},spec)],expected,key);
  assert.equal(pageRules.setEffectLines({setEffects:['legacy blood']},spec).join('|'),key==='deathknight:blood'?'legacy blood':'',key);
 }
}
pageRules.model={character:{class:'mage',spec:'frost',specId:251}};
assert.equal(pageRules.setEffectLines({setEffectsBySpec:{64:['mage frost'],251:['death knight frost']}},'frost')[0],'mage frost');
pageRules.model.character.class='deathknight';
assert.equal(pageRules.setEffectLines({setEffectsBySpec:{64:['mage frost'],251:['death knight frost']}},'frost')[0],'death knight frost');
console.log('PASS: all class/spec candidate masks and set effects, legacy Blood only, stale spec IDs and distinct Frost identities');

// Render the real source table with distinct attribute values so the expected
// primary column cannot accidentally pass by displaying a different attribute.
const elements={};
const sources=vm.createContext({
 $:id=>elements[id]??={innerHTML:'',classList:{toggle(){}},querySelectorAll:()=>[]},
 result:{complete:true,values:{},items:{head:{raw:{strength:111,agility:222,intellect:333}}}},
 boot:{slots:[['head','头部']]},model:null,busy:false,saveId:'',statFilters:[],
 labels:{strength:'力量',agility:'敏捷',intellect:'智力'},fmt:String,panelValue:(key,value)=>value,
 diff:()=>'',esc:String,drawLevelControl(){},drawDock(){},drawGear(){},drawEditor(){}
});
load(sources,'function drawStats(', 'function drawDock(');
const primaryCases=[
 ['力量',111,'deathknight:blood deathknight:frost deathknight:unholy paladin:protection paladin:retribution warrior:arms warrior:fury warrior:protection'],
 ['敏捷',222,'demonhunter:havoc demonhunter:vengeance rogue:assassination rogue:outlaw rogue:subtlety hunter:beast_mastery hunter:marksmanship hunter:survival shaman:enhancement druid:feral druid:guardian monk:brewmaster monk:windwalker'],
 ['智力',333,'demonhunter:devourer warlock:affliction warlock:demonology warlock:destruction mage:arcane mage:fire mage:frost paladin:holy shaman:elemental shaman:restoration priest:discipline priest:holy priest:shadow druid:balance druid:restoration monk:mistweaver evoker:devastation evoker:preservation evoker:augmentation']
];
const covered=[];
for(const [label,value,keys] of primaryCases){
 for(const key of keys.split(' ')){
  const [characterClass,spec]=key.split(':');covered.push(key);
  sources.model={character:{class:characterClass,spec}};sources.drawStats();
  assert(elements.sources.innerHTML.includes('<th>'+label+'</th>'),key);
  assert(elements.sources.innerHTML.includes('<td>'+value+'</td>'),key);
 }
}
assert.deepEqual(covered.sort(),Object.entries(classSpecs).flatMap(([cls,specs])=>Object.keys(specs).map(spec=>cls+':'+spec)).sort());
console.log('PASS: source table renders the correct primary attribute for every supported class/spec');
