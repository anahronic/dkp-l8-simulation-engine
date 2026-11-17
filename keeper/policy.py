"""Deterministic role boundary. Retrieval/context never grants permissions.

This conservative bilingual gate is not a universal semantic classifier. Runtime
has no executor or write tool, independently of this text classification.
"""
import json
import re
import unicodedata

REFUSAL = ("Я Хранитель протоколов Дикенократии. Я отвечаю на вопросы о Дикенократии и помогаю "
           "разобраться в её вычислительной лаборатории. Написание программ и посторонние поручения "
           "в мои задачи не входят.")


def normalized(text):
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


ATTACK = re.compile(
    r"ignore.{0,40}(?:rules|instructions|previous)|игнорир.{0,40}(?:правил|инструкц)|"
    r"(?:forget|disregard).{0,40}(?:rules|instructions)|забудь.{0,40}(?:правил|инструкц)|"
    r"(?:you are now|i am now|act as|pretend to be|ты теперь|я теперь|смени роль|я администратор)|"
    r"(?:reveal|print|show|disclose|read|return|покажи|выдай|раскрой|прочитай|верни).{0,60}"
    r"(?:secret|password|system prompt|private key|парол|секрет|системн.{0,12}(?:инструкц|промпт)|ключ)|"
    r"(?:update|modify|replace|измени|перепиши|удали|добавь).{0,45}"
    r"(?:knowledge|corpus|protocol|site|file|баз.{0,8}знан|корпус|протокол|сайт|файл)|"
    r"(?:run_shell|/etc/passwd|sudo\b|ssh\b|powershell|cmd\.exe)|"
    r"(?:execute|run|выполни|запусти).{0,35}(?:command|shell|bash|python|команд|скрипт)|"
    r"(?:system|assistant)\s*:.*(?:instruction|ignore|obey)|"
    r"(?:follow|obey).{0,25}(?:these|new).{0,15}instructions", re.I)
CODE_REQUEST = re.compile(
    r"(?:write|generate|implement|create|give|produce|provide|напиши|написать|создай|сгенерируй|реализуй|дай)"
    r".{0,100}(?:\bcode\b|python|sql|javascript|script|program|код|программ|скрипт)|"
    r"(?:python|sql|javascript|код|программ).{0,60}(?:напиши|write|generate)", re.I)
ROLE_QUESTION = re.compile(r"^(?:why|почему).{0,45}(?:keeper|хранител).{0,65}(?:code|код|программ)", re.I)
OFF_TOPIC = re.compile(r"анекдот|joke|рецепт|recipe|write.{0,20}poem|напиши.{0,20}стих|"
                       r"weather|погод|football|футбол|horoscope|гороскоп|"
                       r"(?:plan|book).{0,30}(?:holiday|hotel|flight)|"
                       r"(?:спланируй|забронируй).{0,30}(?:отпуск|отел|билет)", re.I)
TOPIC = re.compile(
    r"dikenoc|дикенократ|dkp|хранител|keeper|протокол|protocol|лаборатор|lab\b|"
    r"\b[QF]-\d{3,}\b|unknown|pass|fail|s-lab|dti|work[_ -]cycle|"
    r"восстановл|рабоч.{0,8}цикл|кризис|crisis|recovery|roster|"
    r"график|круглосуточ|staff|workers?|работник|сотрудник|"
    r"метеорит|meteor|катастроф|catastrophe|сайт|website|glossary|кодекс|словар|"
    r"prevention|transport|synergy|exit\b|time\b|api\b|конвертер|converter|דיקנוקרט|"
    # the remaining registered protocol names (website/build_release.py REGISTRY), added 2026-11-17
    r"oracle|оракул|axiom|аксиом|identity|impact|justice|справедлив|assets?\b|financ|labou?r\b|antiterror|"
    r"defen[cs]e|police|upgrade|culture|habitat|integration|resilience|ai[- ]subject|privacy|scope\b|"
    r"transparen|audit|interop|epistemic|эпистем", re.I)
EXECUTABLE = re.compile(
    # an indented line counts only when it looks like code (nested Markdown lists are ordinary prose)
    # a fence counts as code only with a language tag; untagged fences are judged by their content below
    r"(?:```|~~~)\s*(?:python|py|javascript|js|typescript|ts|sql|bash|sh|shell|zsh|powershell|ps1|cmd|c|cpp|c\+\+|java|"
    r"go|rust|ruby|php|perl|lua|kotlin|swift|r|json|yaml|html|css)\b|"
    r"(?:^|\n)\s*(?:def \w+\(|class \w+[:(]|#include\b|function\s*\w*\s*\(|public static\b|\w+\s*\([^)]*\)\s*\{)|"
    r"(?:^|\n)\s{4,}(?:def |class |import |from \w+ import|return\b|for \w+ in |while |\w+\s*=\s*[\w\[{(\"'])|"
    r"\b(?:print|eval|exec|system|subprocess\.run)\s*\(|"
    r"(?:^|[\n;])\s*(?:import \w|from \w+ import|def \w+\(|class \w+[:(]|"
    r"(?:const|let|var) \w+\s*=|SELECT .+ FROM |INSERT INTO |function \w*\(|"
    r"(?:sudo|ssh|bash|sh|curl|wget|pip|npm|systemctl|rm|chmod|chown|cat|echo|ls)\s+(?:-\w|/|~|\$|\w+\.\w+|https?:)|whoami\b)|"
    r"`\s*(?:sudo|ssh|bash|curl|wget|systemctl|rm|ls|cat|python|whoami)\b|"
    r"(?:here is|вот).{0,25}(?:my system prompt|мой системный промпт)|"
    r"\b(?:run|execute|выполните|запустите)\b.{0,30}(?:\bcommand|команд)", re.I)   # backticked terms are prose


