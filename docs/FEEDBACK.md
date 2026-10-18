# Product feedback and friction log

Written by the CareLoop author during the hackathon build (Oct 18, 2026).

**Scope note, for honesty:** the MCP server, tools, tests and web demo were built and run end to end (real MCP client over Streamable HTTP, 8 passing tests, live Streamlit demo). The AWS integrations (Bedrock, DynamoDB, Lambda, EventBridge, SNS) are implemented in code, the SAM template passes `cfn-lint`, and the Bedrock call path is covered by a mocked unit test, but they were **not run against a live AWS account** in this build. Registering the server with a real Alexa+ device was **not tested**; the Alexa+ track is covered through the "simulated Alexa+ experience" path.

## Tools used

| Tool | Used for | Worked well | Needs work |
|---|---|---|---|
| MCP Python SDK 2.x (`MCPServer`) | Tool definitions, Streamable HTTP transport, custom `/health` route, in-process client for tests | Typed parameters with `Annotated[..., Field(...)]` produce clean JSON schemas; stateless HTTP is one flag; the client can talk to the server in memory or over HTTP with the same API | v1 → v2 rename broke most tutorials (friction #1, #2) |
| Amazon Bedrock (Converse API) | Family summaries; tool-use agent that stands in for Alexa+ in the web demo | One API shape across models, `toolConfig` maps directly onto MCP tool schemas | Not run live in this build |
| Amazon DynamoDB | Medicines, doses and symptoms in a single table | On-demand billing; sort-key range queries fit time-ordered events | boto3 returns `Decimal` for numbers, so conversion is manual |
| AWS Lambda, EventBridge, SNS | Nightly summary job and urgent family alerts | SAM template is short and lints cleanly | Not run live in this build |
| Streamlit Community Cloud | Hosting the simulated Alexa+ demo | Deploy from a GitHub repo in a few clicks | Default URL generation repeated the subdomain (friction #3) |

Would build with these again: yes for MCP and Bedrock. MCP cleanly separates the voice conversation from domain logic, which suited a care assistant where correctness matters more than phrasing.

## Friction log

**1. MCP SDK v2 renamed FastMCP**
- Task: create an MCP server from the common quick-start examples.
- Steps: `pip install "mcp[cli]"` (installed 2.2.0), then `from mcp.server.fastmcp import FastMCP`.
- Expected: the import used by most docs and tutorials works.
- Actual: `ModuleNotFoundError`. In 2.x it is `from mcp.server.mcpserver import MCPServer`, and some signatures changed.
- Severity: Medium (blocks the first run; the error message does link to the migration guide).
- Workaround: follow the migration guide.
- Suggestion: have the Alexa+ MCP docs and samples pin an SDK version or show v2 code.

**2. Custom headers on the Python MCP client**
- Task: call a bearer-protected server from a test client.
- Expected: pass an `httpx.AsyncClient(headers=...)`.
- Actual: v2 uses its own `httpx2` client type, so plain `httpx` is neither installed nor accepted.
- Severity: Low.
- Workaround: `mcp.client.streamable_http.create_mcp_http_client(headers=...)`.
- Suggestion: document this helper in the auth section.

**3. Streamlit Community Cloud subdomain**
- Task: deploy with a custom app URL.
- Steps: typed `careloop-alexa` in the optional App URL field on the deploy form.
- Expected: `careloop-alexa.streamlit.app`.
- Actual: the app was created at `careloop-alexacareloop-alexa.streamlit.app` (the value was doubled), and renaming it afterwards did not take effect.
- Severity: Low (cosmetic).
- Workaround: use the generated URL.
- Suggestion: validate the field value after autofill from the query string.

**4. Testing without a device**
- Task: demonstrate an Alexa+ MCP integration without Alexa+ hardware access.
- Actual: no official way to replay utterances against an MCP server, so the build includes its own stand-in (`careloop/assistant.py`).
- Severity: Medium for new developers.
- Suggestion: ship a simulator that takes a list of utterances and shows which MCP tools Alexa+ would call.

## Feature requests

- **Proactive speech from MCP servers** (critical for care use cases): let a server ask Alexa+ to speak a reminder at a set time without the user starting a conversation.
- **Stable per-household identity passed to tools** (important): a privacy-preserving household or user id so one server can serve many families.
- **Utterance-replay simulator for MCP** (nice-to-have): see which tools Alexa+ picks for a list of phrases.
