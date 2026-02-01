from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable, Concatenate, Generic, ParamSpec, Protocol, TypeVar

# Single set of type variables - shared across all decorators
P = ParamSpec("P")
R = TypeVar("R")
T = TypeVar("T")


@dataclass
class Summary:
    condensed: str


@dataclass
class ChatResponse:
    reply: str


class LLMClient: ...


class ObservabilityMixin:
    def record_cost(self, tokens: int) -> None: ...


class MemoryMixin:
    history: list[dict[str, str]] = []


class HasObservability(Protocol):
    def record_cost(self, tokens: int) -> None: ...


class HasMemory(Protocol):
    history: list[dict[str, str]]


# TypeVars bound to protocols - not to the base class
ObservableT = TypeVar("ObservableT", bound=HasObservability)
MemoryAwareT = TypeVar("MemoryAwareT", bound=HasMemory)
AgentT = TypeVar("AgentT", bound="Agent[Any]")


def track_cost(
    func: Callable[Concatenate[ObservableT, P], R],
) -> Callable[Concatenate[ObservableT, P], R]:
    """Record token usage via self.record_cost. Works on any agent with ObservabilityMixin."""

    @wraps(func)
    def wrapper(self: ObservableT, *args: P.args, **kwargs: P.kwargs) -> R:
        result = func(self, *args, **kwargs)
        self.record_cost(tokens=42)
        return result

    return wrapper


def inject_history(
    func: Callable[Concatenate[MemoryAwareT, P], R],
) -> Callable[Concatenate[MemoryAwareT, P], R]:
    """Prepend conversation history. Only works on agents with MemoryMixin."""

    @wraps(func)
    def wrapper(self: MemoryAwareT, *args: P.args, **kwargs: P.kwargs) -> R:
        # decorator reads self.history - only available via MemoryMixin
        _ = self.history
        return func(self, *args, **kwargs)

    return wrapper


def validate_output(
    func: Callable[Concatenate[AgentT, P], R],
) -> Callable[Concatenate[AgentT, P], R]:
    """Retry on malformed output. Only needs base Agent attributes."""

    @wraps(func)
    def wrapper(self: AgentT, *args: P.args, **kwargs: P.kwargs) -> R:
        result = func(self, *args, **kwargs)
        for _ in range(self.max_validation_retries - 1):
            if self.is_valid(result):
                return result
            result = func(self, *args, **kwargs)
        return result

    return wrapper


class Agent(ABC, Generic[T]):
    llm: LLMClient
    max_validation_retries: int = 3

    def is_valid(self, result: Any) -> bool: ...

    @abstractmethod
    def run(self, prompt: str) -> T: ...


class SummarisationAgent(ObservabilityMixin, Agent[Summary]):
    """Has cost tracking (ObservabilityMixin), but no memory."""

    @track_cost  # ✅ Has ObservabilityMixin → satisfies HasObservability
    @validate_output
    def run(self, prompt: str) -> Summary:
        return Summary(condensed=prompt)


class ChatAgent(ObservabilityMixin, MemoryMixin, Agent[ChatResponse]):
    """Has both cost tracking and conversation memory."""

    @track_cost  # ✅ Has ObservabilityMixin → satisfies HasObservability
    @inject_history  # ✅ Has MemoryMixin → satisfies HasMemory
    @validate_output
    def run(self, prompt: str) -> ChatResponse:
        return ChatResponse(reply=prompt)


class AgentWithoutMemory(Agent[Summary]):
    """
    ❌ Type error
    Argument of type "(self: Self@AgentWithoutMemory, prompt: str) -> Summary" cannot be assigned to parameter "func" of type "(MemoryAwareT@inject_history, **P@inject_history) -> R@inject_history" in function "inject_history"
    Type "(self: Self@AgentWithoutMemory, prompt: str) -> Summary" is not assignable to type "(MemoryAwareT@inject_history, **P@inject_history) -> R@inject_history"
      Parameter 1: type "MemoryAwareT@inject_history" is incompatible with type "Self@AgentWithoutMemory"
        "HasMemory*" is not assignable to "AgentWithoutMemory"basedpyrightreportArgumentType
    """

    @inject_history
    def run(self, prompt: str) -> Summary:
        return Summary(condensed=prompt)
