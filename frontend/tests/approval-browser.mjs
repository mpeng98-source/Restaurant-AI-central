import assert from 'node:assert/strict';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { webkit } from 'playwright';

const base = process.env.BASE_URL ?? 'http://localhost:3000';
assert.ok(process.env.BROWSER_FIXTURES_FILE, 'BROWSER_FIXTURES_FILE is mandatory');
const cases = JSON.parse(await readFile(process.env.BROWSER_FIXTURES_FILE, 'utf8'));
const output = process.env.BROWSER_REPORT_FILE ?? '../test-results/browser-report.json';
const screenshots = '../test-results/browser';
await mkdir(screenshots, { recursive: true });
const results = { passed: 0, failed: 0, skipped: 0, cases: [] };
const browser = await webkit.launch({ headless: true });
async function signIn(context, email, password) {
  const page = await context.newPage();
  page.setDefaultTimeout(15000);
  await page.goto(base);
  await page.getByLabel('Work email', { exact: true }).fill(email);
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await page.waitForURL('**/dashboard');
  return page;
}
async function chooseReport(page) {
  await page.goto(`${base}/inventory/approvals`);
  await page.getByRole('heading', { name: 'Inventory approval dashboard', exact: true }).waitFor();
  await page.locator('.count-session-list button').first().waitFor();
  await page.locator('.count-session-list button').first().click();
  await page.getByRole('button', { name: 'Begin review', exact: true }).waitFor();
  await page.getByRole('button', { name: 'Begin review', exact: true }).click();
  await page.getByRole('status').filter({ hasText: 'under review' }).waitFor();
}
try {
  for (const [index, fixture] of cases.entries()) {
    const contexts = [];
    let currentPage;
    const safeName = `${index}-${fixture.name.replaceAll(' ', '-')}`;
    try {
      const options = { viewport: { width: fixture.width, height: fixture.height }, deviceScaleFactor: 2, isMobile: true, hasTouch: true };
      const counterContext = await browser.newContext(options); contexts.push(counterContext);
      const counter = await signIn(counterContext, fixture.counter === 'gm' ? fixture.gm_email : fixture.employee_email, fixture.password);
      currentPage = counter;
      await counter.goto(`${base}/inventory`);
      const create = counter.getByRole('button', { name: 'Create draft', exact: true });
      await create.waitFor();
      if (fixture.counter === 'gm') await counter.getByLabel('Assigned counter', { exact: true }).selectOption(fixture.gm_id);
      const createdResponse = counter.waitForResponse((response) => response.request().method() === 'POST' && /\/count-sessions$/.test(response.url()));
      await create.click();
      const created = await createdResponse;
      assert.equal(created.status(), 201);
      const session = await created.json();
      const quantity = counter.getByRole('textbox', { name: `Quantity for ${fixture.item_name}`, exact: true });
      await quantity.fill('315');
      await counter.getByRole('button', { name: `Save ${fixture.item_name}`, exact: true }).click();
      await counter.getByRole('status').filter({ hasText: 'saved. Session version' }).waitFor();
      await counter.getByRole('button', { name: 'Submit confirmed count', exact: true }).click();
      await counter.getByRole('status').filter({ hasText: 'Count submitted and frozen' }).waitFor();
      const managerContext = await browser.newContext(options); contexts.push(managerContext);
      let manager = await signIn(managerContext, fixture.gm_email, fixture.password);
      currentPage = manager;
      await chooseReport(manager);
      if (fixture.counter === 'gm') {
        await manager.getByRole('alert').filter({ hasText: 'Four-eyes control' }).waitFor();
        assert.equal(await manager.getByRole('button', { name: 'Approve and post adjustments', exact: true }).isDisabled(), true);
        await manager.screenshot({ path: `${screenshots}/${safeName}-blocked.png`, fullPage: true });
        const ownerContext = await browser.newContext(options); contexts.push(ownerContext);
        manager = await signIn(ownerContext, fixture.owner_email, fixture.password);
        currentPage = manager;
        await manager.goto(`${base}/inventory/approvals`);
        await manager.locator('.count-session-list button').first().click();
        await manager.getByLabel(`Review ${fixture.sku}`, { exact: true }).waitFor();
      }
      await manager.getByLabel(`Review ${fixture.sku}`, { exact: true }).selectOption(fixture.action === 'rejected' ? 'disputed' : 'accepted');
      await manager.getByLabel('Decision reason', { exact: true }).fill(`Browser ${fixture.name}: independently reviewed quantity and units`);
      const decisionButton = manager.getByRole('button', { name: fixture.action === 'rejected' ? 'Reject complete report' : 'Approve and post adjustments', exact: true });
      assert.equal(await decisionButton.isDisabled(), true, 'explicit confirmation is required');
      await manager.getByRole('checkbox', { name: 'I reviewed the frozen quantities, units, counters, cutoff and every line decision.', exact: true }).check();
      await manager.screenshot({ path: `${screenshots}/${safeName}-review.png`, fullPage: true });
      assert.equal(await manager.locator('input[type=file]').count(), 0, 'no photo upload is falsely offered');
      await decisionButton.click();
      await manager.getByRole('heading', { name: `Report ${fixture.action === 'rejected' ? 'rejected' : 'approved'}`, exact: true }).waitFor();
      if (fixture.action !== 'rejected') {
        assert.match(await manager.getByTestId('movement-balance').first().innerText(), /-25\.000000 g.*340\.000000.*315\.000000/);
      } else {
        assert.equal(await manager.getByTestId('movement-balance').count(), 0);
      }
      if (fixture.action === 'reversed') {
        await manager.getByRole('button', { name: 'Preview compensating reversal', exact: true }).click();
        await manager.getByLabel('Correction reason', { exact: true }).fill('Browser independently verified correction');
        await manager.getByRole('checkbox', { name: 'I confirm the displayed current balance and compensating movement.', exact: true }).check();
        await manager.getByRole('button', { name: 'Post compensating reversal', exact: true }).click();
        await manager.getByRole('status').filter({ hasText: 'Compensating reversal posted' }).waitFor();
        assert.equal(await manager.getByTestId('movement-balance').count(), 2);
      }
      await manager.screenshot({ path: `${screenshots}/${safeName}-result.png`, fullPage: true });
      assert.equal(await manager.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true, 'tablet layout must not overflow horizontally');
      await counter.reload();
      await counter.locator('.count-session-list button').first().waitFor();
      assert.match(await counter.locator('.count-session-list button').first().innerText(), fixture.action === 'rejected' ? /rejected/ : /approved/);
      results.passed++;
      results.cases.push({ name: fixture.name, viewport: options.viewport, engine: 'WebKit', status: 'passed', report_id: session.id });
      console.log(`BROWSER PASSED: ${fixture.name} (${fixture.width}x${fixture.height})`);
    } catch (error) {
      const detail = String(error).replaceAll(fixture.password, '[redacted]');
      results.failed++;
      results.cases.push({ name: fixture.name, status: 'failed', error: detail });
      if (currentPage) await currentPage.screenshot({ path: `${screenshots}/${safeName}-failure.png`, fullPage: true }).catch(() => {});
      console.error(`BROWSER FAILED: ${fixture.name}: ${detail}`);
    } finally {
      for (const context of contexts) await context.close();
      await writeFile(output, JSON.stringify(results, null, 2));
    }
  }
} finally { await browser.close(); }
console.log(`Browser test report: ${JSON.stringify({ passed: results.passed, failed: results.failed, skipped: results.skipped })}`);
assert.equal(results.failed, 0, 'all required browser acceptance scenarios must pass');
assert.equal(results.passed, cases.length);
