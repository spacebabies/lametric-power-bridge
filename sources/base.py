"""Base definitions for power sources - data contracts and protocols"""
from dataclasses import dataclass
from typing import Protocol, AsyncIterator


@dataclass
class PowerReading:
    """
    Uniform data structure for power measurements from any source.

    Attributes:
        power_watts: Power in Watts. Positive = consuming, negative = producing.
        timestamp: ISO8601 timestamp string, optional (depends on source).
    """
    power_watts: float
    timestamp: str | None = None


class PowerSource(Protocol):
    """
    Protocol for ingress sources (Tibber, HomeWizard, P1 Serial, etc).

    Uses Protocol for duck typing - implementations don't need to inherit,
    just implement the methods with matching signatures.
    """

    async def connect(self) -> None:
        """
        Initialize connection to the power source.

        May involve HTTP bootstrap, authentication, device discovery, etc.
        Should raise exceptions if connection fails.
        """
        ...

    async def stream(self) -> AsyncIterator[PowerReading]:
        """
        Stream power readings as they arrive.

        Should be an async generator that yields PowerReading objects.
        Should handle auto-reconnect internally.
        May run indefinitely.
        """
        ...
