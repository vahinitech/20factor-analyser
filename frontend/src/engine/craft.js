/* SPDX-License-Identifier: AGPL-3.0-only
   © 2026 Vahini Technologies. Contact: info@vahinitech.com. Dual-IMU sensing: Indian Patent No. 584433.
   Distributed under GNU AGPL v3.0 only. Third-party notices: /THIRD-PARTY-NOTICES.md · SBOM: /sbom.spdx.json */
/* =========================================================================
   Vahini Writing Craft: content-level guidance that ADAPTS to what was
   actually written. The upload may be an English letter, an essay, maths,
   science notes, or another language entirely: so the section reshapes
   itself instead of always assuming a formal letter.
   Rule-based + high-precision: a flagged issue is almost always real.
   ========================================================================= */
(function (global) {
'use strict';

/* ---- English grammar / homophone / sign-off rules (run for prose+letter) */
const RULES = [
  { cat:'Grammar & phrasing', sev:'fix',
    re:/look(?:ing)?\s+forward\s+to\s+(hear|see|meet|work|receiv|speak|talk)\b(?!ing)/i,
    msg:'After “look forward to”, use the “-ing” form.',
    fix:(m)=>`“look forward to ${m[1]}…” → “look forward to ${m[1].replace(/e$/,'')}ing…”` },
  { cat:'Grammar & phrasing', sev:'fix',
    re:/\b(must|should|can|could|may|might|will|would|shall)\s+to\s+(\w+)/i,
    msg:'Don’t put “to” after a modal verb (must, should, can…).',
    fix:(m)=>`“${m[1]} to ${m[2]}” → “${m[1]} ${m[2]}”` },
  { cat:'Grammar & phrasing', sev:'check',
    re:/\b(it was|it is)\s+(pleasure|honour|honor|privilege)\b/i,
    msg:'A missing article: add “a”.',
    fix:(m)=>`“${m[1]} ${m[2]}” → “${m[1]} a ${m[2]}”` },
  { cat:'Homophones', sev:'check',
    re:/\byour\s+(welcome|going|doing|right|wrong|the best)\b/i,
    msg:'Likely “you’re” (you are), not “your”.',
    fix:(m)=>`“your ${m[1]}” → “you’re ${m[1]}”` },
  { cat:'Homophones', sev:'check',
    re:/\bits\s+(a|an|the|been|going|not|very|so|really)\b/i,
    msg:'Likely “it’s” (it is), not the possessive “its”.',
    fix:(m)=>`“its ${m[1]}” → “it’s ${m[1]}”` },
  { cat:'Homophones', sev:'check',
    re:/\btheir\s+(is|are|was|were)\b/i,
    msg:'Likely “there”, not the possessive “their”.',
    fix:(m)=>`“their ${m[1]}” → “there ${m[1]}”` },
  { cat:'Formatting & tone', sev:'check',
    re:/\b(u|ur|cu|thru|gonna|wanna|gotta|pls|plz|asap|btw|lol|idk|tbh)\b/i,
    msg:'Informal abbreviation: spell it out in formal writing.',
    fix:(m)=>`“${m[1]}” → write it in full` },
  { cat:'Closings & sign-offs', sev:'fix',
    re:/\b(Yours|Best|Kind|Warm)\s+(Sincerely|Regards|Wishes|Faithfully|Truly)\b/,
    msg:'Don’t capitalise the second word of a sign-off.',
    fix:(m)=>`“${m[1]} ${m[2]}” → “${m[1]} ${m[2].toLowerCase()}”` },
  { cat:'Closings & sign-offs', sev:'check',
    re:/(^|\n)\s*(Sincerely|Regards|Best regards|Kind regards|Best wishes|Yours sincerely|Yours faithfully|Warm regards)\s*\.?\s*(\n|$)/i,
    msg:'End a sign-off with a comma (not a full stop).',
    fix:(m)=>`“${m[2]}” → “${m[2]},”` },
];

/* ---- teaching guides per kind of writing ------------------------------- */
const GUIDES = {
  letter:[
    { title:'Formatting & tone', icon:'format', items:[
      ['Mixing styles','Informal “U”, “cu” in a formal letter, or stiff language in a casual note.'],
      ['Missing elements','Forgetting the date, sender’s address, or clear contact details.'],
      ['Block text','One huge paragraph. Break it into intro · body · conclusion.'] ]},
    { title:'Grammar & phrasing', icon:'grammar', items:[
      ['“Look forward to”','✗ I look forward to <b>hear</b>.  ✓ …to <b>hearing</b>.'],
      ['Modal + “to”','✗ We must <b>to</b> inform.  ✓ We <b>must</b> inform.'],
      ['Missing article','✗ It was <b>pleasure</b>.  ✓ It was <b>a</b> pleasure.'] ]},
    { title:'Homophones', icon:'homophone', items:[
      ['there / their / they’re','place · possession · “they are”.'],
      ['your / you’re','ownership · “you are”.'],
      ['its / it’s','possessive · “it is”.'] ]},
    { title:'Closings & sign-offs', icon:'signoff', items:[
      ['Capitalisation','✗ Yours <b>Sincerely</b>.  ✓ Yours <b>sincerely</b>.'],
      ['Punctuation','End with a comma: “Best regards<b>,</b>”.'],
      ['Match the tone','“Yours faithfully” for “Dear Sir”; “sincerely” when you used a name.'] ]},
  ],
  prose:[
    { title:'Capitalisation & punctuation', icon:'format', items:[
      ['Sentence starts','Begin every sentence with a capital letter.'],
      ['End marks','Close each sentence with a . ? or !'],
      ['Commas','Separate items and clauses with commas.'] ]},
    { title:'Grammar & phrasing', icon:'grammar', items:[
      ['Subject–verb','Keep the subject and verb in agreement.'],
      ['One tense','Stay in a single tense within a passage.'],
      ['Articles','Use a / an / the where they’re needed.'] ]},
    { title:'Homophones', icon:'homophone', items:[
      ['there / their / they’re','place · possession · “they are”.'],
      ['your / you’re','ownership · “you are”.'],
      ['its / it’s','possessive · “it is”.'] ]},
    { title:'Clarity & flow', icon:'signoff', items:[
      ['Short sentences','Prefer short, clear sentences.'],
      ['One idea per line','Break long blocks into points.'],
      ['Read it aloud','It catches awkward phrasing fast.'] ]},
  ],
  math:[
    { title:'Clear digits', icon:'grammar', items:[
      ['0 vs O, 1 vs 7','Make every digit unmistakable.'],
      ['Decimal points','Place them clearly on the line.'],
      ['Fractions','Keep top and bottom lined up.'] ]},
    { title:'Aligned working', icon:'format', items:[
      ['One step per line','Show each step on its own row.'],
      ['Line up the “=”','Keep equals signs under each other.'],
      ['Space operators','Leave room around + − × ÷ =.'] ]},
    { title:'Symbols & signs', icon:'homophone', items:[
      ['+ vs t','Don’t let a plus look like the letter t.'],
      ['× vs x','Distinguish “times” from the letter x.'],
      ['Brackets','Close every bracket you open.'] ]},
    { title:'Presentation', icon:'signoff', items:[
      ['Underline answers','Mark the final answer clearly.'],
      ['Units','Write the unit after the number.'],
      ['Neat rows','Keep equations on straight rows.'] ]},
  ],
  science:[
    { title:'Labels & headings', icon:'format', items:[
      ['Title each part','Label diagrams and sections.'],
      ['Key terms','Write technical words clearly.'],
      ['Numbering','Number steps and points.'] ]},
    { title:'Units & symbols', icon:'grammar', items:[
      ['Units','Always include units (cm, g, °C).'],
      ['Symbols','Form chemical/physics symbols clearly.'],
      ['Sub/superscripts','Place them distinctly (H₂O, m²).'] ]},
    { title:'Clarity', icon:'homophone', items:[
      ['Spell terms in full','At least once, write each term out.'],
      ['Don’t crowd','Leave space around labels and arrows.'],
      ['Be consistent','Use the same term throughout.'] ]},
    { title:'Presentation', icon:'signoff', items:[
      ['Clean diagrams','Keep sketches tidy and labelled.'],
      ['Straight rows','Aligned writing aids reading.'],
      ['Highlight results','Underline key findings.'] ]},
  ],
};

const KINDS = {
  letter:{ label:'a letter', title:'The craft of your letter',
    intro:'This reads like a letter, so beyond the handwriting we check the things that make a letter clear and credible: its structure, grammar and sign-off.',
    runGrammar:true, runCompleteness:true, guide:'letter' },
  prose:{ label:'prose / an essay', title:'The craft of your writing',
    intro:'This reads like continuous writing, so we check the craft that makes prose easy to read: capitalisation, punctuation, grammar and clarity.',
    runGrammar:true, runCompleteness:false, guide:'prose' },
  math:{ label:'maths working', title:'Making your maths readable',
    intro:'This looks like maths. Letter-writing rules don’t apply: instead, clear digits, aligned working and well-formed symbols are what make it easy to follow and mark.',
    runGrammar:false, runCompleteness:false, guide:'math' },
  science:{ label:'science notes', title:'Making your notes clear',
    intro:'This looks like subject notes with labels or diagrams. The craft here is clear labelling, correct units and tidy, consistent terms.',
    runGrammar:false, runCompleteness:false, guide:'science' },
  mixed:{ label:'a form / printed page with handwriting', title:'The craft of your handwritten notes',
    intro:'This page mixes printed text with handwriting (like a form or prescription). We only assess the handwritten notes, with light writing-craft guidance.',
    runGrammar:true, runCompleteness:false, guide:'prose' },
  nonlatin:{ label:'non-English script', title:'Writing-craft (English) not applied',
    intro:'The writing appears to be in a non-English script. Our shape and quality factors still apply, but the language-craft checks below currently support English (Latin script) only: so they were not run on this sample.',
    runGrammar:false, runCompleteness:false, guide:null },
};

function kindOf(text, docKey){
  const t=(text||'').trim();
  const latin = (t.match(/[A-Za-z]/g)||[]).length;
  const nonlatin = (t.match(/[^\x00-\x7F]/g)||[]).length;
  if (t.length>3 && nonlatin > Math.max(3, latin)) return 'nonlatin';
  if (docKey==='symbolic') return 'math';
  if (docKey==='figures')  return 'science';
  if (docKey==='mixed')    return 'mixed';
  if (/\b(dear|hi|hello|sincerely|regards|faithfully|yours|to whom)\b/i.test(t)) return 'letter';
  return 'prose';
}

function analyze(text, docKey){
  const t = (text||'').trim();
  const kind = kindOf(t, docKey);
  const K = KINDS[kind];

  // grammar / homophone findings
  const findings = [];
  if (K.runGrammar && t.length>=4){
    RULES.forEach(r=>{ const m=r.re.exec(t); if(m) findings.push({cat:r.cat, sev:r.sev, msg:r.msg, detail:r.fix(m)}); });
    const longestPara = t.split(/\n{2,}/).map(p=>p.split(/\s+/).length).reduce((a,b)=>Math.max(a,b),0);
    if (longestPara > 70) findings.push({cat:'Formatting & tone', sev:'check', msg:'A very long unbroken block of text.', detail:'Split it into shorter paragraphs.'});
  }

  // letter-completeness (only when it's a letter)
  let present=null, missing=[], completeness=0;
  if (K.runCompleteness){
    present = {
      salutation: /\b(dear|hi|hello|to whom)\b/i.test(t),
      date:       /\b(\d{1,2}[\/\-.]\d{1,2}[\/\-.]\d{2,4}|\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2})\b/i.test(t),
      closing:    /\b(sincerely|regards|faithfully|best wishes|warm regards|yours|thank you)\b/i.test(t),
      signature:  /\n\s*[A-Z][a-z]+(\s+[A-Z][a-z]+)?\s*$/.test(t),
    };
    if (!present.salutation) missing.push(['Salutation','Open with a greeting: “Dear …,”.']);
    if (!present.date)       missing.push(['Date','Add the date so the letter is on record.']);
    if (!present.closing)    missing.push(['Closing','End with a sign-off: “Yours sincerely,”.']);
    if (!present.signature)  missing.push(['Signature','Sign your name under the closing.']);
    completeness = Object.values(present).filter(Boolean).length;
  }

  return {
    kind, label:K.label, title:K.title, intro:K.intro,
    runGrammar:K.runGrammar, runCompleteness:K.runCompleteness,
    findings, count:findings.length,
    present, missing, completeness,
    guide: K.guide ? GUIDES[K.guide] : null,
  };
}

global.VahiniCraft = { analyze, kindOf, GUIDES };
})(window);
