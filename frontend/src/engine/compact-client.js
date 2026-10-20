/* SPDX-License-Identifier: AGPL-3.0-only */
/* Shared browser/JavaScript-app decoder. Access is enforced by the server. */
(function(global){
  'use strict';
  const catalogs=new Map();
  function decode(report,catalog){
    if(report.schema_version!=='2.1'||report.format!=='compact'||report.catalog_version!==catalog.version)throw new Error('Unsupported report dictionary version');
    if(!report.ok)return {ok:false,error_code:report.error?.code||'analysis_failed',error:'The handwriting sample could not be analysed.',analysis:null};
    const seen=new Set();
    const results=report.factors.map(row=>{
      const definition=catalog.factors.find(f=>f.n===row.n),status=catalog.statuses[row.st];
      if(!definition||!status||seen.has(row.n))throw new Error('Invalid compact factor');
      seen.add(row.n);
      if(row.s!==null&&(!Number.isFinite(row.s)||row.s<0||row.s>10))throw new Error('Invalid compact score');
      const band=row.s===null?null:catalog.bands.find(b=>row.s>=b.minimum)?.id;
      const detail=report.inputs?.[String(row.n)];
      return {n:row.n,sec:definition.section,name:definition.name,score:row.s,score100:row.s===null?null:Math.round(row.s*10),band,conf:status==='measured'?'measured':'estimated',unmeasured:status==='unavailable'||row.s===null,imuMeasured:status==='measured',evidence:(detail?.evidence||('Image-based '+definition.reason+'.'+(band?' Score band: '+band+'.':'')))+(definition.limitation?' '+definition.limitation:''),basedOn:detail?.basis||null,ex:definition.exercise,target:definition.target,tip:definition.instruction,value:row.s===null?'':String(Math.round(row.s*10))+'/100'};
    });
    const available=results.filter(f=>!f.unmeasured),sections=catalog.sections.map(s=>{
      const factors=available.filter(f=>f.sec===s.id),avg=factors.length?factors.reduce((n,f)=>n+f.score,0)/factors.length:null;
      return {...s,blurb:'',factors,avg,avg100:avg===null?null:Math.round(avg*10),scoredCount:factors.length};
    }).filter(s=>s.scoredCount);
    const access={...report.access,capabilities:{factor_numbers:results.map(f=>f.n),personalised_worksheets:report.access.tier==='pro'}};
    return {ok:true,access,full_text:report.text||'',counts:report.counts,engine:'server',analysis:{access,results,sections,practice:practiceOf(catalog),recognition:report.recognition||null,comparability:report.comparability||null,overall:report.summary.score,overallMeasured:report.summary.score,measuredCount:available.length,topWeak:[...available].sort((a,b)=>a.score-b.score).slice(0,3),topStrong:[...available].sort((a,b)=>b.score-a.score).slice(0,4),coachTips:report.coaching||[],source:'python'},factor_regions:report.evidence?.factor_regions||{},measurements:report.evidence?.measurements||{},document_context:null,regions:[],layout:{}};
  }
  // The practice catalogue served with this dictionary version (#122):
  // stages, tries by band, tier defaults and each factor's exercises and
  // tips, and (from 2026-10-11) why each skill helps, the win to look for
  // and its website page. Older dictionaries have none; the report then
  // uses its own copy.
  function practiceOf(catalog){
    if(!catalog.practice)return null;
    const factors={};
    const about=f=>typeof f.why==='string'?{why:f.why,win:f.win,page:f.page,i18n:f.i18n||{}}:{};
    catalog.factors.forEach(f=>{if(Array.isArray(f.exercises))factors[String(f.n)]={...about(f),exercises:f.exercises,tips:Array.isArray(f.tips)?f.tips:[]};});
    return {...catalog.practice,factors};
  }
  async function expand(report,endpoint){
    const version=report.catalog_version;
    if(!/^[a-f0-9]{20}$/.test(version))throw new Error('Invalid report dictionary');
    if(!catalogs.has(version)){
      const url=new URL('/api/v2/catalog/'+version,new URL(endpoint,global.location.href));
      const response=await fetch(url,{cache:'force-cache'});
      if(!response.ok)throw new Error('Report definitions could not be loaded');
      const catalog=await response.json();
      if(catalog.version!==version)throw new Error('Report dictionary mismatch');
      catalogs.set(version,catalog);
    }
    return decode(report,catalogs.get(version));
  }
  global.VahiniCompact={decode,expand};
})(typeof window==='undefined'?globalThis:window);
