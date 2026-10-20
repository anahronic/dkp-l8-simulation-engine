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
    r"prevention|transport|synergy|exit\b|time\b|api\b|ayalon|айялон|конвертер|converter", re.I)
EXECUTABLE = re.compile(
    r"```|~~~|(?:^|\n)\s{4,}\S|"
    r"\b(?:print|eval|exec|system|subprocess\.run)\s*\(|"
    r"(?:^|[\n;])\s*(?:import \w|from \w+ import|def \w+\(|class \w+[:(]|"
    r"(?:const|let|var) \w+\s*=|SELECT .+ FROM |INSERT INTO |function \w*\(|"
    r"(?:sudo|ssh|bash|sh|curl|wget|pip|npm|systemctl|rm|chmod|chown|cat|echo|ls)\s+\S|whoami\b)|"
    r"`\s*(?:sudo|ssh|bash|curl|wget|systemctl|rm|ls|cat|python|whoami)\b|"
    r"(?:here is|вот).{0,25}(?:my system prompt|мой системный промпт)|"
    r"(?:run|execute|выполните|запустите).{0,30}(?:command|команд|`)", re.I)


def request_reason(question):
    text = normalized(question)
    if ATTACK.search(text):
        return "role_attack"
    if CODE_REQUEST.search(text) and not ROLE_QUESTION.search(text):
        return "code_request"
    if OFF_TOPIC.search(text):
        return "off_topic"
    if not TOPIC.search(text):
        return "off_topic"
    return None


def output_reason(text):
    if EXECUTABLE.search(text) or ATTACK.search(normalized(text)):
        return "unsafe_model_output"
    if OFF_TOPIC.search(text):
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
    return spans


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
