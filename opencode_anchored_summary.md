## Goal
- Refine CWA storm-radius (暴風半徑) rendering in `plot_web.py`: fix playback crashes, drive circles by timeline only (no stuck end-time layer), and stop interpolating radius between CWA times (step at CWA data times); plus add a lat/lon graticule toggle. Deploy via git when user asks.

## Constraints & Preferences
- Self-contained HTML (data inline, no server); needs internet only for CDN tiles at open.
- `config.json` is gitignored/local-only (CWA API key). Repo auto-commits hourly via `scheduled_update.bat` → keep working tree clean of stray files.
- User wants: WeatherNext removed (its track just duplicated CWA; pending a real Google predicted-path source); graticule added; radius MUST NOT interpolate — only change at times CWA actually specifies.
- User said "先等一下" re deployment → do NOT commit/push until explicitly asked.

## Progress
### Done
- Playback null-crash fixed: `renderPlayback` guards `quadrantCirclePoints` with `hasQuad7 ? ... : []` (root cause was `r7` null at forecast times after earlier Task-2 change).
- `buildQuadTimeline` rewritten to use ONLY the selected (latest) CWA bulletin's forecasts (was aggregating all historical bulletins → same absolute time collided → radius oscillated 250↔80 every 6h). `rebuildTimelines` updated to pass `info` + `t.latest`.
- Removed always-on end-time circles: deleted `staticRadiusGrp` + `drawStormRadiiStatic`; `renderFull()` now calls `renderPlayback()` so a single layer draws circles at the current playhead (follows timeline/scrub/play).
- Removed WeatherNext entirely from page: dropped `drawWeatherNext`, `WN_COLOR`, `wnGrp`, overlay entry, help-modal + legend text; `AGENTS.md` annotated as temporarily disabled.
- Committed + pushed: `57c01d6` "Fix storm-radius playback + remove WeatherNext layer" (files: `AGENTS.md`, `output/各國颱風路徑.html`, `plot_web.py`); branch `main` up to date with `origin/main`.
- Added lat/lon graticule: `buildGraticule(step)` draws 5°-spaced light-grey dashed lines (`#9aa0a6`, weight 0.6, opacity 0.55, `interactive:false`); registered as `overlays['經緯度線']` (default ON); help-modal note added. Regenerated HTML, page initializes OK.
- Cancelled radius interpolation (`quadAt`): changed to step (hold previous CWA value), fixed boundary `T < b.t` so the radius changes exactly AT the CWA time.
- **Investigation of "empty radius maps" resolved as a FALSE ALARM:** the data is NOT empty. `typhoons[0]` in the current JSON is **TD24** (a Tropical Depression), which legitimately has no storm-circle data (all radius-map keys empty). The real typhoons — **SAUDEL** (`_cwa_fc_radius7_map_by_tau`=9 entries, r7avg 250→100), **NARRA** (=5, r7avg 80), **ATSANI** (=2, r7avg 80) — all have full radius data. `fetch_typhoon2000.py` parsing is correct (saved raw CWA response confirms `Circle15ms:{"Radius":"320"}` captured). No fetch/data fix needed.
- **Verified step behavior with REAL SAUDEL data** (harness on regenerated HTML): quadAt holds 250 across 08-24~08-27, jumps to 200 exactly at 08-28, to 100 at 08-29 — pure stepping at CWA times, no interpolation. Synthetic test also passed.

### In Progress
- (none — all code changes complete and verified)

### Blocked
- Deployment pending user go-ahead ("先等一下" earlier).

## Key Decisions
- Radius sources: analysis-time (tau=0) → dashed quadrant circles from `_cwa_an_radius7_quad_map`/`_cwa_an_radius10_quad_map`; forecast-time (tau>0) → solid average circle from `_cwa_fc_radius7_map_by_tau`/`_cwa_fc_radius10_map_by_tau`; fall back to `windKtToRadius(pos.wind)` only when CWA value absent.
- Circles follow the timeline via one `playbackGrp` layer (no separate static layer).
- WeatherNext removed, not fixed (free Open-Meteo returns weather-at-a-point, not a cyclone path).
- Graticule default ON (user can toggle off via layer control).
- Radius steps (no interpolation), changing at the CWA time, per explicit user request.
- TD (e.g. TD24) typhoons have no radii and render no storm circle — expected, not a bug.

## Next Steps
1. Await user decision on deployment: commit + push the graticule feature and the `quadAt` step change (currently uncommitted: `plot_web.py` + regenerated `output/各國颱風路徑.html`). User previously said wait — only deploy when explicitly asked.
2. Keep working tree free of temp diagnostic files before any commit (hourly auto-commit hygiene).

## Critical Context
- `quadAt(qt, T)` ~line 963: boundary `if (T <= qt[0].t) return qt[0]; if (T >= qt[last].t) return qt[last];` then loop `if (T >= a.t && T < b.t)` returns `a`'s values (step). At exactly `b.t` it falls to the next segment and returns `b`'s value (change happens AT the CWA time — user requirement). Verified on real SAUDEL data.
- Data structure: `output/各國颱風路徑.json` is the "latest" format — typhoons have `agencies` + `_cwa_*` radius maps at top level (NO `entries` array); historical `entries` live in `各國颱風路徑_all.json`. TD24 is typhoon[0] and has no radii.
- The "empty radius" alarm was caused by inspecting typhoon[0]=TD24; real storms (index 1/2/3) have full data.
- `output/各國颱風路徑.html` embeds DATA inline; harness uses a Leaflet mock (Proxy) to eval the page script without a browser.
- Git: last push `57c01d6`; uncommitted working changes now = `plot_web.py` (graticule + quadAt step + boundary fix) and regenerated `output/各國颱風路徑.html`. `AGENTS.md` already committed.

## Relevant Files
- `C:\program_code\2026\Web_typhoontrack\plot_web.py` — primary edit target: `quadAt` (step + boundary), `buildQuadTimeline`, `rebuildTimelines`, `renderFull`/`renderPlayback`, graticule `buildGraticule` + `overlays['經緯度線']`, removed `drawWeatherNext`.
- `C:\program_code\2026\Web_typhoontrack\output\各國颱風路徑.html` — regenerated page (graticule + step radius); not yet committed.
- `C:\program_code\2026\Web_typhoontrack\output\各國颱風路徑.json` — CWA source data; radius maps ARE populated for SAUDEL/NARRA/ATSANI; TD24 has none (expected).
- `C:\program_code\2026\Web_typhoontrack\fetch_typhoon2000.py` — radius parsing confirmed correct (lines 242-335); no change needed.
- `C:\program_code\2026\Web_typhoontrack\AGENTS.md` — WeatherNext-disabled note (already committed in 57c01d6).
- `C:\program_code\2026\Web_typhoontrack\scheduled_update.bat` — hourly auto git add/commit/push (working-tree hygiene).
