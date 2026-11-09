# Datasets

Every dataset this repository uses or has used, for training, testing, benchmarks or evaluation: who publishes it, its licence, what it is used for, and whether any of it is in this repository or the analyser image. `THIRD-PARTY-NOTICES.md` carries the attributions and `sbom.spdx.json` lists each one as an `SPDXRef-Data-*` package (purpose `OTHER` with "Dataset" in its comment, since SPDX 2.3 has no data purpose). Vahini keeps one inventory across all its repositories, with the risks and open actions, in vahinitech/Umbrella `docs/DATASETS.md` (private).

Audited on 22 October 2026 against each dataset's own page. "Unverified" means the publisher's page did not settle the fact that day.

## Rules

- **Record a dataset before you use it**: here, in `THIRD-PARTY-NOTICES.md` and in `sbom.spdx.json`. A benchmark set also carries a `source.md` ([18](18-benchmark.md)).
- **The licence comes from the publisher's own page or files.** A mirror, a portal listing or a paper is not the licence. If the page says nothing, write "unverified" and keep the data out of anything that ships until the authors confirm in writing.
- **No raw dataset in the repository or the image.** Derived files (weights, rendered pages, crops) may be committed only when the licence allows it, with the attribution next to them.
- **No non-commercial data in training.** This repository is AGPL and the same engine serves paid Pro reports.
- **No personal data.** Photos of real people's pages stay outside the repository (CONTRIBUTING.md).

## Summary

| Dataset | Licence | Use here | In the repository | In the image |
| --- | --- | --- | --- | --- |
| UJI Pen Characters v2 | CC BY 4.0 | Trains the print-or-handwriting reader; planted-mistake pages; factor tests; the `uji-clean` benchmark | 20 rendered pages (`benchmarks/uji-clean/pages`), evidence crops in `docs/history/` | Weights only (`backend/models/print_hand.json`) |
| Fonts from google/fonts at `66928797` | OFL-1.1, one Apache-2.0 | Printed lines that train the same reader | No | Weights only |
| GNHK | CC BY 4.0 | Evaluation of 200 real photos, 19 October 2026 | No | No |
| IIIT-INDIC-HW-WORDS-Telugu | **Unverified** (see below) | Trains the Telugu reader; Telugu evaluation pages | No | No (the reader is not used by a scan yet) |
| Palmer (1915) and Zaner (Manual 144) penmanship manuals | Public domain | Neat reference set for calibration | 8 crops (`benchmarks/neat-penmanship/pages`) | No |
| The sample photo `handwriting-sample.jpg` | **Source not recorded** | Sample report, fixtures, `sample-page` benchmark | Yes | Yes (`frontend/assets/samples/`, `sample-report-data.js`) |
| `tests/fixtures/samples/` pages | **Source not recorded** | Printed-text refusal tests; real test lines for the print-or-handwriting reader | Yes (8 images, 544 KB) | No |
| Therapist agreement pages (planned) | Written consent from the school and each family, for this test only | Evaluation against therapists' marks ([23](23-therapist-agreement.md)) | No | No |
| IAM Handwriting Database | Non-commercial research only | None directly; the optional TrOCR tier's weights are fine-tuned on it | No | No (tier off) |

Considered and not used: EMNIST (terms unclear), IAM directly and through Roboflow Universe copies (non-commercial), CEDAR (no licence stated), other Roboflow sets (web-scraped or single letters). See [history/real-photos-gnhk-2026-10-19.md](history/real-photos-gnhk-2026-10-19.md).

## UJI Pen Characters (Version 2)

