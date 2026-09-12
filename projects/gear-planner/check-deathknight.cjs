// Real browser workflow using disposable storage; never touches user saves.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const fixtureDir=process.argv[2]||'fixtures/raidbots-deathknight';
 const samples=JSON.parse(fs.readFileSync(path.join(__dirname,fixtureDir,'manifest.json'),'utf8')).samples;
 try{for(const sample of samples){
  const context=await browser.newContext({acceptDownloads:true}),page=await context.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
  await page.route('https://wow.zamimg.com/**',r=>r.abort());
  try{
   const keys=new Set(['deathknight','demonhunter','rogue','warlock','mage','paladin','hunter','shaman','warrior','priest','druid','monk','evoker','spec','level','race','talents','omnium_talents','timeofday',...Object.keys(sample.gear),'shoulder','wrist']);
   const input=fs.readFileSync(path.join(__dirname,fixtureDir,sample.spec+'.input.simc'),'utf8').split(/\r?\n/).filter(line=>keys.has(line.split('=')[0])).join('\n');
   await page.goto('http://127.0.0.1:8765/',{waitUntil:'domcontentloaded'});
   await page.locator('#importBtn').click();await page.locator('#importText').fill(input);await page.locator('#doImport').click();
   async function ready(){await page.waitForFunction(()=>!busy&&result?.complete)}
   await ready();assert.equal(await page.evaluate(()=>model.character.spec),sample.spec);
   const initial=await page.evaluate(()=>structuredClone(result.values));assert.notEqual(initial.ilevel,null);
   // Check the actual UI selection functions for all specs, including stale specId.
   const coverage=await page.evaluate(()=>{
    const spec=model.character.spec;
    const visible=boot.catalog.main_hand.filter(candidateFits);
    const names={blood:['鲜血'],frost:['冰霜'],unholy:['邪恶'],havoc:['浩劫'],vengeance:['复仇'],devourer:['噬灭'],assassination:['奇袭'],outlaw:['狂徒'],subtlety:['敏锐'],affliction:['痛苦'],demonology:['恶魔学识'],destruction:['毁灭'],arcane:['奥术'],fire:['火焰'],holy:['神圣'],protection:['防护'],retribution:['惩戒'],beast_mastery:['野兽控制'],marksmanship:['射击'],survival:['生存'],discipline:['戒律'],shadow:['暗影'],balance:['平衡'],feral:['野性'],guardian:['守护'],brewmaster:['酒仙'],mistweaver:['织雾'],windwalker:['踏风'],devastation:['湮灭'],preservation:['恩护'],augmentation:['增辉'],arms:['武器'],fury:['狂暴'],elemental:['元素'],enhancement:['增强'],restoration:['恢复']};
    return {weapons:visible.map(x=>x.id),effects:setEffectLines({setEffectsBySpec:{250:names.blood,251:['死亡骑士冰霜'],252:names.unholy,577:names.havoc,581:names.vengeance,1480:names.devourer,259:names.assassination,260:names.outlaw,261:names.subtlety,265:names.affliction,266:names.demonology,267:names.destruction,62:names.arcane,63:names.fire,64:['法师冰霜'],65:names.holy,66:names.protection,70:names.retribution,253:names.beast_mastery,254:names.marksmanship,255:names.survival,262:names.elemental,263:names.enhancement,264:names.restoration,71:names.arms,72:names.fury,73:names.protection,256:names.discipline,257:names.holy,258:names.shadow,102:names.balance,103:names.feral,104:names.guardian,105:names.restoration,268:names.brewmaster,270:names.mistweaver,269:names.windwalker,1467:names.devastation,1468:names.preservation,1473:names.augmentation}},spec),missing:setEffectLines({setEffects:['鲜血']},spec)};
   });
   assert(coverage.weapons.length);assert.deepEqual(coverage.effects,[sample.spec==='frost'?(await page.evaluate(()=>model.character.class)==='mage'?'法师冰霜':'死亡骑士冰霜'):{blood:'鲜血',frost:'冰霜',unholy:'邪恶',havoc:'浩劫',vengeance:'复仇',devourer:'噬灭',assassination:'奇袭',outlaw:'狂徒',subtlety:'敏锐',affliction:'痛苦',demonology:'恶魔学识',destruction:'毁灭',arcane:'奥术',fire:'火焰',holy:'神圣',protection:'防护',retribution:'惩戒',beast_mastery:'野兽控制',marksmanship:'射击',survival:'生存',discipline:'戒律',shadow:'暗影',balance:'平衡',feral:'野性',guardian:'守护',brewmaster:'酒仙',mistweaver:'织雾',windwalker:'踏风',devastation:'湮灭',preservation:'恩护',augmentation:'增辉',arms:'武器',fury:'狂暴',elemental:'元素',enhancement:'增强',restoration:'恢复'}[sample.spec]]);
   if(sample.spec!=='blood')assert.deepEqual(coverage.missing,[]);
   await page.locator('#buildName').fill(sample.spec+'原方案');await page.locator('#saveBtn').click();const original=await page.locator('#saved').inputValue();
   await page.locator('[data-slot="neck"]').click();await page.locator('#editGem0').selectOption('');await ready();
   const withoutGem=await page.evaluate(()=>structuredClone(result.values));assert.notDeepEqual(withoutGem,initial);
   for(let i=1;i<await page.locator('[id^=editGem]').count();i++){await page.locator('#editGem'+i).selectOption('');await ready()}
   // Replace a real candidate and exercise the app's level confirmation if needed.
   const old=await page.evaluate(()=>result.items.neck.id);
   const target=await page.evaluate(()=>boot.catalog.neck.findIndex(x=>candidateFits(x)&&x.id!==result.items.neck.id&&!x.crafted));
   assert(target>=0);await page.locator(`[data-target="neck"][data-replace="${target}"]`).click();await ready();
   assert.notEqual(await page.evaluate(()=>result.items.neck.id),old,await page.locator('body').innerText());
   await page.locator('[data-slot="head"]').click();await page.locator('#editEnchant').selectOption('');await ready();
   await page.locator('#copyBtn').click();await page.locator('#saveAsName').fill(sample.spec+'修改方案');await page.locator('#saveAsForm [type="submit"]').click();
   const saved=await page.locator('#saved').inputValue();assert.notEqual(saved,original);
   const before=await page.evaluate(()=>JSON.stringify(model));
   const download=page.waitForEvent('download');await page.locator('#exportBtn').click();const file=await(await download).path();
   const exported=JSON.parse(fs.readFileSync(file,'utf8'));assert.deepEqual(exported.model,JSON.parse(before));
   await page.reload({waitUntil:'domcontentloaded'});await page.locator('#saved').selectOption(saved);await ready();assert.equal(await page.evaluate(()=>JSON.stringify(model)),before);
   await page.locator('#compare').selectOption(original);await page.waitForFunction(()=>compareResult?.complete);
   assert.deepEqual(await page.evaluate(()=>compareResult.values),initial);
   await page.locator('#importBtn').click();await page.locator('#importText').fill(JSON.stringify(exported));await page.locator('#doImport').click();await ready();
   assert.equal(await page.evaluate(()=>JSON.stringify(model)),before);
   if(await page.evaluate(()=>['warlock','mage','priest','evoker'].includes(model.character.class)||model.character.class==='druid'&&['balance','restoration'].includes(model.character.spec))){
    assert.equal(await page.locator('#sources th').nth(1).textContent(),'智力');
    const weapons=await page.evaluate(()=>({
     staff:boot.catalog.main_hand.findIndex(x=>candidateFits(x)&&x.id===159636),
     single:boot.catalog.main_hand.findIndex(x=>candidateFits(x)&&x.id===159137),
     off:boot.catalog.off_hand.findIndex(candidateFits)
    }));
    assert(Object.values(weapons).every(x=>x>=0),JSON.stringify(weapons));
    await page.locator(`[data-target="main_hand"][data-replace="${weapons.staff}"]`).click();await ready();
    assert.equal(await page.evaluate(()=>model.gear.off_hand),undefined);
    const staffModel=await page.evaluate(()=>JSON.stringify(model));
    const mean=await page.evaluate(()=>(Object.values(result.items).reduce((n,x)=>n+x.ilevel,0)+result.items.main_hand.ilevel)/16);
    assert.equal(await page.evaluate(()=>result.values.ilevel),mean);
    await page.locator(`[data-target="off_hand"][data-replace="${weapons.off}"]`).click();
    await page.waitForFunction(()=>!busy);assert.equal(await page.evaluate(()=>JSON.stringify(model)),staffModel);
    assert((await page.locator('body').innerText()).includes('请先选择单手主手武器'));
    await page.locator(`[data-target="main_hand"][data-replace="${weapons.single}"]`).click();await ready();
    await page.locator(`[data-target="off_hand"][data-replace="${weapons.off}"]`).click();await ready();
    assert(await page.evaluate(()=>Boolean(model.gear.off_hand)));
    assert.equal(await page.evaluate(()=>result.values.ilevel),await page.evaluate(()=>Object.values(result.items).reduce((n,x)=>n+x.ilevel,0)/16));
   }
   if(await page.evaluate(()=>model.character.class==='druid'&&['feral','guardian'].includes(model.character.spec))){
    assert.equal(await page.locator('#sources th').nth(1).textContent(),'敏捷');
    assert.equal(await page.evaluate(()=>boot.catalog.off_hand.filter(candidateFits).length),0);
    assert.equal(await page.evaluate(()=>result.values.ilevel),await page.evaluate(()=>(Object.values(result.items).reduce((n,x)=>n+x.ilevel,0)+result.items.main_hand.ilevel)/16));
   }
   if(await page.evaluate(()=>model.character.class)==='monk'){
    assert.equal(await page.locator('#sources th').nth(1).textContent(),'敏捷');
    async function weapon(slot,id){
     const index=await page.evaluate(({slot,id})=>boot.catalog[slot].findIndex(x=>candidateFits(x)&&x.id===id),{slot,id});
     assert(index>=0);await page.locator(`[data-target="${slot}"][data-replace="${index}"]`).click();await ready();
     assert.equal(await page.evaluate(slot=>result.items[slot].id,slot),id);
    }
    await weapon('main_hand',158370);assert.equal(await page.evaluate(()=>model.gear.off_hand),undefined);
    const before=await page.evaluate(()=>JSON.stringify(model));
    const off=await page.evaluate(()=>boot.catalog.off_hand.findIndex(x=>candidateFits(x)&&x.id===159645));
    await page.locator(`[data-target="off_hand"][data-replace="${off}"]`).click();await page.waitForFunction(()=>!busy);
    assert.equal(await page.evaluate(()=>JSON.stringify(model)),before);
    await weapon('main_hand',158714);await weapon('off_hand',159645);
    assert.equal(await page.evaluate(()=>result.values.ilevel),await page.evaluate(()=>Object.values(result.items).reduce((n,x)=>n+x.ilevel,0)/16));
    await weapon('main_hand',158370);assert.equal(await page.evaluate(()=>model.gear.off_hand),undefined);
    assert.equal(await page.evaluate(()=>result.values.ilevel),await page.evaluate(()=>(Object.values(result.items).reduce((n,x)=>n+x.ilevel,0)+result.items.main_hand.ilevel)/16));
   }
   if(await page.evaluate(()=>model.character.class)==='paladin'){
    assert.equal(await page.locator('#sources th').nth(1).textContent(),sample.spec==='holy'?'智力':'力量');
    if(['holy','protection'].includes(sample.spec)){
     const shield=await page.evaluate(()=>boot.catalog.off_hand.findIndex(x=>candidateFits(x)&&x.id!==result.items.off_hand.id));
     assert(shield>=0);await page.locator(`[data-target="off_hand"][data-replace="${shield}"]`).click();await ready();
     assert(await page.evaluate(()=>Boolean(model.gear.off_hand)));
    }else assert.equal(await page.evaluate(()=>boot.catalog.off_hand.filter(candidateFits).length),0);
    assert.equal(await page.evaluate(()=>result.values.ilevel),await page.evaluate(()=>(Object.values(result.items).reduce((n,x)=>n+x.ilevel,0)+(model.gear.off_hand?0:result.items.main_hand.ilevel))/16));
   }
   if(await page.evaluate(()=>model.character.class)==='hunter'){
    assert.equal(await page.locator('#sources th').nth(1).textContent(),'敏捷');
    async function weapon(slot,id){
     const index=await page.evaluate(({slot,id})=>boot.catalog[slot].findIndex(x=>candidateFits(x)&&x.id===id),{slot,id});
     assert(index>=0,slot+':'+id);await page.locator(`[data-target="${slot}"][data-replace="${index}"]`).click();await ready();
     assert.equal(await page.evaluate(slot=>result.items[slot].id,slot),id);
    }
    const average=async()=>assert.equal(await page.evaluate(()=>result.values.ilevel),await page.evaluate(()=>(Object.values(result.items).reduce((n,x)=>n+x.ilevel,0)+(model.gear.off_hand?0:result.items.main_hand.ilevel))/16));
    if(sample.spec==='survival'){
     const blocked=await page.evaluate(()=>boot.catalog.off_hand.findIndex(x=>candidateFits(x)&&x.id===159136));
     const before=await page.evaluate(()=>JSON.stringify(model));
     await page.locator(`[data-target="off_hand"][data-replace="${blocked}"]`).click();await page.waitForFunction(()=>!busy);
     assert.equal(await page.evaluate(()=>JSON.stringify(model)),before);
     assert((await page.locator('body').innerText()).includes('请先选择单手主手武器'));
     await weapon('main_hand',158714);await weapon('off_hand',159136);await average();
     await weapon('main_hand',158370);assert.equal(await page.evaluate(()=>model.gear.off_hand),undefined);await average();
    }else{
     assert.equal(await page.evaluate(()=>boot.catalog.off_hand.filter(candidateFits).length),0);
     await weapon('main_hand',159637);await average();
     await weapon('main_hand',159643);await average();
     await weapon('main_hand',268200);await average();
    }
   }
   if(await page.evaluate(()=>model.character.class)==='shaman'){
    assert.equal(await page.locator('#sources th').nth(1).textContent(),sample.spec==='enhancement'?'敏捷':'智力');
    async function weapon(slot,id){
     const index=await page.evaluate(({slot,id})=>boot.catalog[slot].findIndex(x=>candidateFits(x)&&x.id===id),{slot,id});
     assert(index>=0,slot+':'+id);await page.locator(`[data-target="${slot}"][data-replace="${index}"]`).click();await ready();
     assert.equal(await page.evaluate(slot=>result.items[slot].id,slot),id);
    }
    const average=async()=>assert.equal(await page.evaluate(()=>result.values.ilevel),await page.evaluate(()=>(Object.values(result.items).reduce((n,x)=>n+x.ilevel,0)+(model.gear.off_hand?0:result.items.main_hand.ilevel))/16));
    if(sample.spec==='enhancement'){
     await weapon('main_hand',159645);await weapon('off_hand',251143);await average();
    }else{
     await weapon('main_hand',159636);assert.equal(await page.evaluate(()=>model.gear.off_hand),undefined);await average();
     const shield=await page.evaluate(()=>boot.catalog.off_hand.findIndex(x=>candidateFits(x)&&x.id===159664));
     const previous=await page.evaluate(()=>JSON.stringify(model));
     await page.locator(`[data-target="off_hand"][data-replace="${shield}"]`).click();await page.waitForFunction(()=>!busy);
     assert.equal(await page.evaluate(()=>JSON.stringify(model)),previous);
     assert((await page.locator('body').innerText()).includes('请先选择单手主手武器'));
     await weapon('main_hand',158369);await weapon('off_hand',159664);await average();
     await weapon('off_hand',159667);await average();
    }
   }
   if(await page.evaluate(()=>model.character.class)==='warrior'){
    assert.equal(await page.locator('#sources th').nth(1).textContent(),'力量');
    if(sample.spec==='fury'){
     const off=await page.evaluate(()=>boot.catalog.off_hand.findIndex(x=>candidateFits(x)&&x.id!==result.items.off_hand.id));assert(off>=0);
     await page.locator(`[data-target="off_hand"][data-replace="${off}"]`).click();await ready();
     assert.equal(await page.evaluate(()=>result.values.ilevel),await page.evaluate(()=>Object.values(result.items).reduce((n,x)=>n+x.ilevel,0)/16));
    }
   }
   assert.deepEqual(errors,[]);console.log('PASS: '+sample.spec+' import, candidates, set text, gem, replacement, enchant, save-as, reload, compare, export/reimport');
  }finally{await context.close()}
 }
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
