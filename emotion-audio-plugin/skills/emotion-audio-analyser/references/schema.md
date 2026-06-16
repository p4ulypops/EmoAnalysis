# Affective-Clinical-MD v2.5 — Full Notation Reference
## Changelog
- **v2.5** — Original schema (Jefferson + TEI + CHAT + clinical XML)
- **v2.6** — Added: `[C:]` certainty scores, bystander classification, environmental/acoustic
  event tags, room entry/exit schema, entity register, speaker manifest

## Sources
- Jefferson Transcription System (conversation analysis)
- TEI Guidelines for Spoken Texts
- CHAT (TalkBank / CHILDES)
- Acoustic-prosodic ASD research (UAR 69%, PMC12978205)

---

## Utterance block structure

```
[HH:MM:SS.mmm] {Speaker_ID} [EMOJI Affect : Intensity/10] <Cert:Level>:
utterance text with inline markers
```

**Fields:**
- `HH:MM:SS.mmm` — millisecond-precise timestamp from audio start
- `{Speaker_ID}` — diarised speaker label
- `EMOJI Affect` — Unicode emoji + English affect label
- `Intensity/10` — 1 (barely perceptible) to 10 (maximum)
- `<Cert:High/Med/Low>` — transcription confidence

---

## Paralinguistic markers (Jefferson)

| Symbol | Phenomenon | Notes |
|--------|-----------|-------|
| `~word~` | Shaky / crying voice | Diaphragmatic control loss; grief, distress |
| `WORD` | Shouting / loud | Caps = distinctly louder than baseline |
| `°word°` | Whisper / quiet | Degree signs; shame, conspiracy, trauma recall |
| `#word#` | Creaky voice / vocal fry | Low arousal, exhaustion, confidence collapse |
| `£word£` | Smiley voice / suppressed laugh | Resonance shift from smile |
| `w(h)ord` | Breathiness / laugh spurt | Abrupt breath through word |
| `word::` | Prolonged sound | Each colon ≈ 0.2s extra duration |
| `↑↑word` | Extreme pitch spike | Panic, shock, dysregulation |
| `↓↓word` | Extreme pitch drop | Resignation, defeat |
| `>word<` | Accelerated delivery | Hurried, rushed |
| `<word>` | Decelerated delivery | Deliberate slowing |
| `.hhh` | Sharp inbreath | Shock, trauma trigger, sobbing prep |
| `hhh` | Exhalation | Length ∝ duration |
| `hhih` | Inhaled sobbing | |
| `Hhuyuhh` | Exhaled sobbing | |
| `( )` | Inaudible | No plausible candidate word |
| `(word)` | Uncertain transcription | Analyst best guess |
| `[` | Overlap start | Simultaneous speech onset |
| `=` | Latching | No gap between turns (power/interruption) |
| `(.)` | Micropause | 0.08–0.2s |
| `(0.7)` | Timed pause | Tenths of a second |
| `(1:04.20)` | Extended pause — CHAT | min:sec.ms format |

---

## TEI XML tags

```xml
<!-- Vocal event -->
<vocal desc="throat clearing" int="3"/>

<!-- Kinesic gesture -->
<kinesic desc="rapid hand flapping" sync="word"/>

<!-- Environmental incident -->
<incident desc="police siren" impact="interruption" dur="15s"/>
<incident type="music" desc="classical piano" impact="baseline_noise"/>

<!-- Pause types -->
<pause dur="0.5s" type="fluent"/>
<pause dur="1.8s" type="awkward"/>   <!-- ASD marker -->
<pause dur="1:04.20" type="freeze"/> <!-- PTSD marker -->

<!-- Affect wrapper -->
<affect type="crying" int="8">~word~</affect>
<affect type="shout" int="9">WORD</affect>
<affect type="whisper" int="2">°word°</affect>
<affect type="creak" int="6">#word#</affect>
```

---

## Clinical XML tags

### PTSD / Trauma
```xml
<ptsd-frag type="repetition">text</ptsd-frag>
<ptsd-frag type="unfinished_utterance">text</ptsd-frag>
<somatic>visceral sensory detail here</somatic>
<mental-defeat>heavy I/me/my pronoun cluster</mental-defeat>
<!-- Flag: cognitive processing absent -->
<!-- [NO-COG-PROC] -->
```

### ADHD
```xml
<maze>tangential narrative block</maze>
<cluttering>rapid erratic speech segment</cluttering>
<meta-correction type="rerail">OK but back to the point—</meta-correction>
```

### ASD
```
[F0-VAR: low][ART-RATE: 3.2 sps][Expressivity: 2/10]
```
Place these in the utterance prefix bracket before the affect emoji.

### Deception
```xml
<fs>          <!-- false start — sentence abandoned -->
<corrsp correct="driving">walking</corrsp>  <!-- spontaneous correction -->
<rep n="3">walking</rep>                    <!-- stalling repetition -->
<lack-mem>I don't really remember</lack-mem>
```

---

## Affect emoji reference

| Emoji | Affect label | Typical context |
|-------|-------------|----------------|
| 😐 | Neutral | Baseline / clinical |
| 😨 | Anxious | Pre-trauma, anticipatory |
| 😟 | Empathetic | Clinician mirroring |
| 😢 | Sad | Grief narrative |
| 😠 | Hostile | Conflict |
| 😡 | Furious | Escalation peak |
| 😤 | Frustrated | Blocked / invalidated |
| 😰 | Nervous | Deception baseline |
| 😳 | Panicked | Confrontation / contradiction |
| 🤩 | Excited | ADHD hyperfocus onset |
| 🤔 | Engaged | Problem-solving |
| 😴 | Flat / withdrawn | ASD low affect / dissociation |
| 🚩 | Safeguarding flag | Care advocacy contexts |

