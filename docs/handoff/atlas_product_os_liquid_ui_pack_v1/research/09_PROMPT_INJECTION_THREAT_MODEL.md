# Prompt Injection Threat Model

All external content is untrusted by default: email, PDFs, OCR, webpages, GitHub issues, chats, tool output, logs and imported conversations.

Untrusted content may be summarized or extracted, but must not become instruction, tool call, memory write or outbound action without classification and policy checks.
