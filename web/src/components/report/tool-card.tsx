import { useTranslations } from "next-intl";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { Alert, Finding, Tool } from "@/lib/analysis";

import { EngineText } from "../engine-text";
import { RawText } from "../raw-text";
import { AlertList } from "./alert-list";
import { chainText, Place, placeText } from "./place";
import { Label } from "./section";

const MAX_ROUTES = 3;

function groupByCapability(findings: Finding[]): [string, Finding[]][] {
  const groups = new Map<string, Finding[]>();
  for (const finding of findings) {
    const group = groups.get(finding.capability);
    if (group === undefined) {
      groups.set(finding.capability, [finding]);
    } else {
      group.push(finding);
    }
  }
  return Array.from(groups.entries()).sort(([first], [second]) => first.localeCompare(second));
}

function distinctRoutes(findings: Finding[]): Finding[] {
  const ordered = [...findings].sort((first, second) => first.call_chain.length - second.call_chain.length);
  const routes: Finding[] = [];
  const seen = new Set<string>();
  for (const finding of ordered) {
    const path = finding.call_chain.map((step) => step.function).join("\n");
    if (seen.has(path)) {
      continue;
    }
    seen.add(path);
    routes.push(finding);
    if (routes.length === MAX_ROUTES) {
      break;
    }
  }
  return routes;
}

function Reach({ finding }: { finding: Finding }) {
  const place = placeText(finding.file, finding.line);
  let reach = <EngineText code="cli.directly" params={{ place }} />;
  if (finding.call_chain.length > 0) {
    const chain = chainText(finding.call_chain.map((step) => step.function));
    reach = <EngineText code="cli.via" params={{ chain, place }} />;
  }
  return (
    <>
      {reach}
      {finding.url_kind !== null && (
        <>
          {", "}
          <EngineText code={`cli.url_kind.${finding.url_kind}`} />
        </>
      )}
    </>
  );
}

export function Capabilities({ findings }: { findings: Finding[] }) {
  return (
    <ul className="flex flex-col gap-2">
      {groupByCapability(findings).map(([capability, items]) => {
        const routes = distinctRoutes(items);
        return (
          <li key={capability}>
            <p>
              <span className="font-semibold">
                <EngineText code={`capability.${capability}`} />
              </span>{" "}
              <span className="font-mono text-sm text-muted-foreground">({capability})</span>
            </p>
            <ul className="mt-1 flex list-disc flex-col gap-1 pl-6">
              {routes.map((finding, index) => (
                <li key={index}>
                  <Reach finding={finding} />
                </li>
              ))}
            </ul>
            {items.length > routes.length && (
              <p className="pl-6">
                <EngineText code="cli.others" params={{ count: items.length - routes.length }} />
              </p>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function Announced({ tool }: { tool: Tool }) {
  const t = useTranslations("tool");
  const description = tool.description.trim();
  const annotations = Object.entries(tool.annotations);

  return (
    <div className="flex flex-col gap-3">
      <div>
        <p>
          <Label>{t("description")}</Label>
        </p>
        {description === "" && tool.description_is_dynamic && <p>{t("dynamicDescription")}</p>}
        {description === "" && !tool.description_is_dynamic && <p>{t("noDescription")}</p>}
        {description !== "" && <RawText value={tool.description} variant="block" limit={600} />}
        {description !== "" && tool.description_is_dynamic && (
          <p className="text-sm">
            <EngineText code="cli.tool.description_partly_dynamic" />
          </p>
        )}
      </div>
      {tool.title !== null && (
        <p>
          <Label>{t("title")}</Label>
          {tool.title_is_dynamic && <EngineText code="cli.value.computed" />}
          {!tool.title_is_dynamic && <RawText value={tool.title} limit={200} />}
        </p>
      )}
      {(annotations.length > 0 || tool.annotations_are_dynamic) && (
        <div>
          <p>
            <Label>{t("annotations")}</Label>
          </p>
          <ul className="list-disc pl-6">
            {annotations.map(([key, value]) => (
              <li key={key}>
                <Label>
                  <EngineText code={`annotation.${key}`} />
                </Label>
                <EngineText code={`cli.value.${String(value)}`} />
              </li>
            ))}
          </ul>
          {tool.annotations_are_dynamic && <p className="text-sm">{t("dynamicAnnotations")}</p>}
        </div>
      )}
      {tool.parameters.length > 0 && (
        <div>
          <p>
            <Label>{t("parameters")}</Label>
          </p>
          <ul className="flex list-disc flex-col gap-1 pl-6">
            {tool.parameters.map((parameter, index) => (
              <li key={index}>
                <RawText value={parameter.name} limit={100} />
                {parameter.description !== null && (
                  <>
                    {" "}
                    <RawText value={parameter.description} limit={300} />
                  </>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export function ToolCard({ tool, alerts }: { tool: Tool; alerts: Alert[] }) {
  const t = useTranslations("tool");

  return (
    <Card data-tool={tool.name} className="ring-foreground/25">
      <CardHeader>
        <CardTitle className="text-lg font-bold">
          <h3>
            <span className="sr-only">
              <Label>{t("label")}</Label>
            </span>
            <RawText value={tool.name} limit={120} />
          </h3>
        </CardTitle>
        <p className="text-sm">
          <Label>{t("place")}</Label>
          <Place file={tool.file} line={tool.line} />
          {tool.name_is_dynamic && ` (${t("dynamicName")})`}
        </p>
      </CardHeader>
      <CardContent className="flex flex-col gap-5 text-base">
        <section className="flex flex-col gap-2">
          <h4 className="font-bold">
            {t("announces")} <span className="font-normal italic">({t("byAuthor")})</span>
          </h4>
          <Announced tool={tool} />
        </section>
        <section className="flex flex-col gap-2">
          <h4 className="font-bold">{t("canDo")}</h4>
          {tool.findings.length === 0 && <p>{t("nothingFound")}</p>}
          {tool.findings.length > 0 && <Capabilities findings={tool.findings} />}
          {tool.gaps.length > 0 && (
            <p>
              <Label>{t("incomplete")}</Label>
              {tool.gaps.map((gap, index) => (
                <span key={gap}>
                  {index > 0 && ", "}
                  <EngineText code={`gap.${gap}`} />
                </span>
              ))}
            </p>
          )}
        </section>
        <section className="flex flex-col gap-2">
          <h4 className="font-bold">{t("alerts")}</h4>
          {alerts.length === 0 && <p>{t("noAlert")}</p>}
          {alerts.length > 0 && <AlertList alerts={alerts} />}
        </section>
      </CardContent>
    </Card>
  );
}
