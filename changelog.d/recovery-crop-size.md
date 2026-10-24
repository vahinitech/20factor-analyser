- Line recovery detects each crop at the page setting's scale but at most
  3 MP, instead of up to 4000x1500 (6 MP). On the stage photo of 23
  October 2026 recovery fell from 94 s to 54 s (two CPUs) and the memory
  peak from 2.2 GB to 1.5 GB; the UJI pages read as before (9.41% of
  letters wrong against 9.54%; UPV_W51 13.84% to 14.47%, UJI_W13 and
  UPV_W57 better). The reader output in `benchmarks/uji-clean/reader/`
  was captured again by the live benchmark.
