import { describe, expect, it } from "vitest";

import type { Alert, Lamp, Tool } from "@/lib/analysis";
import { countLamps, defaultToolIndex, joinList, placeText, toolNumber } from "@/lib/report";

function lamp(id: Lamp["id"], state: Lamp["state"]): Lamp {
  return { id, state, rules: [] };
}

function tool(name: string, level: Tool["level"]): Tool {
  return { name, level } as Tool;
}

function alert(toolName: string | null): Alert {
  return { tool: toolName } as Alert;
}

describe("report helpers", () => {
  it("counts the lit lamps and those in danger", () => {
    const lamps = [lamp("files_read", "on"), lamp("internet", "danger"), lamp("commands", "off")];
    expect(countLamps(lamps)).toEqual({ lit: 2, danger: 1, total: 3 });
  });

  it("opens the tool of the first alert, else the worst tool, else the first one", () => {
    const tools = [tool("a", "none"), tool("b", "warn"), tool("c", "danger")];
    expect(defaultToolIndex(tools, [alert(null), alert("b")])).toBe(1);
    expect(defaultToolIndex(tools, [alert("unknown")])).toBe(2);
    expect(defaultToolIndex([tool("a", "none")], [])).toBe(0);
  });

  it("writes a place with its function, file and line", () => {
    expect(placeText({ function: "send", file: "src/index.ts", line: 4 })).toBe("send() · src/index.ts:4");
    expect(placeText({ function: null, file: "setup.py", line: null })).toBe("setup.py");
  });

  it("joins actions the way each language does, and numbers tools on two digits", () => {
    expect(joinList("fr", ["lire tes fichiers", "modifier tes fichiers"])).toBe("lire tes fichiers et modifier tes fichiers");
    expect(joinList("en", ["a", "b", "c"])).toBe("a, b, and c");
    expect(toolNumber(0)).toBe("01");
    expect(toolNumber(13)).toBe("14");
  });
});
