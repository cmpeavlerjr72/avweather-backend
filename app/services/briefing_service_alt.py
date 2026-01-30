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
    "You write a short, passenger-friendly aviation weather briefing that is educational and explanatory. "
    "You are NOT the operating crew, NOT a pilot for this flight, and you must not imply operational authority. "
    "Do not use first-person crew language ('I', 'we', 'your captain', 'our flight'). "
    "\n\n"
    "CRITICAL SCOPE: Do NOT predict turbulence intensity/timing, do NOT promise smoothness, and do NOT provide any "
    "turbulence score, 'ride quality' rating, or guarantee. Avoid phrases like 'smooth departure', 'what to expect', "
    "'should be a smooth ride', or anything that sounds like certainty. "
    "\n\n"
    "DATA RULES: Use ONLY the data provided in the user prompt. Do not invent weather, locations, altitudes, "
    "timelines, or PIREPs. If data is missing or ambiguous, say so plainly. "
    "\n\n"
    "OUTPUT FORMAT (REQUIRED): Write exactly three sections, each 1 short paragraph, separated by a blank line:\n"
    "1) 'What we know from the available reports' (facts only)\n"
    "2) 'How pilots generally think about these conditions' (general concepts; no promises)\n"
    "3) 'Uncertainty & normal variability' (explicitly state limits; no reassurance-by-guarantee)\n"
    "\n\n"
    "TONE: Calm, factual, not overly reassuring. Avoid jargon and codes. If you must mention a term (e.g., SIGMET), "
    "define it in plain English."
)


LAYMAN_SYSTEM_PROMPT = (
    "You translate aviation weather reports into plain English for non-pilots. "
    "Be calm, concise, and factual. Use only what is present in the raw text provided. "
    "Do not invent details or add certainty.\n\n"
    "Do NOT predict turbulence, do NOT promise smoothness, and do NOT give a score or rating. "
    "If the report is incomplete/ambiguous, say so briefly."
)



def _as_paragraphs(text: str) -> str:
    """Convert a GPT string with blank lines into <p> paragraphs, HTML-escaped."""
    if not text:
        return ""
    safe = _html.escape(text.strip())
    parts = [p.strip() for p in safe.split("\n\n") if p.strip()]
    return "<p>" + "</p><p>".join(parts) + "</p>"

def _chat_completions(
    client: OpenAI,
    user_prompt: str,
    model: str,
    max_tokens: int,
    system_prompt: str,
) -> str:

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        # IMPORTANT for GPT-5 family:
        max_completion_tokens=max_tokens,
    )
    return (resp.choices[0].message.content or "").strip()

