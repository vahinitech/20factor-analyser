# Source of the pages

**What these pages are, and are not.** Model pages of adult French
cursive from two French writing manuals: an engraved Paris copybook of
the "écriture américaine" (the French anglaise, early 19th century) and
a Paris school manual of about 1900 that sets out the looped "cursive"
taught in French primary schools. They are the writing a pupil was asked
to copy, printed from plates drawn by a writing master. They are the
ideal end of the range, not children's everyday writing.

Only running sentences were cropped: no drills, single letters,
alphabets, signatures or printed text. The crops were cut from the
Internet Archive's page images on 5 November 2026, each kept to the
handwritten block, and scaled down to 2600 pixels wide where wider.
Nothing else was changed. The D'Avignon crops keep some of the engraved
flourishes round the text, because they run into the lines.

## D'Avignon, L'Écriture américaine (Paris, early 19th century)

- D'Avignon (first name and life dates not found). Paris: "Chez Mme Vve
  Jean, rue St Jean de Beauvais No 10" (imprint on the title plate,
  scan image n5). The Jean firm of print sellers is recorded at no. 10
  rue Saint-Jean-de-Beauvais in 1805 to 1812 (Biblioteca Virtual de
  Defensa authority record "Jean (Paris)"); the plates say "Veuve"
  (widow), so the printing is after Pierre Jean's death (c. 1805). The
  spelling "monnoye" on plate 6 fits the same period. Engraved plates.
- Scan: IAMPETH copy, photographed pages,
  https://archive.org/details/DAvignonLecritureAmercaine
  (item description: "L'écriture Américaine par D'Avignon - "American
  Writing" by D'Avignon, circa 1840").
- Rights: the Internet Archive item has no `possible-copyright-status`,
  `licenseurl` or `rights` field. The book was published in Paris in the
  first half of the 19th century, so it is in the public domain in the
  USA (published 1930 or earlier). A writer who drew a published copybook
  before about 1850 died long before 1965, so it is also in the public
  domain in India (life plus 60 years). The author's exact dates are not
  known; the conclusion rests on the imprint date.

| Page | Scan image | Printed page | Cropped |
|---|---|---|---|
| `davignon-007-salutaire` | n12 | 7 | "Quelque salutaire que soit le conseil..." (5 lines) |
| `davignon-008-flatte` | n13 | 8 | "Celui qui n'est flatté que de son mérite..." (4 lines) |
| `davignon-009-reconnaissance` | n14 | 9 | "Il faut que la reconnaissance paraisse..." (5 lines) |
| `davignon-010-vertu` | n15 | 10 | "La vertu pour se faire aimer..." (5 lines) |

## P. Meyrat, Recueil méthodique de principes d'écriture (about 1900)

- Pierre Meyrat, 1862-1931. Limoges: F. Brégéras, éditeur, 18 rue
  Manigne. The cover says it was "Inscrit sur la liste des ouvrages
  fournis gratuitement par la Ville de Paris à ses Écoles". The BnF
  catalogue record of the 2008 facsimile (Thoste: A. Masset) gives the
  author as "Meyrat, Pierre (1862-1931)" and the original as Limoges,
  F. Brégéras, "[ca 1900]". Bridgeman Images gives the same dates and
  "c. 1900"; Luc Devroye's type pages say "ca. 1920".
- Scan: IAMPETH copy, https://archive.org/details/RecueilMethodiqueDePrincipesDEcriture
  (item description: "P. Meyrat, circa 1920's").
- Rights: the Internet Archive item has no `possible-copyright-status`,
  `licenseurl` or `rights` field. Published in France about 1900 (every
  dating found is 1930 or earlier), so in the public domain in the USA;
  Meyrat died in 1931, so it is in the public domain in India (life plus
  60 years, from 1992). Not checked: whether the IAMPETH copy is an
  original printing or the 2008 facsimile; the facsimile adds no new
  writing.

| Page | Scan image | Printed page | Cropped |
|---|---|---|---|
| `meyrat-018-engagements` | n17 | 18 | "Ne prenons pas d'engagements à la légère..." (5 lines, "moyenne cursive", below the printed heading) |
| `meyrat-020-esprit` | n19 | 20 | "Ce n'est pas un grand avantage d'avoir l'esprit..." (5 lines, below the capitals and the printed heading) |
| `meyrat-021-mirabeau` | n20 | 21 | "A la tribune, Mirabeau avait un geste brusque..." (6 lines of "fine cursive dite expédiée", below the printed paragraph) |
| `meyrat-023-affaires` | n22 | 23 | "Poussez vos affaires..." (3 lines of "fine cursive droite", below the alphabet) |

The written lines of each crop go in `set.json` (`page_text`), lower
case, with the words split across lines as the copy splits them.


