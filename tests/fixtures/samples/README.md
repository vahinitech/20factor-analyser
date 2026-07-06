# Sample pages for the handwriting-only regression suite

Real pages of three kinds, used by
`backend/tests/test_handwriting_only.py` to enforce the analyser's
rule of thumb: printed text is never analysed.

| File | Content | Expected behaviour |
|---|---|---|
| `handwritten_letter_1.jpg` | 1722 handwritten letter | analysed in full |
| `handwritten_letter_2.jpg` | 1889 handwritten letter | analysed in full |
| `handwritten_script_1.jpg` | script font specimen sheet | tricky case: print that imitates handwriting |
| `handwritten_printed_1.jpg` | printed tracing worksheet | refused, no handwriting |
| `handwritten_printed_2.jpg` | typewritten letter | refused, no handwriting |
| `handwritten_printed_3.png` | printed letter template | refused, no handwriting |
| `handwritten_printed_mixed_1.jpg` | 1929 receipt: printed form + pen entries | pen entries scored, printed form excluded |
| `printed_signature_1.jpg` | signature font poster | tricky case: print that imitates handwriting |

None of these pages contains personal data of a living person. Please keep
it that way when adding samples.
