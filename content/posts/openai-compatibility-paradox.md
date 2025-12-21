---
title: "The OpenAI Compatibility Paradox"
date: 2025-12-17T18:00:00+05:30
description: Why the LLM API space needs a true standard
tags:
  - LLM
  - OpenAI
  - Anthropic
  - Gemini
  - Completions API
cover:
  image: /images/openai-compatibility/compatibility.png
  relative: false
  hidden: true
---

The promise of a standardized interface for LLMs via OpenAI-compatible endpoints is compelling. In theory, it allows for a plug-and-play architecture where switching models is as trivial as changing a `base_url`. In practice, this compatibility is often an illusion.

I've spent the past year building a multi-provider LLM backend, and the pattern is always the same: things work for basic text generation, then break the moment you need production-critical features.

This analysis focuses on the `/chat/completions` endpoint, but the same fragmentation applies to `/images/generations` and `/embeddings`. As new agent-focused APIs emerge (like OpenAI's stateful `responses` API, or Anthropic's agent capabilities including code execution, MCP connector, and Files API), the risk of further fragmentation only grows.

---

## Where compatibility breaks

### Structured output

OpenAI lets you pass a JSON schema in `response_format` and the model conforms to it.

Anthropic now supports structured output, but only for newer models (Sonnet 4.5, Opus 4.1, Haiku 4.5 as of December 2025). For older models like Claude 4 Sonnet, you need the tool-calling workaround: define a fake tool with your desired schema, force the model to "call" it, extract the arguments. If you're running a production system with multiple Claude model versions, you need different code paths depending on which model handles the request.

Gemini claims to support structured output through their compatible API but frequently produces non-compliant results. Their native API handles this correctly; the "compatible" layer introduces the problem.

Qwen models recently added structured output support with schema enforcement.

### Tool calling

Tool calling is the backbone of modern agentic systems, and its implementation varies wildly across providers.

One of the most useful optimizations is streaming tool arguments as they're generated. This allows an agent to begin preparing for tool execution before the model finishes outputting all its arguments, helping to reduce perceived latency. Support for this is inconsistent:

OpenAI handles this cleanly. Anthropic only recently added support via a versioned beta header (`anthropic-beta: fine-grained-tool-streaming-2025-05-14`). Gemini doesn't support it. Tool calls are buffered and sent in a single chunk at the end of the stream.

The JSON schema for defining tools is another problem. Every provider documents which parts of the JSON Schema specification they support, but some limitations are undocumented. Gemini imposes a depth limit on tool definition schemas that isn't mentioned anywhere. You discover it when complex tools fail with unhelpful error messages.

### Prompt caching

Prompt caching is beneficial for managing cost and latency, but implementations differ in ways that matter.

OpenAI made caching automatic in October 2024. No code changes required for GPT-4o and newer models. Prompts over 1,024 tokens are cached transparently. Gemini also has automatic caching enabled by default.

Anthropic requires manual cache control. You need to add `cache_control` parameters to mark which parts of your prompt should be cached, with explicit breakpoints and a 5-minute TTL that you must manage. Running Claude on Bedrock? Same manual approach, different SDK. Different approach, different code.

Building a unified caching strategy across providers isn't practical. You either write provider-specific caching logic or leave performance and cost savings on the table. (Note: I wrote the first draft of this 3-4 months ago and already things have changed a lot and I'm lazy to validate all the details.)

### Reasoning traces

Approaches to reasoning tokens vary significantly. Gemini has "adaptive thought" enabled by default. OpenAI doesn't expose reasoning tokens at all, which complicates cost tracking across providers. Both Anthropic and Gemini have "thought signatures" that must be preserved in chat history. Fail to do so and you get cryptic validation errors.

### Chat history structure

Even the fundamental structure of chat history differs across native APIs.

OpenAI uses three roles: `user`, `assistant`, and `tool`. Tool uses appear in assistant messages; results go in dedicated `tool` messages. Anthropic uses only `user` and `assistant`, with tool results as special content blocks within assistant messages. Gemini follows Anthropic's pattern but renames `assistant` to `model`.

This makes chat history management and token tracking across providers unnecessarily complex.

### It keeps changing

Everything I've described above is a snapshot. By the time you read this, some of it will be outdated.

Anthropic added structured output support in November 2025, but only for new models. OpenAI made caching automatic in October 2024. Gemini's tool streaming behavior has changed multiple times. Bedrock's OpenAI-compatible endpoint scope keeps evolving. Gemini has been hinting at tool calling support with structured output for a while.

This is the real problem. You build abstractions that handle today's incompatibilities, then a provider ships a feature, changes their streaming format, or error codes. Your "unified" client becomes a maintenance nightmare.

The fragmentation isn't static. It's actively getting worse as providers race to ship features without coordinating on interfaces.

### Rate limits

Rate limiting sounds straightforward. TPM and RPM numbers that tell you how much capacity you have. In practice, every provider handles this differently, and the numbers alone don't tell you what you need to know.

OpenAI is generous with limits at higher tiers. But when load is high, they queue your requests instead of rejecting them. Your request sits in a queue, eating into your timeout budget, and you have no idea whether it will complete in 2 seconds or 20. For fallback strategies, this is a nightmare. You're waiting on a provider that might never respond in time, instead of failing fast and routing elsewhere.

Gemini takes the opposite approach. Hit a limit, get a 429 immediately. For production systems with fallback logic, this is actually preferable. You know instantly to try another provider. But getting guaranteed capacity requires Provisioned Throughput on Vertex AI, which is expensive and requires upfront commitment.

