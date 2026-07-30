# Round 2 Calibration Outputs — Real Output, Not Summaries

These are the actual generated files from running
`src/run_transcription.py --model base` on 6 real-world testimony/argument
recordings. See [`docs/CALIBRATION_ROUND2.md`](../../CALIBRATION_ROUND2.md)
for the full write-up, source citations, ground-truth citations, and the
agreement table these files support.

Raw source audio is **not** committed (see repo `.gitignore`); only the
tool's derived text/JSON output is here.

| Folder | Source | What it is |
|---|---|---|
| [`gareth_jenkins_30min/`](gareth_jenkins_30min/) | [Post Office Horizon IT Inquiry, Day 156 PM, 25 June 2024](https://archive.org/details/POHII-336-20240625) | Fujitsu engineer Gareth Jenkins testifying about the SEMA-Misra case and his duties as an expert witness |
| [`celotex_roome_30min/`](celotex_roome_30min/) | [Grenfell Tower Inquiry, 11 November 2020](https://archive.org/details/Of6VkWX53zc) | Jonathan Roome (Celotex) questioned on RS5000 marketing material |
| [`hoban_rbkc_30min/`](hoban_rbkc_30min/) | [Grenfell Tower Inquiry, RBKC Building Control, 30 September 2020](https://archive.org/details/RBKC_Building_Control_Evidence_Wednesday_30th_September_2020_1_2) | John Hoban (RBKC) sworn in, early procedural testimony (see limitations note in CALIBRATION_ROUND2.md — window doesn't reach the later "fundamental failings" exchange) |
| [`sffa_harvard_30min/`](sffa_harvard_30min/) | [SCOTUS oral argument, SFFA v. Harvard, 31 Oct 2022](https://www.supremecourt.gov/oral_arguments/audio/2022/20-1199) | Petitioner's opening argument against race-conscious admissions |
| [`tariffs_case_30min/`](tariffs_case_30min/) | [SCOTUS oral argument, Learning Resources v. Trump, 5 Nov 2025](https://www.supremecourt.gov/oral_arguments/audio/2025/24-1287) | Solicitor General's argument for IEEPA tariff authority |
| [`chaffetz_richards/`](chaffetz_richards/) | [House Oversight Committee, Planned Parenthood hearing, 29 Sept 2015](https://archive.org/details/youtube--mPtfaJv2H8) | Jason Chaffetz questioning Cecile Richards, including the "misleading chart" exchange later rated "Pants on Fire" by PolitiFact |

Each folder contains:
- `transcript.md` — the human-readable annotated transcript (Jefferson
  markers, deception/veracity tags, acoustic tags)
- `omni.md` — the combined "everything" view
- `analysis.json` — structured counts/summary data

**Redaction note:** all named individuals in these transcripts (witnesses,
Fujitsu/Post Office staff referenced by name, elected officials, Supreme
Court justices/advocates) appear by name in the underlying public
inquiry/court/congressional record already — see the source citations in
`CALIBRATION_ROUND2.md` for the specific public documents naming them. No
redaction was applied, consistent with the brief's guardrail that redaction
is only required for individuals who are not already named public figures
in an already-public, already-resolved record.
