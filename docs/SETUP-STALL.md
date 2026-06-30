# Vahini Stall Demo — Local Setup & Run Guide

**Event:** stall demo on **June 13th** · **Goal:** a visitor writes on a sheet, you photograph it,
and a polished 20-factor report appears on screen in seconds — optionally shared to their phone by QR.

This guide is written so a non-technical operator can set it up on a Windows or Mac PC.

---

## 0. What you need

- A **laptop/PC** (Windows or Mac), fully charged + charger.
- The **Vahini project folder** (all the files listed in §2) copied onto the PC.
- A modern browser — **Google Chrome** recommended.
- **Printed practice sheets** (from `Vahini Practice Sheet.html` or `Vahini Sample Text.html`).
- Pens.
- *Optional, for QR sharing:* internet (venue Wi-Fi **or** a phone hotspot) and a Google account.
- *Optional, for the "wow" demo:* the Vahini IMU pen.

> The core demo (write → photo → report → Save as PDF) works **100% offline**. Internet is only
> needed for the optional **Google Drive + QR** sharing step.

---

## 1. Get the files onto the PC

1. Download the whole project as a folder (e.g. `Vahini`).
2. Put it somewhere easy, like the **Desktop**: `Desktop/Vahini/`.
3. **Do not rename or move individual files** — they reference each other by name.

---

## 2. Check the folder contents

Inside `Vahini/` you should see these (names matter):

```
Vahini/
├─ Vahini Studio.html          ← THE APP (open this)
├─ Vahini Practice Sheet.html  ← print these for visitors
├─ Vahini Sample Text.html     ← alternative, richer practice passage
├─ Vahini Demo Guide.html      ← booth playbook (this flow, illustrated)
├─ Vahini User Guides.html     ← how-to guides per audience
├─ Vahini Writing Assistant.html
├─ Vahini Accuracy & Document Types.html
├─ Vahini Handwriting Report.html
├─ engine.js  factors.js  imu.js  ocr.js  forecast.js
├─ report-render.js  app.js  share.js
├─ report.css  studio.css
├─ assets/        ← contains vahini-logo.png  (must be present)
└─ uploads/       ← a sample image lives here
```

If `assets/vahini-logo.png` is missing, the logo won't show — make sure the `assets` folder copied over.

---

## 3. Print the practice sheets (do this the night before)

1. Double-click **`Vahini Practice Sheet.html`** → it opens in the browser.
2. Click **"Switch sentence"** if you want a different passage.
3. Click **"Print this sheet"** (or press **Ctrl/Cmd + P**).
4. In the print dialog: **Paper = A4**, **Margins = None/Default**, **Background graphics = ON**.
5. Print **30–50 copies**. (For a fuller sample, use `Vahini Sample Text.html` the same way.)

---

## 4. Run the app — pick ONE method

### Method A — Simplest (offline, PC only)
1. Double-click **`Vahini Studio.html`**. It opens in your browser. That's it.
2. Photos are added by clicking the upload box and choosing an **image file** on the PC.
   - This works if you transfer the visitor's photo to the PC (USB, AirDrop, email, or a webcam app
     that saves a file).

### Method C — Best (adds real text recognition: PP-OCRv5, fully local)
Run the bundled recognition server once and the app upgrades itself: the written text is
**detected and recognised on the PC** (PaddleOCR **PP-OCRv5** — no cloud, no typing the
reference sentence, true spelling/word checks in the report).

1. One-time setup (needs internet once, to download ~20 MB of models):
   ```
   pip install paddlepaddle paddleocr flask flask-cors
   ```
2. Start it (from the `Vahini` folder) and leave it running:
   ```
   python ppocr-server.py
   ```
3. That's it — the app auto-detects `http://127.0.0.1:8868/ocr`. The report's
   "Detected & recognised text" panel now shows the writer's actual words, and the
   reference sentence becomes optional.

> No internet at the stall? Do the `pip install` + one test run at home the night before —
> after the models download, PP-OCRv5 runs fully offline.

### Method B — Recommended (lets a phone photograph straight into the app)
This serves the app on your local network so a **phone on the same Wi-Fi** can open it and use its
camera directly — the smoothest booth flow.

1. Open a terminal in the `Vahini` folder:
   - **Windows:** open the folder, click the address bar, type `cmd`, press Enter.
   - **Mac:** right-click the folder → *New Terminal at Folder*.