Anthropic has its own mechanism: a `service_tier` parameter you pass in API calls. Set it to "auto" and requests use Priority Tier capacity when available, falling back to standard. The response tells you which tier handled your request. It works, but it's yet another provider-specific parameter to manage.

Then there's the cloud provider layer. Running Claude on Bedrock? Different rate limits than Anthropic's native API. OpenAI on Azure? Same story. Each hosting platform adds its own quota system on top of the model provider's limits.

None of this is discoverable from API docs alone. The queuing-vs-rejection behavior difference between OpenAI and Gemini? I learned that from production incidents. Whether you prefer fast failure or patient queuing depends on your use case, but you can't make that choice if you don't know how each provider behaves under pressure.

---

## Same model, different behavior

The same model can behave differently depending on which platform hosts it.

Using an Anthropic model via AWS Bedrock versus Anthropic's native API should be a simple switch. It isn't. For a period, Bedrock's streaming implementation had a bug: requests with invalid payloads and `stream=True` would be accepted, start streaming, then fail mid-stream with a server-side validation error. Anthropic's native API rejected these upfront. Same model, different failure mode, different error handling required.

Bedrock recently added an OpenAI-compatible API, but it only applies to OpenAI models they host. To use Claude through Bedrock, you must abandon the compatible endpoint and use the `boto3` SDK directly. So much for unified interfaces.

---

## The integration overhead

This lack of true compatibility creates a maintenance burden across the entire LLM ecosystem.

The result is a fragmented landscape of SDKs: native provider SDKs (`openai`, `anthropic`, `google-genai`), abstraction layers and agent frameworks (LangChain, Pydantic AI), and compatibility shims (LiteLLM, Mozilla AI's [any-llm](https://github.com/mozilla-ai/any-llm)). These compatibility layers spend enormous engineering effort patching over inconsistencies. They're solving a problem that shouldn't exist.

LiteLLM deserves particular mention. It's the most popular compatibility layer, but it's built on a flawed foundation: rather than leveraging official provider SDKs, it reimplements provider interfaces using OpenAI-compatible parameters. This means LiteLLM is itself subject to the same compatibility assumptions it's trying to abstract away. When a provider's "compatible" endpoint diverges from OpenAI's behavior, LiteLLM inherits the problem. You're adding an abstraction layer that doesn't actually insulate you from the underlying fragmentation.

Mozilla AI's any-llm takes a different approach, wrapping official SDKs rather than reimplementing them. But the fact that we need multiple competing solutions to this problem underscores how broken the current state is.

For production systems that need multi-provider strategies (task-based routing, quota management, load balancing, A/B testing, fallbacks), each API inconsistency adds complexity to routing logic. The burden extends to observability providers like Arize Phoenix and Langfuse, who must build and maintain bespoke integrations for each provider.

---

## What might actually help?

The solution isn't more sophisticated compatibility layers. It's a formal, open standard.

**A versioned specification.** A public schema for request/response formats covering `/chat/completions`, `/embeddings`, and `/images/generations`. This would define the `messages` structure, `tools` behavior, and streaming formats unambiguously.

**A capabilities discovery endpoint.** Instead of discovering limitations through trial and error, a standard endpoint (e.g., `/capabilities`) would let SDKs programmatically query supported features. It could return data like `supports_tool_streaming: true`, `json_schema_compliance: "draft-2020-12"`, or `max_tool_schema_depth: 4`. SDKs could handle limitations gracefully rather than failing unexpectedly.

**Standardized error codes.** A defined set of error codes for common LLM failures (`content_filter_violation`, `tool_schema_unsupported`, `max_context_exceeded`) would make error handling consistent across providers.

**A compliance test suite.** For "compatibility" to mean something, providers claiming compliance should be verifiable against an open-source test suite.

**Standardized rate limit behavior.** A way to query current limits, remaining quota, and specify whether a provider fast-fails or queues requests when approaching limits. This would let multi-provider systems make intelligent routing decisions.

---

## Who could fix this?

Anthropic donated the Model Context Protocol (MCP) to the Agentic AI Foundation (AAIF) under the Linux Foundation. OpenAI contributed AGENTS.md, Block contributed goose. The foundation has backing from Google, Microsoft, AWS, Cloudflare, and Bloomberg.

MCP solved a similar problem (connecting AI models to external tools and data sources) by creating an open, vendor-neutral standard. Within a year it went from internal Anthropic project to industry-wide adoption with millions of monthly SDK downloads.

The AAIF shows that major providers can collaborate on shared infrastructure when there's a neutral governance structure. The `/chat/completions` API and its associated behaviors (tool calling, structured output, streaming) are at least as foundational as MCP. Arguably more so, since every LLM application touches these interfaces.

If the same players who formed the AAIF turned their attention to formalizing the completion API specification, they'd have both the credibility and the organizational structure to make it happen. The Linux Foundation has decades of experience stewarding critical infrastructure like Kubernetes and Node.js.

This seems like a natural extension of what's already being done for tool connectivity.

---

## TL;DR

"OpenAI-compatible" currently means "similar enough to seem interchangeable until it's not." Every serious system I've encountered ends up with provider-specific handling anyway.

The overhead from this fragmentation is real. A formal standard would let SDK authors focus on higher-level tooling instead of patching low-level differences. It would give developers genuine confidence when switching providers. And importantly, it would expand LLM usage beyond the Python/TypeScript ecosystem. Other languages could build robust clients against a stable specification instead of chasing moving targets.

Until then, don't trust the compatibility claims. Use the provider's native API if you're serious about production.