Notes on the text: the spelling is the copy's own ("réüssir",
"pésante", "elle même", "reconnaissance, paraisse"). "quelqu'un",
"l'on", "n'est", "s'en" are written with the apostrophe drawn as an
accent over the next letter. In `meyrat-021-mirabeau` the copy writes a
capital "A" without accent; it is given as "à".

## Style tags

| Page | Slant | Joining | Capitals joined to the next letter |
|---|---|---|---|
| `davignon-007-salutaire` | slanted | anglaise, every small letter joined within a word | Q: yes, its tail runs into "u" |
| `davignon-008-flatte` | slanted | as above | C: no, a gap before "elui" |
| `davignon-009-reconnaissance` | slanted | as above | I: no, it stands alone before "l" |
| `davignon-010-vertu` | slanted | as above | L: appears joined, the base loop leads into "a" |
| `meyrat-018-engagements` | slanted | French school cursive (moyenne cursive), looped ascenders and descenders, every small letter joined within a word | N: yes, into "e"; A of "Agir": no |
| `meyrat-020-esprit` | slanted | French school cursive (fine cursive), as above | C: yes, into "e"; U: yes, into "n"; L: no (apostrophe follows) |
| `meyrat-021-mirabeau` | slanted | "expédiée": fast fine cursive with the manual's variant d, p, s, t (and B, R) made to join without lifting the pen | A, M, S, L: no, each stands apart |
| `meyrat-023-affaires` | upright | "fine cursive droite": upright, small letters mostly joined, some breaks (after "o", "s", "r" in places) | P, A, L: no |

No page leaves a fixed set of small letters unjoined as a rule; the
breaks visible are word spaces, apostrophes and, in the upright page,
occasional pen lifts.

## Looked at and not used

- Frères de l'Instruction chrétienne, "Modèles d'écriture pour le cours
  élémentaire", Laprairie (Quebec),
  https://archive.org/details/modele_ecriture_primaire: Public Domain
  Mark on the item, looped school cursive with running sentences
  (scan images n29 to n37), but no date anywhere in the scan or found
  in catalogues (place names in it suggest the 20th century).
  Unverified, not used.
- "Modèles et exercices d'écriture française", Luxembourg, Heintzé
  frères, 1868 (Jagiellonian Library copy,
  https://archive.org/details/jbc.bj.uj.edu.pl.NDIGDRUK067773,
  "Domena publiczna"): the sentences are set in a script typeface
  ("Typographie ... de Heintzé frères"), not drawn. Not handwriting.
- Guillaume Montfort, "Collection de principes et modèles des
  différentes sortes d'écriture", Paris, Basset, 1799
  (https://archive.org/details/gri_33125009323284,
  "possible-copyright-status: NOT_IN_COPYRIGHT"): engraved running
  sentences, but in the 18th-century ronde and coulée, mostly upright
  and unlooped, with many letters unjoined. Rights are clear; left out
  because it is a different style from school cursive. It could serve a
  separate "French ronde/coulée" set.
- Quebec manuals on Canadiana microfiche: "Méthode d'enseignement du
  système éclectique d'écriture" (Montréal?, 1911, `cihm_76399`) and
  "Manuels d'écriture normale" (Montréal, Beauchemin, 1912,
  `cihm_81504`). Running sentences exist, but the items carry no rights
  field, the microfiche frames carry "© 1995" / "© 1996" CIHM notices,
  and the scans are low-contrast microfiche. Unverified, not used.
- Mironneau and Philippe, "Méthode de lecture" (Paris, Armand Colin,
  1927, `mthodedelecturep00miro`): reading primer, one or two cursive
  lines among print and pictures; Adolphe Mironneau's dates not found.
- Angelo Audifredi, "La calligraphie progressive" (Turin, 1834) and Jean
  Midolle's "Écritures modernes" (1834, stream only): display
  calligraphy, not school cursive; Midolle has no rights field.
- J. Dupuy, "Méthode d'écriture cursive" on archive.org is a Gallica
  scan (bpt6k939383v): excluded.
- Wikimedia Commons: no scans of French writing manuals found under
  Copybooks, French calligraphy, Handwriting in French or by search
  ("modèles d'écriture", "méthode d'écriture", "écriture anglaise",
  "écriture cursive", "cours d'écriture"). The files found were modern
  photos (one of a child writing, one of an adult's notebook), an
  Encyclopédie plate of "écriture coulée" (CC BY-SA photo of an 18th
  century plate, different style) and a 19th-century pupil's exercise
  book in Lyon (a child's writing, excluded).
- Not found with a clear licence: the classic French school copybook
  series (Taupier, Godchaux, Flament, "cahiers d'écriture" of 1880 to
  1930). Searched archive.org by title, creator and subject in French
  and English, and Commons by category and keyword.

The written lines of each crop are in `set.json` (`page_text`), with
the accents and the copy's own spelling, lower case, and each page's
slant and scheme in `page_style`. The pages are committed, not cut
again on each run, for the reason `benchmarks/uji-clean/source.md`
gives.
