---
title: "Type-Safe Python Decorators"
date: 2026-02-01T14:00:00+05:30
description: A practical guide to getting decorator type hints right with ParamSpec, Concatenate, and generics
tags:
  - python
  - type hints
  - decorators
  - ParamSpec
  - mypy
  - pyright
---

Decorators are everywhere in Python. Logging, retries, caching, auth checks - if you've built anything non-trivial, you've written one. But the moment you try to add type hints, things get weird. Your IDE loses autocomplete. You end up with `Callable[..., Any]` and pretend the problem doesn't exist, because `Callable` can't express "whatever arguments the wrapped function takes."

[PEP 612](https://peps.python.org/pep-0612/) introduced `ParamSpec` (Python 3.10+) to solve exactly this. This post walks through using it - from trivial cases to the genuinely painful scenarios I hit while building a multi-LLM agent backend. Read the [TL;DR](#tldr) section for a quick summary.

---

## Level 1: Simple passthrough decorator

The classic timing decorator. It doesn't change arguments or return types - just wraps the call.

{{< include file="level1_timeit.py" lang="python" >}}

`ParamSpec("P")` captures the entire parameter signature. `P.args` and `P.kwargs` are special forms that can only appear together in a function signature. The type checker sees `fetch_data` as `(url: str, timeout: int = 30) -> dict[str, str]` - signature fully preserved.

---

## Level 2: Decorator with arguments

`@retry(times=3)` means `retry(times=3)` returns the actual decorator. Triple nesting.

{{< include file="level2_retry.py" lang="python" >}}

The outer function returns `Callable[[Callable[P, R]], Callable[P, R]]` - a function that takes a callable and returns one with the same signature. Type checkers handle this well.

---

## Level 3: Method decorators

`ParamSpec` captures `self` automatically. The same `timeit` decorator from Level 1 works on methods without changes.

{{< include file="level3_method.py" lang="python" >}}

`P` captures `(self: UserService, user_id: int)`. The type checker is happy, `self.get_user(42)` has correct autocomplete. No special handling needed.

But this breaks when the decorator needs to *access* `self`.

---

## Level 4: Decorators that access `self`

If the decorator body needs `self` - for logging via `self.logger`, checking `self.config`, etc. - you need `Concatenate`.

The problem: `P` is atomic. You can't decompose it to "pull out the first argument." `typing.Concatenate` solves this by letting you prepend specific types to a `ParamSpec`:

{{< include file="level4_concatenate.py" lang="python" >}}

Mental model for `Concatenate`:

```
Original:  def get_user(self, user_id: int) -> dict[str, int]
                        ^^^^  ^^^^^^^^^^^^
Concatenate[SelfT, P] matches as:
  SelfT = UserService (bound to Service)
  P     = (user_id: int)
```

`Concatenate` prepends `SelfT` to `P`, so the full signature is reconstructed as `(self: SelfT, *P.args, **P.kwargs)`. The decorator can use `self.logger` because `SelfT` is bound to `Service`.

---

## Level 5: When the base class isn't enough

Here's where things get interesting. Consider an agent backend where:

- `Agent[T]` is a generic base class - `T` is the structured output type
- Agents gain capabilities through mixins: `ObservabilityMixin` provides `self.record_cost()`, `MemoryMixin` provides `self.history`
- Not every agent has every mixin. `SummarisationAgent` has cost tracking but no memory. `ChatAgent` has both.
- Decorators need access to `self`, but each decorator needs attributes from a *different* mixin

The naive approach - `AgentT = TypeVar("AgentT", bound="Agent[Any]")` for every decorator - breaks immediately. `Agent` doesn't have `record_cost()`. You could dump every attribute onto the base class, but that defeats the purpose of mixins.

The solution: each decorator declares a `Protocol` for the `self` it needs, and binds its TypeVar to that Protocol. `@track_cost` requires `HasObservability`. `@inject_history` requires `HasMemory`. `@validate_output` only needs the base `Agent`.

The type checker then enforces correctness at the decorator application site. Slapping `@inject_history` on a `SummarisationAgent` (which lacks `MemoryMixin`) is a type error - exactly the bug you want caught at dev time, not when `self.history` blows up in production.

{{< include file="full_example.py" lang="python" >}}

`SummarisationAgent` uses `@track_cost` and `@validate_output` - it has `ObservabilityMixin` so it satisfies `HasObservability`, and it extends `Agent` so it satisfies the base bound. `ChatAgent` additionally uses `@inject_history` because it has `MemoryMixin`. `AgentWithoutMemory` at the bottom shows what happens when you get it wrong - pyright rejects it because `Agent[Summary]` alone doesn't satisfy the `HasMemory` protocol.

---

## Common pitfalls

- **TypeVar shadowing across modules:** If decorators in different modules each define their own `R = TypeVar("R")`, the type checker may fail to unify them when stacked. Define a single set of TypeVars in one module and import everywhere.
- **Stacking order breaks when return types change:** If all decorators have identical signatures (`Callable[Concatenate[AgentT, P], R] -> Callable[Concatenate[AgentT, P], R]`), order doesn't matter. If one changes the return type (wrapping in `Result[R]`), the next decorator sees a different `R`. Debug with `reveal_type()` - a special form recognized by mypy/pyright that prints the inferred type during checking (not a runtime function).
- **`P.kwargs` is opaque to the type checker:** At runtime, `kwargs` is a normal mutable dict. But the type checker won't let you treat `P.kwargs` as `dict[str, Any]` - you can't call `kwargs.setdefault()` or index into it without a type error. The type system treats `ParamSpec` kwargs as a sealed contract. Add defaults in the function signature itself, or use `cast`.
- **`@functools.wraps` doesn't affect types:** It copies runtime metadata (`__name__`, `__doc__`), but the type annotations on your wrapper function are what the type checker sees. Use `@wraps` for introspection, rely on annotations for correctness.

---

## TL;DR

| Scenario | Pattern |
|---|---|
| Simple passthrough | `Callable[P, R] -> Callable[P, R]` |
| Decorator with arguments | Outer returns `Callable[[Callable[P, R]], Callable[P, R]]` - triple nesting |
| Decorator accesses `self` | `Concatenate[SelfT, P]` with `SelfT` bound to the base class |
| Decorator accesses mixin state | `Protocol` per decorator, bind `SelfT` to the protocol instead of the base class |
| Stacking decorators | Keep signatures identical across all decorators. Share TypeVars at module level |

What other decorator typing issues have you run into? I'm curious what I've missed.
