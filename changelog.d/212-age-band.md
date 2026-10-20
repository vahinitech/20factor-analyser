- The report request takes an optional `age_band`, the writer's age as
  two whole-year ages from 3 to 18 such as `6-7`, never a birth date
  (#212). A band in any other form is refused with HTTP 422
  `age_band_invalid` before the photo is read. A valid band is echoed in
  the report as `age_band` and not stored; no score uses it yet, so age
  norms (#216) have something to key on when they come. The request,
  report and error schemas are regenerated.
