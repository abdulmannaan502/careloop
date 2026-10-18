# Deploying CareLoop

Alexa+ needs to reach the MCP server over public HTTPS. Pick one option.

## Option A: fastest for the demo (local server + tunnel)

```bash
CARELOOP_API_KEY=choose-a-secret python -m careloop.server
# in another terminal, any HTTPS tunnel works, e.g.
ngrok http 8000            # or: cloudflared tunnel --url http://localhost:8000
```

Your MCP endpoint is `https://<tunnel-host>/mcp`. Check it with `python scripts/demo_conversation.py https://<tunnel-host>/mcp --key choose-a-secret`.

## Option B: AWS (recommended for the submission)

### 1. Data, alerts and nightly summary (SAM)

Prerequisites: AWS CLI and SAM CLI configured, and access to the Bedrock model you choose enabled in the Bedrock console (Model access).

```bash
cd infra
sam build --template template.yaml
sam deploy --guided            # set FamilyEmail; confirm the SNS email subscription afterwards
```

Note the `TableName` and `TopicArn` outputs.

### 2. The MCP server (container)

Build and push the image, then run it on **AWS App Runner** (simplest: HTTPS URL included) or ECS/EC2:

```bash
aws ecr create-repository --repository-name careloop
docker build -t careloop .
docker tag careloop <account>.dkr.ecr.<region>.amazonaws.com/careloop:latest
aws ecr get-login-password | docker login --username AWS --password-stdin <account>.dkr.ecr.<region>.amazonaws.com
docker push <account>.dkr.ecr.<region>.amazonaws.com/careloop:latest
```

In App Runner, use port `8000`, health check path `/health`, and these environment variables:

```
CARELOOP_TABLE=<TableName>
CARELOOP_SNS_TOPIC_ARN=<TopicArn>
BEDROCK_MODEL_ID=amazon.nova-lite-v1:0
AWS_REGION=<region>
CARELOOP_API_KEY=<secret>
CARELOOP_ALLOWED_HOSTS=<your-app-runner-host>
```

The App Runner instance role needs `dynamodb:GetItem/PutItem/DeleteItem/Query` on the table, `sns:Publish` on the topic, and `bedrock:InvokeModel` on the model.

## Connecting to Alexa+

Register the endpoint `https://<host>/mcp` (transport: Streamable HTTP) as an MCP server through the Alexa+ developer preview, following the steps on the hackathon **Resources** page. If you set `CARELOOP_API_KEY`, configure the same bearer token there.

The server's `instructions` and each tool description tell Alexa+ when to call which tool and to read the `say` field aloud.