2. Start a tiny local server (Python is pre-installed on Mac; on Windows install from python.org):
   ```
   python -m http.server 8000
   ```
   (If `python` doesn't work, try `python3 -m http.server 8000`.)
3. On the **PC**, open: `http://localhost:8000/Vahini%20Studio.html`
4. To use a **phone's camera**: find the PC's IP (shown by `ipconfig` on Windows / `ifconfig` on Mac,
   e.g. `192.168.1.42`), connect the phone to the **same Wi-Fi**, and open
   `http://192.168.1.42:8000/Vahini%20Studio.html` on the phone. Tap the upload box → the phone offers
   **"Take Photo"**.

> Tip: keep the PC screen as the "report display" and let visitors watch their result appear there.

---

## 5. The booth loop (≈60 seconds per visitor)

1. **Hand them a printed practice sheet** and a pen.
2. They **copy the sentence** in their normal handwriting (30–40 s).
3. On the app: type their **first name** → **Continue** → choose **Photo / Scan**.
4. **Take/upload the photo** of their writing → **Run analysis**.
5. The **report appears**. Show it on screen — point out their strengths, focus area, and the
   **Growth Forecast** (how much they can improve, and their writing-speed estimate).
6. Optionally **Save as PDF** and/or **share by QR** (§6).
7. Click **New report** for the next visitor.

*For VIPs:* choose **Vahini Writing Assistant** instead and let them write with the IMU pen — the live
208 Hz force/tilt/velocity stream on screen is the showstopper; press **Finish** to generate the report.

---

## 6. Optional — share the report to the visitor's phone by QR

This step needs internet (venue Wi-Fi or your phone hotspot) and a Google account.

1. In the report toolbar, click **Save as PDF** and save the file.
2. Click **QR / Share** → the panel opens with three steps.
3. Click **Open Google Drive**, upload the PDF, then **right-click it → Share → "Anyone with the link"
   → Copy link**.
4. Back in the panel, **paste the link** → click **Make QR**.
5. The visitor **scans the QR** with their phone camera and opens the report. Done.

> The QR image is generated online (the same connection you used for Drive). If you're fully offline,
> skip the QR and just hand over the PDF (AirDrop / email / WhatsApp) — or pre-upload a few sample
> reports to Drive and print their QRs in advance for a scripted demo.

---

## 7. 5-minute pre-event checklist (June 13th morning)

- [ ] Laptop charged + charger packed
- [ ] `Vahini` folder on the Desktop; `assets/vahini-logo.png` present
- [ ] `Vahini Studio.html` opens and shows the intake screen
- [ ] Ran one test: name → Photo/Scan → upload `uploads/test-handwriting.png` → report appears
- [ ] 30–50 practice sheets printed
- [ ] (If sharing) Wi-Fi/hotspot works, signed into Google Drive, did one QR test
- [ ] Browser zoom at 100%, screen brightness up, notifications off (Do Not Disturb)

---

## 8. Quick troubleshooting

| Symptom | Fix |
|---|---|
| Logo/images missing | The `assets` folder didn't copy. Re-copy the whole project folder intact. |
| Report looks unstyled | A `.css`/`.js` file is missing or renamed. Keep all files together with original names. |
| Photo won't analyse / "weak signal" | Use a sharper, well-lit, square-on photo of a few lines; fill the frame with the writing. |
| Camera option missing on phone | Use **Method B** (local server) and open via the PC's IP on the same Wi-Fi. |
| QR won't generate | You're offline. Connect Wi-Fi/hotspot, or hand over the PDF directly. |
| Scores look low for maths/diagram pages | Expected — see `Vahini Accuracy & Document Types.html`. Use prose practice sheets for assessment. |

---

## 9. Handy links (open these locally)

- **The app** → `Vahini Studio.html`  (try `Vahini Studio.html?demo=report` for an instant sample)
- **Booth playbook** → `Vahini Demo Guide.html`
- **How to read the report** → `Vahini User Guides.html`
- **Why the pen matters** → `Vahini Writing Assistant.html`
- **Accuracy & document types** → `Vahini Accuracy & Document Types.html`

Questions during setup: **info@vahinitech.com** · tailored support: **go@vahinitech.com**

— © 2026 Vahini Technologies · IMU Sensor Pen, Patent No. 584433
