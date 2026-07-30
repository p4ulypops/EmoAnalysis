# Round 2 Calibration — Real-World Testimony Against Documented Ground Truth (2026-07-30)

Round 1 ([`CALIBRATION.md`](CALIBRATION.md)) validated `analyze_voice_dynamics()`
against short (10–30s) **acted** film clips, where the "ground truth" was the
performed emotion. That answers "does the detector see what a human viewer
sees in a performance?" but not "does the detector's deception/veracity
framing line up with **documented, independently-published, real-world
findings** about a real witness's testimony?"

Round 2 answers the second question: 6 real recordings (up to ~30 minutes
each) of actual testimony/argument, each cross-checked against a published,
citable, independent finding — a public inquiry report, a court ruling, or a
fact-checker's verdict — rather than the analyst's own impression.

**Real tool output evidence:** as with round 1, the actual generated
`transcript.md` / `omni.md` / `analysis.json` for every clip below is
committed at
[`docs/calibration_outputs/round2/`](calibration_outputs/round2/README.md).
Open that directory to check any line of this document against real output.

## Why 6 clips, not 10

The brief asked for up to 10 clips and explicitly permitted reporting fewer
"rather than force weak/risky ones in." Six clips clear the bar; the
following leads did not and were dropped rather than stretched:

- **YouTube-hosted testimony/hearings could not be downloaded at all.**
  `yt-dlp` in this sandbox is blocked by YouTube's bot detection (HTTP 429 →
  "Sign in to confirm you're not a bot," even with alternate player-client
  extractor args). This eliminated every candidate that only existed as a
  YouTube livestream, which was most of the original tier-1/tier-2
  shortlist. Work pivoted to archive.org (which mirrors many UK inquiry
  hearings and some YouTube content) and to courts' own direct audio
  hosting.
- **Manchester Arena Inquiry (Witness "J"/MI5, DCC Ian Pilling) — dropped.**
  Only procedural/preliminary hearings for this inquiry are indexed on
  archive.org; the actual evidence sessions are not mirrored there and were
  not otherwise obtainable in this sandbox. Rather than substitute a
  different, less-relevant session under the same names, this candidate was
  dropped entirely.
- **Cassidy Hutchinson (Jan 6 committee) — deliberately excluded.** Her
  account is politically contested (disputed by a subsequent GOP-led
  investigation), so it does not clear the brief's bar of an "objective,
  independently-published" ground truth that is uncontested fact rather than
  a live partisan dispute.
- **Claude Wehrle (Arconic) — excluded.** He never gave oral testimony to
  the Grenfell Inquiry (declined to appear, citing French law), so no audio
  exists to source.
- **Infected Blood Inquiry** and a few other candidates were considered but
  not pursued to a specific, sourced witness/claim pairing given time
  constraints.
- **Tier 4 (911 calls / bodycam) was not searched at all.** This is a
  deliberate choice, not an oversight: the brief lists tier 4 as lowest
  preference specifically because of its higher privacy/ethics risk
  (minors, sexual violence, ongoing cases, non-public-figure victims), and
  tiers 1–3 already produced 6 clips that clear the bar cleanly. Per the
  brief's own instruction to "skip tier entirely if bar not cleared rather
  than lowering it," tier 4 was skipped by not opening it at all.

## Method

Each clip was downloaded from a public, named source, trimmed to ≤30 minutes
with `ffmpeg`, and run through the unmodified pipeline:

```
python3 src/run_transcription.py <clip> --model base --no-viewer --no-copy-audio --output-dir calibration_audio_r2/out
```

Two of the six source recordings (Grenfell Inquiry archive.org videos) had
long stretches of pre-hearing dead air before the actual testimony began;
the intended "first 30 minutes" window was verified against a volume probe
first and the extraction start point adjusted so the 30-minute clip actually
contains speech, not silence. This is noted per-clip below.

Raw audio (`.wav`/`.mp3`) is **not** committed — it stays untracked in
`/home/user/workspace/calibration_audio_r2/` per `.gitignore`, matching the
round-1 policy. Only the tool's generated text/JSON outputs are committed.

## The 6 clips

### 1. Gareth Jenkins (Fujitsu) — Post Office Horizon IT Inquiry, Day 156 PM, 25 June 2024

