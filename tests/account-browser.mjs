/* SPDX-License-Identifier: AGPL-3.0-only */
import {chromium} from 'playwright';
import {spawn} from 'node:child_process';
import assert from 'node:assert/strict';
const server=spawn('./node_modules/.bin/http-server',['.','-p','4187','-c-1','--silent']);
let browser;
try {
 for(let i=0;i<60;i++){try{if((await fetch('http://127.0.0.1:4187/')).ok)break;}catch{}await new Promise(r=>setTimeout(r,100));}
 browser=await chromium.launch();const page=await browser.newPage({viewport:{width:390,height:844}});
 await page.route('**/api/v2/me',route=>route.fulfill({json:{access:{tier:route.request().headers().authorization?'pro':'free'}}}));
 let request;
 await page.route('**/api/v2/reports?**',route=>{request=route.request();return route.fulfill({json:{ok:false,error_code:'no_handwriting',error:'Synthetic empty sample'}});});
 await page.goto('http://127.0.0.1:4187/frontend/analyser.html',{waitUntil:'networkidle'});
 await page.getByText('Have a Vahini access key?',{exact:true}).click();
 await page.locator('#account-key').fill('vh_synthetic_browser_test');
 await page.getByRole('button',{name:'Connect account',exact:true}).click();
 await page.waitForFunction(()=>document.querySelector('#account-access [role="status"]').textContent.includes('Pro connected'));
 assert.equal(await page.locator('#account-key').inputValue(),'');
 await page.evaluate(()=>VahiniOCR.serverPythonReport(new Blob(['synthetic']),'test'));
 assert.equal(request.headers().authorization,'Bearer vh_synthetic_browser_test');
 assert.equal(new URL(request.url()).searchParams.get('include'),'text,inputs,coaching,evidence');
 assert.equal(await page.evaluate(()=>Object.values(localStorage).some(value=>value.includes('vh_synthetic'))),false);
 await page.locator('#account-access').screenshot({path:'screenshots/account-access-mobile.png'});
 await page.getByRole('button',{name:'Disconnect',exact:true}).click();
 await page.evaluate(()=>VahiniOCR.serverPythonReport(new Blob(['synthetic']),'test'));
 assert.equal(request.headers().authorization,undefined);
 assert.equal(new URL(request.url()).searchParams.get('include'),'text');
 console.log('PASS browser key handoff, Pro fields, cleared input, no persisted key and Free after disconnect');
} finally {if(browser)await browser.close();server.kill();}
