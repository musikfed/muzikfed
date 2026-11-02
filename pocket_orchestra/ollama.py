"""Optional local Ollama: proposes a bounded four-bar composition plan.

LLMs do not write the score directly: every proposed value is validated and the
rule-based composer handles voice leading and file generation.
"""
import json
import urllib.request
from urllib.error import URLError, HTTPError
from .composer import Config


def generate_plan(cfg: Config, endpoint: str = "http://127.0.0.1:11434/api/generate") -> dict:
    prompt = f"""Ты опытный композитор и оркестровщик. Ответь ТОЛЬКО JSON-объектом,
без markdown и комментариев. Предложи музыкальный замысел для партитуры.
Задание заказчика: {cfg.prompt}
Дано: {cfg.key} {cfg.mode}, {cfg.tempo} BPM, {cfg.bars} тактов,
ансамбль {cfg.ensemble}, напряжённость {cfg.tension}.
Строгая схема ответа:
{{"progression_a":[0,5,2,4], "progression_b":[3,5,4,0],
  "motif":[4,3,2,0], "comment":"Краткий замысел на русском"}}
progression_a/b: ровно 4 целых диатонических ступени 0..6 (0=тоника).
motif: ровно 4 целых интервала по ступеням -4..7.
Сохраняй повторяемость мотива и контраст разделов. Не копируй известные мелодии."""
    body = json.dumps({"model": cfg.model, "prompt": prompt, "stream": False,
                       "format": "json", "options": {"temperature": .55, "num_predict": 400}}).encode("utf-8")
    request = urllib.request.Request(endpoint, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            data = json.loads(response.read(1024 * 1024))
        proposal = json.loads(data["response"])
    except (URLError, HTTPError, TimeoutError, OSError, KeyError, ValueError, json.JSONDecodeError) as e:
        raise RuntimeError(f"Ollama не ответила корректным JSON: {type(e).__name__}: {e}") from e
    if not isinstance(proposal, dict):
        raise ValueError("Ответ LLM должен быть объектом JSON")
    for name, low, high in (("progression_a", 0, 6), ("progression_b", 0, 6), ("motif", -4, 7)):
        value = proposal.get(name)
        if not (isinstance(value, list) and len(value) == 4 and all(type(x) is int and low <= x <= high for x in value)):
            raise ValueError(f"Недопустимая структура LLM: {name}")
    proposal["comment"] = str(proposal.get("comment", ""))[:600]
    proposal["source"] = f"ollama:{cfg.model}"
    return proposal


def generate_lyrics(cfg: Config, endpoint: str = "http://127.0.0.1:11434/api/generate") -> str:
    """Optional original Russian lyric text by local Ollama, not voice synthesis."""
    prompt = f"""Сочини СВОЙ оригинальный текст песни на русском языке для музыки.
Название: {cfg.title}. Стиль: {cfg.style}. Тема: {cfg.prompt}.
Нужно 3 коротких куплета по 4 строки; образность, развитие, выразительный припев,
хорошая ритмика, простые произносимые слова, без известных цитат.
Ответь ТОЛЬКО JSON-объектом вида {{"lyrics":"[Куплет 1]\\n...\\n[Припев]\\n..."}}.
Не описывай процесс и не пиши английские пояснения."""
    body = json.dumps({
        "model": cfg.model, "prompt": prompt, "stream": False,
        "format": "json", "options": {"temperature": .75, "num_predict": 700},
    }).encode("utf-8")
    request = urllib.request.Request(
        endpoint, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            data = json.loads(response.read(1024 * 1024))
        result = json.loads(data["response"])
        lyrics = result["lyrics"]
    except (URLError, HTTPError, TimeoutError, OSError, KeyError, ValueError,
            json.JSONDecodeError) as exc:
        raise RuntimeError(f"Нейросеть не подготовила текст: {type(exc).__name__}") from exc
    if not isinstance(lyrics, str) or not 24 <= len(lyrics.strip()) <= 4000:
        raise ValueError("Ожидался непустой оригинальный текст песни до 4000 символов")
    return lyrics.strip()
