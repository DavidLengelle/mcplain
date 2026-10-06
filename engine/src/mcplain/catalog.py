"""Catalog of the verdict rules in Markdown, generated from the rule registry"""

from mcplain.i18n import Translator
from mcplain.lamps import LAMPS, LampSpec
from mcplain.models import VerdictColor
from mcplain.rules.base import Rule, RuleRegistry
from mcplain.verdict import DEFAULT_REGISTRY, RULES_VERSION

FIXTURES_ROOT = "engine/tests/fixtures"
FIXTURE_CASES = "positive, near_miss, false_positive"


def _anchor(rule: Rule) -> str:
    """Return the GitHub anchor of a rule heading"""

    return f"{rule.identifier}-{rule.slug}".lower()


def _lit_by(spec: LampSpec, t: Translator) -> str:
    """Return what lights a lamp: its capabilities, and invisible characters for the hidden text lamp"""

    parts = [f"`{capability.value}`" for capability in sorted(spec.capabilities)]
    if spec.lit_by_invisible_characters:
        parts.append(t("catalog.lamps.invisible_characters"))
    return ", ".join(parts) or t("catalog.lamps.none")


def render_lamps(t: Translator) -> list[str]:
    """Return the Markdown table of the six lamps"""

    lines = [
        "",
        f"## {t('catalog.lamps.title')}",
        "",
        t("catalog.lamps.intro"),
        "",
        f"| {t('catalog.lamps.column.lamp')} | {t('catalog.lamps.column.id')} "
        f"| {t('catalog.lamps.column.lit_by')} | {t('catalog.lamps.column.danger')} |",
        "| --- | --- | --- | --- |",
    ]
    for spec in LAMPS:
        rules = ", ".join(sorted(spec.red_rules)) or t("catalog.lamps.none")
        lines.append(f"| {t(f'lamp.{spec.lamp.value}.name')} | `{spec.lamp.value}` | {_lit_by(spec, t)} | {rules} |")
    return lines


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
    lines.extend(render_lamps(t))
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
                f"- {t('catalog.plain')}{t('cli.separator')}**{t(rule.text_key('plain_title'))}**. "
                f"{t(rule.text_key('plain_found'))} {t('catalog.plain_advice')}{t('cli.separator')}"
                f"{t(rule.text_key('plain_advice'))}",
                f"- {t('catalog.visible')}{t('cli.separator')}{visible}",
                f"- {t('catalog.false_positive')}{t('cli.separator')}{t(rule.text_key('false_positive'))}",
                f"- {t('catalog.sources')}{t('cli.separator')}".rstrip(),
            ]
        )
        lines.extend(f"  - [{source.name}]({source.url})" for source in rule.sources)
        lines.append(f"- {t('catalog.fixtures')}{t('cli.separator')}`{FIXTURES_ROOT}/{rule.fixtures}/` ({FIXTURE_CASES})")
    return "\n".join(lines)
