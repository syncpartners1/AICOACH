"""Thread-safe Singleton metaclass used across the autogpt package."""


class Singleton(type):
    """Metaclass that ensures only one instance of a class is created."""

    _instances: dict = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]
