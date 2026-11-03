import assert from 'node:assert/strict';
import { readFile,writeFile,mkdir } from 'node:fs/promises';
import { webkit } from 'playwright';
const base=process.env.BASE_URL??'http://localhost:3000';
assert.ok(process.env.BROWSER_PILOT_FIXTURES_FILE,'BROWSER_PILOT_FIXTURES_FILE is mandatory');
const cases=JSON.parse(await readFile(process.env.BROWSER_PILOT_FIXTURES_FILE,'utf8'));
const output=process.env.BROWSER_PILOT_REPORT_FILE??'../test-results/pilot-browser-report.json';
await mkdir('../test-results/browser',{recursive:true});
const result={passed:0,failed:0,skipped:0,cases:[],physical_ipad_uat:'UNVERIFIED — WebKit emulation only'};
const browser=await webkit.launch({headless:true});
async function login(context,email,password) {
  const page=await context.newPage();page.setDefaultTimeout(15000);await page.goto(base);
  await page.getByLabel('Work email',{exact:true}).fill(email);await page.getByLabel('Password',{exact:true}).fill(password);
  await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.waitForURL('**/dashboard');return page;
}
try {
 for(const [index,f] of cases.entries()) {
  const contexts=[];let current;
  try {
   const options={viewport:{width:f.width,height:f.height},deviceScaleFactor:2,isMobile:true,hasTouch:true};
   const gmContext=await browser.newContext(options);contexts.push(gmContext);const gm=await login(gmContext,f.gm_email,f.password);current=gm;
   await gm.goto(`${base}/inventory/operations`);await gm.getByLabel('Opening quantity',{exact:true}).fill('0.340');
   await gm.getByLabel('Opening unit',{exact:true}).selectOption('kg');await gm.getByLabel('Opening reason',{exact:true}).fill('Synthetic pilot manual opening sheet: 340 g');
   await gm.getByRole('checkbox',{name:'I confirmed the item, explicit unit, and physical opening quantity, including any zero.',exact:true}).check();
   const proposed=gm.waitForResponse(r=>r.request().method()==='POST'&&/\/openings$/.test(r.url()));
   await gm.getByRole('button',{name:'Submit opening proposal',exact:true}).dblclick();const proposal=await proposed;assert.equal(proposal.status(),201);
   await gm.getByRole('status').filter({hasText:'Opening proposal submitted'}).waitFor();
   await gm.locator('.count-session-list button').first().click();await gm.getByRole('alert').filter({hasText:'Four-eyes control'}).waitFor();
   assert.equal(await gm.getByRole('button',{name:'Approve opening balance',exact:true}).isDisabled(),true);
   const ownerContext=await browser.newContext(options);contexts.push(ownerContext);const owner=await login(ownerContext,f.owner_email,f.password);current=owner;
   await owner.goto(`${base}/inventory/operations`);await owner.locator('.count-session-list button').first().click();
   await owner.getByLabel('Opening review reason',{exact:true}).fill('Independent synthetic sheet, units and physical quantity reviewed');
   await owner.getByRole('checkbox',{name:'I independently checked the item, unit conversion, physical quantity and reason.',exact:true}).check();
   await owner.getByRole('button',{name:'Approve opening balance',exact:true}).dblclick();
   await owner.getByRole('status').filter({hasText:'Opening balance approved and recorded exactly once'}).waitFor();
   await owner.screenshot({path:`../test-results/browser/pilot-${index}-opening.png`,fullPage:true});
   const employeeContext=await browser.newContext(options);contexts.push(employeeContext);const employee=await login(employeeContext,f.employee_email,f.password);current=employee;
   await employee.goto(`${base}/inventory`);await employee.getByRole('button',{name:'Create draft',exact:true}).click();
   const quantity=employee.getByRole('textbox',{name:`Quantity for ${f.item_name}`,exact:true});await quantity.scrollIntoViewIfNeeded();
   assert.equal(await quantity.evaluate(el=>{const r=el.getBoundingClientRect();return document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)===el;}),true,'quantity input must not be covered by a floating submission panel');await quantity.fill('315');
   await employee.getByLabel('Identification photo',{exact:true}).setInputFiles({name:'synthetic-inventory.png',mimeType:'image/png',buffer:Buffer.from(f.photo_base64,'base64')});
   await employee.getByRole('status').filter({hasText:'Photo uploaded privately'}).waitFor();
   await employee.getByRole('button',{name:`Save ${f.item_name}`,exact:true}).click();await employee.getByRole('status').filter({hasText:'saved. Session version'}).waitFor();
   await employee.getByRole('button',{name:'View protected photo',exact:true}).click();await employee.getByRole('img',{name:/Employee inventory identification evidence/}).waitFor();
   await employeeContext.setOffline(true);await employee.getByRole('alert').filter({hasText:'You are offline'}).waitFor();
   assert.equal(await employee.getByRole('button',{name:'Submit confirmed count',exact:true}).isDisabled(),true);
   await employeeContext.setOffline(false);await employee.getByRole('alert').filter({hasText:'You are offline'}).waitFor({state:'hidden'});
   await employee.reload();await employee.locator('.count-session-list button').first().click();
   assert.match(await employee.getByRole('textbox',{name:`Quantity for ${f.item_name}`,exact:true}).inputValue(),/^315(?:\.0+)?$/,'refresh preserves the exact Decimal quantity');
   await employee.getByRole('button',{name:'View protected photo',exact:true}).click();await employee.getByRole('img',{name:/Employee inventory identification evidence/}).waitFor();
   await employee.screenshot({path:`../test-results/browser/pilot-${index}-photo.png`,fullPage:true});
   await employee.getByRole('button',{name:'Submit confirmed count',exact:true}).click();await employee.getByRole('status').filter({hasText:'Count submitted and frozen'}).waitFor();
   current=gm;await gm.goto(`${base}/inventory/approvals`);await gm.locator('.count-session-list button').first().click();
   await gm.getByRole('button',{name:'Begin review',exact:true}).click();await gm.getByRole('status').filter({hasText:'under review'}).waitFor();
   await gm.getByRole('button',{name:'View protected photo',exact:true}).click();await gm.getByRole('img',{name:/Employee inventory identification evidence/}).waitFor();
   await gm.getByLabel('Evidence control reason',{exact:true}).fill('Preserve synthetic rehearsal review evidence');
   const held=gm.waitForResponse(r=>r.request().method()==='PATCH'&&r.url().endsWith('/retention'));
   await gm.getByRole('button',{name:'Place evidence hold',exact:true}).click();assert.equal((await held).status(),200);
   await gm.getByLabel(`Review ${f.sku}`,{exact:true}).selectOption('accepted');await gm.getByLabel('Decision reason',{exact:true}).fill('Synthetic manual count confirmed 315 g against opening 340 g');
   await gm.getByRole('checkbox',{name:'I reviewed the frozen quantities, units, counters, cutoff and every line decision.',exact:true}).check();
   await gm.getByRole('button',{name:'Approve and post adjustments',exact:true}).click();await gm.getByRole('heading',{name:'Report approved',exact:true}).waitFor();
   assert.match(await gm.getByTestId('movement-balance').first().innerText(),/-25\.000000 g.*340\.000000.*315\.000000/);
   assert.equal(await gm.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true);
   await gm.screenshot({path:`../test-results/browser/pilot-${index}-result.png`,fullPage:true});
   await employee.goto(`${base}/dashboard`);await employee.getByRole('button',{name:'Sign out',exact:true}).click();await employee.waitForURL(base+'/');
   await employee.goto(`${base}/inventory`);await employee.waitForURL(base+'/');
   result.passed++;result.cases.push({name:f.name,status:'passed',engine:'WebKit',viewport:options.viewport});console.log(`PILOT BROWSER PASSED: ${f.name}`);
  } catch(error) {
   const detail=String(error).replaceAll(f.password,'[redacted]');result.failed++;result.cases.push({name:f.name,status:'failed',error:detail});console.error(`PILOT BROWSER FAILED: ${f.name}: ${detail}`);
   if(current)await current.screenshot({path:`../test-results/browser/pilot-${index}-failure.png`,fullPage:true}).catch(()=>{});
  } finally {for(const c of contexts)await c.close();await writeFile(output,JSON.stringify(result,null,2));}
 }
} finally {await browser.close();}
console.log(`Pilot browser report: ${JSON.stringify({passed:result.passed,failed:result.failed,skipped:result.skipped})}`);
assert.equal(result.failed,0);assert.equal(result.passed,cases.length);
