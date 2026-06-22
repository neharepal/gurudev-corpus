# ADR-003: Use Anthropic API for Phase 2 (not Claude.ai consumer subscription)

**Status:** ACCEPTED
**Date:** 2026-06-12
**Author:** Neha (with Claude)

## Context

Phase 2 is a chat platform that takes a user question and produces an LLM-generated, source-cited answer. Whatever LLM we use will be invoked from a server (during demo: local; in production: hosted) on every devotee question.

Neha holds a Claude.ai consumer subscription (Pro/Max tier) — the personal subscription that lets her use Claude via [claude.ai](https://claude.ai) and the Claude Desktop app. This is *not* the same as the Anthropic API, which is a separate billing surface authorizing programmatic LLM access from your own applications.

A question arose: can the consumer subscription power Phase 2, or do we need an API account?

## Decision

Use the **Anthropic API** with pay-per-token billing for Phase 2's chat backend. The consumer subscription remains for Neha's personal Claude use; it does not authorize app integration.

For production model selection (specific Claude version, prompt-caching strategy), see RFC-003 (Retrieval & RAG).

## Alternatives considered

- **Claude.ai consumer subscription only.** Not authorized for building applications. Rejected by policy.
- **Other commercial LLM providers** (OpenAI, Google, etc.). Possible. Claude was preferred because: (a) strong Marathi handling vs. Western-bias competitors; (b) strong citation/honesty behavior — better at "I don't know" responses, which our reverential audience needs; (c) prompt caching cuts costs significantly. Reconsider if Claude's pricing or quality regresses significantly.
- **Self-hosted open model** (Llama 3.x, Qwen, etc.). Free at inference time (only hosting cost), but: (a) Marathi quality drops 10–20% vs. Claude; (b) self-hosting requires GPU infra Neha doesn't have today. Could be a future cost-reduction path if usage scales to thousands of devotees.

## Consequences

**Positive:**
- Predictable cost. Estimated $15–50/month for 500 devotees at 2 questions/devotee/month using Claude Sonnet 4.6 with prompt caching. Scales linearly.
- Top-tier multilingual quality.
- Best-in-class honesty: Claude is more likely to say "I don't see that in the corpus" than to invent — critical for our audience.

**Negative:**
- API costs are usage-dependent; a sudden spike (e.g., a viral WhatsApp share) could surprise the bill. Mitigation: rate limiting, per-user quotas, monitoring.
- Separate billing surface from Neha's personal subscription. Slight admin overhead.
- Vendor lock-in. Switching LLMs later requires re-tuning prompts. Mitigated by keeping the LLM interface abstracted in code.

## References

- [PRD.md §6 Constraints](../PRD.md)
- RFC-003 (Retrieval & RAG strategy) — model selection lives there
- Anthropic API docs: [console.anthropic.com](https://console.anthropic.com)
