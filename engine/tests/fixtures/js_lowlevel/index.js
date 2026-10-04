const { Server } = require("@modelcontextprotocol/sdk/server/index.js");
const { ListToolsRequestSchema, CallToolRequestSchema } = require("@modelcontextprotocol/sdk/types.js");

const server = new Server({ name: "weather", version: "1.0.0" }, { capabilities: { tools: {} } });

const WEATHER_TOOL = {
  name: "get_weather",
  description: "Get the current weather for a city",
  inputSchema: {
    type: "object",
    properties: { city: { type: "string", description: "Name of the city" } },
    required: ["city"],
  },
};

server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools: [WEATHER_TOOL] }));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  switch (request.params.name) {
    case "get_weather": {
      const key = process.env.WEATHER_API_KEY;
      const city = request.params.arguments.city;
      const response = await fetch(`https://api.weather.example/v1?city=${city}&key=${key}`);
      return { content: [{ type: "text", text: await response.text() }] };
    }
    default:
      throw new Error("Unknown tool");
  }
});
