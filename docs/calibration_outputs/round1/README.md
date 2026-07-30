# Round 1 Calibration — Real Tool Output Evidence

This directory contains the **actual generated output** from running the
production pipeline (`python3 src/run_transcription.py <clip>.wav --model base
--no-viewer --no-copy-audio --output-dir calibration_audio/out`) against the
13 real acted-emotion film clips described in
[`docs/CALIBRATION.md`](../../CALIBRATION.md). It exists because the original
`CALIBRATION.md` only reported a summary *table* of before/after tags —
this directory is the primary evidence the table was built from, so a
reader can verify the claims directly against real tool output rather than
someone's transcription of it.

Only derived text/JSON output is committed (`transcript.md`, `omni.md`,
`analysis.json`). Per `.gitignore`, raw `.wav` audio is never committed —
these are also excerpted, transformed (transcribed/analyzed) derivative text
outputs of already-public-domain film audio (see source links below), not
copyrighted media itself. Each clip folder's `transcript.md` also links to
sibling files (`emotions.json`, `things.json`, `meta.json`, `glossary.json`,
`noteworthy.json`) that were generated locally but are **not** committed here
to keep this evidence set focused on the transcript/omni/analysis trio the
calibration write-up actually cites — those links will 404 in this repo
copy; the full local output tree is described in `CALIBRATION.md`.

## Clip index

| # | Clip ID | Film (year) | True emotion / category | Final (tuned) output | Before-tuning output |
|---|---------|-------------|--------------------------|------------------------|------------------------|
| 01 | `01_notld_calm_graveyard` | Night of the Living Dead (1968) | Calm/neutral (control 1) | [round1/01_notld_calm_graveyard](01_notld_calm_graveyard/) | [round1/01_notld_calm_graveyard_before_tuning](01_notld_calm_graveyard_before_tuning/) |
| 02 | `02_notld_fear_panic` | Night of the Living Dead (1968) | Fear/panic | [round1/02_notld_fear_panic](02_notld_fear_panic/) | [round1/02_notld_fear_panic_before_tuning](02_notld_fear_panic_before_tuning/) |
| 03 | `03_detour_anger_shouting` | Detour (1945) | Anger/panic (strangulation argument) | [round1/03_detour_anger_shouting](03_detour_anger_shouting/) | [round1/03_detour_anger_shouting_before_tuning](03_detour_anger_shouting_before_tuning/) |
| 04 | `04_detour_deceptive` | Detour (1945) | Deceptive-sounding / tense manipulation | [round1/04_detour_deceptive](04_detour_deceptive/) | [round1/04_detour_deceptive_before_tuning](04_detour_deceptive_before_tuning/) |
| 05 | `05_detour_resignation` | Detour (1945) | Resignation/flat affect | [round1/05_detour_resignation](05_detour_resignation/) | [round1/05_detour_resignation_before_tuning](05_detour_resignation_before_tuning/) |
| 06 | `06_hgf_joy` | His Girl Friday (1940) | Joy / rapid comedic banter | [round1/06_hgf_joy](06_hgf_joy/) | [round1/06_hgf_joy_before_tuning](06_hgf_joy_before_tuning/) |
| 07 | `07_hgf_calm_neutral` | His Girl Friday (1940) | Calm/neutral (control 2) | [round1/07_hgf_calm_neutral](07_hgf_calm_neutral/) | [round1/07_hgf_calm_neutral_before_tuning](07_hgf_calm_neutral_before_tuning/) |
| 08 | `08_doa_surprise` | D.O.A. (1950) | Surprise / shock reveal | [round1/08_doa_surprise](08_doa_surprise/) | [round1/08_doa_surprise_before_tuning](08_doa_surprise_before_tuning/) |
| 09 | `09_reefer_contempt_courtroom` | Reefer Madness (1936) | Contempt / moral condemnation (courtroom closing) | [round1/09_reefer_contempt_courtroom](09_reefer_contempt_courtroom/) | [round1/09_reefer_contempt_courtroom_before_tuning](09_reefer_contempt_courtroom_before_tuning/) |
| 10 | `10_reefer_sadness_panic` | Reefer Madness (1936) | Sadness/grief/panicked crying | [round1/10_reefer_sadness_panic](10_reefer_sadness_panic/) | [round1/10_reefer_sadness_panic_before_tuning](10_reefer_sadness_panic_before_tuning/) |
| 11 | `11_notld_barbra_breathless` | Night of the Living Dead (1968) | Genuine panicked/breathless screaming (follow-up pass, stumble-detector stress test) | [round1/11_notld_barbra_breathless](11_notld_barbra_breathless/) | *(follow-up-only clip, no before-tuning run exists — sourced after the threshold changes were already made)* |
| 12 | `12_hgf_rapid_frantic` | His Girl Friday (1940) | Second fast-dialogue scene (follow-up pass, stumble-detector stress test) | [round1/12_hgf_rapid_frantic](12_hgf_rapid_frantic/) | *(follow-up-only clip, see above)* |
| 13 | `13_reefer_nervous` | Reefer Madness (1936) | Dealer-negotiation dialogue, moderate pace (follow-up pass, stumble-detector stress test) | [round1/13_reefer_nervous](13_reefer_nervous/) | *(follow-up-only clip, see above)* |

Clips 01–10 are the original calibration pass (with a before/after
comparison, since the threshold changes affected their tags). Clips 11–13
were sourced during the same-day follow-up investigation (see
`CALIBRATION.md`'s "Follow-up investigation" section) — they were run only
once, after tuning, since their purpose was to stress-test the
already-changed stumble detector, not to demonstrate a before/after delta.

Each clip folder contains:

- `transcript.md` — the human-readable transcript with inline `🎙️ ACOUSTIC:`
  tags, Jefferson markers, and certainty annotations.
- `omni.md` — the comprehensive single-file output (all views/indicators
  combined).
- `analysis.json` — structured deception/veracity/voice-dynamics/clinical
  data for the clip.

## Source films (all public domain, archive.org)

- [Night of the Living Dead (1968)](https://archive.org/details/night_of_the_living_dead_dvd)
- [Detour (1945)](https://archive.org/details/Detour_movie)
- [His Girl Friday (1940)](https://archive.org/details/his_girl_friday)
- [D.O.A. (1950)](https://archive.org/details/DOA1950)
- [Reefer Madness (1936)](https://archive.org/details/reefer-madness-1936-inter-pathe-films)

See [`docs/CALIBRATION.md`](../../CALIBRATION.md) for exact timestamps, the
full before/after tag comparison table, threshold-change rationale, and
known limitations.
