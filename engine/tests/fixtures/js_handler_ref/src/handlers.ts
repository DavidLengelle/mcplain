import { rm } from "node:fs/promises";

export const deleteHandler = async (args: { path: string }) => {
  await rm(args.path);
  return { content: [{ type: "text" as const, text: "deleted" }] };
};
