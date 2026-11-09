# Letter-style guess on font-drawn pages (2026-11-04)

A first measure of the "Not sure" guess in `backend/styles/letter_styles.py`
(#350), taken before any real handwriting per family exists (#342). The
pages are drawn in the fonts the registry names, so this checks that the
guess's rules fit each style. It does not say how often the guess is right
on a child's page: font letters are tidier than any hand.

## How it was run

`scripts/letter_style_guess_eval.py <font folder>` draws five lines of
plain English sentences in each face at three sizes (34, 44 and 56 px),
word by word with a gap of about two small-letter heights, at weight 400,
with room between lines. Each page goes through the real scorer
(`scoring.build_analysis`) with the lines as the reader gives them, and
the guess attached to `styleProfile.letterStyle` is compared with the
style the face stands for. The faces are Google Fonts' `ofl/playwrite*`
files (OFL), not kept in this repository; DejaVu Sans is the print control.

## Result

| Face | Stands for | Writing found | Mean lean | Guess first | Right style listed |
|---|---|---|---|---|---|
| Playwrite US Trad | looped | cursive | 17° | 3/3 | 3/3 |
| Playwrite IN | looped (the free sheets) | cursive | 17° | 3/3 | 3/3 |
| Playwrite AR | vertical, Indian straight | cursive | -1° | 3/3 | 3/3 |
| Playwrite GB J | joined with breaks (England) | cursive | 0° | 0/3 | 3/3 |
| Playwrite AU VIC | Australian joined (Victoria) | cursive | 17° | 0/3 | 3/3 |
| Playwrite FR Trad | French | mixed | 0° | 0/3 | 3/3 |
| Playwrite DE LA | German LA | cursive | 17° | 0/3 | 3/3 |
| Playwrite DE VA | German VA | cursive | 9° | 0/3 | 3/3 |
| Playwrite DE SAS | German SAS | cursive | 14° | 0/3 | 3/3 |
| DejaVu Sans | print | print | 0° | 3/3 | 3/3 |

The right style is in the list on all 30 pages and first on 12. Joined or
print, and upright or leaning, are the only two facts the guess has, so
styles that share both come out in table order: every upright joined page
is guessed vertical, every leaning one looped. The break letters (#343)
and the loops on tall letters are what will tell those apart; until then
the page says the guess is a guess and lists the others.

## What it changed in the registry

- **Playwrite IN leans right (17°)**, like US Trad. It was named as the face
  for the upright styles; vertical and Indian straight cursive now use
  Playwrite AR, the upright looped face closest to US looped cursive (no
  Playwrite face draws US Trad upright). The free sheets, drawn in
  Playwrite IN, belong to looped.
- **England and Australia do not lean alike.** GB J stands upright and every
  Australian face leans 15° to 18°, so Australia is its own entry
  (`joined-breaks-au`, Victoria first; NSW, QLD, SA and TAS are entries to add).
- **French cursive is upright** in Playwrite FR Trad.

Lean of all 52 Playwrite faces, measured the same way (word mean, degrees):

- **Upright (under 6°):** AR 0°, AT 0°, BEWAL 0°, BR 0°, CL 0°, DEGRUND 0°, ES 0°, ESDECO 0°, FRMODERNE 0°, FRTRAD 0°, GBJ 0°, GBS 0°, HRLIJEVA 0°, HU 0°, ID 0°, ITMODERNA 0°, ITTRAD 0°, NGMODERN 0°, PE 0°, PL 0°, PT 0°, USMODERN 0°, VN 0°.
- **Leaning right:** AUNSW 15°, AUQLD 15°, AUSA 15°, AUTAS 18°, AUVIC 18°, BEVLG 18°, CA 18°, CO 18°, CU 18°, CZ 18°, DELA 18°, DESAS 15°, DEVA 9°, DKLOOPET 18°, DKULOOPET 18°, HR 18°, IE 18°, IN 18°, IS 14°, MX 18°, NL 18°, NO 18°, NZ 18°, NZBASIC 9°, RO 18°, SK 18°, TZ 15°, USTRAD 18°, ZA 9°.

## What is still owed

Real joined pages per family (#342), the break letters (#343) and a loop
measure, then this note again with handwriting instead of fonts.
French writing came out "mixed" on every page: the face's entry and exit
strokes leave some letters apart in the ink, which the style check counts.
Whether real French school pages do the same is a question for #342.
