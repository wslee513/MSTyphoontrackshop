## Goal
- Refine CWA storm-radius (暴風半徑) rendering in `plot_web.py`: fix playback crashes, drive circles by timeline only (no stuck end-time layer), and stop interpolating radius between CWA times (step at CWA data times); plus add a lat/lon graticule toggle. Deploy via git.

## Constraints & Preferences
- Self-contained HTML (data inline, no server); needs internet only for CDN tiles at open.
- `config.json` is gitignored/local-only (CWA API key). Repo auto-commits hourly via `scheduled_update.bat` → keep working tree clean of stray files.
- User wants: WeatherNext removed (its track just duplicated CWA; pending a real Google predicted-path source); graticule added; radius MUST NOT interpolate — only change at times CWA actually specifies.
- User said "先等一下" re deployment at the graticule step → do NOT commit/push until explicitly asked.

## Progress
### Done
- Playback null-crash fixed: `renderPlayback` guards `quadrantCirclePoints` with `hasQuad7 ? ... : []` (root cause was `r7` null at forecast times after earlier Task-2 change).
- `buildQuadTimeline` rewritten to use ONLY the selected (latest) CWA bulletin's forecasts (was aggregating all historical bulletins → same absolute time collided → radius oscillated 250↔80 every 6h). `rebuildTimelines` updated to pass `info` + `t.latest`.
- Removed always-on end-time circles: deleted `staticRadiusGrp` + `drawStormRadiiStatic`; `renderFull()` now calls `renderPlayback()` so a single layer draws circles at the current playhead (follows timeline/scrub/play).
- Removed WeatherNext entirely from page: dropped `drawWeatherNext`, `WN_COLOR`, `wnGrp`, overlay entry, help-modal + legend text; `AGENTS.md` annotated as temporarily disabled.
- Committed + pushed: `57c01d6` "Fix storm-radius playback + remove WeatherNext layer" (files: `AGENTS.md`, `output/各國颱風路徑.html`, `plot_web.py`); branch `main` up to date with `origin/main`.
- Added lat/lon graticule: `buildGraticule(step)` draws 5°-spaced light-grey dashed lines (`#9aa0a6`, weight 0.6, opacity 0.55, `interactive:false`); registered as `overlays['經緯度線']` (default ON); help-modal note added. Regenerated HTML, page initializes OK.
- Cancelled radius interpolation (`quadAt`): changed to step (hold previous CWA value), and fixed boundary `T < b.t` so the radius changes exactly AT the CWA time (verified with synthetic radii: T+48h jumps 200→250, T+96h jumps 250→300). Regenerated HTML.

### In Progress / Open
- **Discovered blocking data issue (separate from code):** current `output/各國颱風路徑.json` has the CWA radius-map keys present but EMPTY (`_cwa_fc_radius7_map_by_tau` = 0 keys, `_cwa_an_radius7_map` = 0 keys, `_cwa_fc_radius7_quad_map` absent). So the regenerated page currently falls back to wind-*estimate* circles, not CWA data. Likely a `fetch_typhoon2000.py` parsing / CWA-API issue (the maps were populated in an earlier session, then emptied — possibly by an hourly auto-fetch). User has NOT yet been asked / no decision made on whether to investigate.
- The `quadAt` step change is verified correct only with synthetic radii (because real on-disk data has no radii to test against).

### Blocked
- (none)

## Key Decisions
- Radius sources: analysis-time (tau=0) → dashed quadrant circles from `_cwa_an_radius7_quad_map`/`_cwa_an_radius10_quad_map`; forecast-time (tau>0) → solid average circle from `_cwa_fc_radius7_map_by_tau`/`_cwa_fc_radius10_map_by_tau`; fall back to `windKtToRadius(pos.wind)` only when CWA value absent (now the only source given empty maps).
- Circles follow the timeline via one `playbackGrp` layer (no separate static layer).
- WeatherNext removed, not fixed (free Open-Meteo returns weather-at-a-point, not a cyclone path).
- Graticule default ON (user can toggle off via layer control).
- Radius steps (no interpolation), changing at the CWA time, per explicit user request.

## Next Steps
1. Await user decision on the empty-CWA-radius-maps finding: investigate `fetch_typhoon2000.py` / CWA API (why 0 entries), OR proceed against a data version that has radii.
2. After radius data is present (or confirmed), do a real end-to-end harness check with actual CWA radii to confirm stepped circles render.
3. Only after user says so: commit + push the graticule feature and the `quadAt` step change (currently uncommitted: `plot_web.py` + regenerated `output/各國颱風路徑.html`).
4. Keep working tree free of temp diagnostic files before any commit (hourly auto-commit hygiene).

## Critical Context
- `quadAt(qt, T)` ~line 963: boundary `if (T <= qt[0].t) return qt[0]; if (T >= qt[last].t) return qt[last];` then loop `if (T >= a.t && T < b.t)` returns `a`'s values (step). Subtle: at exactly `b.t` it falls to the next segment and returns `b`'s value (change happens AT the CWA time — user requirement).
- `buildQuadTimeline(info, latest)` ~line 947: iterates `info.agencies` CWA forecasts; tau0 pulls from analysis maps (`_cwa_an_radius*_map`/`_cwa_an_radius*_quad_map` by lat,lon key), tau>0 pulls from `_cwa_fc_radius*_map_by_tau`. Currently both source maps are empty in the on-disk JSON.
- `playback.tStart/tEnd` come from `buildTimeline` (position track of selected entry); quad timeline may cover a different (later) span.
- `output/各國颱風路徑.html` embeds DATA inline; harness uses a Leaflet mock (Proxy) to eval the page script without a browser.
- Git: last push `57c01d6`; uncommitted working changes now = `plot_web.py` (graticule + quadAt step + boundary fix) and regenerated `output/各國颱風路徑.html`. `AGENTS.md` already committed.

## Relevant Files
- `C:\program_code\2026\Web_typhoontrack\plot_web.py` — primary edit target: `quadAt` (step + boundary), `buildQuadTimeline`, `rebuildTimelines`, `renderFull`/`renderPlayback`, graticule `buildGraticule` + `overlays['經緯度線']`, removed `drawWeatherNext`.
- `C:\program_code\2026\Web_typhoontrack\output\各國颱風路徑.html` — regenerated page (graticule + step radius); not yet committed.
- `C:\program_code\2026\Web_typhoontrack\output\各國颱風路徑.json` — CWA source data; **currently has EMPTY radius maps (0 entries)** — blocks real verification, likely fetch regression.
- `C:\program_code\2026\Web_typhoontrack\fetch_typhoon2000.py` — candidate for the empty-radius-maps investigation (parsing of CWA `W-C0034-005` radius fields, `_cwa_fc_radius7_map_by_tau` population).
- `C:\program_code\2026\Web_typhoontrack\AGENTS.md` — WeatherNext-disabled note (already committed in 57c01d6).
- `C:\program_code\2026\Web_typhoontrack\scheduled_update.bat` — hourly auto git add/commit/push (working-tree hygiene; may be overwriting radius data with empty fetches).
