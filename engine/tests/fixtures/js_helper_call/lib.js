import fs from "fs/promises";

export async function saveNote(text) {
  await fs.writeFile("notes.txt", text, "utf8");
}
