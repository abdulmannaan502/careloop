# Demo video script (target 2:45, must stay under 3:00)

Record your screen with OBS (free) or the Windows Game Bar (Win + G). Upload to YouTube as **Public** or **Unlisted**, in English, with no copyrighted music.

| Time | On screen | Voice-over |
|---|---|---|
| 0:00–0:20 | Title image (`docs/images/gallery-1-hero.png`) | "My parents live in one city, I work in another. Every day I wonder: did Amma take her BP tablet? CareLoop answers that, using only her voice and Alexa+." |
| 0:20–0:40 | Architecture image | "CareLoop is an MCP server on the 2025-11-25-or-later spec over Streamable HTTP. Alexa+ handles the conversation; CareLoop holds the care logic, stores data in DynamoDB, and uses Amazon Bedrock to write family updates." |
| 0:40–1:50 | **Alexa+ calling CareLoop** (best), or run `python scripts/demo_conversation.py` in a large-font terminal | Walk through: adding a medicine in plain speech, "what do I take now", "I took my BP tablet", the double-dose warning, "I'm feeling dizzy" (recurring this week). |
| 1:50–2:10 | `log_symptom` with "I have chest pain" | "Some things can't wait. Warning signs get an immediate instruction to call 112, and the family gets an SNS alert." |
| 2:10–2:35 | Family summary output + email from SNS | "Each evening, Bedrock turns the day's facts into a short, calm message for the family. Code decides the facts; the model only writes the words." |
| 2:35–2:50 | Repo / tests passing | "It's open source, tested, and deploys with one SAM template. Thanks for watching." |

Tips
- Increase terminal font to 20+ so judges can read it.
- Lead with the human story; judges may stop at 3:00.
- Run `CARELOOP_DB=demo.db python scripts/seed_demo_week.py` first so the summary has a week of history.
