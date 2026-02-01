import logging
from functools import wraps
from typing import Callable, Concatenate, ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")


class Service:
    logger: logging.Logger


SelfT = TypeVar("SelfT", bound=Service)


def with_logging(
    func: Callable[Concatenate[SelfT, P], R],
) -> Callable[Concatenate[SelfT, P], R]:
    @wraps(func)
    def wrapper(self: SelfT, *args: P.args, **kwargs: P.kwargs) -> R:
        self.logger.info(f"Calling {func.__name__}")  # self is typed as SelfT
        return func(self, *args, **kwargs)

    return wrapper


class UserService(Service):
    @with_logging
    def get_user(self, user_id: int) -> dict[str, int]: ...
