# How well does the voice-analysis tool actually work?

A plain-English summary of a testing exercise we ran on one part of this
project: the feature that listens to a recording and notes things like "the
voice got louder here" or "the voice sounded shaky here."

## What is this tool for?

Some professionals need to work through long audio recordings and pick out
the moments that matter most — for example, where someone's voice suddenly
got louder, quieter, higher-pitched, shakier, or where they stumbled over
their words. Listening to a whole recording carefully, end to end, takes a
long time.

This tool automatically reads a recording, writes out what was said, and
adds small notes (marked with a microphone icon, 🎙️) at points where it
detects a change in how something was said — not just what was said. The
idea is to help a busy professional quickly spot the parts of a recording
worth a closer listen, rather than replacing their own judgement.

## Why we tested it

The rules the tool uses to decide "this sounds shaky" or "this sounds loud"
had only ever been checked against a computer-generated voice reading text
in a flat, emotionless tone. We didn't actually know if those rules held up
against a real person's real emotional voice — someone genuinely angry,
frightened, sad, or being deliberately vague. So we tested it properly.

## How we tested it

We found 10 short clips (10–30 seconds each) of real film dialogue where
actors are clearly conveying a specific emotion: shouting in anger, panic,
grief, joy, contempt, calm resignation, a sly/evasive tone, sudden shock,
and two calm, everyday conversations to use as a baseline comparison. All
of these clips came from old films that are legally free for anyone to use
(public domain), hosted on the free online archive [archive.org](https://archive.org).

We ran each clip through the tool, then compared what it flagged against
what a person listening would honestly say was actually happening in the
scene.

## What we found

**The good news:** after testing, most of the tool's biggest mistakes are
now fixed.

- Before testing, the tool wrongly flagged a "shaky voice" on **calm,
  ordinary conversation** almost as often as on genuinely distressed
  speech — including on a completely flat, unremarkable line. That was a
  real problem: it meant the "shaky voice" flag wasn't trustworthy at all.
  We traced this to one of its two internal checks being essentially
  useless — it reacted to normal ups and downs in anyone's speaking volume,
  not genuine vocal shakiness. We've switched that check off as a
  stand-alone trigger and now rely on a better-performing measurement
  (based on pitch changes), which did show a real difference between calm
  and distressed voices in our tests.
- We also found the tool was too quick to call a normal conversation
  "excited" or "alarmed" just because someone's pitch drifted up slightly
  over a few sentences. We've made that check stricter.
- After these fixes, we re-ran all 10 clips: 9 wrongly-flagged "shaky
  voice" moments and 4 wrongly-flagged "excited/alarmed" moments
  disappeared, while every flag that looked genuinely correct — including a
  proper "raised voice" flag on a panicked, shouting scene — stayed exactly
  as it was.

**The honest limits — what still doesn't work well:**

- If an entire short recording is loud all the way through (for example, an
  argument that's shouted from start to finish), the tool currently has
  **no quieter moment within that same clip to compare against**, so it may
  fail to flag it as "raised voice" at all, even though a human would
  obviously call it shouting. We looked hard for a fix and couldn't find
  one we could actually prove worked without also being wrong elsewhere in
  our tests — so for now, this is a known blind spot rather than something
  we've silently patched over.
- One calm conversation still gets a borderline "excited" flag we couldn't
  fully remove without breaking other, correct results elsewhere.
- We don't yet have enough evidence to say whether the "stumbled over
  words" flag works reliably on old or fast-talking recordings — we only
  saw two real examples in our whole test, which isn't enough to be
  confident either way.
- The tool currently has **no way to detect surprise or shock** at all — in
  our test clip of a startled reaction, it stayed silent rather than
  flagging anything, correct or not.

## The bottom line

This tool is a **time-saving assistant for spotting moments worth a closer
listen** — it is not, and was never designed to be, a lie detector, an
emotion-reading device, or any kind of proof about how someone was
genuinely feeling. Every flag it produces should be treated as a prompt to
go and listen to that part of the recording yourself, not as a conclusion
on its own. Our testing improved its accuracy meaningfully, but it was done
on a small number of clips (10 short film scenes), so it should be seen as
an early check, not a guarantee — and the limits described above are real
and currently unresolved, not hidden.

Full technical detail and the complete list of test clips and their exact
sources are available in this project's `docs/CALIBRATION.md` file, for
anyone who wants to check our working.
