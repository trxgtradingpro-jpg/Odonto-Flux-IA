from abc import ABC, abstractmethod


class LLMProvider(ABC):
    @abstractmethod
    def complete(self, *, task: str, prompt: str) -> dict:
        raise NotImplementedError
