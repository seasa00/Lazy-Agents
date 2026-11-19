import {chromium} from '@playwright/test';
import {writeFile} from 'node:fs/promises';
const browser=await chromium.launch({headless:false});
try {
 const results=[];
 for(const [name,url] of [['reference','http://127.0.0.1:3013'],['next','http://127.0.0.1:3012/office-pixel']]) {
 const page=await browser.newPage({viewport:{width:1280,height:900},reducedMotion:'reduce'});
 await page.goto(url); await page.locator('canvas').waitFor(); await page.waitForTimeout(700);
 const states={};
 for(const theme of ['day','night']) {
 await page.getByText('DEV CONTROLS').click(); await page.getByRole('button',{name:theme==='day'?'Paper':'Neon',exact:true}).click(); await page.getByText('DEV CONTROLS').click();
 await page.mouse.move(0, 0); await page.waitForTimeout(400);
 states[theme]=await page.locator('canvas').evaluate(c=>({pixels:Array.from(c.getContext('2d').getImageData(0,0,c.width,c.height).data),width:c.getBoundingClientRect().width,height:c.getBoundingClientRect().height}));
 await page.screenshot({path:`test-results/office-pixel/${name}-${theme}.png`});
 }
 await page.getByRole('button',{name:/Developer/}).first().click(); await page.waitForTimeout(300);
 await page.screenshot({path:`test-results/office-pixel/${name}-inspector.png`});
 states.inspector=await page.locator('.ai').evaluate(e=>({width:e.getBoundingClientRect().width,height:e.getBoundingClientRect().height}));
 results.push(states); await page.close();
 }
 const difference = theme => { const a=results[0][theme],b=results[1][theme]; let differingChannels=0; for(let i=0;i<a.pixels.length;i++) if(a.pixels[i]!==b.pixels[i]) differingChannels++; return {identical:differingChannels===0&&a.width===b.width&&a.height===b.height,differingChannels,referenceSize:[a.width,a.height],nextSize:[b.width,b.height]}; };
 const day=difference('day'),night=difference('night');
 const report={dayCanvasIdentical:day.identical,nightCanvasIdentical:night.identical,day,night,inspector:results.map(r=>r.inspector)};
 await writeFile('test-results/office-pixel/comparison.json',JSON.stringify(report,null,2)); console.log(report);
 if(!report.dayCanvasIdentical||!report.nightCanvasIdentical) throw Error('Canvas differs');
} finally {await browser.close()}
