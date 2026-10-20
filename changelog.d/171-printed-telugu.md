- A page of printed Telugu is set aside as print instead of scored as
  handwriting (#171). Two things kept clean, confident printed Telugu lines
  as handwriting: the print-or-hand line reader, trained on Latin only, gave
  them a print probability of 0.001 to 0.01 and vetoed the "clean, confident
  line is printed" rule; and the clean-text share counted Telugu vowel signs
  and the virama as noise. The reader's veto now applies only to lines whose
  letters are mostly in the language pack's Latin letter class, and the
  clean share keeps the marks written on a letter. Handwritten Telugu reads
  at 0.61 to 0.70, below the 0.93 the rule needs, so it stays handwriting.
  Latin lines are classified exactly as before.
