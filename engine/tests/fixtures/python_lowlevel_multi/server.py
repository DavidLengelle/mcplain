import os
import shutil
import subprocess
from enum import Enum

from mcp.server import Server
from mcp.types import Tool

WRITE_TOOL = "write_note"


class ToolNames(str, Enum):
    READ = "read_note"
    DELETE = "delete_notes"
    RUN = "run_script"


TOOLS = [
    Tool(name=ToolNames.READ.value, description="Read a note", input_schema={"type": "object", "properties": {}}),
    Tool(name=WRITE_TOOL, description="Write a note", input_schema={"type": "object", "properties": {}}),
    Tool(name=ToolNames.DELETE, description="Delete all notes", input_schema={"type": "object", "properties": {}}),
    Tool(name="run_script", description="Run the notes script", input_schema={"type": "object", "properties": {}}),
]


def _read(path: str) -> str:
    with open(path) as handle:
        return handle.read()


async def call_tool(ctx: object, params: object) -> str:
    audit = open("audit.log", "a")
    audit.write(params.name)
    if params.name == ToolNames.READ.value:
        return _read("note.txt")
    elif params.name == WRITE_TOOL:
        os.makedirs("notes")
        return "written"
    match params.name:
        case ToolNames.DELETE:
            shutil.rmtree("notes")
        case "run_script":
            subprocess.run(["./notes.sh"])
    return "done"


server = Server("notes", on_call_tool=call_tool)
