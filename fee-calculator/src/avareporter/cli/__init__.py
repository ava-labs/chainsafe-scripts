from typing import Callable, List, Dict

__registered__: Dict[str, Callable] = {}


def script(name: str):
    def _script_wrapper_(func: Callable):
        if name not in __registered__:
            __registered__[name] = func
        else:
            raise RuntimeError("A script with the name {} is already registered, try a different name".format(name))

        return func

    return _script_wrapper_


def script_by_name(name: str) -> Callable:
    return __registered__[name]


def all_scripts() -> List[str]:
    return list(__registered__.keys())

__all__ = [
    "script",
    "script_by_name",
    "all_scripts",
]