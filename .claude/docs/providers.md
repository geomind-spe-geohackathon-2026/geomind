# Providers

Interchangeable LLM services behind one protocol, in `geomind/providers/`. The name differs from
gemini's `backends` because these are services. Keys live only here: they never enter a sandbox, a
prompt, an event or a log.

## Protocol

`LLM.complete(messages, tools, *, model, settings, on_text=None) -> Completion`, exactly as in
[contracts.md](../../../docs/contracts.md) section 3. `tools` is a list of
`{name, description, input_schema}`, `settings` holds `temperature` and `max_tokens`, and
`on_text(delta)` is a plain function. A provider may have `secrets`, a tuple of values the engine
redacts from every event.

## Retries

`RetryLLM(llm)` wraps any `LLM`, so a backend-made provider gets it too. The engine wraps whatever
it receives, once, through `with_retries`. A failure with `is_retryable` set, or a `TimeoutError`, is
tried again up to `retry_count` times, with a delay of `retry_delay * 2**attempt`. Then the models
in `Model.fallbacks` are tried in order. A failure that is not retryable goes straight to the next
model. Every retry is a `retry` event. Text streamed before a failure stays streamed, so a client
can see it twice; the logged completion holds only the final text.

## OpenRouter

`OpenRouter(api_key=None, base_url=..., transport=None)` reads `OPENROUTER_API_KEY` when no key is
given, and raises `ProviderError` when there is none. It streams with `httpx.AsyncClient` and the
`request_timeout` setting, and fills `Usage`, including cost, from the response. HTTP and API errors
raise `ProviderError` with `status` and the message; 429, 5xx, timeouts and connection failures are
retryable. Tool arguments that are not valid JSON stay visible as `{invalid_json_arguments: text}`,
so validation sends them back to the model. `transport` replaces the network in tests.

**Prompt caching.** With the setting `prompt_caching` (on by default), a request to a model of
`CACHED_MODELS` (`anthropic/`) sends its first system message, the agent's prompt, as one text
part with `cache_control: {"type": "ephemeral"}` (five minutes). The prompt is cached in the order
tools, system, messages, so this one breakpoint caches the tool schemas too; OpenRouter documents
breakpoints on content parts, not on tools, so none is set on a tool. The rendered problem state,
a later system message, changes with every call and is not cached, and no top-level automatic
breakpoint is sent, since it would write the cache again on every call. The tokens read from the
cache (`usage.prompt_tokens_details.cached_tokens`) fill `Usage.cached_tokens`, part of
`input_tokens`; they stay out of the contract's usage JSON (`step.finished`, the run log).

## FakeLLM

`FakeLLM(completions)` returns scripted completions in order and streams their text; an exception
in the script is raised, and calling past the end raises `ProviderError`. `calls` keeps what it
received. `FakeLLM.from_events(events)` rebuilds the script from a stored run, for replay, and
`FakeLLM.from_recording(path)` from a recording: one completion as JSON per line.

## Recorder

`Recorder(llm, path)` calls another provider and appends each completion, without `raw`, to a
recording. `evals --live` uses it.
