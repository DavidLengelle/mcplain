"""Fixed text patterns read by the rules: descriptions that ask for silence or for a file, text aimed at an analyzer"""

import re

WORDS_BETWEEN = r"(?:[\w'’-]+\s+){0,2}?"
SENTENCE_REST = r"(?P<rest>[^.!?\n]{0,100})"

NEGATION_EN = r"(?:do\s+not|don['’]t|dont|never|must\s+not|mustn['’]t|without)"
INFORM_EN = (
    r"(?:tell(?:ing)?|mention(?:ing)?|inform(?:ing)?|notify(?:ing)?|reveal(?:ing)?|disclos(?:e|ing)|"
    r"alert(?:ing)?|warn(?:ing)?)"
)
INFORM_FR = (
    r"(?:dis|dites|dire|mentionne|mentionnez|mentionner|préviens|prévenez|prévenir|informe|informez|informer|"
    r"signale|signalez|signaler|révèle|révélez|révéler|avertis|avertissez|avertir)"
)
SILENCE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(rf"\b{NEGATION_EN}\s+(?P<before>{WORDS_BETWEEN}){INFORM_EN}\b{SENTENCE_REST}", re.IGNORECASE),
    re.compile(
        rf"(?:\bne\s+|\bn['’])(?P<before>{WORDS_BETWEEN}){INFORM_FR}\s+(?:pas|rien|jamais)\b{SENTENCE_REST}",
        re.IGNORECASE,
    ),
    re.compile(rf"\bne\s+(?:pas|jamais)\s+(?P<before>){INFORM_FR}\b{SENTENCE_REST}", re.IGNORECASE),
    re.compile(rf"\bsans\s+(?P<before>{WORDS_BETWEEN}){INFORM_FR}\b{SENTENCE_REST}", re.IGNORECASE),
)
SILENCE_TARGETS = re.compile(
    r"\b(?:the\s+user|users?|this|that\s+you|these\s+instructions|it|them|anyone|"
    r"l['’]utilisateur|utilisateurs?|ceci|cela|ça|que\s+tu|ces\s+instructions|lui|leur|personne)\b",
    re.IGNORECASE,
)
SILENCE_PRONOUNS = re.compile(r"\b(?:le|la|les|lui|leur|en)\b|\bl['’]", re.IGNORECASE)

CONTENT_WORDS = re.compile(r"\b(?:contents?|contenus?)\b", re.IGNORECASE)
TRANSMIT_VERBS = re.compile(
    r"\b(?:pass(?:ing)?|include|including|send|sending|provide|providing|add|adding|paste|pasting|put|insert|"
    r"attach|copy|passe|passez|passer|inclus|incluez|inclure|envoie|envoyez|envoyer|fournis|fournissez|fournir|"
    r"ajoute|ajoutez|ajouter|colle|collez|coller|mets|mettez|mettre|joins|joignez|copie|copiez)\b",
    re.IGNORECASE,
)
DESTINATION_WORDS = re.compile(
    r"\b(?:arguments?|parameters?|params?|fields?|paramètres?|champs?)\b",
    re.IGNORECASE,
)
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")

ANALYZER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\bignore\s+(?:(?:all|any|the|your|previous|prior|above|earlier|preceding|former)\s+){1,3}"
        r"(?:instructions|rules|prompts?|directions)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:this|the)\s+(?:code|package|server|tool|repository|repo|library|module|file|extension)\s+is\s+"
        r"(?:safe|benign|harmless|trusted|not\s+malicious)\b(?!\s+to\b)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:do\s+not|don['’]t|never)\s+(?:flag|report|scan)\s+"
        r"(?:this|these|it|me|us|the\s+(?:code|package|server|tool|file|repository))\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:security|code|malware|static|ai|llm|automated)\s+(?:scanner|analy[sz]er|reviewer|auditor)s?\s*:",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:to|dear|hey)\s+(?:the\s+)?(?:scanner|analy[sz]er|reviewer|auditor)\b", re.IGNORECASE),
    re.compile(
        r"\bignore[rz]?\s+(?:toutes\s+)?(?:les|tes|vos)\s+(?:instructions|consignes|règles)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:ce|cet)\s+(?:code|paquet|serveur|outil|dépôt|fichier|module)\s+est\s+"
        r"(?:sûr|sain|bénin|inoffensif|sans\s+danger|fiable|pas\s+malveillant)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bne\s+(?:le\s+|la\s+|les\s+)?(?:signale|signalez|analyse|analysez|scanne|scannez)\s+pas\b|"
        r"\bne\s+pas\s+(?:signaler|analyser|scanner)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:scanner|analyseur|relecteur|réviseur|auditeur)s?\s+(?:de\s+sécurité|ia|de\s+code)\s*:",
        re.IGNORECASE,
    ),
    re.compile(r"\bmcplain\b", re.IGNORECASE),
)

