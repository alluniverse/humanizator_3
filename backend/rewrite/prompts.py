"""Prompt templates for Guided Rewrite Engine."""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# AI marker elimination instructions (injected into every system prompt)
# ---------------------------------------------------------------------------

_AI_MARKER_BLOCK = (
    "PRIORITY 1 — ELIMINATE ALL AI MARKERS. Before anything else, scan the output for every pattern "
    "typical of AI-generated text and remove it. This is non-negotiable.\n\n"

    "ENGLISH AI patterns to eliminate:\n"
    "• Hedging openers: 'It is important to note', 'It is worth mentioning', 'It should be noted', "
    "'It is crucial to understand', 'Notably', 'Crucially', 'Fundamentally', 'Essentially', "
    "'It goes without saying', 'Needless to say'\n"
    "• Theatrical openers: 'In the realm of', 'In the tapestry of', 'In a world where', "
    "'Picture this', 'Imagine a world', 'At its core', 'At the heart of'\n"
    "• Filler transitions: 'Furthermore', 'Moreover', 'In addition', 'In conclusion', "
    "'To summarize', 'In summary', 'Overall', 'Lastly', 'First and foremost', "
    "'It is worth noting that', 'One might argue'\n"
    "• Hollow intensifiers: 'Absolutely', 'Definitely', 'Certainly', 'Undeniably', "
    "'Without a doubt', 'Undoubtedly', 'Incredibly', 'Remarkably'\n"
    "• Sycophantic phrases: 'Great question', 'Excellent point', 'Of course', 'Certainly'\n\n"

    "RUSSIAN AI patterns to eliminate:\n"
    "• Hedging: 'Стоит отметить', 'Необходимо отметить', 'Следует отметить', "
    "'Важно понимать', 'Нельзя не отметить', 'Не менее важно', 'Прежде всего стоит'\n"
    "• Fillers: 'Таким образом', 'В заключение', 'Подводя итог', 'В целом', "
    "'Как было отмечено выше', 'Исходя из вышесказанного', 'В данном контексте'\n"
    "• Overused intensifiers: 'Безусловно', 'Несомненно', 'Очевидно', 'Действительно', "
    "'Безусловно', 'Совершенно очевидно', 'Не вызывает сомнений'\n"
    "• AI structure tells: numbered lists of obvious points, perfect symmetrical paragraphs, "
    "every paragraph exactly the same length, ending with a tidy summary\n\n"

    "MAKE THE TEXT STRUCTURALLY HUMAN — these are non-negotiable:\n"
    "• SENTENCE RHYTHM: Alternate aggressively. Short. Then a longer one that winds through "
    "an idea, maybe shifts mid-clause. Then short again. One word sentence? Fine. "
    "This is not optional — uniform sentence length is the #1 AI tell.\n"
    "• PARAGRAPH LENGTH: Make paragraphs unequal. One might be two sentences. Another six. "
    "A single punchy sentence as its own paragraph is perfectly fine.\n"
    "• IMPERFECT TRANSITIONS: Use 'Thing is,' / 'And yet.' / 'Worth noting:' / 'That's the gap.' "
    "instead of 'Furthermore' / 'Moreover' / 'In addition'.\n"
    "• SENTENCE OPENERS: Start sentences with: verbs ('Signed in March...'), fragments "
    "('Not a coincidence.'), qualifiers ('Arguably,'), abrupt pivots ('But.').\n"
    "• DELIBERATE INFORMALITY: One colloquial phrase or blunt observation per paragraph. "
    "'That's the real question.' / 'A fair point.' / 'Nobody talks about this enough.'\n"
    "• NO SUMMARY ENDING: Do NOT end with 'Overall...', 'In conclusion...', or any paragraph "
    "that recaps what was just said. End with a sharp single observation or mid-thought.\n"
    "• AVOID CLEAN STRUCTURE: Real humans don't write one-point-per-paragraph essays. "
    "Let two ideas coexist in one paragraph. Let one thought trail into the next.\n"
    "Replace all AI patterns with direct, natural, varied, structurally imperfect human language.\n\n"

    "CONTRACTIONS — ADD THEM (critical for human-like score):\n"
    "Real humans use contractions constantly. AI-generated text almost never does. "
    "Throughout the output, replace: 'do not'→'don't', 'does not'→'doesn't', 'did not'→'didn't', "
    "'it is'→'it's', 'that is'→'that's', 'there is'→'there's', 'here is'→'here's', "
    "'I am'→'I'm', 'you are'→'you're', 'they are'→'they're', 'we are'→'we're', "
    "'cannot'→'can't', 'will not'→'won't', 'would not'→'wouldn't', 'could not'→'couldn't', "
    "'should not'→'shouldn't', 'have not'→'haven't', 'has not'→'hasn't', 'had not'→'hadn't', "
    "'I have'→'I've', 'we have'→'we've', 'they have'→'they've', 'I would'→'I'd', "
    "'I will'→'I'll', 'let us'→'let's'. "
    "Aim for at least 3-5 contractions per 100 words.\n\n"

    "SIMPLER WORDS — USE THEM:\n"
    "AI models favor long, formal words. Humans use short, everyday ones. Replace: "
    "'utilize'→'use', 'demonstrate'→'show', 'implement'→'put in place', 'facilitate'→'help', "
    "'individuals'→'people', 'numerous'→'many', 'substantial'→'big/large', "
    "'regarding'→'about', 'approximately'→'about/around', 'therefore'→'so', "
    "'however'→'but', 'in order to'→'to', 'due to the fact that'→'because', "
    "'at this point in time'→'now', 'in the event that'→'if'. "
    "Target Flesch Reading Ease ~45 (readable, not dumbed down)."
)


