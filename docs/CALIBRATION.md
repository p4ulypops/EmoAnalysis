# Voice-Dynamics Detector Calibration (2026-07-30)

This document records the empirical calibration of `analyze_voice_dynamics()`
in `src/run_transcription.py` against **real acted emotional speech**. Prior
to this pass, the function's thresholds had only been smoke-tested against
flat, unemotional TTS audio, so it was unknown whether they held up on
genuine vocal delivery (shouting, crying, panic, contempt, comedic banter,
etc.).

**Real tool output evidence:** this document summarizes results as tables;
the actual generated `transcript.md`/`omni.md`/`analysis.json` files for
every clip referenced below (13 in total, including the 3 follow-up-pass
clips) are committed at
[`docs/calibration_outputs/round1/`](calibration_outputs/round1/README.md)
— open that directory to verify any claim in this document against real
tool output rather than this summary alone.

## Method

10 short (10–30s) dialogue clips were extracted with `ffmpeg` (via HTTP
range requests directly against archive.org's CDN, so no full films were
downloaded) from six genuinely **public-domain** films on
[archive.org](https://archive.org), spanning a deliberate range of emotional
deliveries plus calm/neutral controls. Each clip was run through the full
production pipeline:

```
python3 src/run_transcription.py <clip>.wav --model base --no-viewer --no-copy-audio --output-dir calibration_audio/out
```

The resulting `🎙️ ACOUSTIC:` tags in `transcript.md` / `analysis.json` were
compared, segment by segment, against an honest human judgment of the actual
delivery in the source scene. Raw audio and pipeline outputs are **not**
committed to this repo (see `.gitignore`) — only the manifest, this
document, and the code changes are tracked.

## Clip manifest

| # | Clip ID | Film (year) | Source (archive.org) | Start–End | True emotion / character |
|---|---|---|---|---|---|
| 01 | `01_notld_calm_graveyard` | Night of the Living Dead (1968) | [archive.org/details/night_of_the_living_dead_dvd](https://archive.org/details/night_of_the_living_dead_dvd) | 4:04–4:26 | Calm/neutral (control 1) — Barbra & Johnny bantering about a grave marker |
| 02 | `02_notld_fear_panic` | Night of the Living Dead (1968) | [archive.org/details/night_of_the_living_dead_dvd](https://archive.org/details/night_of_the_living_dead_dvd) | 5:58–6:20 | Fear rising to panic — Johnny taunts Barbra, a ghoul appears, she flees |
| 03 | `03_detour_anger_shouting` | Detour (1945) | [archive.org/details/Detour_movie](https://archive.org/details/Detour_movie) | 1:01:30–1:01:55 | Anger/panic — Al & Vera's climactic drunken argument/strangulation |
| 04 | `04_detour_deceptive` | Detour (1945) | [archive.org/details/Detour_movie](https://archive.org/details/Detour_movie) | 40:00–40:25 | Deceptive-sounding, controlled manipulation — Vera coercing Al ("Siamese twins") |
| 05 | `05_detour_resignation` | Detour (1945) | [archive.org/details/Detour_movie](https://archive.org/details/Detour_movie) | 1:03:00–1:03:24 | Resignation/flat affect — Al's fatalistic voice-over monologue |
| 06 | `06_hgf_joy` | His Girl Friday (1940) | [archive.org/details/his_girl_friday](https://archive.org/details/his_girl_friday) | 20:08–20:38 | Joy/rapid comedic banter — newsroom reporters joking, fast overlapping dialogue |
| 07 | `07_hgf_calm_neutral` | His Girl Friday (1940) | [archive.org/details/his_girl_friday](https://archive.org/details/his_girl_friday) | 5:00–5:30 | Calm/neutral (control 2) — Hildy & Bruce discussing marriage/divorce, even tone |
| 08 | `08_doa_surprise` | D.O.A. (1950) | [archive.org/details/DOA1950](https://archive.org/details/DOA1950) | 2:10–2:36 | Surprise/shock reveal — the famous "I want to report a murder / I was" scene |
| 09 | `09_reefer_contempt_courtroom` | Reefer Madness (1936) | [archive.org/details/reefer-madness-1936-inter-pathe-films](https://archive.org/details/reefer-madness-1936-inter-pathe-films) | 50:00–50:30 | Contempt/moral condemnation — prosecutor's cold courtroom closing argument |
| 10 | `10_reefer_sadness_panic` | Reefer Madness (1936) | [archive.org/details/reefer-madness-1936-inter-pathe-films](https://archive.org/details/reefer-madness-1936-inter-pathe-films) | 41:37–41:57 | Sadness/grief/panicked crying — right after an accidental shooting ("Mary! You killed her... I'm sorry") |

**Note on sourcing:** an originally planned D.O.A. opening-scene control clip
(background-music-heavy, ~0:40) produced zero Whisper segments (no
detectable speech) and was replaced with clip 07 above as the second
calm/neutral control. All 10 target emotion categories from the brief
(anger, sadness, fear, joy, calm ×2, contempt, resignation, deceptive,
surprise) were successfully sourced and validated.

## Before/after tag comparison

"Tags" = the `🎙️ ACOUSTIC:` phenomena emitted per segment. ✅ = correct,
❌ = false positive, ⚠️ = plausible but weak signal.

| # | Clip | True emotion | Tags — BEFORE | Tags — AFTER | Verdict |
|---|------|--------------|----------------|----------------|---------|
| 01 | calm_graveyard | Calm (control) | `shaky` ❌ | *(none)* | **Fixed** |
| 02 | fear_panic | Fear→panic | `shaky` ×2 ❌ (CV-driven, no f0 basis) | *(none)* | CV false positives removed; no f0-based shaky signal was actually present in this clip either — see limitations |
| 03 | detour_anger_shouting | Anger/shouting/strangulation | `shaky` + `falling pitch` (mislabeled "resignation") | `shaky` + `falling pitch` (same) — never got `raised_voice` | ⚠️ Unchanged — shaky/falling-pitch correctly retained (genuine f0 signal); `raised_voice` false negative is a **documented structural limitation**, not threshold-fixed (see below) |
| 04 | detour_deceptive | Calm, controlled manipulation | *(none)* | *(none)* | ✅ Correct, unchanged |
| 05 | detour_resignation | Flat, quiet monotone | `quiet` + freeze event | `quiet` + freeze event | ✅ Correct, unchanged |
| 06 | hgf_joy | Energetic, fast comedic banter | `shaky` ×1 ❌ + spurious pitch arcs ×3 ❌ + stumbles ×4 ⚠️ | spurious pitch arcs removed; `shaky` false positive removed; stumbles ×4 retained | **Improved** — pitch/shaky noise removed; stumbles kept (see limitations, likely a Whisper-confidence artifact of old/fast audio, not clearly wrong) |
| 07 | hgf_calm_neutral | Calm relationship talk | `shaky` ×2 ❌ + `rising pitch` (+49Hz) ❌ + stumbles ×2 ⚠️ | `shaky` removed; `rising pitch` (+49Hz) still fires (just above new 40Hz bar); stumbles ×2 retained | **Improved** — shaky false positives gone; one borderline pitch-arc false positive remains (see limitations) |
| 08 | doa_surprise | Shock/tension reveal | `shaky` ×3 ❌, no distinct surprise signature | *(none)* | **Fixed** — false positives removed; detector has no positive signature for "surprise" specifically (known gap) |
| 09 | reefer_contempt_courtroom | Cold, controlled contempt | `shaky` ×3 + spurious `falling pitch` ❌ + 3 rising-pitch tags (1 arguably spurious) | `shaky` ×3 (genuine, f0-driven, unchanged) + 1 real rising-pitch arc (+74Hz) retained; spurious falling-pitch (seg0) and one duplicate rising-pitch tag removed | **Improved** — noise reduced; the 3 shaky flags are the one genuinely reproducible signal in this clip (contempt manifesting as high f0 variance under tight vocal control — an interesting, unanticipated finding) |
| 10 | reefer_sadness_panic | Panicked, grief-stricken shouting | `raised_voice` + `shaky` (CV-driven) | `raised_voice` retained (genuine); `shaky` removed (was CV-only, no f0 basis) | ✅ **Correct** — the one clip where `raised_voice` fired correctly; shaky flag was actually spurious once inspected and is now correctly dropped |

### Summary counts

- **False positives eliminated:** 9 `shaky` flags (01×1, 02×2, 06×1, 07×2, 08×3) and 4 spurious pitch-arc tags (06×3, 09×1) that had no basis in real vocal instability.
- **True positives retained:** all f0-driven `shaky` flags (03×2, 09×3), the genuine `raised_voice` on clip 10, the genuine falling-pitch arcs on clip 03, and the genuine rising-pitch arc on clip 09.
- **Unresolved:** `raised_voice` false negative on clip 03 (structural limitation, see below); one borderline pitch-arc false positive on clip 07; stumble flags on fast/old-audio dialogue (06, 07) that may be Whisper-confidence artifacts rather than genuine disfluencies.

## Threshold changes made

All changes are in `analyze_voice_dynamics()`, `src/run_transcription.py`.
The function signature and existing return structure are unchanged.

### 1. Shaky-voice detection — removed the RMS-CV branch as a standalone trigger

**Evidence:** Across 86 real dialogue segments sampled from all 10 clips,
`rms_cv` (coefficient of variation of frame-level RMS within a segment) had
**mean 0.75, median 0.69** — sitting almost exactly on top of the old `0.8`
cutoff — with **no separation between calm/joy and anger/fear/contempt
groups** (e.g. calm mean 0.78 vs. anger mean 0.77 vs. contempt mean 0.78 at
segment durations ≥1.5s). It fired on flatly-delivered lines ("San Francisco
last night", cv=2.12) as readily as on any emotional one, and it was the
sole cause of every false-positive `shaky` tag observed (clips 01, 02, 07,
08, 10). By contrast, `f0_std` (pitch standard deviation) showed real
separation: calm median ≈10.2, joy median ≈9.6, anger median ≈29.1, fear
median ≈35.7, contempt median ≈59.2 — and every f0-driven shaky flag in the
before-tuning run was on a segment with 50+ voiced pitch frames, i.e.
statistically well-supported.

**Change:**
```python
# OLD
shaky = False
if f0_std > 60 and f0_mean > 80:
    shaky = True
frame_rms = librosa.feature.rms(y=clip, frame_length=512, hop_length=256)[0]
if len(frame_rms) > 4:
    rms_cv = float(np.std(frame_rms) / (np.mean(frame_rms) + 1e-8))
    if rms_cv > 0.8:
        shaky = True

# NEW
shaky = False
if f0_std > 60 and f0_mean > 80 and f0_clean is not None and len(f0_clean) >= 6:
    shaky = True
frame_rms = librosa.feature.rms(y=clip, frame_length=512, hop_length=256)[0]
seg_dur_s = len(clip) / sr
if len(frame_rms) > 4 and seg_dur_s >= 1.5:
    rms_cv = float(np.std(frame_rms) / (np.mean(frame_rms) + 1e-8))
    if rms_cv > 1.4 and f0_std > 45 and f0_mean > 80:
        shaky = True
```

- Added a `len(f0_clean) >= 6` voiced-frame floor to the f0 branch (mirrors
  the floor already used for pitch-trend, below) so f0 statistics from
  near-silent/unvoiced segments can't spuriously trigger `shaky`.
- The RMS-CV branch is **no longer a standalone trigger**. It now requires
  `rms_cv > 1.4` (raised from 0.8, well above the observed ~0.6–1.0 noise
  band) **AND** a supporting, slightly relaxed f0 condition (`f0_std > 45`
  instead of 60), plus a minimum 1.5s segment duration so the frame-RMS
  estimate itself is statistically stable. This keeps amplitude instability
  as a corroborating signal without letting it fire alone.

### 2. Pitch-trend (rising/falling arc) threshold raised 25Hz → 40Hz

**Evidence:** the "segments" `analyze_voice_dynamics()` receives are
Whisper's merged speaker turns, often several sentences long — not single
utterances. A turn that simply strings together a few ordinary sentences
(each with its own normal end-of-sentence pitch fall or question-like rise)
can cross a 25Hz first-third/last-third delta purely by chance. This
produced a false "alarm/excitement" rising-arc tag (+49Hz) on a calm,
unhurried His Girl Friday conversation (clip 07) and 3 spurious arcs on the
fast-comedic-banter clip (06). Raising the bar to 40Hz preserves every
genuine arc observed (Detour's −153Hz/−76Hz falling arcs under real anger,
Reefer's +54Hz/+74Hz rising arcs under contempt) while dropping the weaker,
borderline false positives on clip 06. **Known residual:** clip 07 seg0
still measures +49Hz and remains above even the new 40Hz bar — flagged
below as an open limitation rather than further threshold-chased, since
lowering it further would reintroduce clip 06's false positives.

```python
# OLD: if pitch_delta_hz > 25 / < -25
# NEW: if pitch_delta_hz > 40 / < -40
```

### 3. RMS-ratio raised/quiet/whisper thresholds — left unchanged (documented limitation, not a threshold fix)

**Evidence considered:** clip 03 (Detour's shouted strangulation argument)
never triggered `raised_voice` even though it is unambiguously the loudest,
most aggressive delivery in the whole test set. Investigation showed this
is **not fixable by moving the `1.8` cutoff** — `global_rms` is computed
once per audio file, and this clip is uniformly loud throughout (segment
ratios all cluster 0.58–1.91 relative to its own elevated mean, since there
is no quiet baseline moment inside the 25s clip to contrast against).
Renormalizing against the median segment RMS instead of the whole-clip mean
was tested and made the problem slightly worse, not better (ratios shifted
down, not up), confirming the issue is the *absence of internal contrast*,
not the normalization statistic chosen. A cross-clip absolute-loudness
floor was also tested and rejected: raw `global_rms` varies by >4× across
the 10 clips purely from each film's own mastering/transfer levels (Reefer
Madness ≈0.14 vs. Detour ≈0.03), independent of acting delivery, so an
absolute dBFS floor would be unreliable across different source recordings.
**This is recorded as a structural limitation** (see below) rather than
patched with an unjustified threshold change.

### 4. Stumble/repetition thresholds — left unchanged

**Evidence considered:** an initial raw-Whisper diagnostic (short,
non-merged segments) suggested word-confidence on old/noisy 1940s audio is
pervasively low (many ordinary words scored 0.06–0.5), which looked like it
would cause runaway stumble false positives. However, re-checking against
the **actual production code path** (merged speaker turns, full sentence
context, `word_timestamps=True`) showed only 6 words total across all 10
clips met the gap-timing precondition (0.35–1.5s gap), and of those only 2
were below the `probability<0.45` cutoff — both defensible (a dramatic
pre-verdict pause in the courtroom clip, and a genuinely garbled word in
His Girl Friday's rapid-fire dialogue). With such a small, plausible sample,
there is no clear evidence the current thresholds are miscalibrated, so
they were left as-is. Flagged as an area to revisit with more fast-dialogue
and more period-audio samples.

## Known limitations (not resolved by this calibration pass)

1. **`raised_voice` requires internal contrast within a single clip.**
   Because `global_rms` is a per-file baseline, a short clip that is
   uniformly loud or uniformly quiet throughout will never show a segment
   crossing the raised/quiet ratio thresholds relative to its own mean, even
   if the absolute delivery is extreme (demonstrated on clip 03's shouting
   argument). This will matter less in production if real recordings are
   longer and contain more dynamic range than these 10–30s test clips, but
   short single-affect clips are a real, and currently unhandled, failure
   mode.
2. **One residual pitch-arc false positive** (clip 07, +49Hz, just above the
   new 40Hz bar) on a calm conversational turn. Not further tuned because
   lowering the bar would reintroduce known false positives on clip 06.
3. **Stumble detection on old/fast/noisy audio is not deeply validated.**
   Only 2 real trigger events were observed in this test set, both
   defensible but not enough to confidently validate or invalidate the
   `probability<0.45` / 0.35–1.5s gap thresholds against genuine disfluency
   vs. Whisper mistranscription of period audio or rapid (His Girl Friday
   -style) delivery.
4. **Small per-category sample sizes.** With only 10 clips and 1–2 samples
   for some categories (resignation, sadness/panic, surprise), the f0_std
   category means reported above (e.g. sadness/panic mean 3.1) are not
   statistically robust and should not be over-interpreted as category
   "signatures" — they are directional evidence, not validated norms.
5. **No positive signature for "surprise."** Clip 08 (D.O.A.'s shock reveal)
   produced no acoustic tags at all after tuning — the detector currently
   has no feature tuned to catch a sudden startle/shock delivery
   specifically; it's tag-negative rather than wrongly tagged.
6. **Segment granularity depends on Whisper's internal turn-merging**, which
   varies with decoding parameters. The f0/RMS statistics validated here
   were computed on the actual merged-turn segments the production pipeline
   uses, but a change to Whisper's VAD/segmentation behavior in a future
   dependency upgrade could shift segment lengths and warrant re-checking
   these thresholds.

## Follow-up investigation (2026-07-30, same day, second pass)

After the initial calibration above, four of the open limitations were
re-investigated with additional real-audio evidence to see whether any
were now addressable. Three more clips were sourced (same archive.org
public-domain-film method) specifically to stress-test the stumble
detector, and a wider-context extraction was pulled around clip 03 to
test a windowed-loudness-baseline idea for `raised_voice`. The standard
from the original pass was kept: no threshold or code change without
direct evidence it helps, and no forced fix if the evidence says otherwise.

**Result: no code changes were made in this follow-up pass.** All four
items were investigated and are either confirmed structural (not
threshold-fixable) or unsupported by the evidence gathered. Details below.

### Extra clips sourced for this pass

| ID | Film | Source | Start | Dur | Purpose | Outcome |
|----|------|--------|-------|-----|---------|---------|
| `11_notld_barbra_breathless` | Night of the Living Dead (1968) | [archive.org/details/night_of_the_living_dead_dvd](https://archive.org/details/night_of_the_living_dead_dvd) | 6:35 | 20s | Genuine panicked/breathless screaming, for stumble/repetition testing | Whisper failed to transcribe the repeated non-lexical "No!" screaming as usable words (mostly treated as noise/silence) — no stumble data obtainable from this clip; itself a documented finding (see below) |
| `12_hgf_rapid_frantic` | His Girl Friday (1940) | [archive.org/details/his_girl_friday](https://archive.org/details/his_girl_friday) | 41:40 | 25s | A second, independent fast-dialogue scene for stumble testing | Only one usable merged turn came out of transcription; no new low-confidence-word stumble triggers observed here |
| `13_reefer_nervous` | Reefer Madness (1936) | [archive.org/details/reefer-madness-1936-inter-pathe-films](https://archive.org/details/reefer-madness-1936-inter-pathe-films) | 25:00 | 25s | Dealer-negotiation dialogue, moderate pace, period audio | Produced one new stumble trigger (`'bad.'`, prob 0.33) plus 2 rising-pitch tags and 1 shaky flag on what is actually calm, businesslike delivery — see stumble section below |

A fourth wider-context clip (`03_wide_context`, 3 minutes of audio
surrounding the original anger scene, same Detour source) was pulled to
test the `raised_voice` windowing idea; it is a superset of an already-
cited timestamp range and is not a new emotion category.

### C.1 revisited — `raised_voice` blind spot: still not fixable, and now better understood

Tested whether a wider loudness-reference window (surrounding audio
rather than just the 25s clip itself) would give clip 03 the internal
contrast it needs. Result: **the film does contain quieter passages
nearby** (a near-silent moment ~20s after the scene, RMS ratio 0.20 vs.
the 3-minute window's own mean) — so in principle more context does add
dynamic range. However, running the actual production pipeline
end-to-end on this longer 3-minute clip showed **zero** `raised_voice`
flags, not more: Whisper's own turn-merging combines the one genuinely
loud utterance ("Where it is, you're drunk" — measured at up to 2.08x a
local per-Whisper-segment baseline) together with quieter neighbouring
words into a single longer speaker turn, and the loud moment gets diluted
by averaging before `analyze_voice_dynamics()` ever sees it. So the
bottleneck is not really the RMS-normalization window at all — it is
**segment/turn granularity**: a real fix would mean analyzing loudness at
a finer, sub-turn (near word-level) granularity, which is a materially
larger design change than a threshold or windowing tweak, and was not
attempted here since it would touch the segmentation contract the rest of
the pipeline (Jefferson markers, deception/clinical markers, transcript
rendering) all depend on. **No code change made.** This is now understood
more precisely than in the original pass (originally attributed purely to
per-file normalization; now also implicates turn-merging granularity) but
remains an open, documented limitation.

### C.2 revisited — no positive "surprise" signature: evidence argues against a simple fix

Tested the hypothesis that a short-window loudness/pitch onset detector
(a sudden jump right after a pause) could catch a surprise/shock reaction,
using the D.O.A. clip's actual reveal line ("I was.", following a 4.6s
pause). The reveal line does show a genuine 13x RMS jump versus the
immediately preceding silence — but two pieces of evidence rule out a
simple onset detector as a viable fix:

1. **The same "quiet-then-loud after a pause" pattern occurs on ordinary,
   non-surprising dialogue** in this test set, at equal or larger
   magnitudes: 7.3x on a calm graveyard conversation, 4.1x on a fear-panic
   line, and 13.6x — larger than the surprise clip itself — on a line from
   the controlled contempt courtroom scene. A pause before someone's next
   line is a universal feature of ordinary turn-taking, not a surprise
   marker.
2. **The reveal line itself is not loud in absolute terms** — only 1.31x
   the clip's own global RMS, i.e. unremarkable relative to the rest of
   the scene's normal dialogue volume. Its "surprise" quality comes from
   dramatic pacing and silence beforehand (a screenwriting/editing choice),
   not a measurable acoustic spike in the line itself.

Given a naive onset detector would fire on ordinary conversational pauses
as readily as on genuine surprise, and the one surprise example available
doesn't even show an absolute loudness anomaly, there is no evidence base
to build this feature on. **No code change made.** This remains an
honest, undetected gap rather than a false-tagging problem — the tool says
nothing about surprise, rather than saying something wrong.

### C.3 revisited — stumble/repetition detector: evidence strengthened, conclusion unchanged

Three additional clips were sourced specifically to stress-test this
detector (table above). Yield was low: clip 11's screamed dialogue wasn't
transcribed into usable words by Whisper at all (a new, separate finding —
see limitations below); clip 12 produced only one long merged turn with no
new low-confidence-word triggers; clip 13 produced exactly one new trigger
(`'bad.'`, probability 0.33, 0.58s gap). Inspecting clip 13's full word-
level confidence trace showed the same pattern as the original pass: **old,
degraded period audio produces pervasively low Whisper word-confidence
(several words scoring 0.06–0.33) independent of any real stumbling** — the
transcribed text itself ("I'm just going to sell a rotten gin right for the
dough") is visibly garbled, consistent with a transcription-quality
artifact rather than the actor stumbling. This is now a 3rd data point
reinforcing the original caution rather than new counter-evidence, and it
still isn't enough (3 real trigger events total, all explainable either
way) to justify moving the `probability<0.45` / 0.35–1.5s gap thresholds
in either direction. **No code change made.**

### C.4 revisited — should `acoustic_tags` corroborate/conflict with deception/clinical markers?

The architecture would support this cleanly: `analyze_voice_dynamics()`
already runs before `build_emotions()` in `run_transcription.py`, and both
are indexed by the same segment number, so cross-referencing would not
require changing either detector's own logic. However, checking actual
co-occurrences across all 13 clips found only ~10 segments total where a
text-based deception/veracity/clinical marker and a non-"normal" acoustic
tag land on the same segment, and **every one of them is either "both
present" or "text marker with an acoustically normal segment" — none show
a genuine conflict** (e.g. text suggesting composure while acoustics show
genuine instability, or vice versa) that a corroboration/conflict feature
could meaningfully flag. Most text-based co-occurrences are benign
veracity patterns (`appropriate_recall_pause`, `contextual_embedding`),
not high-stakes deception markers, further limiting what such a feature
could responsibly claim. Building a "corroborating vs. conflicting
evidence" indicator on this sample would not be backed by an observed
pattern — it would be speculative labelling dressed up as a validated
feature, which is a particular risk for a tool that may be used in
safeguarding-adjacent contexts. **No code change made.** If revisited
later, this would need a substantially larger and more diverse evidence
base, ideally with genuine cases of acoustic/text disagreement, before
being implemented.

### New limitation surfaced by this pass

7. **Screamed/non-lexical panic vocalisations are poorly transcribed by
   Whisper**, which starves every text-dependent detector (stumble,
   repetition, Jefferson markers, deception/clinical markers) of usable
   input for exactly the kind of acute-distress audio a clinical user is
   most likely to care about. `analyze_voice_dynamics()`'s RMS/pitch
   measurements are computed directly from the audio and are unaffected,
   but nothing downstream that depends on Whisper's word output currently
   compensates for this. Observed directly on clip 11 (Barbra's repeated
   screamed "No!" in Night of the Living Dead), where a 20-second scene of
   unambiguous panic produced only one short recognized phrase and an
   "Extended freeze (>10s)" marker, with no acoustic tags either (the
   scene was short and loud throughout, the same per-file-normalization
   issue as item 1 above).

### Reproducibility caveat observed during regression re-testing

While re-running the original 10 clips end-to-end to confirm no regressions
from this pass (none were expected, since no code changed), clip 10
(`10_reefer_sadness_panic`) produced a different Whisper transcription on
each of 3 runs ("Thanks." / "I think...." / "Wrap!" for the same audio
moment) with correspondingly different segment boundaries. This is
Whisper decoding nondeterminism on ambiguous/quiet audio, not a defect in
`analyze_voice_dynamics()` — the underlying acoustic measurement is
deterministic from the waveform and correctly classified the segment as
`raised_voice` in 2 of the 3 runs; the third run's Whisper boundary
happened to isolate a quieter word instead. Noted here as an observed
property of the pipeline as a whole (relevant to reproducibility
expectations), not a new finding about the voice-dynamics code itself.

## Reproducing this calibration

Clip manifest with exact timestamps: `calibration_audio/clip_manifest.json`
(not committed — local/untracked per `.gitignore`, since it references raw
audio paths). All `.wav` files and full local pipeline outputs live under
`calibration_audio/` outside this repo and are excluded from git. The
generated `transcript.md`/`omni.md`/`analysis.json` for every clip **are**
committed, at [`docs/calibration_outputs/round1/`](calibration_outputs/round1/README.md).

## See also

- [`docs/calibration_outputs/round1/`](calibration_outputs/round1/README.md) — real committed tool output for every clip in this document.
- [`docs/CALIBRATION_ROUND2.md`](CALIBRATION_ROUND2.md) — round 2 calibration against longer, real-world clips with independently-documented ground truth (public inquiries, fact-checked hearings, court rulings), rather than acted-film performances.
