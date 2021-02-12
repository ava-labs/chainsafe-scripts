from typing import Optional

from pydantic import BaseModel


class Transaction(BaseModel):
    blockNumber: str
    hash: str
    nonce: str
    value: str
    gas: str
    gasPrice: str
    input: str
    cumulativeGasUsed: str
    gasUsed: str

    @property
    def from_address(self) -> str:
        raise NotImplemented()

    @property
    def to_address(self) -> Optional[str]:
        raise NotImplemented()

    @property
    def tx_index(self) -> int:
        raise NotImplemented()

    @property
    def tx_status(self) -> str:
        raise NotImplemented()

    @property
    def contract_address(self) -> Optional[str]:
        raise NotImplemented()
