/* SPDX-License-Identifier: AGPL-3.0-only
   © 2026 Vahini Technologies. Contact: infor@vahinitech.com. Dual-IMU sensing: Indian Patent No. 584433.
   Distributed under GNU AGPL v3.0 only. Third-party notices: /THIRD-PARTY-NOTICES.md · SBOM: /sbom.spdx.json */
/* =========================================================================
   Vahini Engine — deterministic computer-vision analysis (browser)
   Implements the §2A / §4C pipeline: binarize → segment → measure.
   Everything here is REAL geometry computed from the uploaded pixels.
   ========================================================================= */
(function (global) {
'use strict';

/* ---- scoring helpers (verbatim from guide §4C) ------------------------- */
function scoreFromError(error, tolGood, tolBad){
  if (error <= tolGood) return 10;
  if (error >= tolBad)  return 0;
  return 10 * (tolBad - error) / (tolBad - tolGood);
}
function mean(a){ return a.length ? a.reduce((s,x)=>s+x,0)/a.length : 0; }
function std(a){ if(a.length<2) return 0; const m=mean(a); return Math.sqrt(mean(a.map(x=>(x-m)*(x-m)))); }
function cv(a){ const m=mean(a); return m? std(a)/Math.abs(m) : Infinity; }
function median(a){ if(!a.length) return 0; const b=[...a].sort((x,y)=>x-y); const n=b.length; return n%2? b[(n-1)/2] : (b[n/2-1]+b[n/2])/2; }
function scoreFromConsistency(values, cvGood, cvBad){
  if (values.length<2 || mean(values)===0) return 5;
  return scoreFromError(cv(values), cvGood, cvBad);
}

/* ---- 1. load image to a working canvas (downscale for speed) ----------- */
function toWorkingCanvas(img, maxW){
  maxW = maxW || 1100;
  const scale = Math.min(1, maxW / img.naturalWidth);
  const w = Math.round(img.naturalWidth * scale);
  const h = Math.round(img.naturalHeight * scale);
  const c = document.createElement('canvas'); c.width=w; c.height=h;
  const ctx = c.getContext('2d', { willReadFrequently:true });
  ctx.drawImage(img, 0, 0, w, h);
  return { canvas:c, ctx, w, h, scale };
}

/* ---- 2. grayscale ------------------------------------------------------ */
function grayscale(ctx, w, h){
  const d = ctx.getImageData(0,0,w,h);
  const g = new Float32Array(w*h);
  const p = d.data;
  for (let i=0, j=0; i<p.length; i+=4, j++){
    g[j] = 0.299*p[i] + 0.587*p[i+1] + 0.114*p[i+2];
  }
  return g;
}

/* ---- 3a. Otsu global threshold (§2A.0) --------------------------------- */
function otsuThreshold(gray){
  const hist = new Array(256).fill(0);
  for (let i=0;i<gray.length;i++) hist[gray[i]|0]++;
  const total = gray.length;
  let sum=0; for(let t=0;t<256;t++) sum+=t*hist[t];
  let sumB=0, wB=0, max=-1, thr=127;
  for (let t=0;t<256;t++){
    wB+=hist[t]; if(!wB) continue;
    const wF=total-wB; if(!wF) break;
    sumB+=t*hist[t];
    const mB=sumB/wB, mF=(sum-sumB)/wF;
    const between=wB*wF*(mB-mF)*(mB-mF);
    if (between>max){ max=between; thr=t; }
  }
  return thr;
}

/* ---- 3b. binarize: ink=1. Adaptive mean for uneven light (§2A.0) ------- */
function binarize(gray, w, h, adaptive){
  const ink = new Uint8Array(w*h);
  if (!adaptive){
    const thr = otsuThreshold(gray);
    for (let i=0;i<gray.length;i++) ink[i] = gray[i] < thr ? 1 : 0;
    return { ink, method:'Otsu global', thr };
  }
  // integral-image adaptive mean threshold
  const integ = new Float64Array((w+1)*(h+1));
  for (let y=0;y<h;y++){ let row=0;
    for (let x=0;x<w;x++){ row+=gray[y*w+x]; integ[(y+1)*(w+1)+(x+1)] = integ[y*(w+1)+(x+1)] + row; }
  }
  const r = Math.max(8, Math.round(Math.min(w,h)/22)); // window radius
  const C = 8; // bias
  for (let y=0;y<h;y++){
    const y0=Math.max(0,y-r), y1=Math.min(h-1,y+r);
    for (let x=0;x<w;x++){
      const x0=Math.max(0,x-r), x1=Math.min(w-1,x+r);
      const area=(x1-x0+1)*(y1-y0+1);
      const s = integ[(y1+1)*(w+1)+(x1+1)] - integ[y0*(w+1)+(x1+1)] - integ[(y1+1)*(w+1)+x0] + integ[y0*(w+1)+x0];
      const m = s/area;
      ink[y*w+x] = gray[y*w+x] < (m - C) ? 1 : 0;
    }
  }
  return { ink, method:'Adaptive mean', thr:null };
}

/* ---- 4. connected components (BFS, 8-neighbour) ------------------------ */
function connectedComponents(ink, w, h){
  const label = new Int32Array(w*h).fill(0);
  const comps = [];
  const stack = new Int32Array(w*h);
  let cur = 0;
  for (let s=0;s<ink.length;s++){
    if (!ink[s] || label[s]) continue;
    cur++; let sp=0; stack[sp++]=s; label[s]=cur;
    let minx=w,miny=h,maxx=0,maxy=0,area=0,sumx=0,sumy=0;
    while (sp){
      const p=stack[--sp];
      const x=p%w, y=(p/w)|0;
      area++; sumx+=x; sumy+=y;
      if(x<minx)minx=x; if(x>maxx)maxx=x; if(y<miny)miny=y; if(y>maxy)maxy=y;
      for(let dy=-1;dy<=1;dy++) for(let dx=-1;dx<=1;dx++){
        if(!dx&&!dy) continue;
        const nx=x+dx, ny=y+dy;
        if(nx<0||ny<0||nx>=w||ny>=h) continue;
        const np=ny*w+nx;
        if(ink[np] && !label[np]){ label[np]=cur; stack[sp++]=np; }
      }
    }
    comps.push({ x:minx, y:miny, w:maxx-minx+1, h:maxy-miny+1, area, cx:sumx/area, cy:sumy/area });
  }
  return { label, comps };
}

/* ---- 5. filter noise + group components into text lines ---------------- */
function buildLines(comps, w, h){
  if (!comps.length) return { lines:[], letters:[] };
  // Robust text-height reference via the AREA-WEIGHTED median height.
  // A noisy notebook photo (spiral binding, dotted/dashed rules, broken
  // strokes, texture) yields hundreds of tiny specks that would dominate a
  // plain median — but each speck carries almost no ink. Letters carry far
  // more ink-area, so weighting each component's height by its area lands the
  // estimate squarely on real letters. We exclude huge blobs (binding, boxes)
  // so they can't skew it upward.
  const pageArea = w*h;
  const cand = comps.filter(c => c.h>2 && c.area < pageArea*0.004 && c.w < w*0.5)
                    .map(c => ({h:c.h, a:Math.sqrt(c.area)}))   // sqrt(area): soften giant letters
                    .sort((p,q)=>p.h-q.h);
  let medH = 10;
  if (cand.length){
    const total = cand.reduce((s,p)=>s+p.a, 0);
    let acc=0; for (const p of cand){ acc+=p.a; if (acc >= total/2){ medH=p.h; break; } }
  }
  // keep plausible letter blobs, drop specks, page-spanning blobs, underlines,
  // ruled-guideline dashes and ink-blobs — quality gate (is_bad_component style)
  const letters = comps.filter(c => {
    if (c.h < Math.max(6, medH*0.42) || c.h > medH*3.2) return false; // too small / too tall
    if (c.area < 10 || c.w > w*0.6) return false;                     // noise / page-spanning
    const fill = c.area / Math.max(1, c.w*c.h);                       // ink fill of bounding box
    const aspect = c.w / Math.max(1, c.h);
    if (aspect > 2.6 && c.h < 0.7*medH) return false;                 // horizontal rule / dash / underline
    if (c.h < 0.5*medH && aspect > 1.6) return false;                 // short flat guideline-dash fragment
    // a single letter is never many times wider than the text is tall. A very
    // wide blob is a ruled box, an underline, or bold print merged into one bar
    // (e.g. a boxed form code) — never one handwritten letter. Left in, it gets
    // picked as the "heaviest stroke / roughest letterform" in evidence crops.
    if (c.w > medH*4) return false;                                   // merged multi-glyph bar / box / rule
    // form-field FRAMES & boxes: a wide bounding box with low ink-fill is a
    // ruled rectangle (the box around a printed code/label), not a letter.
    if (c.w > medH*3.4 && fill < 0.34) return false;                  // hollow frame / long ruled box
    if (fill < 0.04 || fill > 0.92) return false;                     // hairline noise / solid blob
    return true;
  });
  if (!letters.length) return { lines:[], letters:[] };
  // sort by y, greedily group into lines by vertical overlap of centres
  const sorted = [...letters].sort((a,b)=>a.cy-b.cy);
  const lineTol = medH*0.7;
  const lines = [];
  sorted.forEach(c=>{
    let placed=null;
    for (const L of lines){ if (Math.abs(c.cy - L.cyMean) < lineTol){ placed=L; break; } }
    if (!placed){ placed={ boxes:[], cyMean:c.cy }; lines.push(placed); }
    placed.boxes.push(c);
    placed.cyMean = mean(placed.boxes.map(b=>b.cy));
  });
  lines.forEach(L=>L.boxes.sort((a,b)=>a.x-b.x));
  // Trim far-isolated outliers: a component sitting many text-heights away from
  // the rest of its row — with empty space between — belongs to another column
  // or is stray form furniture (e.g. a preprinted code sharing the writer's
  // baseline). Left in, it stretches a line's crop across unrelated content AND
  // corrupts the baseline fit. Real words sit ≤ ~2 text-heights apart, so a
  // 9×-height void only ever separates genuinely unrelated material.
  const GAP = medH*9;
  lines.forEach(L=>{
    if (L.boxes.length < 4) return;
    const clusters=[[L.boxes[0]]];
    for (let i=1;i<L.boxes.length;i++){
      const prev=L.boxes[i-1], cur=L.boxes[i];
      if (cur.x - (prev.x+prev.w) > GAP) clusters.push([cur]);
      else clusters[clusters.length-1].push(cur);
    }
    if (clusters.length>1){
      clusters.sort((a,b)=> b.length-a.length || (b[b.length-1].x-b[0].x)-(a[a.length-1].x-a[0].x));
      L.boxes = clusters[0];
      L.cyMean = mean(L.boxes.map(b=>b.cy));
    }
  });
  lines.sort((a,b)=>a.cyMean-b.cyMean);
  // rebuild the flat letter list from the trimmed lines so dropped strays
  // leave the analysis entirely (not just the crops).
  const keptLetters = [];
  lines.forEach(L=>L.boxes.forEach(b=>keptLetters.push(b)));
  return { lines, letters: keptLetters, medH };
}

/* ---- 6. words within a line (gap thresholding) ------------------------- */
function splitWords(line, medH){
  const words=[]; let cur=[];
  const gapThresh = medH*0.6;
  line.boxes.forEach((b,i)=>{
    if (i>0){ const prev=line.boxes[i-1]; const gap=b.x-(prev.x+prev.w); if (gap>gapThresh){ words.push(cur); cur=[]; } }
    cur.push(b);
  });
  if (cur.length) words.push(cur);
  return words;
}

/* ---- 7. geometry metrics + per-line baseline regression --------------- */
function linReg(xs, ys){
  const n=xs.length; if(n<2) return {m:0,c:ys[0]||0};
  const mx=mean(xs), my=mean(ys);
  let num=0, den=0;
  for(let i=0;i<n;i++){ num+=(xs[i]-mx)*(ys[i]-my); den+=(xs[i]-mx)*(xs[i]-mx); }
  const m = den? num/den : 0; return { m, c: my - m*mx };
}

/* ---- 8. slant via gradient orientation on ink (§4C F17) --------------- */
function slantAngles(gray, ink, w, h){
  const angles=[];
  for (let y=1;y<h-1;y++) for (let x=1;x<w-1;x++){
    if(!ink[y*w+x]) continue;
    const gx = gray[y*w+x+1]-gray[y*w+x-1];
    const gy = gray[(y+1)*w+x]-gray[(y-1)*w+x];
    const mag = Math.hypot(gx,gy);
    if (mag < 25) continue;
    // stroke direction is perpendicular to gradient
    let a = Math.atan2(gx, -gy) * 180/Math.PI; // 0 = vertical upstroke
    if (a<0) a+=180;
    // fold to signed deviation from vertical, keep near-vertical strokes
    let dev = a - 90;
    if (Math.abs(dev) < 65) angles.push(dev);
  }
  return angles;
}

/* ---- 8b. shear-search deslant (robust slant, adapted from the public
   projection-profile method, e.g. PPS/Manmatha deslanting) --------------
   For a region of ink we shear the columns at a set of candidate angles and
   keep the angle whose vertical projection has the strongest vertical strokes
   (tall, solid columns). This is far more robust on cursive than per-pixel
   gradients, and gives ONE dominant slant per word — so the spread across
   words is a clean measure of slant consistency (F17) & uprightness (F12). */
const SHEAR_ANGLES = [-42,-32,-22,-14,-7,0,7,14,22,32,42]; // degrees
function slantOfRegion(ink, w, x0, x1, y0, y1){
  const H = y1 - y0;
  if (H < 6 || (x1 - x0) < 3) return null;
  const yMid = (y0 + y1) / 2;
  const strongFrac = 0.34 * H;          // a "vertical stroke" fills >~1/3 of the row height
  let bestScore = -1, bestAng = 0, found = false;
  for (const deg of SHEAR_ANGLES){
    const t = Math.tan(deg * Math.PI/180);
    const cols = new Float64Array(w + H + 2);
    const off = Math.ceil(Math.abs(t) * H) + 1;
    for (let y=y0; y<y1; y++){
      const shift = Math.round(t * (y - yMid));
      const row = y*w;
      for (let x=x0; x<x1; x++){
        if (ink[row + x]) cols[x + shift + off] += 1;
      }
    }
    let score = 0;
    for (let i=0;i<cols.length;i++){ if (cols[i] >= strongFrac) score += cols[i]*cols[i]; }
    if (score > bestScore){ bestScore = score; bestAng = deg; found = true; }
  }
  return found ? bestAng : null;
}
function slantByShear(ink, w, h, lines, medH){
  const perWord = [];
  lines.forEach(L=>{
    (L.words || []).forEach(word=>{
      const x0=Math.min(...word.map(b=>b.x));
      const x1=Math.max(...word.map(b=>b.x+b.w));
      const y0=Math.min(...word.map(b=>b.y));
      const y1=Math.max(...word.map(b=>b.y+b.h));
      if ((x1-x0) < medH*0.8) return;            // need enough width to judge a slant
      const a = slantOfRegion(ink, w, x0, x1, y0, y1);
      if (a !== null) perWord.push(a);
    });
  });
  return perWord;
}

/* ---- MAIN: analyse an HTMLImageElement -> metrics + overlay ------------ */
/* Detect the bright paper rectangle via row/column brightness projections.
   Returns a slightly-inset box, or null if the page fills the frame (so the
   clean synthetic test images are unaffected). */
function detectPageBox(gray, w, h){
  // bright threshold = midpoint between mean and max brightness
  let sum=0, mx=0; for(let i=0;i<gray.length;i++){ sum+=gray[i]; if(gray[i]>mx)mx=gray[i]; }
  const mean0 = sum/gray.length;
  const thr = (mean0 + mx) / 2;
  const rowFrac = new Float32Array(h), colFrac = new Float32Array(w);
  for (let y=0;y<h;y++){ let c=0; const off=y*w; for(let x=0;x<w;x++) if(gray[off+x]>thr) c++; rowFrac[y]=c/w; }
  for (let x=0;x<w;x++){ let c=0; for(let y=0;y<h;y++) if(gray[y*w+x]>thr) c++; colFrac[x]=c/h; }
  const span = (arr, n)=>{ // first/last index where bright fraction is substantial
    let a=-1,b=-1; for(let i=0;i<n;i++){ if(arr[i]>0.45){ if(a<0)a=i; b=i; } }
    return [a,b];
  };
  const [y0,y1] = span(rowFrac,h), [x0,x1] = span(colFrac,w);
  if (x0<0||y0<0) return null;
  const bw=x1-x0, bh=y1-y0;
  // only crop if the bright region is a clear sub-region of the frame
  if (bw > w*0.95 && bh > h*0.95) return null;
  if (bw < w*0.25 || bh < h*0.25) return null;       // too small → unreliable, skip
  const padX = Math.round(bw*0.015), padY = Math.round(bh*0.015);
  return { x0:Math.max(0,x0+padX), y0:Math.max(0,y0+padY), x1:Math.min(w-1,x1-padX), y1:Math.min(h-1,y1-padY) };
}

function analyze(img){
  const work = toWorkingCanvas(img);
  const { ctx, w, h } = work;
  const gray = grayscale(ctx, w, h);
  // pick path: adaptive if the image looks unevenly lit
  const corners = [gray[0], gray[w-1], gray[(h-1)*w], gray[h*w-1]];
  const uneven = (Math.max(...corners)-Math.min(...corners)) > 45;
  const bin = binarize(gray, w, h, uneven);
  // ---- crop to the bright PAGE region so a dark desk, spiral binding, shadows
  // and other surroundings don't get counted as ink. Conservative: only applies
  // when a clear page rectangle smaller than the frame is found.
  const page = detectPageBox(gray, w, h);
  if (page){
    for (let y=0;y<h;y++) for (let x=0;x<w;x++){
      if (x<page.x0 || x>page.x1 || y<page.y0 || y>page.y1) bin.ink[y*w+x] = 0;
    }
  }
  const { label, comps } = connectedComponents(bin.ink, w, h);
  const { lines, letters, medH } = buildLines(comps, w, h);

  // accumulate measurements
  const letterHeights=[], letterWidths=[], wordGaps=[], letterGaps=[];
  const leftX=[], rightX=[], lineSlopesDeg=[], baselineRMSnorm=[];
  let wordCount=0, charCount=0;
  const wordBoxesAll=[];

  // ---- printed vs handwritten -------------------------------------------
  // A SINGLE neat handwriting sample is geometrically identical to printed text
  // (same uniform heights, same straight baseline), so a per-line classifier
  // alone wrongly flags clean handwriting. Instead we detect a MIXED page: only
  // when the page also contains genuinely hand-varied lines do we strip the
  // print-like ones. A uniform page is treated wholly as handwriting.
  const cvOf = (a)=>{ const m=mean(a); return m? std(a)/m : 0; };
  lines.forEach(L=>{
    const hs = L.boxes.map(b=>b.h);
    const sw = L.boxes.map(b=>b.area/Math.max(1,(b.w+b.h)));
    const xs0=L.boxes.map(b=>b.cx), ys0=L.boxes.map(b=>b.y+b.h);
    const reg = linReg(xs0, ys0);
    const pred = xs0.map(x=>reg.m*x+reg.c);
    // ROTATION-INVARIANT straightness: residual of letter-bottoms off the fitted
    // baseline (÷ medH). A tilted photo leaves printed lines tight here even when
    // their raw slope is non-zero, so this beats a slope threshold.
    L._hsCV = cvOf(hs);
    L._swCV = cvOf(sw);
    L._mh   = median(hs);   // typical letter height on this line (script-robust size cue)
    L._rms  = Math.sqrt(mean(ys0.map((y,i)=>(y-pred[i])*(y-pred[i])))) / Math.max(1, medH);
  });
  // genuinely handwritten lines = wavy baseline OR uneven letter heights
  const handLinesRef = lines.filter(L => L.boxes.length>=4 && (L._hsCV>=0.30 || L._rms>=0.22));
  const handVaried = handLinesRef.length;
  // Size-bimodality catch: some mixed pages have only 1-2 handwritten lines,
  // so variance-only gating can miss them. If we see a clear small-text band
  // (print/labels) and a clear larger-text band (handwriting), treat as mixed.
  const smallBand = lines.filter(L=>L.boxes.length>=4 && L._mh < medH*0.72).length;
  const largeBand = lines.filter(L=>L.boxes.length>=4 && L._mh > medH*0.92).length;
  const mixedBySize = smallBand >= 2 && largeBand >= 1;
  const mixedPage = handVaried >= 2 || mixedBySize;
  // reference size of the ACTUAL handwriting on this page — printed letterhead /
  // footer / table text is almost always set markedly smaller than the hand.
  const largeRef = lines.filter(L=>L.boxes.length>=4 && L._mh > medH*0.92);
  const handMH = handVaried
    ? median(handLinesRef.map(L=>L._mh))
    : (largeRef.length ? median(largeRef.map(L=>L._mh)) : medH);
  lines.forEach(L=>{
    const enough = L.boxes.length >= 5;
    // Path A — classic machine print (Latin letterhead, table rules): letters sit
    //   tight on a straight baseline with even strokes.
    const printA = enough && L._rms < 0.16 && L._swCV < 0.34;
    // Path B — SIZE-led, script-robust. Printed Telugu (and small English print)
    //   often shows a wavy baseline only because conjuncts / vowel-signs add
    //   vertical extent, so Path A misses it. Instead key on: clearly SMALLER than
    //   the handwriting + even stroke width + even letter height. This catches the
    //   printed header & footer lines without touching the larger hand-written body.
    const small = L._mh < handMH*0.66;
    const printB = enough && small && L._swCV < 0.42 && L._hsCV < 0.34 && L._rms < 0.45;
    // In mixed pages, both print signatures are valid.
    // In uncertain pages, keep only the size-led print path so small printed
    // headers/labels are still removed without over-flagging neat handwriting.
    L.printed = mixedPage ? (printA || printB) : printB;
  });
  const handwrittenLines = lines.filter(L=>!L.printed);
  const printedCount = lines.length - handwrittenLines.length;
  // If mixed content is detected, always keep handwritten-only lines as long as
  // at least one handwritten line survived. This prevents printed text leaking
  // into factors on short form-style samples (1-2 handwritten lines).
  const usePrintedFilter = printedCount > 0 && handwrittenLines.length >= 1;
  const printedLines = usePrintedFilter ? printedCount : 0;
  const scoreLines = usePrintedFilter ? handwrittenLines : lines;
  // Flat list of ONLY the handwritten letters — every crop / per-letter factor
  // reads this, so printed characters never leak into the analysis or evidence.
  const scoreLetters = [];
  scoreLines.forEach(L=>{ if(L.boxes) L.boxes.forEach(b=>scoreLetters.push(b)); });

  scoreLines.forEach(L=>{
    L.boxes.forEach(b=>{ letterHeights.push(b.h); letterWidths.push(b.w); });
    // baseline regression on letter bottoms
    const xs=L.boxes.map(b=>b.cx), ysB=L.boxes.map(b=>b.y+b.h);
    const reg = linReg(xs, ysB);
    const pred = xs.map(x=>reg.m*x+reg.c);
    const rms = Math.sqrt(mean(ysB.map((y,i)=>(y-pred[i])*(y-pred[i]))));
    baselineRMSnorm.push(rms/Math.max(1,medH));
    lineSlopesDeg.push(Math.atan(reg.m)*180/Math.PI);   // SIGNED — deskewed below
    leftX.push(Math.min(...L.boxes.map(b=>b.x)));
    rightX.push(Math.max(...L.boxes.map(b=>b.x+b.w)));
    L.reg = reg;
    // words
    const words = splitWords(L, medH);
    L.words = words; wordCount += words.length;
    words.forEach(word=>{
      const wx0=Math.min(...word.map(b=>b.x)), wx1=Math.max(...word.map(b=>b.x+b.w));
      const wy0=Math.min(...word.map(b=>b.y)), wy1=Math.max(...word.map(b=>b.y+b.h));
      wordBoxesAll.push({x:wx0,y:wy0,w:wx1-wx0,h:wy1-wy0});
      // intra-word letter gaps
      for(let i=1;i<word.length;i++){ letterGaps.push(word[i].x-(word[i-1].x+word[i-1].w)); }
    });
    charCount += L.boxes.length;
    // inter-word gaps
    for(let i=1;i<words.length;i++){
      const a=words[i-1], b=words[i];
      const ar=Math.max(...a.map(x=>x.x+x.w)), bl=Math.min(...b.map(x=>x.x));
      wordGaps.push(bl-ar);
    }
  });

  /* ---- AUTO-DESKEW (review item: hand-held phone tilt) ------------------
     A photo shot by hand is almost never perfectly square to the page, so EVERY
     text line shares a small common tilt. That camera tilt is not the writer's
     fault and must not score against them on Line Straightness (F11). We measure
     the page's dominant skew as the MEDIAN signed line slope (robust to a few
     genuinely crooked lines) and subtract it, so each line's slope is now measured
     relative to the page's own axis — i.e. the page is straightened first, then
     judged. Baseline-RMS and slant are already rotation-invariant, so this is the
     honest, low-risk place to correct tilt. */
  const pageSkewDeg = lineSlopesDeg.length ? median(lineSlopesDeg) : 0;
  for (let i=0;i<lineSlopesDeg.length;i++) lineSlopesDeg[i] = Math.abs(lineSlopesDeg[i] - pageSkewDeg);

  const xHeight = median(letterHeights) || medH || 10;

  // zone ratios: classify letters by extent vs line baseline/x-height band
  let upper=0, lowerN=0, mid=0, zoneTot=0;
  scoreLines.forEach(L=>{
    if(!L.reg) return;
    const bodyTop = L.cyMean - xHeight*0.5;
    L.boxes.forEach(b=>{
      const base = L.reg.m*b.cx + L.reg.c;
      if (b.y < bodyTop - xHeight*0.35) upper++;
      if (b.y+b.h > base + xHeight*0.35) lowerN++;
      mid++; zoneTot++;
    });
  });

  // ink intensity variation (pressure proxy, §4C F14)
  const inkVals=[];
  for(let i=0;i<bin.ink.length;i++) if(bin.ink[i]) inkVals.push(gray[i]);
  // stroke width proxy from area/perimeter-ish: area / total ink-bbox length
  const strokeWidths = scoreLetters.map(c=>c.area/Math.max(1,(c.w+c.h)));
  // loop closure: count components with interior holes via euler-ish (holes = background pockets)
  const loopRatio = estimateLoopClosure(bin.ink, label, comps, w, h, scoreLetters);
  // F12 vertical-alignment keeps the per-pixel scatter; F17 slant-consistency
  // uses the more robust per-word shear-search angles when available.
  const slant = slantAngles(gray, bin.ink, w, h);
  const slantWord = slantByShear(bin.ink, w, h, scoreLines, medH);
  const slantMethod = slantWord.length >= 4 ? 'shear-search (per word)' : 'gradient (per pixel)';

  // tiny ink marks (dots, commas, dashes) — too small for the letter gate but
  // needed by the punctuation audit in letters.js
  const smallMarks = comps.filter(c => c.h <= Math.max(3, medH*0.5) && c.w <= medH*1.2 && c.area >= 3 && c.area <= medH*medH*0.5);

  const overlay = { w, h, scale:work.scale, lines, scoreLines, words:wordBoxesAll, letters:scoreLetters, smallMarks, canvas:work.canvas, ink:bin.ink, binMethod:bin.method };

  const docType = classifyDocument(comps, letters, scoreLines, wordCount, charCount, w, h, medH, printedLines);

  /* ---- sample-quality validity gate (review item: retake guidance) ---- */
  const quality = (()=>{
    const issues=[], tips=[];
    const srcW = (img.naturalWidth||w);
    if (charCount < 30){ issues.push('Short sample — only '+charCount+' letters found'); tips.push('Write 3–4 full lines for a confident read'); }
    if (scoreLines.length < 2){ issues.push('Only one line of handwriting detected'); tips.push('Multiple lines let us measure margins and line spacing'); }
    if (srcW < 900){ issues.push('Low photo resolution ('+srcW+'px wide)'); tips.push('Move closer or use the rear camera — fill the frame with the writing'); }
    if (uneven){ issues.push('Uneven lighting / shadow detected (compensated)'); tips.push('Face a window or lamp so light falls evenly'); }
    if (xHeight && xHeight < 9){ issues.push('Writing appears very small in the photo'); tips.push('Photograph from closer so letters are larger'); }
    const grade = issues.length===0 ? 'Good' : issues.length===1 ? 'Usable' : 'Limited';
    return { grade, issues, tips };
  })();

  /* ---- VALIDITY GATE: reject non-handwriting / insufficient samples ------
     A photo of a desk, floor, a couple of scribbled numbers, a crumpled page
     or a blurry shot gets binarised into hundreds of specks (creases, shadows,
     texture) that masquerade as "letters". The tell-tale signs:
       • token length ~1 char  → each "word" is a single mark, not a real word
       • dozens of fragmented lines, most holding only 1–2 marks
       • too little genuine ink to measure 20 factors at all
     Genuine handwriting (even a short, neat 2–3 line sample) clears every test:
     its words average 3+ letters and its lines hold several letters each.
     We REFUSE rather than emit a confident-looking but meaningless report. */
  const validity = (()=>{
    const tokenLen = charCount / Math.max(1, wordCount);          // letters per word
    const lettersPerLine = charCount / Math.max(1, scoreLines.length);
    const smallLines = scoreLines.filter(L => (L.boxes ? L.boxes.length : 0) < 3).length;
    const smallLineFrac = scoreLines.length ? smallLines/scoreLines.length : 1;

    /* ---- ACCEPT OVERRIDE -------------------------------------------------
       Genuine handwriting — even messy, slanted, on a creased or spiral page —
       carries a lot of real ink: many characters spread across real words and
       lines. Photos of a desk, a couple of scribbled numbers or pure texture
       never do. If a sample shows substantial connected ink, we ACCEPT it and
       skip the rejection heuristics entirely, so a real page is never bounced
       just because creases or ruling added a few noisy "lines". */
    const looksLikeWriting =
      (charCount >= 55 && wordCount >= 8 && tokenLen >= 1.7) ||   // a real paragraph
      (charCount >= 90 && lettersPerLine >= 3.2) ||               // lots of ink per line
      (wordCount >= 14 && tokenLen >= 2.0) ||                     // many genuine words
      (scoreLines.length >= 8 && wordCount >= 24 && lettersPerLine >= 1.8); // a full, multi-line written page (dim/low-contrast capture still reads as handwriting)

    let reason=null, detail=null;
    if (charCount < 14 || scoreLines.length < 2){
      reason = "Not enough handwriting to analyse";
      detail = "We could only find a few clear marks. The 20-factor report needs at least a couple of full lines of handwriting.";
    } else if (looksLikeWriting){
      /* clearly a page of handwriting — never reject */
    } else if (tokenLen < 1.25){
      reason = "This doesn't look like handwritten words";
      detail = "The marks read as isolated dots, digits or texture rather than connected words — typically a photo that isn't a page of handwriting, or a very noisy/creased shot.";
    } else if (scoreLines.length > 45 && tokenLen < 2.0 && smallLineFrac > 0.78){
      reason = "Couldn't find a clean page of handwriting";
      detail = "We picked up scattered specks (paper creases, shadows or background) instead of real text lines. Photograph a flat, well-lit page of handwriting up close.";
    } else if (scoreLines.length > 22 && smallLineFrac > 0.8 && tokenLen < 1.8){
      reason = "Handwriting is too fragmented to score";
      detail = "Most detected lines hold only one or two marks, which usually means noise or stray jottings rather than a page of writing.";
    }
    return {
      rejected: reason != null,
      reason, detail,
      tips: [
        "Use a flat, well-lit page with a few full lines of handwriting",
        "Fill the frame with the writing — avoid the desk, floor or background",
        "Hold the camera square to the page and keep it sharp",
      ],
      signals: { tokenLen:+tokenLen.toFixed(2), lettersPerLine:+lettersPerLine.toFixed(1), nLines:scoreLines.length, smallLineFrac:+smallLineFrac.toFixed(2) },
    };
  })();

  const metrics = {
    ok: charCount >= 8 && scoreLines.length >= 1,
    reject: validity,
    quality,
    w, h, nLines:scoreLines.length, nWords:wordCount, nChars:charCount, printedLines,
    xHeight, medH, docType, pageSkewDeg:+pageSkewDeg.toFixed(1),
    letterHeights, letterWidths, wordGaps, letterGaps, leftX, rightX,
    lineSlopesDeg, baselineRMSnorm,
    wordGapNorm: wordGaps.map(g=>g/xHeight),
    letterGapNorm: letterGaps.map(g=>g/xHeight),
    zoneUpper: zoneTot? upper/zoneTot : 0,
    zoneLower: zoneTot? lowerN/zoneTot : 0,
    inkIntensity: inkVals, strokeWidths, loopRatio,
    slant, slantWord, slantMethod, binMethod: bin.method, adaptive: uneven,
  };
  return { metrics, overlay };
}

/* -------------------------------------------------------------------------
   Document-type classifier (coarse, geometry-only — honest by design).
   Distinguishes connected prose (where the engine is most accurate) from
   sparse answers, numeric/symbolic content, and pages containing figures.
   It does NOT read the text; it reasons from layout statistics only.
   ------------------------------------------------------------------------- */
function classifyDocument(comps, letters, lines, nWords, nChars, w, h, medH, printedLines){
  const pageArea = w*h;
  // large connected regions that aren't text-sized → likely diagrams/figures.
  // Ignore the spiral-binding edges (outer ~12% left/right) and the top header
  // band so binding rings / a "NOTES" header don't masquerade as figures.
  const bigBlobs = comps.filter(c => {
    const cx = c.x + c.w/2;
    if (cx < w*0.12 || cx > w*0.88) return false;   // binding / margin furniture
    if (c.y + c.h < h*0.08) return false;            // top header strip
    return (c.w > w*0.5 && c.h > medH*3) ||          // a wide interior band (true figure / table)
           (c.area > pageArea*0.04 && c.w > medH*5 && c.h > medH*5);  // a big solid drawing
  }).length;
  const nLines = lines.length;
  const wordsPerLine = nWords / Math.max(1, nLines);
  const avgTokenLen  = nChars / Math.max(1, nWords);     // letters per "word" token
  const inkRatio = letters.reduce((s,c)=>s+c.area,0) / pageArea;

  let key, label, accuracy, note;
  const printedTag = printedLines>0 ? ` ${printedLines} printed line${printedLines>1?'s':''} (letterhead/table) were detected and excluded; only the handwriting was scored.` : '';
  if (nChars < 8 || nLines === 0){
    key='sparse'; label='Sparse / very short sample';
    accuracy='Indicative only';
    note='Too few marks for reliable scoring. Upload a few full lines of handwriting for an accurate read.'+printedTag;
  } else if (printedLines >= 1){
    key='mixed'; label='Mixed printed + handwritten';
    accuracy='Handwriting only';
    note=`This page mixes printed text with handwriting.${printedTag} The scores describe the handwriting alone.`;
  } else if (bigBlobs >= 3){
    key='figures'; label='Text with diagrams / figures';
    accuracy='Reduced — figures excluded';
    note='Large non-text regions (diagrams, sketches, boxes) were detected and ignored. Scores reflect only the handwritten text on the page; figures are not assessed.';
  } else if (avgTokenLen <= 1.8 && wordsPerLine <= 5 && nLines <= 14){
    key='symbolic'; label='Numeric / symbolic (equations, short tokens)';
    accuracy='Reduced — tuned for prose';
    note='Many short, isolated tokens were found (typical of equations, numbers or one-word answers). The engine is calibrated for connected prose, so spacing, baseline and slant factors are less reliable here.';
  } else if (nLines <= 3 && nWords <= 10){
    key='short'; label='Short answers / few lines';
    accuracy='Moderate';
    note='A small but usable sample. More lines of continuous handwriting improve accuracy, especially for spacing and margin factors.'+printedTag;
  } else {
    key='prose'; label='Handwritten prose';
    accuracy='High (intended use)';
    note='Connected, multi-line handwriting — the content type the engine is designed and calibrated for.'+printedTag;
  }
  return { key, label, accuracy, note, printedLines:printedLines||0, signals:{ bigBlobs, nLines, nWords, wordsPerLine:+wordsPerLine.toFixed(1), avgTokenLen:+avgTokenLen.toFixed(1), inkRatio:+inkRatio.toFixed(3) } };
}

/* loop closure estimate: a letter with an enclosed counter has a background
   pocket fully surrounded by its ink (§4C F3). Approximate by flood-filling
   background from image border; un-reached background inside letter bboxes
   that touch ink = holes. */
function estimateLoopClosure(ink, label, comps, w, h, letters){
  const bg = new Uint8Array(w*h); // 1 = background reachable from border
  const stack=[]; 
  for(let x=0;x<w;x++){ stack.push(x); stack.push((h-1)*w+x); }
  for(let y=0;y<h;y++){ stack.push(y*w); stack.push(y*w+w-1); }
  while(stack.length){
    const p=stack.pop(); if(ink[p]||bg[p]) continue; bg[p]=1;
    const x=p%w,y=(p/w)|0;
    if(x>0)stack.push(p-1); if(x<w-1)stack.push(p+1);
    if(y>0)stack.push(p-w); if(y<h-1)stack.push(p+w);
  }
  let withHole=0, eligible=0;
  letters.forEach(c=>{
    if (c.w<6||c.h<6) return;
    eligible++;
    let hole=false;
    for(let y=c.y; y<c.y+c.h && !hole; y++)
      for(let x=c.x; x<c.x+c.w; x++){
        const p=y*w+x;
        if(!ink[p] && !bg[p]){ hole=true; break; } // interior background pocket
      }
    if(hole) withHole++;
  });
  return eligible? withHole/eligible : 0.9;
}

global.VahiniEngine = { analyze, scoreFromError, scoreFromConsistency, mean, std, cv, median };
})(window);