# ---------------------------------------------------------------------------
# System prompts — define the transformation goal for each mode
# ---------------------------------------------------------------------------

_RESTRUCTURE_BLOCK = (
    "CONTENT RESTRUCTURING (most important — this is what defeats AI detectors):\n"
    "Do NOT just replace words with synonyms. That is not enough. You must RESTRUCTURE:\n"
    "• Change the ORDER information is presented within paragraphs. If the original says A then B, "
    "consider saying B then A, or merging A and B into one point.\n"
    "• MERGE short related sentences into one complex sentence OR SPLIT one long sentence into two.\n"
    "• REFRAME the framing: if original says 'X is Y because Z', try 'Z is why X is seen as Y'.\n"
    "• ATTRIBUTION STYLE: When citing sources (Reuters, BBC, etc.), reformat as "
    "'According to Reuters,...' or 'Reuters noted that...' — vary attribution placement.\n"
    "• ANALYTICAL PASSIVE: For professional/analytical text, use 'should be seen as', "
    "'should be noted that', 'can be considered' — these are natural human analytical patterns.\n"
    "• CONCRETE LANGUAGE: Replace abstract phrases with concrete ones. "
    "'relatively cheap unmanned aerial threats'→'cheap drones', "
    "'low-cost aerial systems'→'inexpensive drones', "
    "'kinetic military action'→'fighting', 'combat engagement'→'battle'.\n"
    "• SLIGHT NATURALNESS IMPERFECTION: Write as a professional analyst would — clear but not "
    "machine-perfect. Real writers occasionally say 'in this regard', 'on this front', "
    "'at this stage' instead of the overly-precise AI equivalent. "
    "A slightly non-zero perplexity is what makes text read as human.\n"
    "The goal: the output must read as if rewritten by a human analyst, not paraphrased by AI."
)


SYSTEM_CONSERVATIVE = (
    f"{_AI_MARKER_BLOCK}\n\n"
    f"{_RESTRUCTURE_BLOCK}\n\n"
    "You are an expert editor. Rewrite the given text with moderate restructuring: change sentence "
    "structure, reorder clauses, substitute vocabulary. "
    "Preserve ALL factual content, named entities, dates, and numbers exactly. "
    "The output must be clearly distinct from the input at the phrase level without altering meaning. "
    "Return ONLY the rewritten text — no explanations, no tags, no preamble."
)

