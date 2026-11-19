import { chromium } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
const dir = 'test-results/office-pixel';
await mkdir(dir, { recursive: true });
const browser = await chromium.launch({ headless: false });
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
const errors = [];
page.on('pageerror', e => errors.push(e.message));
const shot = name => page.screenshot({ path: `${dir}/${name}.png` });
try {
 await page.goto('http://127.0.0.1:3012/office-pixel');
 await page.locator('canvas').waitFor();
 await page.waitForTimeout(500);
 await shot('main');
 for (const id of ['manager', 'reviewer', 'developer']) {
  const pt = await page.evaluate(id => window.__officeHit(id), id);
  await page.mouse.click(...pt);
  await page.locator('.ai').waitFor();
 }
 await shot('developer-selected'); await shot('inspector');
 for (const name of ['Overview','Execution Trace','Prompt & Context','Decisions','Tools','Output','Evidence','Usage']) {
  await page.getByRole('tab', { name, exact: true }).click();
  await shot(name === 'Usage' ? 'usage-optimization' : name.toLowerCase().replaceAll(/[^a-z]+/g,'-'));
 }
 await page.getByText('DEV CONTROLS').click();
 await page.getByRole('button', {name:'Paper',exact:true}).click(); await shot('day');
 await page.getByRole('button', {name:'Neon',exact:true}).click(); await shot('night');
 await page.getByText('DEV CONTROLS').click();
 const popupPromise = page.waitForEvent('popup');
 await page.getByRole('button',{name:'Pop out ⧉'}).click();
 const popup=await popupPromise; await popup.waitForLoadState(); await popup.locator('canvas').waitFor();
 await popup.screenshot({path:`${dir}/standard-popout.png`});
 await popup.setViewportSize({width:480,height:540});
 await popup.getByRole('button',{name:/Developer/}).first().click();
 await popup.locator('.cc').waitFor(); await popup.screenshot({path:`${dir}/compact-popout.png`});
 await popup.getByRole('button',{name:'Inspect',exact:true}).click(); await popup.locator('.ai.sheet').waitFor();
 await page.getByRole('button',{name:'Fullscreen ⛶'}).click();
 await page.waitForFunction(()=>!!document.fullscreenElement); await shot('fullscreen');
 if(errors.length) throw Error(errors.join('\n'));
 console.log('Headed Office interactions passed; screenshots:',dir);
} finally { await browser.close(); }
