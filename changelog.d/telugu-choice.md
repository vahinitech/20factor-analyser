- The check page asks which language the page is written in. English sends
  `lang=auto` as before. Telugu sends `lang=te`, shows "Telugu handwriting is
  not scored yet" before Run, and gets the `handwriting_not_read` refusal,
  which now asks for four lines in English. A Telugu page is no longer scored
  from an English misreading when the family says it is Telugu (#172). The
  sample page is checked as English. The page no longer says it reads
  Telugu: its FAQ, structured data and help box say English today.