---

## Certainty levels

| Level | Meaning |
|-------|---------|
| `<Cert:High>` | Clear audio, confident transcription |
| `<Cert:Med>` | Some ambiguity — speaker or word uncertain |
| `<Cert:Low>` | Audio degraded, mumbled, or overlapping |

---

---

## Certainty scoring [C:0.00–1.00]

Every automated annotation carries a confidence score. This is Claude being honest —
not every claim can be made with equal certainty from audio alone.

| Score range | Meaning | Action |
|-------------|---------|--------|
| [C:0.90–1.00] | High confidence | Trust, archive |
| [C:0.70–0.89] | Moderate confidence | Spot-check |
| [C:0.50–0.69] | Low confidence | ⚠️ Verify before citing |
| [C:<0.50] | Speculative | Flag for manual review |

**Format:** `[C:0.87]` inline, or `cert="0.87"` inside XML attributes.

```
[00:15:08.500] {Patient_34} [😨 Anxious : 8/10] [C:0.82] <Cert:High>:
```

---

## Speaker roles

```
{PRIMARY}    — main participant, central to the recording's purpose
{SECONDARY}  — present throughout but less central
{BYSTANDER}  — incidental, brief, not part of the core interaction
```

Bystander blocks are visually set off and excluded from clinical analysis:

```
--- BYSTANDER INTERACTION [C:0.65] ---
[00:04:12.000] {Bystander_01} [😐 Neutral : 3/10] [C:0.60]:
Lovely day, isn't it!
[00:04:13.500] {Pauly} [😐 Neutral : 5/10] [C:0.90]:
Yeah, not bad!
--- END BYSTANDER ---
```

---

## Entity Register (document header)

```markdown
## Entity Register
| Entity | Type | [C:] | Occurrences | Notes |
|--------|------|------|-------------|-------|
| Natalia | Person/PRIMARY | [C:0.95] | 23 | Confirmed via known_primaries |
| Jacky | Person/PRIMARY | [C:0.95] | 17 | Confirmed via known_primaries |
| 6th November 2025 | Date | [C:0.92] | 2 | Recording date context |
| Barnet | Location | [C:0.71] | 1 | ⚠️ verify — single mention |
```

---

## Environmental Events Log (document header)

```markdown
## Environmental Events Log
| Time | Duration | Type | [C:] | Impact | TEI |
|------|----------|------|------|--------|-----|
| 00:03:41 | 12.3s | music/radio | [C:0.61] ⚠️ | background | `<incident type="music" .../>` |
| 00:17:12 | 0.1s | door_event | [C:0.48] ⚠️ | possible entry | `<incident type="door_event" .../>` |
| 00:22:05 | 0.8s | transient_impact | [C:0.55] ⚠️ | car horn? | `<incident type="acoustic_event" .../>` |
```

---

## Environmental TEI tags (v2.6)

```xml
<!-- Music / radio / TV -->
<incident type="music" desc="radio in background" dur="12.3s" cert="0.61" impact="baseline_noise"/>
<incident type="tv" desc="television audible — not primary content" dur="45s" cert="0.55"/>

<!-- AI assistant interruptions -->
<incident type="ai_voice" desc="Alexa/Siri response" dur="3.2s" cert="0.90" impact="interruption"/>

<!-- Acoustic events -->
<incident type="car_horn" desc="vehicle horn outside" dur="0.8s" cert="0.72"/>
<incident type="door_event" desc="possible door open/close — entry/exit?" dur="0.1s" cert="0.48"/>
<incident type="dog_bark" desc="dog barking" dur="1.5s" cert="0.65"/>
<incident type="phone_ring" desc="phone ringing" dur="3.0s" cert="0.80" impact="interruption"/>
<incident type="footsteps" desc="footsteps approaching — possible arrival" dur="4.0s" cert="0.42"/>

<!-- Room entry/exit -->
<incident type="room_entry" desc="[name] enters — door + footsteps" cert="0.65"/>
<kinesic desc="[name] enters room" sync="[word]"/>
<!-- Remaining: {Primary_A, Primary_B} -->

<incident type="room_exit" desc="[name] leaves" cert="0.60"/>
<!-- Remaining: {Primary_A} -->
```

---

## Shenanigans Watch

When `detect_room_changes` flags a potential entry/exit during a sensitive exchange:

```markdown
## ⚠️ Shenanigans Watch

**[17:12]** Possible door event [C:0.48] — verify by listening.
→ Check content immediately **before** [17:12] and immediately **after**.
→ If someone entered at this point, they may have overheard content from [~17:00] onward.
→ If someone exited, note what changed in the conversation dynamics afterward.

Schema: `<incident type="room_entry" desc="[name]? — unconfirmed" cert="0.48"/>`
```

---

## Complete utterance block example

```
[00:15:08.500] {Patient_34} [😨 Anxious : 8/10] <Cert:High>:
(2.5) I remember the- the sound mostly. It was like a:: crunching metal sound.
And then >everything got really quiet< (.) I(h) mean dead quiet.
I couldn't- <ptsd-frag type="unfinished_utterance">I couldn't feel my</ptsd-frag>—
<somatic>legs.</somatic>
[NO-COG-PROC]
(1:04.20) ((Patient exhibits profound freeze response, stares at floor))
```