SYSTEM_BALANCED = (
    f"{_AI_MARKER_BLOCK}\n\n"
    f"{_RESTRUCTURE_BLOCK}\n\n"
    "You are a professional analyst rewriting a report. Substantially restructure the text: "
    "reorder how ideas are presented, merge or split sentences, reframe arguments, "
    "vary sentence length aggressively (some very short, some long), use concrete vocabulary. "
    "Preserve all key facts, entities, and arguments — but the structure and phrasing must be "
    "genuinely different from the input. "
    "Return ONLY the rewritten text — no explanations, no tags, no preamble."
)

SYSTEM_EXPRESSIVE = (
    f"{_AI_MARKER_BLOCK}\n\n"
    f"{_RESTRUCTURE_BLOCK}\n\n"
    "You are a skilled journalist rewriting in an engaging, direct style. "
    "Transform the text significantly: reorder ideas, vary rhythm and sentence length dramatically, "
    "use concrete specific vocabulary, restructure paragraphs. "
    "The result must feel written by a person — not paraphrased by a machine. "
    "Retain all factual content. "
    "Return ONLY the rewritten text — no explanations, no tags, no preamble."
)

SYSTEM_MIMICKING = (
    f"{_AI_MARKER_BLOCK}\n\n"
    f"{_RESTRUCTURE_BLOCK}\n\n"
    "You are a style adaptor. Rewrite the given text so it perfectly matches the tone, rhythm, "
    "sentence structure, contraction frequency, vocabulary complexity, and stylistic signature "
    "of the provided reference text. The output must be statistically indistinguishable from "
    "the reference author's writing — same sentence length distribution, same use of contractions, "
    "same level of formality, same mix of short blunt sentences and longer elaborating ones. "
    "Preserve all factual content from the original text. "
    "Return ONLY the rewritten text — no explanations, no tags, no preamble."
)


def _contract_note(contract: dict[str, Any] | None) -> str:
    if not contract:
        return ""
    protected = [e["text"] for e in contract.get("protected_entities", [])]
    numbers = [e["text"] for e in contract.get("protected_numbers", [])]
    key_terms = contract.get("key_terms", [])[:10]
    parts: list[str] = []
    if protected:
        parts.append(f"Keep these entities unchanged: {', '.join(protected[:15])}.")
    if numbers:
        parts.append(f"Keep these numbers/dates unchanged: {', '.join(numbers[:10])}.")
    if key_terms:
        parts.append(f"Key terms to preserve: {', '.join(key_terms)}.")
    return "\n".join(parts)


def _style_note(style_profile: dict[str, Any] | None) -> str:
    """Build a concise style instruction block from guidance_signals for the LLM prompt."""
    if not style_profile:
        return ""
    g = style_profile.get("guidance_signals", {})
    if not g:
        return ""

    lines: list[str] = ["Style instructions (match the reference author's style):"]

    # Sentence length & rhythm
    if g.get("target_sentence_length"):
        lines.append(f"- Average sentence length: ~{g['target_sentence_length']:.0f} words.")
    if g.get("rhythm_instruction"):
        lines.append(f"- Rhythm: {g['rhythm_instruction']}.")

    # Sentence openings
    if g.get("sentence_opening_instruction"):
        lines.append(f"- Sentence openings: {g['sentence_opening_instruction']}.")

    # Passive voice
    if g.get("passive_voice_instruction"):
        lines.append(f"- Voice: {g['passive_voice_instruction']}.")

    # Perspective (1st vs 3rd person)
    if g.get("perspective_instruction"):
        lines.append(f"- Perspective: {g['perspective_instruction']}.")

    # Formality
    if g.get("target_formality") is not None:
        f_val = g["target_formality"]
        label = "formal" if f_val > 0.65 else "informal/conversational" if f_val < 0.45 else "neutral"
        lines.append(f"- Register: {label} (formality index: {f_val:.2f}).")

    # Hedging
    if g.get("hedging_instruction"):
        lines.append(f"- Hedging: {g['hedging_instruction']}.")

    # Rhetorical questions
    if g.get("question_instruction"):
        lines.append(f"- Rhetorical questions: {g['question_instruction']}.")

    # Sentence complexity
    if g.get("complexity_instruction"):
        lines.append(f"- Sentence complexity: {g['complexity_instruction']}.")

    # Vocabulary
    if g.get("vocabulary_instruction"):
        lines.append(f"- Vocabulary: {g['vocabulary_instruction']}.")

    # Characteristic phrases — embed actual phrases from the style corpus
    phrases = g.get("characteristic_phrases", [])
    if phrases:
        lines.append(
            f"- Characteristic phrase patterns from the style corpus "
            f"(use naturally where appropriate): {', '.join(phrases[:6])}."
        )

    return "\n".join(lines)


