/* SPDX-License-Identifier: AGPL-3.0-only
   © 2026 Vahini Technologies. Contact: info@vahinitech.com. Dual-IMU sensing: Indian Patent No. 584433.
   Distributed under GNU AGPL v3.0 only. Third-party notices: /THIRD-PARTY-NOTICES.md · SBOM: /sbom.spdx.json */
/* =========================================================================
   Vahini Narration: five-beat factor stories, ~45 words, second person.
   [What we measured] → [What we saw] → [Why it matters] → [One drill]
   → [What changes next scan]
   Proxy / pen-pending factors use the honest-labelling pattern instead:
   "we can only estimate this from a photo … treat it as a hint, not a score."
   ========================================================================= */
(function (global) {
'use strict';

/* Each entry: measured, saw{strong,dev,focus}, why, drill, next.
   Optional honest(f): full override body for photo-mode proxy factors.
   Optional pen{...}: variants used when the IMU pen actually measured it. */
const T = {
1:{ honest:(f)=>`True letter-shape checking compares each letter to a model: from a photo we can only estimate it from how regular and well-closed your letters look. Yours look ${f.band==='strong'?'well-formed':f.band==='dev'?'mostly regular, with a few rough shapes':'irregular in places'}.`,
    drill:'Build from the two “magic strokes” every letter shares, clockwise and anticlockwise circles, then slow block rows of a, o and b', next:'treat this as a hint, not a score: shape-by-shape checking is coming.' },
2:{ honest:()=>`The order you build each letter in happens in time: a photo only shows the finished mark, so we cannot truly see it. The Battu records every stroke as you write.`,
    drill:'Trace guided stroke-order sheets slowly', next:'until a Battu capture, treat this as a hint, not a score.' },
3:{ measured:'We checked whether your round letters (a, o, e, g) close fully.',
    saw:{ strong:(v)=>`${v} do, which is genuinely good control.`, dev:(v)=>`${v} close; the rest are left slightly open.`, focus:(v)=>`Only ${v} close: many are left open.` },
    why:'The “bowl” of a round letter should join up. When it’s left open, an a starts to look like a u and an o like a c: so closing loops is one of the simplest things that makes words easy to read.',
    drill:{ strong:'Keep one row of o’s each session to hold it; open and close a bottle lid as a warm-up', dev:'Warm up by opening and closing a bottle lid (anticlockwise, then clockwise), then write rows of oooo and aaaa closing every bowl', focus:'Warm up with the bottle-lid drill (open anticlockwise, close clockwise), then slow rows of oooo and aaaa, closing every circle' },
    next:'your next scan should show the closed share climbing.' },
4:{ measured:'We traced how steady each stroke stays along its path.',
    saw:{ strong:()=>'Your strokes run smooth and even.', dev:()=>'Your strokes wobble a little in places.', focus:()=>'Your strokes wobble noticeably.' },
    why:'This is about line steadiness: whether each line glides or shakes as it’s drawn. Smooth, confident strokes look calm and controlled; a shaky line is the visible sign of a hesitant or rushed hand.',
    drill:'Two minutes of “magic strokes” before writing: clockwise and anticlockwise circles, then figure-8s, then slow rows of llll and cccc', next:'next scan should show steadier, smoother lines.' },
5:{ measured:'We measured the height of every letter you wrote.',
    saw:{ strong:()=>'Your letters sit in one even band: excellent control.', dev:()=>'Most letters match, with a few jumping taller or smaller.', focus:()=>'Your letters range from very small to quite tall within the same word.' },
    why:'Even sizing is the single biggest driver of neat-looking writing.',
    drill:'Two-line drill: on doubled lines, keep every small letter exactly touching the top rule so each lands in one even band', next:'your next scan should show letters settling into one band.' },
6:{ measured:'We measured how far tall letters reach up and tails reach down.',
    saw:{ strong:()=>'Your tall letters and tails are nicely balanced.', dev:()=>'Your tall letters and tails are close, but not quite balanced.', focus:()=>'Your tall letters or tails are running short.' },
    why:'Balanced heights keep h, l, g and y unmistakable.',
    drill:'Tall–short pattern rows: bl bl bl', next:'next scan should show the three zones sharing space evenly.' },
7:{ measured:'We drew the invisible line your words sit on and measured the drift off it.',
    saw:{ strong:()=>'Your letters sit neatly on the line.', dev:()=>'Your letters bounce slightly above and below it.', focus:()=>'Your letters bounce visibly above and below it.' },
    why:'A steady baseline is what makes a page look calm and ordered.',
    drill:'Trace along the rule on lined paper', next:'next scan should show words settling onto one line.' },
8:{ measured:'We measured the gap between every pair of words.',
    saw:{ strong:()=>'Your word gaps are even: about one letter wide.', dev:()=>'Your word gaps drift between tight and roomy.', focus:()=>'Your word gaps vary a lot: some touch, some gape.' },
    why:'Even word gaps are the fastest single win for readability.',
    drill:'Leave one finger-width between words', next:'next scan should show the gaps evening out.' },
9:{ measured:'We measured the space between letters inside each word.',
    saw:{ strong:()=>'Your letters are evenly spaced.', dev:()=>'Some letters crowd while others spread.', focus:()=>'Letters crowd together, then spread apart.' },
    why:'Even letter spacing keeps words from smudging into a blur.',
    drill:'Slow writing with a matchstick gap between letters', next:'next scan should show steadier spacing.' },
10:{ measured:'We checked where each line starts and ends on the page.',
    saw:{ strong:()=>'Your left edge runs straight down the page: a real strength.', dev:()=>'Your left edge wanders a little as the page goes on.', focus:()=>'Your left edge steps in and out noticeably.' },
    why:'A steady margin frames everything else you write.',
    drill:'Rule a light margin line and start each line on it', next:'next scan should show a straighter edge.' },
11:{ measured:'We measured whether your lines run level or drift up and down.',
    saw:{ strong:()=>'Your lines run level across the page.', dev:()=>'Your lines drift gently as they cross the page.', focus:()=>'Your lines climb or sink visibly.' },
    why:'Level lines instantly make a whole page look tidier.',
    drill:'Pause at the right edge and reset to the rule', next:'next scan should show flatter lines.' },
12:{ measured:'We measured whether your up-and-down strokes all point the same way.',
    saw:{ strong:()=>'Your strokes stand consistently.', dev:()=>'A few strokes tilt off the common angle.', focus:()=>'Your strokes tilt in several directions.' },
    why:'Strokes that agree make writing look intentional, not accidental.',
    drill:'Slant rails: rule faint guide lines at one chosen angle (straight or right, never left) and keep every up-stroke parallel to them', next:'next scan should show the strokes agreeing.' },
13:{ honest:()=>`Writing speed is invisible in a photo: we can only estimate it from how your strokes thin and thicken. The Battu times every stroke directly, 208 times a second.`,
    drill:'Write to a steady 1-2-3 count per word', next:'until a Battu capture, treat this as a hint, not a score.',
    pen:{ measured:'The pen timed every stroke as you wrote.',
      saw:{ strong:()=>'Your writing speed stays steady from stroke to stroke.', dev:()=>'Your writing speed surges and slows between strokes.', focus:()=>'Your writing speed swings widely between strokes.' },
      why:'A steady writing speed is the engine of fast, comfortable writing.',
      drill:'Write to a steady 1-2-3 count per word', next:'your next pen session should show a smoother speed line.' } },
14:{ honest:()=>`Pen pressure is invisible in a photo: we can only estimate it from ink darkness. Your ink ${'varies'}, which may mean uneven pressure. The Battu measures pressure directly.`,
    drill:'Aim for a light hand: about 20% of your usual force; if your fingertip whitens or the page embosses, ease off (a relaxed grip writes longer without tiring)', next:'until a Battu capture, treat this as a hint, not a score.',
    pen:{ measured:'The pen felt your grip and tip force throughout.',
      saw:{ strong:()=>'Your pressure stays relaxed and even.', dev:()=>'Your pressure rises and eases noticeably.', focus:()=>'Your pressure swings from light to heavy.' },
      why:'Even, relaxed pressure is what keeps the hand from tiring.',
      drill:'Same-pressure line rows: one steady, relaxed force', next:'your next pen session should show a flatter force line.' } },
15:{ honest:(f)=>`From a photo we can only count how many separate pieces each word is built from: a rough stand-in for true stroke flow. Your words break into ${f.value||'several parts'}.`,
    drill:'Treat each word as one stroke: join all its letters in a single flow without lifting, adding any i-dots and t-bars only after the word is finished', next:'the pen reads true flow directly: treat this as a hint until then.',
    pen:{ measured:'The pen tracked where your strokes flow and where they break.',
      saw:{ strong:()=>'Your strokes join smoothly into words.', dev:()=>'Some words break into stop-start pieces.', focus:()=>'Most words break into many short pieces.' },
      why:'Flowing strokes are faster and feel far easier.',
      drill:'Join letters within each word without lifting', next:'next pen session should show longer, smoother strokes.' } },
16:{ honest:()=>`Pen lifts happen in time: a photo cannot show them at all, so this is a neutral placeholder. The Battu counts every lift the moment it happens.`,
    drill:'Write whole words without lifting mid-word', next:'until a Battu capture, this is not a score.',
    pen:{ measured:'The pen counted every time it left the paper.',
      saw:{ strong:()=>'You lift rarely: your words flow on.', dev:()=>'You lift a little more than needed mid-word.', focus:()=>'You lift often inside words.' },
      why:'Every extra lift is a tiny pause that quietly slows writing down.',
      drill:'Write whole words without lifting mid-word', next:'next pen session should show the lift count falling.' } },
17:{ measured:'We measured the lean of each word you wrote.',
    saw:{ strong:()=>'Your lean is steady from word to word.', dev:()=>'Your lean drifts between words.', focus:()=>'Your lean changes direction between words.' },
    why:'One consistent lean reads as confidence on the page.',
    drill:'Pick one lean and commit (straight or a right slant, never left), then write slant rails (//// at that single angle) before your normal lines', next:'next scan should show the lean settling on one angle.' },
18:{ honest:(f)=>`There is no single legibility dial: we blend your size, spacing and baseline results, the basics that decide how easy writing is to read. Yours blends to ${f.band==='strong'?'an easy, readable page':f.band==='dev'?'mostly readable, with friction in places':'a page that takes effort to read'}.`,
    drill:'Lift your two lowest factors first', next:'legibility rises with them on the next scan.' },
19:{ honest:(f)=>`We estimated how clearly look-alike letters are told apart, from how well your round letters close. The pairs to watch in your writing: ${(f.value&&/[a-z]\/|,/.test(f.value))?f.value:'a/o, n/h, r/v'}.`,
    drill:'Write the confusable pairs side by side until each is unmistakable', next:'treat this as a pointer to practise, not a precise score.' },
20:{ measured:'We combined your size, spacing, line and baseline results into one tidiness read.',
    saw:{ strong:()=>'Together they make a genuinely neat page.', dev:()=>'Together they make a decent page with a few rough patches.', focus:()=>'Together they leave the page looking busy.' },
    why:'Neatness is not a talent: it is these few habits, repeated.',
    drill:'Pick your single lowest factor and drill only that', next:'this score follows automatically next scan.' },
};

function pick(v, f){ return typeof v==='function' ? v(f.value, f) : (v && v[f.band]!==undefined ? (typeof v[f.band]==='function'? v[f.band](f.value,f) : v[f.band]) : v); }

function narrate(f){
  const t = T[f.n];
  if (!t) return null;
  const usePen = f.imuMeasured && t.pen;
  const src = usePen ? t.pen : t;
  // honest-labelling path (photo-mode proxy / pen-pending / blended factors)
  if (!usePen && t.honest){
    const body = t.honest(f);
    const drill = pick(t.drill, f);
    return { label:'What this means', body, action: drill + ': ' + t.next };
  }
  const saw = src.saw ? (typeof src.saw[f.band]==='function' ? src.saw[f.band](f.value) : src.saw[f.band]) : '';
  const body = `${src.measured} ${saw} ${src.why}`;
  const drill = pick(src.drill, f);
  return { label: f.band==='strong' ? 'Why it scored well' : f.band==='dev' ? 'Why it’s developing' : 'Why this is a focus',
           body, action: drill + ': ' + src.next };
}

global.VahiniNarrate = { narrate };
})(window);