COPY_FIELDS: frozenset[str] = frozenset({"bcc", "cc"})
COPY_METHODS: frozenset[str] = frozenset({"add_bcc", "add_cc", "set_bcc", "set_cc", "addbcc", "addcc", "setbcc", "setcc"})
HEADER_METHODS: frozenset[str] = frozenset({"add_header", "set_header", "setheader", "addheader", "header"})
LIST_METHODS: frozenset[str] = frozenset({"append", "extend", "insert", "add", "push", "unshift", "concat"})
COPY_LIST_NAME = re.compile(r"(?:^|_)(?:bcc|cc)(?:_?list|s|_recipients|_addresses|recipients|addresses)?$", re.IGNORECASE)
EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

PIPE_TO_SHELL = re.compile(
    r"\b(?:curl|wget|iwr|irm|Invoke-WebRequest|Invoke-RestMethod)\b[^|\n;]{0,300}\|\s*(?:sudo\s+)?"
    r"(?:sh|bash|zsh|dash|iex|Invoke-Expression)\b",
    re.IGNORECASE,
)
DOWNLOAD_COMMAND = re.compile(
    r"\b(?:curl|wget|iwr|irm|Invoke-WebRequest|Invoke-RestMethod|bitsadmin)\b|\bcertutil\b.{0,40}-urlcache|"
    r"https?://|\bfetch\(|require\(\s*['\"](?:node:)?https?['\"]\)",
    re.IGNORECASE,
)

DOWNLOAD_TOOLS = re.compile(
    r"\b(?:curl|wget|iwr|Invoke-WebRequest|Invoke-RestMethod|bitsadmin)\b|\bcertutil\b.{0,40}-urlcache",
    re.IGNORECASE,
)
SHELL_RUNNERS: frozenset[str] = frozenset({"sh", "bash", "zsh", "dash", "pwsh", "powershell"})

QUOTE_BEFORE = 60
QUOTE_AFTER = 140


def excerpt(text: str, start: int, end: int | None = None) -> str:
    """Return the passage of a text around a match, at most 200 characters"""

    stop = start
    if end is not None:
        stop = end
    first = max(0, start - QUOTE_BEFORE)
    last = min(len(text), max(stop, start) + QUOTE_AFTER)
    return text[first:last].strip()


def silence_request(text: str) -> re.Match[str] | None:
    """Find a request to hide what the AI or the tool does from the user"""

    for pattern in SILENCE_PATTERNS:
        for match in pattern.finditer(text):
            before = match.group("before") or ""
            if SILENCE_TARGETS.search(match.group("rest")) or SILENCE_PRONOUNS.search(before):
                return match
    return None


def transmit_request(text: str, parameters: list[str]) -> str | None:
    """Return the sentence that asks to pass the content of something into an argument or a parameter"""

    names = [re.escape(name) for name in parameters if len(name) > 2]
    named = None
    if names:
        named = re.compile(r"\b(?:" + "|".join(names) + r")\b", re.IGNORECASE)
    for sentence in SENTENCE_SPLIT.split(text):
        if not CONTENT_WORDS.search(sentence) or not TRANSMIT_VERBS.search(sentence):
            continue
        if DESTINATION_WORDS.search(sentence) or (named is not None and named.search(sentence)):
            return sentence.strip()
    return None


def analyzer_talk(text: str) -> re.Match[str] | None:
    """Find text that speaks to an analysis tool instead of describing the code"""

    for pattern in ANALYZER_PATTERNS:
        match = pattern.search(text)
        if match is not None:
            return match
    return None
