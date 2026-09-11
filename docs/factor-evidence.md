# Factor evidence locations

The report pairs a complete crop with a small page map highlighting its source. Evidence is selected from all accepted handwriting regions, independently of the eight-image preview limit.

Each `factor_regions` entry keeps `url` and `caption` and adds:

- `status`: `measurement`, `context`, or `unavailable`.
- `bbox`: `[x, y, width, height]` of the encoded crop in processed-image pixels, or null when unavailable.
- `source_size`: `[width, height]` of that processed image.
- `coordinate_space`: `processed-image`. Coordinates follow EXIF correction and server resizing; they are not raw upload coordinates.
- `region_ids`: selected handwriting regions, numbered top to bottom then left to right within this evidence response. These identify detected regions, which may be words or lines depending on the OCR backend.
- `selection_method`: the rule used to select the crop.
- `location_url`: a small page map with selected boxes highlighted.

Size evidence selects the largest height deviation from the median. Baseline and straightness evidence select the largest absolute polygon angle. Margin evidence selects the largest corrected-left-edge deviation, using the scorer's camera-tilt correction. Word-spacing evidence uses the scorer's row grouping and selects the largest normalized-gap deviation, showing both adjacent regions.

A selected measurement is a contributing region, not a claim that it is the only problem. Factors based on OCR confidence, character-width proxies, loop-letter frequency or composite scores are explicitly labeled as context. They cannot identify an exact faulty character from their current scoring inputs. Factors 13-16 require sensor data and return an empty URL with unavailable status.

Aggregate images and page maps retain accepted handwriting rectangles and blank the rest. This prevents excluded headers and labels from returning through whole-page previews. It does not correct a printed region that the upstream classifier mistakenly accepts, or separate printed and handwritten pixels inside one accepted box.

The browser uses `object-fit: contain` so the crop is not cut off again during display. Older consumers can continue reading `url` and `caption`, but must allow an empty URL for unavailable evidence. Changes to scoring proxies and minimum evidence are tracked in issues #46 and #47.
