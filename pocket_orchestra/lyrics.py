"""Russian lyric drafts and score labels. These are NOT synthesized singing.

The soundtrack remains GM/SF2; only a dedicated singing model can articulate words.
"""
from __future__ import annotations

from dataclasses import replace
from random import Random
import re

from .composer import Config, Piece, _stable_seed

STANZAS = (
    (
        "Над землёй затихает заря,",
        "И сквозь тучи мерцает дорога,",
        "Я храню это пламя не зря,",
        "Чтобы свет не покинул порога.",
    ),
    (
        "Тихий ветер качает траву,",
        "За рекою проснулись рассветы,",
        "Я навстречу надежде иду,",
        "И поёт мне душа до рассвета.",
    ),
    (
        "Где просторы встречают закат,",
        "Мы услышим дыхание неба,",
        "Пусть тревоги на миг замолчат,",
        "И весна возвратится из снега.",
    ),
    (
        "Через годы и тысячи дней,",
        "Пронесём мы заветное слово,",
        "Среди звёзд и знакомых огней,",
        "Наша песня начнётся снова.",
    ),
    (
        "Я сквозь бури иду за мечтой,",
        "По дорогам, где светит надежда,",
        "И встречаюсь с родною весной,",
        "Пусть любовь остаётся, как прежде.",
    ),
)


def draft_lyrics(cfg: Config) -> str:
    """Original short template draft; optional user text takes precedence.

    Templates are meant as editable starting points, not an assertion that a
    language model understood the entire description or that words will be sung.
    """
    if cfg.lyrics.strip():
        return cfg.lyrics.strip()
    rng = Random(_stable_seed(cfg) ^ 0xA48F1)
    verse_a, verse_b = rng.sample(STANZAS, 2)
    title = cfg.title.strip()
    return (
        f"{title}\n\n"
        "[Куплет 1]\n" + "\n".join(verse_a) + "\n\n"
        "[Куплет 2]\n" + "\n".join(verse_b) + "\n\n"
        "[Финал]\n" + "\n".join((verse_a[0], verse_b[1], verse_a[2], verse_b[3]))
    )


def annotate_score_lyrics(piece: Piece, text: str) -> int:
    """Put lyric *words* on soprano notes in MusicXML. No phoneme/voice synthesis.

    OpenUtau and other specialist tools will require manual syllable alignment.
    """
    if "soprano" not in piece.tracks:
        return 0
    lines = [line for line in text.splitlines()
             if line.strip() and not line.strip().startswith("[")
             and line.strip() != piece.config.title.strip()]
    words = re.findall(r"[А-Яа-яЁёA-Za-z]+(?:-[А-Яа-яЁёA-Za-z]+)*", " ".join(lines))
    if not words:
        return 0
    soprano = piece.tracks["soprano"]
    n = min(len(soprano), len(words))
    piece.tracks["soprano"] = [
        replace(note, lyric=words[i]) if i < n else note
        for i, note in enumerate(soprano)
    ]
    return n
