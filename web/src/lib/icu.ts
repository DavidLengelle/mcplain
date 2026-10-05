export type MessageTree = { [key: string]: string | MessageTree };

const ICU_SYNTAX = new Set(["{", "}", "<", ">"]);
const KEY_PATTERN = /^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*$/;
const FIELD_PATTERN = /^[A-Za-z_][A-Za-z0-9_]*$/;
const FORBIDDEN_SEGMENTS = new Set(["__proto__", "prototype", "constructor"]);

function quoteLiteral(text: string): string {
  let output = "";
  let quoted = false;
  for (const character of text) {
    if (character === "'") {
      output += "''";
    } else if (ICU_SYNTAX.has(character)) {
      if (!quoted) {
        output += "'";
        quoted = true;
      }
      output += character;
    } else {
      if (quoted) {
        output += "'";
        quoted = false;
      }
      output += character;
    }
  }
  if (quoted) {
    output += "'";
  }
  return output;
}

export function pythonToIcu(template: string): string | null {
  let output = "";
  let literal = "";
  let index = 0;
  while (index < template.length) {
    const character = template[index];
    const next = template[index + 1];
    if ((character === "{" && next === "{") || (character === "}" && next === "}")) {
      literal += character;
      index += 2;
    } else if (character === "{") {
      const end = template.indexOf("}", index);
      if (end === -1) {
        return null;
      }
      const field = template.slice(index + 1, end);
      if (!FIELD_PATTERN.test(field)) {
        return null;
      }
      output += quoteLiteral(literal) + `{${field}}`;
      literal = "";
      index = end + 1;
    } else if (character === "}") {
      return null;
    } else {
      literal += character;
      index += 1;
    }
  }
  return output + quoteLiteral(literal);
}

function isTree(value: string | MessageTree | undefined): value is MessageTree {
  return typeof value === "object" && value !== null;
}

function insert(tree: MessageTree, segments: string[], message: string): void {
  let node = tree;
  for (const segment of segments.slice(0, -1)) {
    const child = node[segment];
    if (child === undefined) {
      const created: MessageTree = {};
      node[segment] = created;
      node = created;
    } else if (isTree(child)) {
      node = child;
    } else {
      return;
    }
  }
  const last = segments[segments.length - 1];
  if (node[last] === undefined) {
    node[last] = message;
  }
}

export function engineCatalogToMessages(catalog: unknown): MessageTree | null {
  if (typeof catalog !== "object" || catalog === null || Array.isArray(catalog)) {
    return null;
  }
  const tree: MessageTree = {};
  for (const [key, value] of Object.entries(catalog)) {
    if (typeof value !== "string" || !KEY_PATTERN.test(key)) {
      continue;
    }
    const segments = key.split(".");
    if (segments.some((segment) => FORBIDDEN_SEGMENTS.has(segment))) {
      continue;
    }
    const message = pythonToIcu(value);
    if (message !== null) {
      insert(tree, segments, message);
    }
  }
  if (Object.keys(tree).length === 0) {
    return null;
  }
  return tree;
}
