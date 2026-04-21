"""Multilingual chain (grammatical shatter) for AI-pattern destruction.

EN → ZH → EN round-trip via Google Translate.

Chinese has fundamentally different grammar: no articles, no verb conjugation,
SOV-adjacent word order, topic-comment structure. The round-trip forces
syntactic restructuring that breaks the token-probability patterns that
GPTZero and similar detectors look for in GPT-4o output.

For longer texts the chain runs paragraph-by-paragraph to avoid
Google Translate's soft length limits (~5000 chars per request).
"""

from __future__ import annotations

import asyncio
import logging
import re
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# Thread pool for blocking deep_translator calls
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="translate")

# Intermediate languages — ordered by how much they restructure English syntax.
# ZH is the primary choice: tonal, no inflection, completely different clause structure.
# JA is the backup: SOV order, postpositional, agglutinative.
CHAIN_ZH = ["zh-CN", "en"]         # EN→ZH→EN
CHAIN_JA = ["ja", "en"]            # EN→JA→EN
CHAIN_ZH_JA = ["zh-CN", "ja", "en"]  # EN→ZH→JA→EN  (default — most aggressive)


def _translate_sync(text: str, source: str, target: str) -> str:
    """Blocking translate call — runs in thread pool."""
    from deep_translator import GoogleTranslator
    # Google Translate has a ~5000 char soft limit per call
    translator = GoogleTranslator(source=source, target=target)
    return translator.translate(text) or text


async def _translate(text: str, source: str, target: str) -> str:
    """Async wrapper around blocking GoogleTranslator."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _executor, _translate_sync, text, source, target
    )


def _split_paragraphs(text: str) -> list[str]:
    return [p for p in re.split(r"\n{2,}", text) if p.strip()]


def _rejoin(paragraphs: list[str]) -> str:
    return "\n\n".join(p.strip() for p in paragraphs if p.strip())


async def apply_chain(text: str, chain: list[str] = CHAIN_ZH, source_lang: str = "en") -> str:
    """Apply multilingual chain to text paragraph-by-paragraph.

    chain: list of target languages in order, e.g. ["zh-CN", "ja", "en"]
    source_lang: language of the input text (default "en")

    Splits into paragraphs to stay within Google Translate limits (~5000 chars),
    runs all paragraphs concurrently, then reassembles.
    """
    paragraphs = _split_paragraphs(text)
    if not paragraphs:
        return text

    async def _run_paragraph(p: str) -> str:
        current_lang = source_lang
        current_text = p
        for target_lang in chain:
            try:
                current_text = await _translate(current_text, current_lang, target_lang)
                current_lang = target_lang
            except Exception as exc:
                logger.warning("translate %s→%s failed: %s", current_lang, target_lang, exc)
        return current_text

    tasks = [_run_paragraph(p) for p in paragraphs]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    output: list[str] = []
    for original, result in zip(paragraphs, results):
        if isinstance(result, Exception):
            logger.warning("Chain failed for paragraph: %s — using original", result)
            output.append(original)
        else:
            output.append(result)

    return _rejoin(output)
