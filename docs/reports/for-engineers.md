# Voice-Dynamics Calibration — Engineering Report

Audience: developers maintaining `analyze_voice_dynamics()` in
`src/run_transcription.py`. This is a condensed, code-focused distillation
of `docs/CALIBRATION.md` — read that document for the full clip manifest,
per-clip tag tables, and archive.org source citations. Nothing here
contradicts it; this is the same evidence, organized for someone about to
touch the code. The real generated `transcript.md`/`omni.md`/`analysis.json`
for every clip are committed at
[`docs/calibration_outputs/round1/`](../calibration_outputs/round1/README.md)
— open that directory to check any tag claim below against actual tool
output.

## TL;DR

The `analyze_voice_dynamics()` thresholds had only been smoke-tested
against flat TTS. We validated against 10 real acted-emotion clips from
public-domain films (archive.org) and found the RMS coefficient-of-variation
(CV) shaky-voice branch was statistically indistinguishable from noise. We
removed it as a standalone trigger, tightened the pitch-trend threshold, and
left the RMS-ratio (raised/quiet) and stumble/repetition logic unchanged
after investigating them and finding the issues were structural, not
threshold bugs. Full diffs are in commit `ae4f0f8`.

## Method

- 10 clips, 10–30s, extracted via `ffmpeg` HTTP range requests directly
  against archive.org CDN URLs (no full-film downloads).
- Ran through the actual production entrypoint:
  `python3 src/run_transcription.py <clip>.wav --model base --no-viewer --no-copy-audio --output-dir calibration_audio/out`
- Compared emitted `🎙️ ACOUSTIC:` tags against manual ground-truth judgment
  of the real delivery, segment by segment (segments = Whisper's merged
  speaker turns as the pipeline actually produces them, not raw
  single-sentence Whisper output — this distinction mattered, see below).
- Categories: anger/shouting, fear→panic, sadness/panic, joy, contempt,
  resignation/flat affect, deceptive/controlled, surprise/shock, calm ×2
  (controls).

## Finding 1 — `rms_cv > 0.8` shaky-voice branch was pure noise

Sampled `rms_cv` (std/mean of frame-level RMS, `frame_length=512,
hop_length=256`) across 86 real segments from all 10 clips:

- Mean 0.75, median 0.69, range 0.14–2.12.
- At segment durations ≥1.5s, per-category means were flat: calm 0.78,
  anger 0.77, contempt 0.78, joy 0.73, fear 0.79 — **no separation**.
- It fired on flatly delivered lines ("San Francisco last night", cv=2.12)
  as often as on any emotional line, and never failed to fire on a
  representative fraction of *every* category.
- It was the sole cause of every false-positive `shaky` tag in the
  before-tuning run (clips 01, 02×2, 07×2, 08×3, 10 — 9 total).

`f0_std` (pyin pitch stdev), by contrast, showed real separation: calm
median ≈10.2, joy ≈9.6, anger ≈29.1, fear ≈35.7, contempt ≈59.2. Every
f0-driven shaky flag observed was on a segment with ≥50 voiced pitch
frames — statistically well-supported, unlike the CV branch which fires
regardless of frame count.

**Fix** (`analyze_voice_dynamics()`, shaky-voice block):

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

- Added `len(f0_clean) >= 6` voiced-frame floor to the f0 condition (was
  previously ungated; the pitch-trend code already had this floor, this
  just brings the shaky-voice branch in line).
- CV is demoted from standalone trigger to corroborating signal: needs
  `rms_cv > 1.4` (up from 0.8) **and** a relaxed but still-present f0
  condition (`f0_std > 45`, down from 60) **and** `seg_dur_s >= 1.5`, so a
  short/noisy frame-RMS estimate can't fire alone.

## Finding 2 — pitch-trend arcs fired on ordinary multi-sentence turns

`analyze_voice_dynamics(segments, audio_path)` receives Whisper's merged
speaker turns, which are frequently several sentences long — not single
utterances. Comparing mean f0 of the first third vs. last third of voiced
frames at the old 25Hz bar crossed by coincidence on ordinary sentence-final
falls/question-like rises stacked across a multi-sentence turn: +49Hz false
positive ("alarm/excitement") on a calm His Girl Friday conversation (clip
07), plus 3 spurious arcs on the fast-banter clip (06).

**Fix:** raised `pitch_delta_hz` threshold from `25` to `40` for both rising
and falling. This retains every genuine arc seen (Detour −153Hz/−76Hz
falling under real anger, Reefer +54Hz/+74Hz rising under contempt) while
dropping clip 06's 3 false positives. **Not fully resolved:** clip 07 seg0
still measures +49Hz, above even the new 40Hz bar — left as an open,
documented limitation because lowering the bar further reintroduces clip
06's false positives. This is a real precision/recall trade-off, not an
oversight.

## Finding 3 — RMS-ratio raised/quiet/whisper (1.8/0.8/0.3/0.1) — investigated, left unchanged