def _responses_api(
    client: OpenAI,
    user_prompt: str,
    model: str,
    max_tokens: int,
    system_prompt: str,
) -> str:

    messages = [
        {"role": "system", "content": [{"type": "text", "text": system_prompt}]},
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

def call_model_with_retries_for_briefing(
    client: OpenAI,
    user_prompt: str,
    primary_model: str,
    max_tokens: int,
    system_prompt: str = AVIATION_SYSTEM_PROMPT,
) -> Tuple[str, list]:


    tried = []

    # 1) Chat completions attempts
    for m in [primary_model] + [x for x in MODEL_FALLBACKS if x != primary_model]:
        try:
            tried.append((m, "chat"))
            text = _chat_completions(client, user_prompt, m, max_tokens, system_prompt)

            if text:
                return text, tried
        except Exception as e:
            tried.append((m, f"chat_error:{e}"))

    # 2) Responses API attempts
    for m in [primary_model] + [x for x in MODEL_FALLBACKS if x != primary_model]:
        try:
            tried.append((m, "responses"))
            text = _responses_api(client, user_prompt, m, max_tokens, system_prompt)

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
        self.model_free = (os.getenv("OPENAI_MODEL_FREE") or "gpt-4o-mini").strip()
        self.model_pro = (os.getenv("OPENAI_MODEL_PRO") or "gpt-5").strip()

        self.max_tokens_free = int(os.getenv("OPENAI_MAX_TOKENS_FREE", "180"))
        self.max_tokens_pro = int(os.getenv("OPENAI_MAX_TOKENS_PRO", "320"))

        # default behavior (no IAP yet): free
        self.model = self.model_free
        self.max_tokens = self.max_tokens_free

        self.allow_fallback = (os.getenv("ALLOW_BRIEFING_FALLBACK", "0").strip() == "1")

        # How many times to regenerate if output violates banned language rules
        self.max_banned_regens = int(os.getenv("BRIEFING_MAX_BANNED_REGENS", "3"))

        if not self.api_key:
            msg = "OPENAI_API_KEY not set (in this uvicorn process)."
            if self.allow_fallback:
                self._init_error = msg
            else:
                raise RuntimeError(msg)

        self.client = OpenAI(api_key=self.api_key)
        self._interpret_cache: dict[str, str] = {}

    def _contains_banned_claims(self, text: str) -> bool:
        t = (text or "").lower()

        # Keep this list tight; you can expand later
        banned_substrings = [
            "turbulence score",
            "ride quality",
            "guarantee",
            "guaranteed",
            "you can expect",
            "expect ",
            "smooth",
            "smoother",
            "predict",
        ]
        return any(b in t for b in banned_substrings)


    def set_tier(self, tier: str | None):
        tier = (tier or "free").lower().strip()
        if tier == "pro":
            self.model = self.model_pro
            self.max_tokens = self.max_tokens_pro
        else:
            self.model = self.model_free
            self.max_tokens = self.max_tokens_free



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
        lines.append(f"Passenger preference: {'extra calm tone' if inp.calm else 'standard tone'}")
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
        lines.append("SCOPE / SAFETY (must follow):")
        lines.append("- This is an educational weather context briefing, not a turbulence forecast.")
        lines.append("- Do NOT predict turbulence intensity or timing. Do NOT promise smoothness.")
        lines.append("- Do NOT provide any 'turbulence score', 'ride quality', or comfort rating.")
        lines.append("- Use ONLY the provided data; if something is unknown, say so.")
        lines.append("- Avoid the words: smooth, smoother, predict, guarantee, expect, risk score, ride quality.")
        lines.append("")
        lines.append(
            "Write exactly three short paragraphs separated by a blank line, matching these headings exactly:\n"
            "What we know from the available reports\n"
            "How pilots generally think about these conditions\n"
            "Uncertainty & normal variability\n"
            "Keep it passenger-friendly; avoid codes/jargon."
        )

        return "\n".join(lines)

    def generate(self, inp: BriefingInputs) -> str:
        base_prompt = self._build_prompt(inp)

        all_tried = []
        last_text = ""

        for attempt in range(self.max_banned_regens + 1):
            # On retry, add a short correction note (keeps it from repeating the same mistake)
            if attempt == 0:
                prompt = base_prompt
            else:
                prompt = (
                    base_prompt
                    + "\n\nREWRITE NOTE: The previous draft included banned promise/prediction language. "
                      "Rewrite while strictly avoiding: smooth/smoother, expect, predict, guarantee, "
                      "turbulence score, ride quality. Do not imply certainty."
                )

            text, tried = call_model_with_retries_for_briefing(
                self.client,
                prompt,
                primary_model=self.model,
                max_tokens=self.max_tokens,
            )
            all_tried.extend(tried)
            last_text = (text or "").strip()

            if not last_text:
                continue

            if self._contains_banned_claims(last_text):
                # try again (up to cap)
                continue

            return last_text

        # If we get here, everything was empty or kept violating banned language rules
        reason = (
            f"Briefing could not be generated without banned language after "
            f"{self.max_banned_regens + 1} attempts. Tried: {all_tried}"
        )
        if self.allow_fallback:
            return self._fallback(inp, reason)
        raise RuntimeError(reason)

    def interpret_metar(self, raw_metar: str, station: str | None = None) -> str:
        raw_metar = (raw_metar or "").strip()
        if not raw_metar:
            return ""

        key = f"METAR::{raw_metar}"
        if key in self._interpret_cache:
            return self._interpret_cache[key]

        station = (station or "").upper().strip()
        prompt_lines = []
        if station:
            prompt_lines.append(f"Station: {station}")
        prompt_lines.append("Type: METAR")
        prompt_lines.append(f"Raw: {raw_metar}")
        prompt_lines.append("")
        prompt_lines.append(
            "Explain in 2–4 short bullet points for a passenger. Cover: "
            "1) wind (direction/speed if present), 2) visibility and clouds/ceiling, "
            "3) precipitation/obstructions if present, "
            "4) a plain-language summary (good/okay/poor) without VFR/IFR jargon. "
            "Do NOT imply prediction beyond this report. Avoid acronyms; if you must use one, define it."
        )

        user_prompt = "\n".join(prompt_lines)

        text, _tried = call_model_with_retries_for_briefing(
            self.client,
            user_prompt=user_prompt,
            primary_model=self.model,
            max_tokens=min(self.max_tokens, 180),
            system_prompt=LAYMAN_SYSTEM_PROMPT,
        )

        out = (text or "").strip()
        self._interpret_cache[key] = out
        return out


    def interpret_pirep(self, raw_pirep: str, fl: str | int | None = None) -> str:
        raw_pirep = (raw_pirep or "").strip()
        if not raw_pirep:
            return ""

        key = f"PIREP::{raw_pirep}"
        if key in self._interpret_cache:
            return self._interpret_cache[key]

        prompt_lines = ["Type: PIREP"]
        if fl not in (None, ""):
            prompt_lines.append(f"Reported altitude: {fl}")
        prompt_lines.append(f"Raw: {raw_pirep}")
        prompt_lines.append("")
        prompt_lines.append(
            "Explain in 2–4 short bullet points for a passenger. "
            "State what the report says about bumps using the same intensity words in the report "
            "(e.g., light/moderate/severe) without adding certainty about where/when it will happen. "
            "If icing is mentioned, explain in general terms what that means operationally (without advice). "
            "Do not give operational advice. Do not exaggerate or reassure with guarantees."
        )

        user_prompt = "\n".join(prompt_lines)

        text, _tried = call_model_with_retries_for_briefing(
            self.client,
            user_prompt=user_prompt,
            primary_model=self.model,
            max_tokens=min(self.max_tokens, 180),
            system_prompt=LAYMAN_SYSTEM_PROMPT,
        )

        out = (text or "").strip()
        self._interpret_cache[key] = out
        return out


