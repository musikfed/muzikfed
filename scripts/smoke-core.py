#!/usr/bin/env python3
"""Live API smoke test for all five v0.1 ensembles on CORE .100.

No extra dependencies. Sends five small 8-bar test compositions through the
running FastAPI service, validates MusicXML/MIDI/JSON and separated choir stems,
and renders a *rough* WAV for the orchestra (or every ensemble with --wav-all).
It creates test jobs in /1tbdisk/muzikfed/outputs/ through the normal API.
Russian sung words and MuseSounds fidelity are NOT tested here.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

BASE = "http://192.168.0.100:9095"
CHOIR = {"soprano", "alto", "tenor", "choral_bass"}
QUARTET = {"violin_1", "violin_2", "viola", "cello"}
ORCHESTRA = QUARTET | {"bass", "flute", "oboe", "clarinet", "horn", "trumpet", "harp", "timpani"}
CASES = (
    ("orchestra", "Только оркестр", ORCHESTRA, set()),
    ("quartet", "Струнный квартет", QUARTET, set()),
    ("choir", "Только SATB (гласные)", CHOIR, {"choir.musicxml", "choir.mid"}),
    ("orchestra_choir", "Оркестр + SATB", ORCHESTRA | CHOIR,
     {"choir.musicxml", "choir.mid", "orchestra.musicxml", "orchestra.mid"}),
    ("quartet_choir", "Квартет + SATB", QUARTET | CHOIR,
     {"choir.musicxml", "choir.mid", "quartet.musicxml", "quartet.mid"}),
)


def request(base: str, path: str, payload: dict | None = None) -> bytes:
    url = urllib.parse.urljoin(base.rstrip("/") + "/", path.lstrip("/"))
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    method = "POST" if payload is not None else "GET"
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json"} if data is not None else {},
    )
    with urllib.request.urlopen(req, timeout=200) as response:
        return response.read()


def check_one(base: str, ensemble: str, label: str, expected: set[str],
              extra: set[str], wav: bool, llm: bool = False) -> dict:
    cfg = {
        "title": f"Тест — {label}",
        "prompt": ("Негромкое вступление, затем развитие и кульминация, "
                   "в конце тихая кода. Оригинальная музыка."),
        "ensemble": ensemble, "bars": 8, "tempo": 94, "seed": 42,
        "use_ollama": llm, "model": "qwen3:8b",
    }
    response = json.loads(request(base, "/api/generate", {
        "config": cfg, "render_preview": wav,
    }))
    actual = set(response["composition"]["parts"])
    assert actual == expected, f"{label}: партии {sorted(actual)}, ожидалось {sorted(expected)}"
    quality = response["quality"]
    assert quality["passed"] == quality["total"], f"{label}: {quality}"
    links = response["urls"]
    required = {"musicxml", "midi", "report"} | extra
    assert required <= set(links), f"{label}: нет файлов {required - set(links)}"
    if not CHOIR.intersection(expected):
        assert "choir.mid" not in links, f"{label}: обнаружен неожиданный хор"

    # Real downloaded score and MIDI, not just links or API JSON metadata.
    xml = request(base, links["musicxml"])
    root = ET.fromstring(xml)
    assert root.tag == "score-partwise"
    assert len(root.findall("part")) == len(expected)
    assert all(len(part.findall("measure")) == 8 for part in root.findall("part"))
    midi = request(base, links["midi"])
    assert midi[:4] == b"MThd", f"{label}: invalid MIDI header"
    report = json.loads(request(base, links["report"]))
    assert report["quality"]["passed"] == report["quality"]["total"]
    for file in extra:
        blob = request(base, links[file])
        if file.endswith(".mid"):
            assert blob[:4] == b"MThd", f"{label}: invalid stem {file}"
        else:
            assert ET.fromstring(blob).tag == "score-partwise"
    if wav:
        assert "wav" in links, f"{label}: preview not generated: {response['render']}"
        audio = request(base, links["wav"])
        assert audio[:4] == b"RIFF" and audio[8:12] == b"WAVE",             f"{label}: invalid WAV preview"
    if llm:
        assert response["llm"].startswith("LLM:"),             f"Ollama not used; API fell back to composer: {response['llm']}"

    return {"name": label, "job_id": response["job_id"], "parts": len(actual),
            "notes": quality["statistics"]["notes"], "wav": "wav" in links,
            "llm": response["llm"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=BASE, help=f"API base URL (default: {BASE})")
    parser.add_argument("--wav-all", action="store_true",
                        help="Render a rough FluidSynth WAV for each ensemble")
    parser.add_argument("--no-wav", action="store_true",
                        help="Skip WAV entirely: test only notation and API")
    parser.add_argument("--llm", action="store_true",
                        help="Also test an optional Ollama request; requires running qwen3:8b")
    args = parser.parse_args()
    print(f"CORE smoke test at {args.base}", flush=True)
    try:
        health = json.loads(request(args.base, "/api/health"))
        assert health.get("status") == "ok", f"unexpected health: {health}"
        print(f"Health: OK, FluidSynth ready: {bool(health.get('renderer'))}", flush=True)
    except (OSError, ValueError, AssertionError) as exc:
        print(f"[FAIL] Server health: {exc}", file=sys.stderr)
        return 1
    failures = 0
    for ensemble, label, parts, stems in CASES:
        render = not args.no_wav and (args.wav_all or ensemble == "orchestra")
        try:
            info = check_one(args.base, ensemble, label, parts, stems, render)
            print(f"[OK] {label}: {info['parts']} part(s), "
                  f"{info['notes']} notes, WAV: {'yes' if info['wav'] else 'no'}, "
                  f"job={info['job_id']}", flush=True)
        except (OSError, ValueError, KeyError, AssertionError, ET.ParseError,
                urllib.error.HTTPError) as exc:
            failures += 1
            print(f"[FAIL] {label}: {exc}", file=sys.stderr, flush=True)
    if args.llm:
        try:
            info = check_one(args.base, "orchestra", "Оркестр + Ollama",
                             ORCHESTRA, set(), False, llm=True)
            print(f"[OK] Ollama: {info['llm']}", flush=True)
        except (OSError, ValueError, KeyError, AssertionError, ET.ParseError) as exc:
            failures += 1
            print(f"[FAIL] Ollama optional check: {exc}", file=sys.stderr, flush=True)
    print(f"Result: {len(CASES) + bool(args.llm) - failures} passed, "
          f"{failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