# Output side: signs that the model followed an injected instruction or disclosed what it must not.  The visitor-side
# ATTACK verbs are ordinary prose in an answer ("покажите в заключении", "удалите записи из файла", "propose_run для
# запуска … команда") and refused ordinary answers live on 2026-10-20; the answer has no tool that could change anything.
OUTPUT_ATTACK = re.compile(
    r"ignore (?:all |the )?(?:previous|prior|above) (?:instructions|rules)|"
    r"игнорируй(?:те)? (?:все )?(?:предыдущие|прежние) (?:инструкции|правила)|"
    r"\b(?:i am now|you are now)\b|\bя теперь (?:администратор|админ|root|разработчик)|"
    r"\b(?:my|мой|мои) (?:system prompt|системн\w* (?:промпт|инструкци))|"
    r"-----begin [a-z ]*private key|\bssh-(?:rsa|ed25519)\b|\bsk-[a-z0-9_-]{16,}|"
    r"run_shell|/etc/(?:passwd|shadow)|\bsudo\b|cmd\.exe|(?:password|пароль)\s*[:=]")


def request_reason(question):
    text = normalized(question)
    if ATTACK.search(text):
        return "role_attack"
    if CODE_REQUEST.search(text) and not ROLE_QUESTION.search(text):
        return "code_request"
    if OFF_TOPIC.search(text):
        return "off_topic"
    # A question without a listed topic word is not refused here (live 2026-11-17: "Explain the Justice Function",
    # "Что такое ORACLE?" and every Hebrew question were refused). Unrelated questions still end as no_sources in
    # the gateway when retrieval is weak as well; on_topic() is that routing signal.
    return None


SCRIPT_LANGS = (("he", re.compile("[\u0590-\u05FF]")), ("ar", re.compile("[\u0600-\u06FF\u0750-\u077F]")),
                ("zh", re.compile("[\u3400-\u9FFF]")))
UPPER_ID = re.compile(r"\b[A-Z0-9][A-Z0-9§.-]+\b")          # DKP-0-ORACLE-001, ORACLE, F-001, DTI: identifiers, not language


def answer_language(question, lang):
    """The language of the answer follows the question's script; the widget sends the page language (2026-11-17:
    every page is English, so Russian and Hebrew questions were answered in English or refused). A Latin-script
    question keeps the page language."""
    for code, pattern in SCRIPT_LANGS:
        if pattern.search(question):
            return code
    text = UPPER_ID.sub(" ", question)
    if len(re.findall("[\u0400-\u04FF]", text)) > len(re.findall("[A-Za-z]", text)):
        return "ru"
    return lang


def shingles(text, n=48):
    """Normalized n-character windows (step 8) of the system instructions, for instruction_echo()."""
    t = normalized(text)
    return {t[i:i + n] for i in range(0, max(0, len(t) - n + 1), 8)}


def instruction_echo(answer, instruction_shingles, n=48):
    """True when the answer reproduces a passage of the system instructions (any n-character window)."""
    t = normalized(answer)
    return any(t[i:i + n] in instruction_shingles for i in range(0, max(0, len(t) - n + 1)))


def on_topic(question):
    """The question names Dikenocracy, the Keeper, the lab or a listed protocol term."""
    return bool(TOPIC.search(normalized(question)))


# Letters the BM25 tokenizer cannot read (it reads Latin and Cyrillic only): Hebrew, Arabic, kana, CJK, Hangul.
FOREIGN_SCRIPT = re.compile("[֐-׿؀-ۿݐ-ݿ぀-ヿ㐀-鿿가-힯]")


def output_reason(text, context=""):
    """context = the question and the fragments the model was given."""
    if EXECUTABLE.search(text) or OUTPUT_ATTACK.search(normalized(text)):
        return "unsafe_model_output"
    # an off-topic word that the question or the sources themselves contain is on topic ("погодные условия" in CRISIS)
    known = normalized(context)
    if any(normalized(m.group(0)) not in known for m in OFF_TOPIC.finditer(text)):
        return "off_topic"
    return None


def hostile_source(text):
    return bool(ATTACK.search(normalized(text)))


def private_spans(fragments):
    """Long overlapping spans catch copied translation passages, not common words."""
    spans = set()
    for fragment in fragments:
        text = normalized(fragment.get("search_ru", ""))
        if not text:
            continue
        spans.add(text)
        if len(text) >= 80:
            spans.update(text[i:i + 80] for i in range(0, len(text) - 79, 40))
    # Private = in the translation AND in no public fragment: English left untranslated and passages the published
    # canon itself contains are public, not private translation.
    spans = {s for s in spans if sum("а" <= ch <= "я" or ch == "ё" for ch in s) >= 20}
    public = " ".join(normalized(f.get("text", "")) for f in fragments)
    return {s for s in spans if s not in public}


def contains_private(value, spans):
    text = normalized(json.dumps(value, ensure_ascii=False))
    return any(s in text for s in spans) or any(s in text for s in
           ("search_ru", "private_do_not_publish", "ru-sources"))


def refuse(result, reason):
    result.update(state="refused", reason=reason, answer_kind="role_refusal",
                  answer=REFUSAL, citations=[], found_sources=[], notices=[],
                  proposal=None, flags=[])
    result.pop("missing", None)
    result.pop("summary", None)
    result["provenance"]["retrieved"] = []
