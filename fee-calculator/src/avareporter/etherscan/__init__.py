from typing import Optional

import requests
from avareporter.etherscan.models import EthereumSource, EtherscanResult, EtherscanAccountTransactionsResult, EtherscanContractResult


def get_contract_source(address: str, api_key: str) -> EtherscanContractResult:
    url = "https://api.etherscan.io/api?module=contract&action=getsourcecode&address={}&apikey={}".format(address, api_key)

    resp = requests.get(url)
    data = resp.json()

    return EtherscanContractResult(**data)


def get_transactions_by_account(address: str, api_key: str = 'UF9IAYD4IHATIXQ3IAW1BMEJX3YSK83SZJ',
                                start_block: int = 0, end_block: int = 99999999999999999999,
                                sort: str = 'asc') -> EtherscanAccountTransactionsResult:
    url = "https://api.etherscan.io/api?module=account&action=txlist&address={}&startblock={}&endblock={}&sort={}&apikey={}".format(address, start_block, end_block, sort, api_key)

    resp = requests.get(url)
    data = resp.json()

    return EtherscanAccountTransactionsResult(**data)


__all__ = [
    'EtherscanAccountTransactionsResult',
    'EtherscanContractResult',
    'EthereumSource',
    'EtherscanResult',
    'get_transactions_by_account',
    'get_contract_source'
]