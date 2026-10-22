# Source of the page

The analyser's own sample photo: `tests/fixtures/handwriting-sample.jpg`,
also served as `frontend/assets/samples/handwriting-sample.jpg` and shown
in `sample-report.html`. One notebook page of an adult's practice
sentences, photographed at 960x1280, with no name or other personal data
(the CONTRIBUTING.md rule on real handwriting). It is copied here so the
set's pixels never change with the fixture.

`reader/handwriting-sample.json` is the real reader's output for it,
read on 22 October 2026 on a GitHub runner with the analyser image of
main at 4232e36 (`benchmark.py capture --set sample-page`), with the
stage analyser's settings in `set.json`. Replayed through main at that
commit it gives exactly what the stage analyser gave the same day for
this photo with `lang=auto`.

The page is ruled and photographed at an angle: its lower lines slope by
three to six degrees, so their boxes are much taller than the lines and
take in the rows above and below. That is what this set is for
(`backend/tests/test_sample_page.py`).
