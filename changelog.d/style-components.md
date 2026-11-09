- The cursive/print style check counts each word's pen lifts with
  OpenCV's connected-components labelling instead of a pixel-by-pixel
  Python flood fill. The flood fill took about half of the benchmark
  replay's time in the first profiling run (#231). The count is the same
  8-connected components with the same size floor, so every score stays
  as it was; the flood fill remains as the test reference and as the
  fallback without cv2.
