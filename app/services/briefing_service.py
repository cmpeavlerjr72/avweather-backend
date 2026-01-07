from __future__ import annotations

import os
import html as _html
from dataclasses import dataclass
from typing import Dict, Optional, Tuple, List

# --- Load .env like the working technical demonstrator ---
try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(usecwd=True))
except Exception:
    # If python-dotenv isn't installed, we won't crash here;
    # we'll error explicitly if key is missing below.
    pass

from openai import OpenAI


# ---------------- GPT wiring (mirrors your working app.py) ----------------

MODEL_FALLBACKS = ["gpt-5-mini", "gpt-4o-mini", "gpt-5"]

AVIATION_SYSTEM_PROMPT = (
    "Write a concise, passenger-friendly en-route briefing in the voice and clarity of an airline captain, "
    "but do NOT present yourself as the actual pilot or crew for this flight. "
    "Avoid first-person statements that imply operational control (e.g., 'I', 'we', 'this is your captain speaking'). "
    "Use neutral phrasing like 'Passengers can expect…', 'The flight may encounter…', and keep it calm, factual. "
    "Do not invent data."
)

def _as_paragraphs(text: str) -> str:
    """Convert a GPT string with blank lines into <p> paragraphs, HTML-escaped."""
    if not text:
        return ""
    safe = _html.escape(text.strip())
    parts = [p.strip() for p in safe.split("\n\n") if p.strip()]
    return "<p>" + "</p><p>".join(parts) + "</p>"

def _chat_completions(client: OpenAI, user_prompt: str, model: str, max_tokens: int) -> str:
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": AVIATION_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        # IMPORTANT for GPT-5 family:
        max_completion_tokens=max_tokens,
    )
    return (resp.choices[0].message.content or "").strip()

def _responses_api(client: OpenAI, user_prompt: str, model: str, max_tokens: int) -> str:
    messages = [
        {"role": "system", "content": [{"type": "text", "text": AVIATION_SYSTEM_PROMPT}]},
        {"role": "user", "content": [{"type": "text", "text": user_prompt}]},
    ]
    r = client.responses.create(
        model=model,
        input=messages,
        max_output_tokens=max_tokens,
    )
    txt = (getattr(r, "output_text", None) or "").strip()
    if txt:
        return txt

    # If SDK returns older shape, assemble manually
    parts: List[str] = []
    output = getattr(r, "output", None)
    if isinstance(output, list):
        for item in output:
            content = getattr(item, "content", None)
            if isinstance(content, list):
                for chunk in content:
                    t = chunk.get("text") or chunk.get("value") or ""
                    if isinstance(t, str) and t:
                        parts.append(t)
    return "\n".join(parts).strip()

def call_model_with_retries_for_briefing(client: OpenAI, user_prompt: str, primary_model: str, max_tokens: int) -> Tuple[str, list]:
    tried = []

    # 1) Chat completions attempts
    for m in [primary_model] + [x for x in MODEL_FALLBACKS if x != primary_model]:
        try:
            tried.append((m, "chat"))
            text = _chat_completions(client, user_prompt, m, max_tokens)
            if text:
                return text, tried
        except Exception as e:
            tried.append((m, f"chat_error:{e}"))

    # 2) Responses API attempts
    for m in [primary_model] + [x for x in MODEL_FALLBACKS if x != primary_model]:
        try:
            tried.append((m, "responses"))
            text = _responses_api(client, user_prompt, m, max_tokens)
            if text:
                return text, tried
        except Exception as e:
            tried.append((m, f"responses_error:{e}"))

    return "", tried


# ---------------------- Briefing service layer ----------------------

@dataclass
class BriefingInputs:
    origin: str
    destination: str
    cruise_fl: int
    calm: bool

    origin_metar_cat: Optional[str] = None
    dest_metar_cat: Optional[str] = None

    origin_metar_raw: Optional[str] = None
    dest_metar_raw: Optional[str] = None

    origin_taf_raw: Optional[str] = None
    dest_taf_raw: Optional[str] = None

    pirep_counts: Optional[Dict[str, int]] = None
    sigmet_count: int = 0
    gairmet_counts: Optional[Dict[str, int]] = None


class BriefingService:
    """
    Uses GPT for briefing (no silent fallback in dev unless explicitly enabled).
    Set ALLOW_BRIEFING_FALLBACK=1 if you want to allow fallback text.
    """

    def __init__(self) -> None:
        self.api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
        self.model = (os.getenv("OPENAI_MODEL") or "gpt-5").strip()
        self.max_tokens = int(os.getenv("OPENAI_MAX_TOKENS", "260"))
        self.allow_fallback = (os.getenv("ALLOW_BRIEFING_FALLBACK", "0").strip() == "1")

        if not self.api_key:
            msg = "OPENAI_API_KEY not set (in this uvicorn process)."
            if self.allow_fallback:
                self._init_error = msg
            else:
                raise RuntimeError(msg)

        self.client = OpenAI(api_key=self.api_key)

    def _fallback(self, inp: BriefingInputs, reason: str) -> str:
        # Keep this short; you said you don’t want fallback, but if enabled, show why.
        return (
            "Briefing unavailable right now.\n\n"
            f"Reason: {reason}\n\n"
            "Layers remain live — click METAR/PIREP items for details."
        )

    def _build_prompt(self, inp: BriefingInputs) -> str:
        pirep = inp.pirep_counts or {}
        g = inp.gairmet_counts or {}

        def _clip(s: Optional[str], n: int = 650) -> str:
            if not s:
                return ""
            s = s.strip()
            return s[:n] + ("…" if len(s) > n else "")

        # This matches the demonstrator’s “short paragraphs with blank lines” style.
        lines = []
        lines.append(f"Route: {inp.origin} → {inp.destination}")
        lines.append(f"Cruise: FL{inp.cruise_fl}")
        lines.append(f"Nervous flyer: {bool(inp.calm)}")
        lines.append("")
        lines.append(f"Departure/arrival METAR categories: {inp.origin}={inp.origin_metar_cat or 'UNK'}, {inp.destination}={inp.dest_metar_cat or 'UNK'}")
        lines.append(f"Origin TAF raw: {_clip(inp.origin_taf_raw)}")
        lines.append(f"Destination TAF raw: {_clip(inp.dest_taf_raw)}")
        lines.append("")
        lines.append(
            f"PIREPs (counts): LGT={int(pirep.get('LGT',0))}, MOD={int(pirep.get('MOD',0))}, SEV={int(pirep.get('SEV',0))}"
        )
        lines.append(
            f"Advisories (counts): SIGMET={int(inp.sigmet_count)}, G-AIRMET tango={int(g.get('tango',0))}, zulu={int(g.get('zulu',0))}, sierra={int(g.get('sierra',0))}"
        )
        lines.append("")
        lines.append(
            "Write 2–3 short paragraphs separated by a blank line. "
            "Do NOT imply you are the operating crew. Avoid codes/jargon."
        )
        return "\n".join(lines)

    def generate(self, inp: BriefingInputs) -> str:
        prompt = self._build_prompt(inp)

        text, tried = call_model_with_retries_for_briefing(
            self.client,
            prompt,
            primary_model=self.model,
            max_tokens=self.max_tokens,
        )

        if text:
            return text

        # No output from all attempts
        reason = f"All model attempts returned empty. Tried: {tried}"
        if self.allow_fallback:
            return self._fallback(inp, reason)
        raise RuntimeError(reason)
