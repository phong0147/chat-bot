# AI Studio Playground agent configuration

These files add a read-only lookup tool to the existing Playground agent.
They do not create a frontend/backend application or upload knowledge files.

Before starting a new agent conversation:
1. Keep the assignment's exact system prompt in System instructions.
2. Enable Code execution; disable Google Search and URL context.
3. Add two Inline file sources:
   - query_store.py -> /workspace/query_store.py
   - agent-instructions.md -> /workspace/.agents/AGENTS.md
4. Save the Sources dialog.
5. Inspect Environment > Network. Gemini API access must be authenticated
   with the same key/project used to upload the store. AI Studio's linked
   Gemini API access should be configured by the platform. Never paste the
   key into source files, a user message, or system instructions.
6. Ask: How do I add a YouTube video?
7. Check the tool result has grounded=true and correct source URLs, then
   take a screenshot of the Playground question and answer.

The helper uses only Python's standard library. Its query was checked
locally with GEMINI_API_KEY from the project .env. The managed Playground
environment and its key-injection configuration still require verification.
No billing settings are changed by these files.

References:
https://ai.google.dev/gemini-api/docs/aistudio-agents
https://ai.google.dev/gemini-api/docs/agent-environment

For a different Google project, update STORE in query_store.py to the store saved in data/upload-state.json before adding the inline file. The store identifier is configuration, not an API key. The exact assignment prompt is saved in system-prompt.txt.
