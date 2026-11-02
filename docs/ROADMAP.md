# Roadmap — Pocket Orchestra

## Today: implemented in v0.1

**Instrumental score generation**: orchestra (12), string quartet (4), choir-note SATB (4), quartet + choir (8), orchestra + choir (16). Programmatic MusicXML, MIDI, quality JSON, optional *rough* FluidSynth preview; manually rendered high-quality MuseSounds audio via MuseScore Studio on Windows.

**Choir in v0.1 = pitched choir parts singing only Ahh/Ooh/Mmm syllables.** There is NO intelligible Russian sung-text generator, NO isolated neural singer, and NO guaranteed vocal WAV stem yet. This distinction is essential.

## Proposed v0.2 — three separate modes

1. **Vocal only**: a cappella singer, duet, quartet or choir. Russian text with syllabification, stresses, phoneme alignment, duration control, multiple takes and lyric intelligibility checks. Requires a separately researched, compatible, locally run singing synthesis/audio model with verified terms, Russian support and enough VRAM.
2. **Instrumental only**: the existing score engine enhanced with motifs, harmony, orchestration, realistic dynamics and MuseSounds quality evaluation.
3. **Vocal + arrangement**: isolated vocal track(s), score-based instrument layers, synchronized BPM/timebase, mix and independent revision of chorus/intro/individual bars.

Do not claim these modes are already usable. A text-to-song audio model doesn't necessarily produce score-accurate stems or phonemes; exact text-to-notes singing must be evaluated separately. Long songs may require section-by-section generation and continuity checks.

## Quality criteria

- Two independent tracks: **composition quality** (motif/harmony/structure/ranges/voicing/phrasing) and **render quality** (sample choice, timing, articulation, balance, mix, audibility of Russian lyrics).
- Add audio-based user ratings and A/B compare at the *same loudness*; avoid pretending structural tests measure emotional artistry.
- Allow regeneration of selected bars or a chorus without destroying the surrounding piece.
- Introduce instrument-specific performance passes (CC1/CC11 for dynamic sampled instruments where supported, bowing/legato, brass attacks, breath pauses).
- Render and assess final WAV on .103 with MuseSounds, not FluidSynth.

## v0.3+

- Reliable Russian text-to-singing vocals with explicit syllable alignment; tested RTX 3060 12 GB workflow.
- Stem-oriented timeline (singer/duet/SATB + orchestra) with independent volume, panning, effects and replacement of selected segments.
- Optional offline queue to GRAPHICS .103; no hidden internet exposure; authorization and quotas before enabling remote multi-user operation.
- More diverse forms, contrapuntal development, tempo maps, 3–10-minute works by musical sections.

Each new release should ship reproducible quality examples and record what was *actually* auditioned on user hardware.
