from abc import ABC, abstractmethod
from typing import Dict, Any

class ExecutionEngine(ABC):
    """
    Abstract base class enforcing identical execution interfaces across
    paper simulation and live broker routing venues.
    """
    @abstractmethod
    async def submit_order(self, order_params: Dict[str, Any]) -> Dict[str, Any]:
        """Submits an order to the execution venue."""
        pass

    @abstractmethod
    async def modify_order(self, order_id: str, modify_params: Dict[str, Any]) -> Dict[str, Any]:
        """Modifies an open working order."""
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Cancels an existing working order."""
        pass

    @abstractmethod
    async def get_positions(self) -> Dict[str, Any]:
        """Fetches active positions and exposures."""
        pass

    @abstractmethod
    async def get_account_balance(self) -> Dict[str, Any]:
        """Retrieves available liquid capital and margin."""
        pass
