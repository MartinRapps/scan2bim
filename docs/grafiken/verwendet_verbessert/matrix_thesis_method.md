# Matrix figures for the bachelor thesis

- Combined stage observations: **36**
- Complete stage observations: **28**
- Incomplete stage observations: **8**
- STS rows: **24**; SuGaR-Coarse rows: **12**
- Source batches: historical `matrix_full_pipe`, `matrix_rest`, and the completed `matrix_sugar_followup_12`
- Image metrics: **object-masked-only**; model stage is recorded separately

## Files used

- `manifest.json`: completion status, FPS, variant and camera model
- `parameters.json`: resolution, STS, SIFT and mesh parameters
- `metrics/sts_masked.json`: PSNR, SSIM and LPIPS
- `metrics/sugar_coarse_masked.json`: successful SuGaR-Coarse PSNR, SSIM and LPIPS
- `masks/ideal/mask_coverage_report.json`: empty-mask fraction
- `pipeline_run/run.md`: archived step durations for the time quotient
- `run.log`: detailed failure reason and last reached stage
- `matrix_overview_table.pdf`: grouped overview with PSNR, SSIM and LPIPS under 2 FPS, 5 FPS and Average
- `matrix_combined_overview_table.pdf`: successful historical A/STS rows together with the completed SuGaR-Coarse rows
- `matrix_sugar_overview_table.pdf`: grouped SuGaR-Coarse overview under 2 FPS, 5 FPS and Average
- `matrix_sugar_status_table.pdf`, `matrix_sugar_psnr_table.pdf`, `matrix_sugar_ssim_table.pdf`, `matrix_sugar_lpips_table.pdf`, `matrix_sugar_time_quality_table.pdf`: stage-specific SuGaR-Coarse figures

## Time/quality quotient

The runtime is the sum of the archived STS workspace, STS training, object filtering, SuGaR meshing and centerline/postprocess steps. SAM3, COLMAP, rendering and metric-container time are not included because the matrix did not archive their per-experiment wall-clock intervals separately. The displayed relative quality index is the mean of min-max normalized PSNR and SSIM plus inverted LPIPS across complete runs. Failed routes are not ranked, even if an STS baseline metric exists.

## Interpretation rule

The previous SIMPLE_RADIAL-A rows are included for completeness and marked with `*`. SuGaR rows with `†` contain an STS baseline metric but their SuGaR route is incomplete; they must not be interpreted as successful SuGaR results. Green cells identify the best available result within an FPS column, not a proof of statistical significance.

The `Average` column in the metric tables is the arithmetic mean of the 2-FPS and 5-FPS values for the same route and resolution. It is shown only when both FPS runs are complete and successful. A gray/orange dash marks an incomplete pair; this avoids presenting a one-sided average as a balanced FPS comparison.

The `sts_masked.json` file in a failed historical `simple_radial_sugar` experiment is the STS baseline metric produced before the SuGaR-specific rendering step. It is not a successful SuGaR metric. The completed `matrix_sugar_followup_12` is evaluated from `sugar_coarse_masked.json`; its `sugar_refined_masked.json` files are explicitly skipped because no refined PLY was exported.

Consequently, the older `simple_radial_sugar` values in the original STS
overview must not be compared numerically as if they were SuGaR-Coarse values.
The combined overview uses successful historical STS/A rows together with the
new, genuinely rendered SuGaR-Coarse rows and labels the model stage
separately.

Resolution caveat: lower-resolution runs are evaluated in their own downsampled image domain. Downsampling can smooth edge misalignment, high-frequency noise and mask-boundary errors, so higher PSNR/SSIM or lower LPIPS at low resolution does not prove better geometry. The time/quality quotient is therefore an exploratory screening result, not the primary scientific ranking. Runtime covers the archived STS-to-postprocess steps, not the complete SAM3/COLMAP/render/metric wall time.
