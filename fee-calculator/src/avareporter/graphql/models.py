from typing import Optional

from pydantic import BaseModel

from avareporter.models import Transaction


class AvaTransaction(Transaction):
    block: str
    hash: str
    createdAt: str
    nonce: str
    gasPrice: str
    gasLimit: str
    blockGasUsed: str
    blockGasLimit: str
    blockNonce: str
    blockHash: str
    recipient: str
    value: str
    input: Optional[str]
    toAddr: str
    fromAddr: str
    v: str
    r: str
    s: str

    @property
    def block_number(self) -> str:
        return self.block

    @property
    def gas_limit(self) -> str:
        return self.blockGasLimit

    @property
    def cumulative_gas_used(self) -> str:
        return self.gasLimit

    @property
    def gas_used(self) -> str:
        return self.blockGasUsed

    @property
    def from_address(self) -> str:
        return self.fromAddr.lower()

    @property
    def to_address(self) -> str:
        return self.toAddr.lower() if self.toAddr is not None else ''