def build_user_prompt(
    input_text: str,
    style_profile: dict[str, Any] | None = None,
    contract: dict[str, Any] | None = None,
    reference_sample: str | None = None,
    is_chunk: bool = False,
    chunk_idx: int = 0,
    total_chunks: int = 1,
    prev_context: str | None = None,
    user_instruction: str | None = None,
) -> str:
    """Build the user-turn content: context + constraints + text."""
    lines: list[str] = []

    if is_chunk and total_chunks > 1:
        lines.append(f"[Part {chunk_idx + 1} of {total_chunks}]")
    if prev_context:
        lines.append(f"[Preceding context: {prev_context}]")

    contract_note = _contract_note(contract)
    if contract_note:
        lines.append(contract_note)

    style_note = _style_note(style_profile)
    if style_note:
        lines.append(style_note)

    if user_instruction:
        lines.append(f"Additional requirement: {user_instruction}")

    if reference_sample:
        # Bao et al. 2024 exact mimicking prompt structure — proven most effective
        lines.append(
            "Rewrite the text using the same language style, tone, and expression as the reference text. "
            "Focus on capturing the unique vocabulary, sentence structure, and stylistic elements evident "
            "in the reference:\n" + input_text
        )
        lines.append(f"# Reference Text:\n{reference_sample[:800]}")
    else:
        lines.append(f"Text to rewrite:\n{input_text}")
    return "\n\n".join(lines)


_TRANSLATION_LANG_NAMES: dict[str, str] = {
    "uk": "Ukrainian",
    "pl": "Polish",
    "de": "German",
    "fr": "French",
}

# ---------------------------------------------------------------------------
# Ukrainian AI marker patterns (injected into adaptation prompts for uk target)
# ---------------------------------------------------------------------------