- **Source:** [archive.org — POHII-336-20240625](https://archive.org/download/POHII-336-20240625/POHII-336-20240625%20-%20Gareth%20Jenkins%20-%20Day%20156%20PM%20%2825%20June%202024%29%20-%20Post%20Office%20Horizon%20IT%20Inquiry.mkv) — official inquiry hearing recording, tier 1.
- **Ground truth:** Post Office's own confidential 2013 legal advice from barrister Simon Clarke, disclosed to the Inquiry as exhibit **POL00043284**, states: *"His credibility as an expert witness was fatally undermined; he should not be asked to provide expert evidence in any current or future prosecution"* because *"Dr. Jenkins failed to disclose material known to him but which undermined his expert opinion"* — [POL00043284, Post Office Horizon IT Inquiry](https://www.postofficehorizoninquiry.org.uk/sites/default/files/2024-06/pol00043284_4_0_0.pdf) (fetched and quote re-verified this session, section 3.1–3.2.2). Corroborated by [BBC News coverage of Clarke's own evidence session](https://www.bbc.com/news/articles/c4n1yxd9znxo) and *Bates & Others v Post Office Ltd* [2019] EWHC 3408 (QB), which found the Horizon system had bugs, errors and defects.
- **Segment checked:** 00:00–29:57 of the 25 June 2024 PM session, in which Jenkins is questioned about his understanding of an expert witness's disclosure duties and the SEMA-Misra case.
- **Tool output:** 251 segments; 32 deception markers, 214 veracity markers, 44 clinical markers, 5 freeze events ([full output](calibration_outputs/round2/gareth_jenkins_30min/)).
- **Agreement:** repeated `⚠️ DECEPTION: Memory disclaimer — claiming inability to recall <lack-mem>` and `Qualified memory — weakening commitment to statement <lack-mem>` tags cluster precisely around Jenkins's answers about whether he was aware of / attended to his duties as an expert witness ("I can't remember," "I probably..."). This is the same behaviour — evasive, qualified memory about a duty he is later found to have breached — that the Post Office's own lawyer characterised as "fatally undermined" credibility. **Agree** (tool's tags land on the same substantive exchanges the documented finding is about, though the tool cannot and does not itself label anything "fatally undermined" — it flags the linguistic behaviour consistent with that finding).

### 2. Jonathan Roome (Celotex) — Grenfell Tower Inquiry, 11 November 2020 (AM)

- **Substitution note:** the original target was Jonathan Roper's 17 November 2020 session; that specific date could not be located on archive.org under any searchable identifier. Roome's 11 November session covers the same "Celotex marketing" evidence module and the same Phase 2 Report finding applies to both witnesses, so this is a like-for-like substitution, not a different topic.
- **Source:** [archive.org — Of6VkWX53zc](https://archive.org/download/Of6VkWX53zc/Of6VkWX53zc.mp4) — Grenfell Tower Inquiry hearing recording, tier 1.
- **Ground truth:** the Grenfell Tower Inquiry's Phase 2 Report (4 September 2024) found that Jonathan Roome had taken misleading marketing wording from Celotex's own marketing department, that the RS5000 datasheet "made no reference to its being suitable for use as part of a cladding system," and that Celotex ran "a dishonest scheme to mislead its customers and the wider market" — [Grenfell Tower Inquiry Phase 2 Report, Vol. 4](https://assets.publishing.service.gov.uk/media/66d817d9c52d5fb4c82dddf0/CCS0923434692-004_GTI_Phase_2_Volume_4_BOOKMARKED.pdf) (re-fetched and quote-checked this session). Corroborated by [BBC News: "Firm made 'false claims' over Grenfell cladding"](https://www.bbc.com/news/articles/cx2ld1eew8mo) and [BBC News: Jonathan Roper's own admission of "dishonest" conduct](https://www.bbc.co.uk/news/uk-54967895) in a related session.
- **Segment checked:** ~15:37–18:21 of the extracted window (dead-air-adjusted; see below), in which counsel puts to Roome that better-performing insulation is "the better for marketing purposes" and walks him through a Celotex marketing document he cannot fully explain the authorship of.
- **Extraction note:** the first 1,180 seconds of the raw file are pre-hearing dead air (silence check via RMS sampling); the 30-minute window was re-extracted starting at offset 1180s so it contains the actual hearing.
- **Tool output:** 261 segments; 25 deception markers, 137 veracity markers, 46 clinical markers, 1 freeze event ([full output](calibration_outputs/round2/celotex_roome_30min/)).
- **Agreement:** the tool tags `⚠️ DECEPTION: Word corrected via dash <corrsp>` and a 2.6s `🏥 CLINICAL: Non-grammatical pause` right at "Are you able to tell us who within Celotex compiled this document? — I, from experience, it would have been the product, between the product management and marketing department..." — a hedged, unable-to-fully-account-for-authorship answer about the exact marketing document the Inquiry's report later found to contain misleading claims. **Agree** (tags cluster on the marketing-authorship exchange the ground-truth finding is specifically about).

### 3. John Hoban (RBKC Building Control) — Grenfell Tower Inquiry, 30 September 2020 (AM)

- **Source:** [archive.org — RBKC_Building_Control_Evidence_Wednesday_30th_September_2020_1_2](https://archive.org/download/RBKC_Building_Control_Evidence_Wednesday_30th_September_2020_1_2/RBKC_Building_Control_Evidence_-_Wednesday_30th_September_2020_1_2-gBLQRhK-QGE.mp4) — Grenfell Tower Inquiry hearing recording, tier 1.
- **Ground truth:** an independent expert report by Beryl Menzies, cited in the Inquiry, found RBKC building control's checks contained "fundamental failings," specifically that "failure to ask for detailed information about the cladding system was a fundamental failing," and separately that Hoban told the inquiry he was "swamped" reviewing ~130 projects at once — [Inside Housing, 27 Oct 2020](https://www.insidehousing.co.uk/news/rbkc-building-control-checks-contained-fundamental-failings-says-expert-grenfell-witness-68341) (fetched and quote-checked earlier this session — confirmed accurate).
- **Segment checked:** **honesty caveat — this is a limitation, not a match.** The 30-minute window actually extracted (00:06–~30:00 of usable audio) covers the very start of Hoban's evidence: being sworn in, confirming his written witness statement, and early questions about corrections to that statement and his professional development/performance review history. It does **not** reach the later "swamped with work" / "fundamental failings" exchange that Inside Housing quotes — that discussion happens later in the hearing than this window extends. This was checked directly: a text search of the full transcript for "swamp," "struggl," "fundamental," "failing," "cladding system," and "130 project" returns zero matches in this window.
- **Extraction note:** the first ~2,380 seconds (~40 minutes) of the raw file are pre-hearing dead air; had to probe and re-extract starting at that offset to reach any speech at all, and even then landed on the swearing-in/procedural portion rather than the substantive exchange the ground truth quotes.
- **Tool output:** 228 segments; 26 deception markers, 143 veracity markers, 34 clinical markers, 2 freeze events ([full output](calibration_outputs/round2/hoban_rbkc_30min/)).
- **Agreement: SILENT / not applicable to this specific finding.** The tool's output for this window cannot be scored against the "fundamental failings" ground truth because the window doesn't contain that exchange. What the window does contain is honestly reported: the sworn statement, corrections to a prior draft, and a `⚠️ DECEPTION: Emphasis on honesty — possible overcompensation <defensive>` tag on the oath itself ("I swear by Almighty God...") — expected, low-value boilerplate, not evidence either way. This clip is retained in the round-2 set for transparency about what a 30-minute excerpt of a multi-hour hearing can and cannot capture, and is counted as a **silent/inapplicable** row in the agreement table below rather than forced into agree or disagree.

### 4. Students for Fair Admissions v. Harvard — SCOTUS oral argument, 31 October 2022 (No. 20-1199)

- **Source:** [Supreme Court of the United States, official audio](https://www.supremecourt.gov/oral_arguments/audio/2022/20-1199), direct file `http://www.supremecourt.gov/media/audio/mp3files/20-1199.mp3` — tier 3 (public court oral argument).
- **Ground truth:** the Supreme Court ruled 6–3 on 29 June 2023 that Harvard's and UNC's race-conscious admissions programs violated the Equal Protection Clause — [opinion, 20-1199 (supremecourt.gov)](https://www.supremecourt.gov/opinions/22pdf/20-1199_hgdj.pdf).
- **Segment checked:** 00:00–~11:00 of the argument, petitioner's counsel arguing that Harvard's use of race fails each of *Grutter*'s core assumptions (race as a "plus" only, individualized treatment, workable end point).
- **Tool output:** 194 segments; 85 deception markers, 113 veracity markers, 37 clinical markers, 0 freeze events ([full output](calibration_outputs/round2/sffa_harvard_30min/)).
- **Agreement:** this is prepared appellate advocacy, not spontaneous witness recall, so the tool's `⚠️ DECEPTION: Complex sentence — high cognitive load for spontaneous speech <cog-load>` tags fire frequently and predictably on long, rehearsed, multi-clause sentences ("Grutter assumed that race would only be a plus... But race is a minus for Asians...", 84 words). This is a **known false-positive mode, not a hit** — the ground truth here is about the case's ultimate legal outcome, not about whether counsel was being deceptive, and the tool has no basis to distinguish prepared advocacy from genuine spontaneous evasiveness. **Disagree / not a meaningful signal** — flagged honestly rather than claimed as a match; this data point argues for treating `<cog-load>` deception tags as much weaker evidence in prepared-speech contexts (oral argument, opening statements) than in cross-examination-style Q&A.

### 5. Learning Resources, Inc. v. Trump — SCOTUS oral argument, 5 November 2025 (No. 24-1287, tariffs case)

- **Source:** [Supreme Court of the United States, official audio](https://www.supremecourt.gov/oral_arguments/audio/2025/24-1287), direct file `http://www.supremecourt.gov/media/audio/mp3files/24-1287.mp3` — tier 3.
- **Ground truth:** the Supreme Court ruled 6–3 on **20 February 2026** (opinion by Chief Justice Roberts) that the International Emergency Economic Powers Act (IEEPA) does **not** authorize the President to impose tariffs, striking down the tariffs at issue — [opinion, 24-1287 (supremecourt.gov)](https://www.supremecourt.gov/opinions/25pdf/24-1287_4gcj.pdf); confirmed independently via [SCOTUSblog's case page](https://www.scotusblog.com/cases/learning-resources-inc-v-trump/) and [SCOTUSblog's breakdown of the decision](https://www.scotusblog.com/2026/02/a-breakdown-of-the-courts-tariff-decision/). (At the time this clip was sourced, the ruling had not yet issued; it was decided during the course of this task, so this citation was fetched fresh and verified before being written up here.)
- **Segment checked:** 00:00–~10:00 of the argument, the Solicitor General arguing that IEEPA's grant of authority to "regulate... importation" extends to tariffs, and that the major-questions doctrine is a poor fit here because tariffs are a traditional executive tool.
- **Tool output:** 380 segments; 42 deception markers, 93 veracity markers, 40 clinical markers, 0 freeze events ([full output](calibration_outputs/round2/tariffs_case_30min/)).
- **Agreement:** as with clip 4, this is prepared appellate advocacy. The ground truth (the eventual ruling against the government's position) is not something the deception/veracity tags can or should predict — a losing legal argument is not the same thing as a deceptive one, and the tool does not claim otherwise. **Disagree / not a meaningful signal**, for the same structural reason as clip 4: oral argument is the wrong genre to validate a deception detector against a "did they win or lose" ground truth. Retained and reported honestly rather than dropped, because it reinforces the same limitation found independently in clip 4.

### 6. Jason Chaffetz questioning Cecile Richards — House Oversight Committee, Planned Parenthood hearing, 29 September 2015

- **Source:** [archive.org YouTube mirror — youtube--mPtfaJv2H8](https://archive.org/download/youtube--mPtfaJv2H8/-mPtfaJv2H8.mp4) — tier 2 (congressional hearing, cross-checked against an independent fact-checker). Note: the original plan was the full C-SPAN3 broadcast recording (archive.org identifier `CSPAN3_20150929_170000_Politics_and_Public_Policy_Today`), but that item returned HTTP 403 ("Item not available due to issues with the item's content" — a rights/DMCA restriction), so this shorter YouTube-mirrored excerpt was used instead.
- **Length caveat:** this clip is **7.6 minutes** (458.6s), not close to the ~30-minute target. This is disclosed rather than padded — it was the only available un-restricted excerpt of this specific exchange, and the brief permits "up to" 30 minutes, not a minimum.
- **Ground truth:** PolitiFact rated Chaffetz's chart claiming Planned Parenthood's abortions had risen while its breast exams fell "Pants on Fire" — the chart's actual source was Americans United for Life, an anti-abortion advocacy group, not Planned Parenthood's own data — [House Oversight Democrats press release citing the PolitiFact rating](https://oversightdemocrats.house.gov/news/press-releases/politifact-awards-chaffetz-a-rating-of-pants-on-fire-for-using-misleading-chart); official transcript: [Congress.gov, CHRG-114hhrg26029](https://www.congress.gov/114/chrg/CHRG-114hhrg26029/CHRG-114hhrg26029.pdf).
- **Segment checked:** 06:41–07:34 of the clip — the exact chart exchange: Richards says "This is a slide that has never been shown to me before... it absolutely does not reflect what's happening at Planned Parenthood," then identifies the chart's actual source: "He's my lawyer's affirming me that the source of this is actually Americans United for Life, which is an anti-abortion group, so I would check your source."
- **Tool output:** 76 segments; 6 deception markers, 38 veracity markers, 3 clinical markers, 0 freeze events ([full output](calibration_outputs/round2/chaffetz_richards/)).
- **Agreement:** the tool places a `⚠️ DECEPTION: Word corrected via dash <corrsp>` tag directly on Richards's sentence identifying the chart's true source as an anti-abortion group — i.e., the detector flags linguistic "correction" behaviour on the very line that, per the independently-published fact-check, was Richards accurately correcting the record about a misleading chart Chaffetz had presented. This is a case where the deception tag fires on the person telling the documented truth, not the person using the misleading chart (the tool has no segment-level output for Chaffetz's own presentation of the chart itself in this excerpt, since he is largely asking short questions rather than making extended claims in this window). **Disagree** — a clear, worth-reporting mismatch: a "deception" tag lands on the corroborated-true statement, not on the documented-false one, in the one exchange this clip was specifically sourced to test.

## Agreement table

| Clip | Segment / claim | Documented ground truth | Tool's tag(s) at that point | Agree / Disagree / Silent |
|---|---|---|---|---|
| Gareth Jenkins | Awareness of expert-witness disclosure duties, SEMA-Misra case | Post Office's own legal advice: credibility "fatally undermined," failed to disclose material undermining his opinion ([POL00043284](https://www.postofficehorizoninquiry.org.uk/sites/default/files/2024-06/pol00043284_4_0_0.pdf)) | `⚠️ DECEPTION: Memory disclaimer <lack-mem>`, `Qualified memory <lack-mem>` clustered on the same exchanges | **Agree** |
| Jonathan Roome (Celotex) | Authorship/accuracy of RS5000 marketing document | Phase 2 Report: Celotex ran "a dishonest scheme to mislead," datasheet omitted key suitability info ([Phase 2 Report Vol. 4](https://assets.publishing.service.gov.uk/media/66d817d9c52d5fb4c82dddf0/CCS0923434692-004_GTI_Phase_2_Volume_4_BOOKMARKED.pdf)) | `⚠️ DECEPTION: Word corrected via dash <corrsp>`, extended non-grammatical pause, right on the "who compiled this document" exchange | **Agree** |
| John Hoban (RBKC) | Adequacy of building-control checks on cladding | Expert report: checks contained "fundamental failings" ([Inside Housing](https://www.insidehousing.co.uk/news/rbkc-building-control-checks-contained-fundamental-failings-says-expert-grenfell-witness-68341)) | N/A — extracted window ends before this exchange occurs in the hearing | **Silent** (window doesn't reach the relevant testimony) |
| SFFA v. Harvard | Petitioner's opening argument against race-conscious admissions | SCOTUS ruled 6–3 admissions programs unconstitutional ([opinion](https://www.supremecourt.gov/opinions/22pdf/20-1199_hgdj.pdf)) | `⚠️ DECEPTION: Complex sentence — high cognitive load <cog-load>` fires repeatedly on prepared advocacy | **Disagree** (tag reflects sentence complexity of rehearsed argument, not deception; wrong genre for this detector) |
| Learning Resources v. Trump | SG's argument that IEEPA authorizes tariffs | SCOTUS ruled 6–3 against the government, Feb 2026 ([opinion](https://www.supremecourt.gov/opinions/25pdf/24-1287_4gcj.pdf)) | Same `<cog-load>` pattern on prepared advocacy | **Disagree** (same structural mismatch as above) |
| Chaffetz / Richards | Richards identifying the chart's true (anti-abortion-group) source | PolitiFact: "Pants on Fire" for the misleading chart ([press release](https://oversightdemocrats.house.gov/news/press-releases/politifact-awards-chaffetz-a-rating-of-pants-on-fire-for-using-misleading-chart)) | `⚠️ DECEPTION: Word corrected via dash <corrsp>` lands on Richards's truthful correction, not on Chaffetz's misleading chart | **Disagree** (tag on the wrong speaker/statement relative to the documented finding) |

**Headline numbers: 2 of 6 clips agree, 3 of 6 disagree, 1 of 6 silent (window didn't reach the relevant testimony).**

This is a materially different — and more sobering — result than round 1's
acted-clip calibration, which was primarily about whether measured acoustic
features (pitch, volume, shakiness) matched a performed emotion. Round 2
tests something harder: whether the deception/veracity *language* tags line
up with independently documented real-world credibility findings. The
pattern in the disagreements is systematic, not random:

- **Prepared advocacy (oral argument) is the wrong genre for this detector.**
  Both SCOTUS clips show `<cog-load>` deception tags firing on long,
  fluent, rehearsed sentences — exactly what skilled appellate advocacy
  sounds like, and exactly what the "complex sentence, high cognitive load
  for *spontaneous* speech" heuristic is not designed to distinguish from
  genuine evasiveness. The heuristic's own label ("for spontaneous speech")
  already flags this as a scope limitation; round 2 is the first real
  evidence that the mismatch actually occurs in practice, not just in
  theory.
- **The tool's deception tags are speaker-agnostic to context.** In the
  Chaffetz/Richards clip, the one deception tag in the relevant exchange
  lands on the truthful correction, not the misleading original claim —
  because "word corrected via dash" is a surface linguistic pattern
  (self-correction), not a claim about which party is being accurate. This
  is a useful, concrete illustration of why these tags should be read as
  "possible signal of X linguistic behaviour," never as an accuracy or
  honesty verdict, which is consistent with round 1's existing caveats but
  now has a specific real-world counter-example attached.

## Threshold changes

**None, because the round-2 evidence argues for changing interpretation
guidance, not the underlying acoustic/linguistic thresholds.** The
disagreements found here are not calibration errors in the sense of "the
pitch/volume/pause thresholds are numerically wrong" (round 1's subject) —
they are genre-mismatch and speaker-attribution issues in how the
*deception* heuristics should be read, which is a documentation/interpretation
fix, not a threshold-tuning fix. Retuning `<cog-load>` sentence-length
thresholds specifically to suppress hits on SCOTUS advocates would be
overfitting to two clips of one genre, not a generalizable improvement — the
correct fix, if any is warranted in a future pass, is to add explicit
genre-awareness (prepared statement vs. spontaneous Q&A) as a modifier
before the deception heuristics fire, which is a larger design change than
this calibration pass is scoped to make.

## Limitations of this round

- 6 clips, not 10 — see "why 6, not 10" above.
- One clip (Chaffetz/Richards) is 7.6 minutes, well under the ~30-minute
  target, for source-availability reasons documented above.
- One clip (Hoban/RBKC) does not reach the specific documented finding
  within its 30-minute window — an honest "silent" result rather than a
  forced match.
- Two clips (both SCOTUS oral arguments) demonstrate a genre mismatch
  between prepared legal advocacy and a detector tuned partly against
  spontaneous-speech assumptions; this is reported as a disagreement/
  limitation rather than suppressed.
- As in round 1, all ground-truth citations were independently re-fetched
  and quote-checked during this pass (per the `fable-judge` skill's
  standing instruction not to trust a citation without re-opening it) —
  every citation linked above was verified to actually contain the quoted
  language at the time of writing.

## Reproducing this

```
python3 src/run_transcription.py <clip> --model base --no-viewer --no-copy-audio \
  --output-dir calibration_audio_r2/out
```

Raw source audio is not committed (see `.gitignore`); the six source URLs
above are sufficient to re-download and re-derive every output file in
[`docs/calibration_outputs/round2/`](calibration_outputs/round2/README.md).
