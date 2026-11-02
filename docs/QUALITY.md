# Quality-first roadmap

## What v0.1 does

1. Four-bar harmonic cells with contrasting B section and tonic cadence.
2. Melodic motif recurrence instead of purely random notes.
3. Roles: strings, countermelody, harp arpeggio, woods, horn, trumpet climax and choral SATB.
4. SATB beam search: minimize leaps, crossed voices and parallel fifths/octaves at bar boundaries.
5. Instrument range, single-voice overlap, harmonic downbeat and large-leap checks.
6. Structured MusicXML for scoring, GM MIDI for preview.

## Musical deficits needing real listening tests

- Harmonic rhythm is simple, with repetitive 4-bar cycles.
- SATB checks use downbeats. They do NOT detect all classical voice-leading issues (e.g., tendency tones, unprepared dissonance, parallels between inner beats, chord doubling, text prosody).
- Orchestra uses basic division of roles and cannot yet control multiple articulations and expression envelopes as a pro sample library would.
- Flowing music quality is not proven by any percentage displayed in the UI.
- 16/64 bars at 94 BPM means ~41 seconds/~2m43s respectively. Tempo and notated durations determine exact runtime; free tempo rubato is not yet implemented.
- Muse Choir makes vowels, not complete intelligible lyrics without additional compatible vocal synthesis.

## v0.2 quality work (proposed)

1. **Arrange in phrase units**: each group has a role, intensity envelope, motivic variation, entry and release.
2. **Better harmony**: secondary dominants, suspensions, modulations and style-constrained transitions; no random chromaticism.
3. **Counterpoint and choral writing**: dissonance prep/resolution, tendency tones, smoother lines, chord-doubling rules, both outer and inner voices.
4. **Dynamics/audio**: MusicXML crescendo hairpins, staccato/legato/tremolo, per-phrase MIDI CC11/CC1, velocity curves, proper reverb and instrumental balance.
5. **Multiple candidates**: generate 3 alternative phrases, reject structural errors, present them side-by-side for listening. Avoid uncalibrated numerical aesthetic scores.
6. **Real high-quality renderer**: MuseScore installed on .103 with working MuseSounds mapping. First verify GUI export from imported MusicXML; only then automate.
7. **Iterative editing**: "поправь 9–12 такты", "приглуши трубы", "введи хор позже" without changing other phrases.
8. **Human listening tests**: 10–20 diverse prompt briefs, blinded A/B comparison, playback on MuseSounds, subjective scoring of melody, form, harmony, orchestration and audio realism.

### Proposed acceptance criteria for a release called 'high quality'

- Valid MusicXML and MIDI with 0 incorrect ranges, 0 broken measures, 0 crossed SATB voices or unintentional parallel perfect intervals.
- 100% test fixture compatibility with MuseScore Studio on GRAPHICS .103 (confirmed on real hardware, not guessed).
- Real listening tests: >=80% of independently evaluated outputs accepted without rewrites at <=60 seconds, with >=3 reviewers and documented prompts. This is a proposed target, not an observed result.
- Stable, reproducible score editing with no changes outside requested bars.

## License caveats

MuseSounds Core playback/render happens in MuseScore Studio only; not a VST that can be used in FluidSynth. Different instrument sets have different EULAs. Never commit sample libraries, generated audio or secrets.
