# Explicit short-distance request corrections

This change only strengthens existing trip-distance interpretation. It does not
change model weights, provider settings, frontend/examples, route algorithms,
database contents, weather, speech recognition, or production deployment.

## Behavior

- `가까운 거리 우선`, `거리가 짧은 길`, `덜 걷고 싶어`, `빠른 길`,
  `빨리 도착하고 싶어`, and `지름길` express the existing `distance_m/minimize`
  preference. In this service, faster-arrival language maps to shorter walking
  distance; it is not a new real-time travel-time optimization feature.
- `경찰서에 가까운 길` and `병원과의 거리가 짧은 길` describe facility proximity,
  not the user's overall trip distance. Explicit rejection and existing
  last-mention cancellation remain respected.
- A distance-only request cannot activate CCTV/crossing cards without source
  evidence for those conditions. Explicit compound requests remain intact.

`distance_preference.short_distance_choice` is shared by the Laya preview
adapter and final Gemma intent normalization. The correction does not bypass
Gemma, execute route tools during preview, or change the current eight-card
schema. Crossing/bridge utilization changes from the separate local experiment
are not included.

## Verification and delivery

- 61 distance-specific fixture tests, including the reported phrase at the HTTP
  boundary, final parser omissions, negative/facility expressions, and compounds.
- 794 related backend tests passed (Laya adapters, final intent/unit tests;
  local speech/PyAV-dependent suites were not part of this run).
- 328 stored native Laya responses replayed successfully through the complete
  updated preview pipeline, without live model/API/DB calls.
- The tracked source archive is regenerated from a pinned source commit. Its
  runtime-alignment test includes the new shared helper and final intent parser.

No training/evaluation datasets, experimental programs, model files, keys,
private environment files or database backups are added to this MR. Regression
tests use model fixtures only; they do not train models or make paid calls.
This MR is for review, not an operational rollout. The operator must rebuild the
backend when applying it; a frontend-only rebuild does not update Python code.
