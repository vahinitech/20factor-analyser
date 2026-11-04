- The letter-style registry (#350): `backend/styles/letter_styles.json`
  lists the styles schools teach (looped, vertical, Indian straight
  cursive, joined with breaks, French, three German school scripts, and
  print as the control), each with its lean, break letters, capitals,
  loops, Playwrite face, countries and free sheets, checked against its
  schema and the rules in `test_letter_styles.py`. The style check's
  profile now carries `letterStyle`, the "Not sure" guess from joined or
  print writing and the words' mean lean. Nothing shows it yet, and no
  factor score moves.