Clip 03 (Detour's shouted strangulation scene) never crossed `rms_ratio >
1.8` despite being the loudest, most aggressive delivery in the test set.
Root cause: `global_rms` is a per-file mean computed once; this clip is
uniformly loud throughout (segment ratios cluster 0.58–1.91 around its own
elevated mean), so there's no quiet baseline *within the clip* to contrast
against. Two fixes were tested and rejected with evidence:

1. **Renormalize against median segment RMS instead of whole-clip mean** —
   tested on clip 03; made ratios lower, not higher (0.64–1.61 vs.
   0.75–1.91), the opposite of what's needed. Rejected.
2. **Cross-clip absolute-loudness (dBFS) floor** — `global_rms` varies >4×
   across the 10 clips purely from each film's own mastering/transfer level
   (Reefer Madness ≈0.14 vs. Detour ≈0.03), independent of acting delivery.
   An absolute floor calibrated on one film's mastering would misfire on
   another's. Rejected as unreliable across heterogeneous source recordings.

This is recorded as a structural limitation of per-file self-normalization
on short, single-affect clips, not a threshold bug. See Part C follow-up
below for the current status (still unresolved — a proper fix needs either
much longer/more varied source audio per file, or a fundamentally different
loudness-referencing approach; neither was validated with evidence in this
round, see the "Part C" addendum in CALIBRATION.md).

## Finding 4 — stumble/repetition thresholds — investigated, left unchanged

An initial diagnostic using raw (non-merged) Whisper segments suggested
pervasive low word-confidence on old 1940s audio (many ordinary words
scoring 0.06–0.5), which looked like a false-positive risk for the
`probability<0.45` stumble condition. Re-checking against the **actual
production code path** (merged turns, full sentence context,
`word_timestamps=True`) told a different story: only 6 words across all 10
clips even met the gap-timing precondition (0.35–1.5s inter-word gap), and
only 2 of those were below the 0.45 probability cutoff — both defensible
(a dramatic pre-verdict pause in the courtroom clip; a genuinely garbled
word in His Girl Friday's rapid dialogue). Sample too small to justify a
threshold change either way. Left unchanged; flagged for more evidence
(addressed in Part C below).

## Regression testing

After edits: `python3 -m py_compile src/run_transcription.py` passes (one
pre-existing, unrelated `SyntaxWarning` on an embedded JS regex at line
~2771, not touched by this work). All 10 clips were re-run end-to-end
through the production CLI after the threshold changes; diffed against the
before-tuning snapshot to confirm: 9 shaky false positives and 4 spurious
pitch-arc tags gone, all previously-correct positive tags (clip 03's
shaky+falling-pitch, clip 09's shaky+rising-pitch, clip 10's raised_voice,
clip 05's quiet+freeze) unchanged.

## Known code-level limitations (unchanged from CALIBRATION.md unless noted)

- `raised_voice`/`quiet`/`whisper` levels are per-file-relative and blind to
  uniformly-loud or uniformly-quiet short clips (clip 03 false negative).
- One residual pitch-arc false positive (clip 07, +49Hz vs. 40Hz bar).
- Stumble detection evidence base is thin (originally 2 real trigger
  events); see Part C addendum for whether this was strengthened.
- Category f0_std means reported here are directional (n=1–3 per category
  in several cases), not statistically validated norms.
- No positive acoustic signature exists for "surprise" as of the original
  pass; see Part C addendum for whether an onset-based detector was added.
- Segment granularity is coupled to Whisper's internal VAD/turn-merging
  behavior; a future Whisper/dependency upgrade could shift this and
  warrant re-validation.

See `docs/CALIBRATION.md` for the full before/after tag table with every
segment, and its "Known limitations" section (as amended, if applicable)
for the latest status of each item above.

## Round 2 addendum: real-world testimony vs. documented ground truth

A second calibration pass ([`docs/CALIBRATION_ROUND2.md`](../CALIBRATION_ROUND2.md))
tested 6 real recordings (public inquiry/court/hearing audio, up to ~30 min
each) against independently-published, documented findings, rather than
acted-clip impressions. Result for engineers: **2 of 6 agree, 3 of 6
disagree, 1 of 6 silent** — see the full agreement table and per-clip
reasoning in that document. The two systematic disagreement patterns worth
knowing before touching this code:

- **`<cog-load>` ("complex sentence... high cognitive load for spontaneous
  speech") fires heavily on prepared appellate advocacy** (both SCOTUS
  oral-argument clips), which is fluent and rehearsed, not spontaneous. The
  heuristic's own docstring already scopes it to spontaneous speech; round
  2 is the first concrete evidence the mismatch actually fires in a
  real, non-toy input. If this code is touched, consider gating
  `<cog-load>` behind a genre/context flag (prepared statement vs.
  cross-examination) rather than changing its sentence-length thresholds,
  which would just overfit to two argument transcripts.
- **Deception tags are speaker- and truth-blind by design** (surface
  linguistic pattern only) — round 2 produced a concrete case
  (`chaffetz_richards`) where the one `<corrsp>` tag in the relevant
  exchange lands on the speaker later shown by an independent fact-check to
  be telling the truth, not on the speaker making the debunked claim. No
  code change is proposed for this — it's a correct illustration of an
  existing, already-documented caveat — but it's worth keeping as a
  concrete regression/example case if this heuristic is ever reworked.

No threshold or code changes were made as a result of round 2; see that
document's "Threshold changes" section for why (documentation/interpretation
issue, not a numeric-threshold issue).
