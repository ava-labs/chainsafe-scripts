from typing import List, Optional

from pydantic import BaseModel

from avareporter.models import Transaction


class EtherscanResult(BaseModel):
    status: str
    message: str


class EthereumSource(BaseModel):
    SourceCode: str
    ABI: str
    ContractName: str
    CompilerVersion: str
    OptimizationUsed: str
    Runs: str
    ConstructorArguments: str
    EVMVersion: str
    Library: str
    LicenseType: str
    Proxy: str
    Implementation: str
    SwarmSource: str


class EthTransaction(Transaction):
    blockNumber: str
    hash: str
    nonce: str
    timeStamp: str
    blockHash: str
    transactionIndex: int
    from_: str
    to: Optional[str]
    value: str
    gas: str
    gasPrice: str
    gasUsed: str
    isError: str
    txreceipt_status: str
    input: str
    contractAddress: Optional[str]
    cumulativeGasUsed: str
    confirmations: str

    class Config:
        fields = {
            'from_': 'from'
        }

    @property
    def from_address(self) -> str:
        return self.from_.lower()

    @property
    def to_address(self) -> Optional[str]:
        return self.to.lower()

    @property
    def tx_index(self) -> int:
        return self.transactionIndex

    @property
    def tx_status(self) -> str:
        return self.txreceipt_status

    @property
    def contract_address(self) -> Optional[str]:
        return self.contractAddress


class EtherscanContractResult(EtherscanResult):
    result: List[EthereumSource]


class EtherscanAccountTransactionsResult(EtherscanResult):
    result: List[EthTransaction]


