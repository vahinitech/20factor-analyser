/* SPDX-License-Identifier: AGPL-3.0-only
   (c) 2026 Vahini Technologies. */
// Real PDF.js module + worker; synthetic two-page PDF; no OCR required.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { chromium } from 'playwright';

const source = await readFile('frontend/src/app/app.js', 'utf8');
const helper = source.slice(source.indexOf('let pdfJsPromise = null;'), source.indexOf('\nfunction showSample('));
const urls = [...new Set(helper.match(/https:\/\/[^' ]+\.mjs/g))];
assert.equal(urls.length, 2);
const assets = new Map(await Promise.all(urls.map(async url=>{
  const response = await fetch(url);
  assert.ok(response.ok, `Cannot load ${url}`);
  return [url, await response.text()];
})));

function syntheticPdf(){
  const stream = '0 0 0 rg 20 20 100 20 re f\n';
  const objects = [
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 100] /Resources << >> /Contents 5 0 R >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 200] /Resources << >> /Contents 5 0 R >>',
    `<< /Length ${stream.length} >>\nstream\n${stream}endstream`,
  ];
  let pdf = '%PDF-1.4\n';
  const offsets = [0];
  objects.forEach((object, i)=>{ offsets.push(pdf.length); pdf += `${i+1} 0 obj\n${object}\nendobj\n`; });
  const xref = pdf.length;
  pdf += `xref\n0 6\n0000000000 65535 f \n${offsets.slice(1).map(n=>`${String(n).padStart(10,'0')} 00000 n \n`).join('')}trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`;
  return [...Buffer.from(pdf)];
}

const browser = await chromium.launch();
try {
  const context = await browser.newContext();
  await context.route('http://pdf-test.local/**', route=>route.fulfill({contentType:'text/html',body:'<!doctype html><body></body>'}));
  await context.route('https://cdn.jsdelivr.net/**', route=>{
    const body = assets.get(route.request().url());
    assert.ok(body, `Unexpected PDF asset ${route.request().url()}`);
    return route.fulfill({contentType:'text/javascript',headers:{'access-control-allow-origin':'*'},body});
  });
  const page = await context.newPage();
  await page.goto('http://pdf-test.local/');
  await page.addScriptTag({content:helper+'\nwindow.renderPdfForTest = pdfFirstPageToImage;'});
  const result = await page.evaluate(async bytes=>{
    const outputs = [];
    for (let i=0;i<3;i++){
      const result = await window.renderPdfForTest(new File([new Uint8Array(bytes)],'synthetic.pdf',{type:'application/pdf'}));
      const canvas = document.createElement('canvas');
      canvas.width = result.img.width; canvas.height = result.img.height;
      const ctx=canvas.getContext('2d'); ctx.drawImage(result.img,0,0);
      outputs.push({pages:result.pages,width:canvas.width,height:canvas.height,ink:ctx.getImageData(50,140,1,1).data[0]});
    }
    let rejected = false;
    try { await window.renderPdfForTest(new File(['invalid'],'bad.pdf')); } catch { rejected=true; }
    return {outputs,rejected};
  }, syntheticPdf());
  for (const output of result.outputs) assert.deepEqual(output,{pages:2,width:400,height:200,ink:0});
  assert.equal(result.rejected,true);
  console.log('PASS PDF upload: real module/worker, first page, three repeated uploads, malformed PDF rejection.');
} finally { await browser.close(); }

