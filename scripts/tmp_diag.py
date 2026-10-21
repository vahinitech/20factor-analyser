# Throwaway diagnostics for #277 (never merged).
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import benchmark as b

for name in sys.argv[1:]:
    folder, meta = b._load_set(name)
    b._apply_settings(meta)
    import ink_geometry as ig
    import scoring
    from scoring_parts import advisory
    import cv2
    for page in b._pages(folder):
        raw, arr = b._image(folder, page, meta)
        reader = json.load(open(os.path.join(folder, "reader", page + ".json")))
        _f, hand = b._reader_lines(arr, raw, reader, meta)
        rows, cover = ig.reader_rows(arr, hand)
        checks = advisory.run_checks(arr, hand)
        st = checks["style"] or {}
        print(f"\n### {page} {arr.shape} style={st.get('verdict')} {st.get('shares')} used={st.get('wordsUsed')} {st.get('reason','')}")
        for l in hand:
            print("  hand", [round(v) for v in l["box"]], repr(l["text"])[:40])
        for r in rows:
            print("  row ", [round(v) for v in r["box"]], repr(r["text"])[:40])
        if rows:
            fx = scoring._extract_features(arr, rows, {})
            print("  rows fx", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in fx.items() if k in ("size_cv","size_basis","size_count","left_cv","line_wave","line_slope_abs","words_off_size","letter_gap_cv")})
        fx = scoring._extract_features(arr, hand, {})
        print("  hand fx", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in fx.items() if k in ("size_cv","size_basis","size_count","left_cv","line_wave","line_slope_abs","words_off_size","letter_gap_cv")})
