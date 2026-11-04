#!/usr/bin/env node
const { spawnSync } = require("node:child_process");
const path = require("node:path");

function binaryPath() {
  const name = `@example/notes-native-${process.platform}-${process.arch}`;
  const folder = path.dirname(require.resolve(`${name}/package.json`));
  return path.join(folder, "bin", "notes-native");
}

function launch() {
  const result = spawnSync(binaryPath(), process.argv.slice(2), { stdio: "inherit" });
  return result.status;
}

module.exports = { launch };
