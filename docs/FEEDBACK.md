# Product feedback and friction log (draft)

Paste into the Devpost feedback fields. Entries marked ✏️ need your own experience before submitting.

## Tools used

| Tool | Used for | Worked well | Needs work |
|---|---|---|---|
| MCP Python SDK 2.x (`MCPServer`) | Tool definitions, Streamable HTTP transport, custom `/health` route | Typed tool parameters with `Annotated[..., Field(...)]` generate clean JSON schemas; stateless mode was one flag | v1 → v2 rename broke every tutorial (see friction log) |
| Alexa+ MCP integration | Voice front end for all tools | ✏️ | ✏️ |
| Amazon Bedrock (Converse API, Nova Lite) | Family summary writing | One API shape across models; system prompt + JSON facts kept output grounded | ✏️ model-access request step |
| Amazon DynamoDB | Medications, doses, symptoms (single table) | On-demand billing, range queries on `sk` fit time-ordered events | Decimal conversion for numbers in boto3 is still manual |
| AWS Lambda + EventBridge Scheduler | Nightly family summary | ✏️ | ✏️ |
| Amazon SNS | Family email/SMS alerts | ✏️ | ✏️ |

Would build with it again: ✏️

## Friction log

**1. MCP SDK v2 renamed FastMCP**
- Task: create an MCP server from the official quick-start examples.
- Steps: `pip install "mcp[cli]"` (installed 2.2.0), then `from mcp.server.fastmcp import FastMCP`.
- Expected: the import from most docs and tutorials works.
- Actual: `ModuleNotFoundError`. In 2.x it's `from mcp.server.mcpserver import MCPServer`, and some signatures changed.
- Severity: Medium (blocks first run; error message does link to the migration guide).
- Workaround: read the migration guide and use `MCPServer`.
- Suggestion: have Alexa+ MCP docs pin a version, or show v2 code, and say which SDK version the Alexa+ samples were tested with.

**2. Custom HTTP headers on the Python MCP client**
- Task: call a bearer-protected server from a test client.
- Expected: pass an `httpx.AsyncClient(headers=...)`.
- Actual: the v2 SDK uses its own `httpx2` client type, so plain `httpx` is not installed and isn't accepted.
- Severity: Low.
- Workaround: `mcp.client.streamable_http.create_mcp_http_client(headers=...)`.
- Suggestion: document the helper in the auth section.

**3.** ✏️ Alexa+ MCP registration / testing (add what happened when you connected the server)

## Feature requests

- **Proactive notifications from MCP servers to Alexa+** (critical for care use cases): let a server ask Alexa+ to speak a reminder at 9 PM without the user starting the conversation.
- **Per-household identity passed to MCP tools** (important): a stable, privacy-preserving household or user id so one server can serve many families.
- **Simulator with voice transcripts for MCP** (nice-to-have): replay a list of utterances and see which tools Alexa+ picked.
