# Synthetic metric and import references

These fixtures contain no real athlete data.

- `metric-reference.json` is consumed by the mobile calculation tests and
  `tests/test_mobile_metric_reference.py`. It covers matching LTHR, HRR-corrected
  LTHR, HRR, max-HR boundaries, Daniels estimates, and explicitly calibrated
  HR/pace stress approximations. It deliberately excludes desktop's missing-input
  fallback behavior and VO₂max clipping.
- `synthetic-run.tcx` is an illustrative 30-minute / 6 km run with 10-second HR
  samples. The activity name explicitly identifies it as synthetic.
- `synthetic-run.fitops.json` is the same activity in the version 1 transfer
  envelope. The importer test checks that both files normalize to the same
  canonical record. Its exported date is fixed for reproducibility.

To test on a phone, copy the TCX or JSON file to Downloads, import it through
Activities, and review it before saving. A synthetic fixture must not be presented
as proof of a real Huawei data read or a physiological test.