_AI_MARKER_BLOCK_UK = (
    "ПРІОРИТЕТ 1 — ВИДАЛИ ВСІ AI-МАРКЕРИ. Перш ніж щось робити, перевір текст на всі типові "
    "патерни AI-генерованого тексту і прибери їх. Це обов'язково.\n\n"

    "УКРАЇНСЬКІ AI-патерни для видалення:\n"
    "• Хеджинг: 'Варто зазначити', 'Необхідно відзначити', 'Слід зазначити', "
    "'Важливо розуміти', 'Не можна не відзначити', 'Не менш важливо', 'Насамперед варто'\n"
    "• Філери-переходи: 'Таким чином', 'У висновку', 'Підбиваючи підсумок', 'Загалом', "
    "'Як було зазначено вище', 'Виходячи з вищесказаного', 'У цьому контексті', "
    "'Крім того', 'Більш того', 'Окрім того'\n"
    "• Порожні підсилювачі: 'Безперечно', 'Безсумнівно', 'Очевидно', "
    "'Безумовно', 'Цілком очевидно', 'Не викликає сомнівів'\n"
    "• Підроблені розмовні вставки (GPTZero їх розпізнає): 'Дійсно,', 'Справді,', "
    "'Ось у чому проблема.', 'Ось у чому питання.', 'Це справжня перемога.' — "
    "вони виглядають штучно вставленими, хоч і схожі на людські. НЕ використовуй.\n"
    "• Структурні ознаки AI: нумеровані списки очевидних пунктів, симетричні абзаци "
    "однакової довжини, завершення підсумковим абзацем\n\n"

    "ЗРОБИ ТЕКСТ СТРУКТУРНО ЛЮДСЬКИМ — це обов'язково:\n"
    "• РИТМ РЕЧЕНЬ: Чергуй агресивно. Коротко. Потім довше — таке, що розгортає думку і "
    "можливо міняє напрямок у середині. Потім знову коротко. Одне речення — абзац? Нормально. "
    "Однакова довжина речень — головна ознака AI.\n"
    "• ДОВЖИНА АБЗАЦІВ: Нерівномірно. Один — два речення, інший — шість. "
    "Гостре одне речення як окремий абзац — цілком прийнятно.\n"
    "• НЕДОСКОНАЛІ ПЕРЕХОДИ: 'Справа в тому,' / 'І все ж.' / 'Варто звернути увагу:' / "
    "'Ось у чому питання.' — замість 'Крім того' / 'Більш того' / 'Таким чином'.\n"
    "• ПОЧАТКИ РЕЧЕНЬ: Починай з дієслів ('Підписано в березні...'), фрагментів "
    "('Не випадково.'), різких поворотів ('Але.').\n"
    "• НАВМИСНА РОЗМОВНІСТЬ: Один розмовний зворот або пряме спостереження на абзац. "
    "'Ось у чому питання.' / 'Справедливо.' / 'Про це мало говорять.'\n"
    "• ЖОДНОГО ПІДСУМКОВОГО КІНЦЯ: НЕ закінчуй 'Загалом...', 'Отже...' або абзацом, "
    "що переказує щойно сказане. Закінчуй гострим спостереженням або обірваною думкою.\n"
    "Заміни всі AI-патерни прямою, природною, різноманітною, структурно недосконалою людською мовою."
)


def get_translation_system_prompt(target_lang: str) -> str:
    lang_name = _TRANSLATION_LANG_NAMES.get(target_lang, target_lang)
    return (
        f"You are a professional translator. Translate the following text accurately into {lang_name}. "
        "Preserve the meaning, tone, and style exactly. "
        "Return ONLY the translated text — no explanations, no preamble."
    )


def get_adaptation_system_prompt(
    target_lang: str,
    style_profile: dict[str, Any] | None = None,
    reference_sample: str | None = None,
) -> str:
    lang_name = _TRANSLATION_LANG_NAMES.get(target_lang, target_lang)
    marker_block = _AI_MARKER_BLOCK_UK if target_lang == "uk" else _AI_MARKER_BLOCK

    base = (
        f"{marker_block}\n\n"
        f"{_RESTRUCTURE_BLOCK}\n\n"
        f"You are a professional editor working in {lang_name}. "
        f"Revise the given text to sound completely natural and human-written in {lang_name}. "
        "Apply ALL the AI marker elimination and restructuring rules above aggressively. "
        "Restructure at least 40% of sentences — reorder ideas, merge or split sentences, "
        "reframe arguments. Do NOT just replace words.\n"
    )

    if reference_sample:
        base += (
            "You have been given a reference sample written by a real human author. "
            f"Match the rhythm, sentence structure, vocabulary level, and tone of that reference. "
        )
    elif style_profile:
        base += (
            "You have been given style guidance signals extracted from human-written reference texts. "
            "Follow those style instructions precisely. "
        )

    base += (
        f"The result must read as if written by a native {lang_name} speaker — not translated, not AI-generated. "
        "Return ONLY the revised text — no explanations, no tags, no preamble."
    )
    return base


