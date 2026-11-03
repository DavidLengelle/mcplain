"""Fixed text patterns read by the rules: descriptions that ask for silence or for a file, text aimed at an analyzer"""

import re

WORDS_BETWEEN = r"(?:[\w'’-]+\s+){0,2}?"
SENTENCE_REST = r"(?P<rest>[^.!?\n]{0,100})"

NEGATION_EN = r"(?:do\s+not|don['’]t|dont|never|must\s+not|mustn['’]t|without)"
INFORM_EN = (
    r"(?:tell(?:ing)?|mention(?:ing)?|inform(?:ing)?|notify(?:ing)?|reveal(?:ing)?|disclos(?:e|ing)|"
    r"alert(?:ing)?|warn(?:ing)?|report(?:ing)?)"
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
    r"\b(?:the\s+user|users?|this|that\s+you|these|those|it|them|anyone|"
    r"l['’]utilisateur|utilisateurs?|ceci|cela|ça|que\s+tu|ces\s+instructions|lui|leur|personne)\b",
    re.IGNORECASE,
)
SILENCE_PRONOUNS = re.compile(r"\b(?:le|la|les|lui|leur|en)\b|\bl['’]", re.IGNORECASE)
SENSITIVE_ACTIONS = re.compile(
    r"\b(?:reads?|reading|send(?:s|ing)?|sent|forward(?:s|ed|ing)?|transfer(?:s|red|ring)?|cop(?:y|ies|ied|ying)|"
    r"shar(?:e|es|ed|ing)|upload(?:s|ed|ing)?|files?|keys?|tokens?|passwords?|passphrases?|e-?mail\s+address(?:es)?|"
    r"bcc|lis|lit|lire|lu|lue|lus|lues|lisez|envoi(?:e|es|ent)?|envoy(?:er|é|ée|és|ées|ez)|"
    r"transf[èé]r(?:e|es|ent|er|é|ée|és|ées|ez)|transferts?|copi(?:e|es|ent|er|é|ée|és|ées|ez)|"
    r"partag(?:e|es|ent|er|é|ée|és|ées|ez)|t[ée]l[ée]vers(?:e|es|ent|er|é|ée|és|ées|ez)|fichiers?|cl[ée]s?|clefs?|"
    r"jetons?|mots?\s+de\s+passe|adresses?\s+(?:e-?mail|mail|électronique)|cci)\b",
    re.IGNORECASE,
)
BACK_REFERENCES = re.compile(
    r"\b(?:it|this|that|them|these|those|ceci|cela|ça|le|la|les|en)\b|\bl['’]",
    re.IGNORECASE,
)

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
        r"\b(?:scanner|analyseur|relecteur|réviseur|auditeur)s?\s+(?:de\s+sécurité|ia|de\s+code)\s*:",
        re.IGNORECASE,
    ),
    re.compile(r"\bmcplain\b", re.IGNORECASE),
)
DISMISS_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(?:do\s+not|don['’]t|never)\s+(?:flag|report|scan|mention)\s+"
        r"(?:this|these|that|those|it|them|me|us|the\s+(?:code|package|server|tool|file|repository))\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bignore\s+(?:it|this|that|them|these|those|the\s+(?:warning|alert|finding|result)s?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bne\s+(?:le\s+|la\s+|les\s+)?(?:signale|signalez|analyse|analysez|scanne|scannez|mentionne|mentionnez)\s+pas\b|"
        r"\bne\s+pas\s+(?:signaler|analyser|scanner|mentionner)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bignore[rz]?-(?:le|la|les)\b|\bignore[rz]?\s+(?:ce|cette|ces)\s+(?:alertes?|avertissements?|signalements?|résultats?)\b",
        re.IGNORECASE,
    ),
)
ANALYSIS_TOOLS = re.compile(
    r"\b(?:scanners?|scanning\s+tools?|analy[sz]ers?|static\s+analysis|code\s+analysis|security\s+(?:analysis|reviews?|tools?)|"
    r"audits?|auditors?|reviewers?|code\s+reviews?|sast|mcplain|analyseurs?|analyse\s+statique|auditeurs?|"
    r"relecteurs?|réviseurs?|revue\s+de\s+(?:sécurité|code)|outils?\s+(?:d['’]analyse|de\s+sécurité))\b",
    re.IGNORECASE,
)
SENTENCE_END = re.compile(r"[.!?\n]")

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


def silenced_sensitive_action(text: str, match: re.Match[str]) -> bool:
    """Tell whether a request for silence is about a sensitive action: reading, sending, a file, a key, a token..."""

    sentence = sentence_around(text, match.start(), match.end())
    if SENSITIVE_ACTIONS.search(sentence):
        return True
    if not BACK_REFERENCES.search(sentence):
        return False
    start = text.find(sentence)
    before = text[:start].rstrip()
    if not before:
        return False
    previous = sentence_around(before, len(before) - 1, len(before) - 1)
    return SENSITIVE_ACTIONS.search(previous) is not None


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


def ends_sentence(text: str, index: int) -> bool:
    """Tell whether a character ends a sentence: a new line, ! or ?, or a period followed by a space or the end"""

    if not SENTENCE_END.match(text[index]):
        return False
    return text[index] != "." or index + 1 == len(text) or text[index + 1].isspace()


def sentence_around(text: str, start: int, end: int, with_mark: bool = False) -> str:
    """Return the sentence of a text that holds a match, with its final mark when asked"""

    first = start
    while first > 0 and not ends_sentence(text, first - 1):
        first -= 1
    last = end
    while last < len(text) and not ends_sentence(text, last):
        last += 1
    if with_mark and last < len(text) and text[last] in ".!?":
        last += 1
    return text[first:last]


def analyzer_talk(text: str) -> re.Match[str] | None:
    """Find a known attack formula, or a request not to report or to ignore aimed at an analysis tool"""

    for pattern in ANALYZER_PATTERNS:
        match = pattern.search(text)
        if match is not None:
            return match
    for pattern in DISMISS_PATTERNS:
        for match in pattern.finditer(text):
            if ANALYSIS_TOOLS.search(sentence_around(text, match.start(), match.end())):
                return match
    return None
