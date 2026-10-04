"""Catalog of the verdict rules in Markdown, generated from the rule registry"""

from mcplain.i18n import Translator
from mcplain.models import VerdictColor
from mcplain.rules.base import Rule, RuleRegistry
from mcplain.verdict import DEFAULT_REGISTRY, RULES_VERSION

FIXTURES_ROOT = "engine/tests/fixtures"
FIXTURE_CASES = "positive, near_miss, false_positive"


def _anchor(rule: Rule) -> str:
    """Return the GitHub anchor of a rule heading"""

    return f"{rule.identifier}-{rule.slug}".lower()


def render_catalog(t: Translator, registry: RuleRegistry = DEFAULT_REGISTRY) -> str:
    """Return the Markdown catalog of every registered rule, in one language"""

    rules = registry.rules()
    red = [rule for rule in rules if rule.color is VerdictColor.RED]
    lines = [
        f"# {t('catalog.title')}",
        "",
        t("catalog.intro", version=RULES_VERSION, count=len(rules), red=len(red), orange=len(rules) - len(red)),
        "",
        t("catalog.how"),
        "",
        f"| {t('catalog.column.rule')} | {t('catalog.column.color')} | {t('catalog.column.title')} |",
        "| --- | --- | --- |",
    ]
    for rule in rules:
        lines.append(
            f"| [{rule.identifier} {rule.slug}](#{_anchor(rule)}) | {t('color.' + rule.color.value)} "
            f"| {t(rule.text_key('title'))} |"
        )
    for rule in rules:
        visible = t("cli.value." + str(rule.visible_in_code).lower())
        lines.extend(
            [
                "",
                f"## {rule.identifier} {rule.slug}",
                "",
                f"**{t(rule.text_key('title'))}**{t('cli.separator')}{t('color.' + rule.color.value)}, "
                f"{t('kind.' + rule.kind.value)}.",
                "",
                t(rule.text_key("explanation")),
                "",
                f"- {t('catalog.visible')}{t('cli.separator')}{visible}",
                f"- {t('catalog.false_positive')}{t('cli.separator')}{t(rule.text_key('false_positive'))}",
                f"- {t('catalog.sources')}{t('cli.separator')}".rstrip(),
            ]
        )
        lines.extend(f"  - [{source.name}]({source.url})" for source in rule.sources)
        lines.append(f"- {t('catalog.fixtures')}{t('cli.separator')}`{FIXTURES_ROOT}/{rule.fixtures}/` ({FIXTURE_CASES})")
    return "\n".join(lines)
