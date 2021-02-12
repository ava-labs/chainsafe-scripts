from typing import Optional

from avareporter.models import Transaction


class AvaTransaction(Transaction):
    blockNumber: str
    hash: str
    nonce: str
    fromAddressHash: str
    toAddressHash: Optional[str]
    value: str
    gas: str
    gasPrice: str
    gasUsed: str
    error: Optional[str]
    id: str
    index: int
    status: str
    input: str
    cumulativeGasUsed: str
    createdContractAddressHash: Optional[str]

    @property
    def from_address(self) -> str:
        return self.fromAddressHash.lower()

    @property
    def to_address(self) -> str:
        return self.toAddressHash.lower() if self.toAddressHash is not None else ''

    @property
    def tx_index(self) -> int:
        return self.index

    @property
    def tx_status(self) -> str:
        return self.status

    @property
    def contract_address(self) -> Optional[str]:
        return self.createdContractAddressHash
