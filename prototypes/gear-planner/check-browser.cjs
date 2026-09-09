const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const context=await browser.newContext({acceptDownloads:true}); // disposable storage, never the user's profile
 const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('https://wow.zamimg.com/**',r=>r.abort());
 const output=path.join(__dirname,'browser-check');fs.mkdirSync(output,{recursive:true});
 const report=[];
 async function ready(){await page.waitForFunction(()=>document.querySelector('#calcStatus').textContent.includes('计算完成'));await page.waitForFunction(()=>!document.querySelector('#saveBtn').disabled)}
 async function exportFile(name){const wait=page.waitForEvent('download');await page.locator('#exportBtn').click();const d=await wait;const file=path.join(output,name);await d.saveAs(file);return {file,data:JSON.parse(fs.readFileSync(file,'utf8'))}}
 async function save(name){await page.locator('#buildName').fill(name);await page.locator('#saveBtn').click()}
 try{
  await page.goto('http://127.0.0.1:8765/?variant=a');
  await page.locator('#importBtn').click();await page.locator('#importText').fill(fs.readFileSync(path.resolve(__dirname,'fixtures/cn-user-20260909-0349.input.simc'),'utf8'));await page.locator('#doImport').click();await ready();
  assert.match(await page.locator('#core').innerText(),/3,449/);
  await save('闭环原方案');const a=await page.locator('#saved').inputValue();assert(a);
  await page.locator('[data-slot="neck"]').click();await page.locator('#editGem0').selectOption('');await ready();
  await page.locator('#copyBtn').click();await page.locator('#saveAsName').fill('闭环原方案');await page.locator('#saveAsForm [type="submit"]').click();assert.match(await page.locator('#saveAsError').innerText(),/名称/);await page.locator('#cancelSaveAs').click();
  await page.locator('#copyBtn').click();await page.locator('#saveAsName').fill('闭环修改方案');await page.locator('#saveAsForm [type="submit"]').click();const b=await page.locator('#saved').inputValue();assert.notEqual(a,b);
  const saved=await exportFile('roundtrip.json');assert(!saved.data.model.gear.neck.includes('gem_id='));
  await page.reload();await page.locator('#saved').selectOption(b);await ready();const loaded=await exportFile('reloaded.json');assert.deepEqual(loaded.data,saved.data);
  await page.locator('#compare').selectOption(a);await page.waitForFunction(()=>document.querySelector('#secondary').textContent.includes('−16'));
  report.push('real import/edit/save-as/reload/compare/export');
  page.once('dialog',d=>d.dismiss());await page.locator('#deleteBtn').click();assert.equal(await page.locator('#saved').inputValue(),b);
  page.once('dialog',d=>d.accept());await page.locator('#deleteBtn').click();
  page.once('dialog',d=>d.accept());await page.locator('#saved').selectOption(a);await ready();
  page.once('dialog',d=>d.accept());await page.locator('#deleteBtn').click();await page.waitForFunction(()=>document.querySelector('#characterInfo').textContent.includes('尚未导入'));
  assert.equal(await page.locator('#saved option').count(),1);report.push('delete cancel and last-build empty state');
  await page.locator('#importBtn').click();await page.locator('#fileInput').setInputFiles(saved.file);await page.waitForFunction(()=>document.querySelector('#importText').value.startsWith('{'));await page.locator('#doImport').click();await ready();
  const again=await exportFile('reimported.json');assert.deepEqual(again.data,saved.data);report.push('downloaded file reimport matches original export');
  await save('失败保护');const id=await page.locator('#saved').inputValue();
  const before=await page.evaluate(()=>localStorage.getItem('gear-planner-prototype-v1'));
  await page.evaluate(()=>{window.testSetItem=Storage.prototype.setItem;Storage.prototype.setItem=function(){throw new DOMException('quota','QuotaExceededError')}});
  await page.locator('#buildName').fill('不应保存');await page.locator('#saveBtn').click();await page.waitForFunction(()=>document.body.textContent.includes('浏览器保存失败'));
  await page.evaluate(()=>{Storage.prototype.setItem=window.testSetItem});
  assert.equal(await page.evaluate(()=>localStorage.getItem('gear-planner-prototype-v1')),before);
  // Select the stored record after failure to check the in-memory record, not only disk.
  page.once('dialog',d=>d.accept());await page.locator('#saved').selectOption(id);await ready();assert.equal(await page.locator('#buildName').inputValue(),'失败保护');
  report.push('actual save failure preserves persisted and in-memory saved record');
  await page.locator('[data-slot="neck"]').click();
  await page.getByRole('button',{name:'替换颈部：护卫之牙束带',exact:true}).click();await ready();
  let replacement=await exportFile('replacement.json');assert.match(replacement.data.model.gear.neck,/id=273781(?:,|$)/);
  const option=await page.locator('#editLevel option').evaluateAll(es=>es.find(e=>e.textContent.startsWith('308 '))?.value);assert(option);await page.locator('#editLevel').selectOption(option);await ready();assert.equal((await page.locator('[data-slot="neck"] .ilvl').innerText()).trim(),'308');
  await page.locator('[data-slot="head"]').click();await page.locator('#editEnchant').selectOption('');await ready();
  const edited=await exportFile('enchant-edit.json');assert(!edited.data.model.gear.head.includes('enchant_id='));
  await page.locator('[data-stat-filter="crit"]').check();assert(await page.locator('.filter-muted').count()>0);assert.equal(await page.locator('.filter-muted[disabled]').count(),0);await page.locator('#clearFilters').click();assert.equal(await page.locator('.filter-muted').count(),0);
  report.push('candidate replacement, legal level change, enchant removal and clickable muted filters');
  await page.screenshot({path:path.join(output,'final.png')});assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(output,'report.json'),JSON.stringify({passed:report,pageErrors:errors},null,2));console.log('PASS:',report.join('; '));
 }catch(e){console.error('PAGE ERRORS',errors,'BODY',await page.locator('body').innerText());throw e}finally{await context.close();await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