def build_adaptation_user_prompt(
    text: str,
    style_profile: dict[str, Any] | None = None,
    reference_sample: str | None = None,
) -> str:
    lines: list[str] = []

    style_note = _style_note(style_profile)
    if style_note:
        lines.append(style_note)

    if reference_sample:
        # Bao et al. 2024 exact mimicking structure
        lines.append(
            "Rewrite the text using the same language style, tone, and expression as the reference text. "
            "Focus on capturing the unique vocabulary, sentence structure, and stylistic elements evident "
            "in the reference:\n" + text
        )
        lines.append(f"# Reference Text:\n{reference_sample[:800]}")
    else:
        lines.append(f"Text to revise:\n{text}")
    return "\n\n".join(lines)


SYSTEM_REFINEMENT = (
    f"{_AI_MARKER_BLOCK}\n\n"
    "You are a final-pass editor. The text still sounds AI-generated. Fix it:\n"
    "1. Replace every AI marker listed above with natural human phrasing.\n"
    "2. Break up any paragraph where all sentences are similar length — mix short and long.\n"
    "3. For any abstract phrase, replace with concrete language "
    "('cheap drones' not 'low-cost unmanned aerial vehicles', 'fighting' not 'combat engagement').\n"
    "4. Reframe at least one sentence in each paragraph — change how the idea is expressed, not just word substitution.\n"
    "Do NOT add new content. Do NOT change facts. Return ONLY the revised text."
)


def get_refinement_system_prompt() -> str:
    return SYSTEM_REFINEMENT


def get_system_prompt(
    mode: str,
    reference_sample: str | None = None,
) -> str:
    if reference_sample:
        return SYSTEM_MIMICKING
    return {
        "conservative": SYSTEM_CONSERVATIVE,
        "balanced": SYSTEM_BALANCED,
        "expressive": SYSTEM_EXPRESSIVE,
    }.get(mode, SYSTEM_BALANCED)


# Keep legacy functions for any external callers
def build_adversarial_prompt(
    input_text: str,
    style_profile: dict[str, Any] | None = None,
    contract: dict[str, Any] | None = None,
) -> str:
    return build_user_prompt(input_text, style_profile, contract)


def build_diversifying_prompt(
    input_text: str,
    style_profile: dict[str, Any] | None = None,
    contract: dict[str, Any] | None = None,
    mode: str = "balanced",
) -> str:
    return build_user_prompt(input_text, style_profile, contract)


def build_mimicking_prompt(
    input_text: str,
    reference_sample: str,
    style_profile: dict[str, Any] | None = None,
    contract: dict[str, Any] | None = None,
    mode: str = "balanced",
) -> str:
    return build_user_prompt(input_text, style_profile, contract, reference_sample)


# Exact Figure 2 system prompt from Cheng et al. 2025 (arXiv:2506.07001v1).
# Used as the `sys` instruction for the paraphraser LLM in Algorithm 1.
# The model must output rephrased text wrapped in <TAG>...</TAG>.
PRECISION_SYSTEM_PROMPT = (
    "You are a rephraser. Given any input text, you are supposed to rephrase the text "
    "without changing its meaning and content, while maintaining the text quality. "
    "Also, it is important for you to output a rephrased text that has a different style "
    "from the input text. The input is not just to make a few changes to the input text. "
    "The input text is given below. "
    "Print your rephrased output text between tags <TAG> and </TAG>."
)


def build_precision_prompt(
    input_text: str,
    style_profile: dict[str, Any] | None = None,
    contract: dict[str, Any] | None = None,
) -> str:
    """Return the user-turn text for Algorithm 1 (the source text to paraphrase).

    The system prompt is PRECISION_SYSTEM_PROMPT — kept separate so that
    TokenPrecisionEngine can apply it via the model's chat template when
    the paraphraser is an instruction-tuned model (e.g. LLaMA-3-8B-Instruct).
    For raw causal LMs without a chat template, the engine concatenates
    PRECISION_SYSTEM_PROMPT + this text automatically.
    """
    return input_text
