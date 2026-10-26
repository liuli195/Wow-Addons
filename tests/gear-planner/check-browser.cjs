const PROJECT = require('node:path').resolve(__dirname, '../../projects/gear-planner');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const context=await browser.newContext({acceptDownloads:true}); // disposable storage, never the user's profile
 const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 page.on('dialog',d=>d.accept());
 const calculations=[];page.on('request',r=>{if(/\/api\/(?:import|calculate)$/.test(r.url()))calculations.push(new URL(r.url()).pathname)});
 await page.route('https://wow.zamimg.com/**',r=>r.abort());
 // These unasserted side paths can start native work or fetch/cache effect data.
 await page.route(/\/api\/(?:original-matches|effects)$/,r=>r.abort());
 const output=path.resolve(__dirname,'../../.local/tests/gear-planner/browser-check');fs.mkdirSync(output,{recursive:true});
 const report=[];
 async function ready(){await page.waitForFunction(()=>!busy&&result?.complete&&!document.querySelector('#importDialog').open);await page.waitForFunction(()=>!document.querySelector('#saveBtn').disabled)}
 async function exportFile(name){const wait=page.waitForEvent('download');await page.locator('#exportBtn').click();const d=await wait;const file=path.join(output,name);await d.saveAs(file);return {file,data:JSON.parse(fs.readFileSync(file,'utf8'))}}
 async function save(name){await page.locator('#buildName').fill(name);await page.locator('#saveBtn').click()}
 try{
  await page.goto('http://127.0.0.1:8765/?variant=a');
  await page.locator('#importBtn').click();await page.locator('#importText').fill(fs.readFileSync(path.resolve(PROJECT,'fixtures/cn-user-20260909-0349.input.simc'),'utf8'));await page.locator('#doImport').click();await ready();
  assert.match(await page.locator('#core').innerText(),/3,449/);
  const initial=await page.evaluate(()=>structuredClone(result.values));
  await save('闭环原方案');const a=await page.locator('#saved').inputValue();assert(a);
  await page.locator('[data-slot="neck"]').click();await page.locator('#editGem0').selectOption('');await ready();
  assert.equal(initial.haste-(await page.evaluate(()=>result.values.haste)),16);
  await page.locator('#copyBtn').click();await page.locator('#saveAsName').fill('闭环修改方案');await page.locator('#saveAsForm [type="submit"]').click();const b=await page.locator('#saved').inputValue();assert.notEqual(a,b);
  const saved=await exportFile('roundtrip.json');assert(!saved.data.model.gear.neck.includes('gem_id='));
  await page.reload();await page.locator('#saved').selectOption(b);await ready();const loaded=await exportFile('reloaded.json');assert.deepEqual(loaded.data,saved.data);
  await page.locator('#compare').selectOption(a);await page.waitForFunction(()=>document.querySelector('#secondary').textContent.includes('−16'));
  assert.deepEqual(await page.evaluate(()=>compareResult.values),initial);
  report.push('real import/edit/save-as/reload/compare/export');
  await page.locator('#importBtn').click();await page.locator('#fileInput').setInputFiles(saved.file);await page.waitForFunction(()=>document.querySelector('#importText').value.startsWith('{'));await page.locator('#doImport').click();await ready();
  const again=await exportFile('reimported.json');assert.deepEqual(again.data,saved.data);report.push('downloaded file reimport matches original export');
  await page.locator('[data-stat-filter="crit"]').check();assert(await page.locator('.filter-muted').count()>0);assert.equal(await page.locator('.filter-muted[disabled]').count(),0);await page.locator('#clearFilters').click();assert.equal(await page.locator('.filter-muted').count(),0);
  report.push('clickable muted filters');
  await page.screenshot({path:path.join(output,'final.png')});assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(output,'report.json'),JSON.stringify({passed:report,pageErrors:errors,calculationRequests:calculations},null,2));console.log('PASS:',report.join('; '),'calculation requests:',calculations.length);
 }catch(e){console.error('PAGE ERRORS',errors,'BODY',await page.locator('body').innerText());throw e}finally{await context.close();await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
