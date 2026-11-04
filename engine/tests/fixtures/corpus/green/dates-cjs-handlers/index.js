const { Server } = require("@modelcontextprotocol/sdk/server/index.js");
const { ListToolsRequestSchema, CallToolRequestSchema } = require("@modelcontextprotocol/sdk/types.js");

const LAUNCH_DAY = "2026-07-14";
const DAY_MS = 24 * 60 * 60 * 1000;

const TOOLS = [
  {
    name: "launch_day",
    description: "Return the fixed launch day of the project",
    inputSchema: { type: "object", properties: {} },
  },
  {
    name: "days_between",
    description: "Count the days between two dates written as YYYY-MM-DD",
    inputSchema: {
      type: "object",
      properties: { from: { type: "string" }, to: { type: "string" } },
      required: ["from", "to"],
    },
  },
];

function daysBetween(from, to) {
  return Math.round((Date.parse(to) - Date.parse(from)) / DAY_MS);
}

function build() {
  const server = new Server({ name: "dates", version: "1.0.0" }, { capabilities: { tools: {} } });
  server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools: TOOLS }));
  server.setRequestHandler(CallToolRequestSchema, async (request) => {
    const args = request.params.arguments;
    switch (request.params.name) {
      case "launch_day":
        return { content: [{ type: "text", text: LAUNCH_DAY }] };
      case "days_between":
        return { content: [{ type: "text", text: String(daysBetween(args.from, args.to)) }] };
      default:
        throw new Error("Unknown tool");
    }
  });
  return server;
}

module.exports = { build };