- **Publisher:** F. Prat, M. J. Castro, D. Llorens, A. Marzal and J. M. Vilar (Universitat Jaume I and Universitat Politècnica de València), UCI Machine Learning Repository, 2009.
- **URL:** <https://archive.ics.uci.edu/dataset/177/uji+pen+characters+version+2>, doi:10.24432/C5FG8S.
- **Version:** `ujipenchars2.txt`, SHA-256 `cc56f72f8477e763dd06a44746ba05a679e9232468aac93b3a7aad46a0300d61`, downloaded and checked by `scripts/planted_pages.py` into `~/.cache/vahini/` (CI caches it under the same hash).
- **Licence:** CC BY 4.0, on the UCI page. Commercial use and adaptation are allowed with attribution and a note of changes.
- **Citation:** Prat, F., Castro, M., Llorens, D., Marzal, A., and Vilar, J. (2008). UJI Pen Characters (Version 2) [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C5FG8S.
- **Use:** the 40 training writers train `print_hand.json` (`scripts/train_print_hand.py`); the 20 test writers make every synthetic test page (`scripts/planted_pages.py`, `factor_tests.py`, `letter_boxes_eval.py`, `score_ranges.py`) and the committed `uji-clean` benchmark pages.
- **Changes we make:** letters arranged into lines and drawn to look like a phone photo of paper; the letters themselves are unchanged ([benchmarks/uji-clean/source.md](../benchmarks/uji-clean/source.md)).

## Fonts for printed lines

The 24 font families (25 files) listed with their SHA-256 in `scripts/print_hand_data.py`, from github.com/google/fonts at commit `66928797f271fed5ee428544e7229685e2d90127`: OFL-1.1, Special Elite Apache-2.0. Names in `THIRD-PARTY-NOTICES.md`. No font file is committed. The `WORDS` list drawn in them (the cast's names, then common English words) has no recorded source.

## GNHK (GoodNotes Handwriting Kollection)

- **Publisher:** GoodNotes; A. W. C. Lee, J. Chung and M. Lee.
- **URL:** <https://github.com/GoodNotes/GNHK-dataset>.
- **Licence:** CC BY 4.0, stated in that repository's README, supplied "as is", with a takedown promise to anyone who finds their own information in it.
- **Citation:** A. W. C. Lee, J. Chung and M. Lee, "GNHK: A Dataset for English Handwriting in the Wild", ICDAR 2021.
- **Our copy:** 200 of 687 pages, fetched on 19 October 2026 from the Hugging Face repository `aryaman27/goodnotes-handwritten-dataset` at revision `904297760a9fec813fdc1ecb5f8055cb1ca03550`, because GoodNotes' own download link no longer leads to the files. That mirror declares no licence, and its files have not been compared with GoodNotes' release.
- **Use:** evaluation only ([history/real-photos-gnhk-2026-10-19.md](history/real-photos-gnhk-2026-10-19.md)). The pages hold personal data (names, a phone number), so they stay on the server, outside every repository.

## IIIT-INDIC-HW-WORDS-Telugu

- **Publisher:** CVIT, IIIT Hyderabad (S. Gongidi and C. V. Jawahar).
- **URLs:** <https://ilocr.iiit.ac.in/dataset/23>; <https://cvit.iiit.ac.in/research/projects/cvit-projects/indic-hw-data>; <https://cvit.iiit.ac.in/ihtr2022/dataset.html>.
- **Licence: unverified for our copy.** ILOCR states CC BY 4.0 for a release of 88,534 training words, and the AIKOSH portal lists CC BY 4.0. The CVIT project pages state no licence. The ICFHR 2022 IHTR competition page, whose Telugu split has 80,637 training words, says the data is for the competition only. Our training archive has 80,637 labelled words, and the page it was downloaded from is not recorded. The owner is asking the authors to confirm the terms in writing ([20](20-languages.md)).
- **Citation:** S. Gongidi and C. V. Jawahar, "IIIT-INDIC-HW-WORDS: A Dataset for Indic Handwritten Text Recognition", ICDAR 2021; K. Dutta, P. Krishnan, M. Mathew and C. V. Jawahar, "Towards Spotting and Recognition of Handwritten Words in Indic Scripts", ICFHR 2018.
- **Use:** trains the Telugu reader (`scripts/train_telugu_reader.py`); its weights are not committed and no scan uses them. Builds the Telugu evaluation pages, kept outside the repository ([18](18-benchmark.md#a-set-kept-outside-the-repository)). Until the terms are confirmed, neither the pages nor weights trained on them go into this repository, the image or a report.

## Palmer and Zaner penmanship manuals

A. N. Palmer, *The Palmer Method of Business Writing*, 1915 (<https://archive.org/details/palmermethodofbu00palmrich>), and the Zaner-Bloser *Manual 144* (<https://archive.org/details/zaner-method-writing-manual-144>). Public domain, as recorded in [benchmarks/neat-penmanship/source.md](../benchmarks/neat-penmanship/source.md).

## Sample and fixture photos

- `handwriting-sample.jpg` (and its HEIC version): one adult's notebook page, in the repository since the first public release. Who wrote it and on what terms is not recorded. It is in the image and in the public sample report.
- `tests/fixtures/samples/`: letters from 1722 and 1889, a 1929 receipt, a script font specimen, a signature font poster, a tracing worksheet, a typewritten letter and a letter template. Where each came from, and under what licence, is not recorded ([README](../tests/fixtures/samples/README.md)).

Both need their source written down, or replacing with pages whose source and terms are known.

## Pretrained models and their training data

| Model | Weights licence | Trained on | Here |
| --- | --- | --- | --- |
| PaddleOCR PP-OCRv5 detection and recognition, PP-DocLayout | Apache-2.0 | Not fully disclosed | Default engine; downloaded at build or first use |
| TrOCR `microsoft/trocr-base-handwritten` | MIT (model card) | IAM (non-commercial research only) | Optional tier, off (`VAHINI_WITH_TROCR=0`) |
| Surya (datalab) | Weights: modified AI Pubs Open Rail-M, "free for research, personal use, and startups under $5M funding/revenue" | Not disclosed | Optional tier, off (`VAHINI_WITH_SURYA=0`); checkpoint not recorded |

Turning on TrOCR or Surya for Free or Pro reports is an owner decision because of these terms.
