# Writing skills: AI-isms to avoid

House rules for every word this project ships: docs, READMEs, report copy,
commit messages, PR descriptions, UI strings. Generated text is welcome here,
but it must not read like generated text. Check your writing against this
list before committing.

## Punctuation and structure

- No em dashes. Use a comma, a colon, or a new sentence.
- No "It's not X, it's Y" constructions. Say what it is.
- Don't open with "In today's world" or "In the realm of". Start with the
  point.
- Don't end with a summary paragraph that repeats what was just said, or
  with "In conclusion".
- Don't turn everything into bullet lists. Three short sentences beat five
  fragments. Use a list only when the items are truly parallel.
- No emoji in docs, code comments, or commit messages. The report UI may use
  them where they are part of the design for children.

## Words that flag machine writing

Avoid these; they add nothing:

- delve, dive into, deep dive (in prose; the report's "deep-dive" product
  name is fine)
- seamless, seamlessly, effortlessly
- robust, comprehensive, cutting-edge, state-of-the-art
- leverage (as a verb for "use")
- utilize (just "use")
- crucial, vital, pivotal (usually "important", often deletable)
- landscape, ecosystem (for anything that is not land or biology)
- streamline, supercharge, elevate, empower, unlock
- "a testament to", "stands as", "serves as"
- furthermore, moreover, additionally (starting consecutive sentences)

## Tone mistakes

- Don't hedge everything. "This may potentially help improve" means "this
  helps".
- Don't flatter the reader ("Great question!", "You're absolutely right").
- Don't apologise for the software in docs. State what it does and what it
  does not do.
- Don't inflate certainty either. If OCR accuracy is 89%, print 89%, never
  "high accuracy".
- Write for the actual audience. Report copy is read by Indian school
  children and their parents: short words, concrete claims, no jargon.
  "Hand shaky" beats "tremor", "writing flow" beats "rhythm".

## Formatting habits

- Headings in sentence case, not Title Case Everywhere.
- No bold on random noun phrases. Bold marks the one thing to not miss.
- Keep code comments about constraints the code cannot show. Never comment
  what the next line obviously does.
- Numbers get units and context: "82 ms on a laptop CPU", not "blazing
  fast".

## The test

Read it aloud. If a sentence would sound odd said to a colleague across a
desk, rewrite it. If a paragraph could be pasted into any other project's
README without change, it says nothing; delete it.
