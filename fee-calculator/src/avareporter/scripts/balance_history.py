import configparser
import io
from pathlib import Path

from avareporter.cli import script
from avareporter.abis import multisig, eth_bridge_abi, erc20
from web3 import Web3
import avareporter.etherscan as es

# temp because cant read file
config_data = """
[bridge_data]
addresses = 0x8c14EdCC7bFdDB43a4d6Cb36c25c3B4F30D8B121,0x5069Ac8c8aFe3cF32e889F2f887FF8549593044f,0x773EBE37332aF018b4A2FCAe4ECA0d747d0722d3,0xFF1941fb64A91568fC69Fe8f723f19Fa584d1Fc5,0x83e461899d4C6E28E26576b717a22fE9944ec852
multisig_only_addresses = 0xf77ACF8b76345CeFD22324dfB3404b81D982574d,0xf0414c9846c25894D89DA41267f1C21e6E829164,0x03EE42Ed02fDDC2345aB7b64299fdA4FA817C4AD,0x97475851fc6424287ff8a1df05bbbe6bcee8f686,0x24dA883FeD6FE099EdFe305f1906b58FEC6B8903
eth_start_block = 0
eth_end_block   = latest
ava_start_block = 1113166
ava_end_block   = 1305926
eth_bridge_address = 0x96B845aBE346b49135B865E5CeDD735FC448C3aD
ava_bridge_address = 0x6460777cDa22AD67bBb97536FFC446D65761197E
eth_multisig_address = 0xfD018E845DD2A5506C438438AFA88444Cf7A8D89
ava_multisig_address = 0x751e9AD7DdA35EC5217fc2D1951a5FFB0617eafE
output_csv = True
output_json = True
output_stdout = True
eth_rpc_url = <FILL>
ava_rpc_url = <FILL>
"""


@script('balance-checker')
def execute():
    config = configparser.ConfigParser()
    config.read_string(config_data)

    addresses = config['bridge_data']['addresses'].split(',')
    multisig_only = config['bridge_data']['multisig_only_addresses'].split(',')
    eth_multisig_address = config['bridge_data']['eth_multisig_address']
    ava_multisig_address = config['bridge_data']['ava_multisig_address']
    eth_bridge_address = config['bridge_data']['eth_bridge_address']
    ava_bridge_address = config['bridge_data']['ava_bridge_address']
    eth_start_block = int(config['bridge_data']['eth_start_block'])
    ava_start_block = int(config['bridge_data']['ava_start_block'])
    eth_end_block = config['bridge_data']['eth_end_block']
    ava_end_block = config['bridge_data']['ava_end_block']
    eth_rpc_url = config['bridge_data']['eth_rpc_url']
    ava_rpc_url = config['bridge_data']['ava_rpc_url']
    output_csv = bool(config['bridge_data']['output_csv'])
    output_json = bool(config['bridge_data']['output_json'])
    output_stdout = bool(config['bridge_data']['output_stdout'])

    eth_web3 = Web3(Web3.HTTPProvider(eth_rpc_url))
    ava_web3 = Web3(Web3.HTTPProvider(ava_rpc_url))

    if eth_end_block == 'latest':
        eth_end_block = eth_web3.eth.blockNumber
    else:
        eth_end_block = int(eth_end_block)

    if ava_end_block == 'latest':
        ava_end_block = ava_web3.eth.blockNumber
    else:
        ava_end_block = int(ava_end_block)

    print("Grabbing all Ethereum Multisig transactions via Etherscan")
    eth_multisig_transactions = es.get_transactions_by_account(eth_multisig_address, start_block=eth_start_block,
                                                               end_block=eth_end_block).result

    print("Filtering for exec transaction calls")
    exec_transactions = list(filter(lambda t: t.input.startswith('0x6a761202'), eth_multisig_transactions))

    eth_multisig_contract = eth_web3.eth.contract(address=eth_multisig_address, abi=multisig)
    eth_bridge_contract = eth_web3.eth.contract(address=eth_bridge_address, abi=eth_bridge_abi)

    print("Looking for adminWithdrawal in exec transactions")
    admin_withdrawals = []
    withdrawals = {}
    for tx in exec_transactions:
        _, normalized_input = eth_multisig_contract.decode_function_input(tx.input)

        transaction_data = Web3.toHex(normalized_input['data'])

        if transaction_data.startswith('0x780cf004'):
            admin_withdrawals.append(transaction_data)
            _, normalized_withdrawal_input = eth_bridge_contract.decode_function_input(transaction_data)

            token = normalized_withdrawal_input['tokenAddress'].lower()
            amount = normalized_withdrawal_input['amountOrTokenID']
            if token not in withdrawals:
                withdrawals[token] = amount
            else:
                withdrawals[token] += amount

    print("Final totals")
    print(withdrawals)

    print("Total for USDT")
    print(withdrawals['0xdac17f958d2ee523a2206206994597c13d831ec7'.lower()])
