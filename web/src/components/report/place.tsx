import { RawText } from "../raw-text";

export function Place({ file, line }: { file: string; line: number | null }) {
  let suffix = "";
  if (line !== null) {
    suffix = `:${line}`;
  }

  return (
    <span>
      <RawText value={file} limit={160} />
      {suffix}
    </span>
  );
}

export function placeText(file: string, line: number | null): string {
  if (line === null) {
    return file;
  }
  return `${file}:${line}`;
}

export function chainText(functions: string[]): string {
  return functions.join(" -> ");
}
