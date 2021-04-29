from typing import Optional

from pydantic import BaseModel


class Transaction(BaseModel):
    hash: str
    nonce: str
    value: str
    gasPrice: str
    input: str

    @property
    def block_number(self) -> str:
        raise NotImplemented()

    @property
    def gas_limit(self) -> str:
        raise NotImplemented()

    @property
    def cumulative_gas_used(self) -> str:
        raise NotImplemented()

    @property
    def gas_used(self) -> str:
        raise NotImplemented()

    @property
    def from_address(self) -> str:
        raise NotImplemented()

    @property
    def to_address(self) -> Optional[str]:
        raise NotImplemented()
