import configparser
import io
from pathlib import Path

from avareporter.cli import script
from avareporter.abis import multisig, bridge_abi, erc20_abi, handler_abi
from web3 import Web3
import avareporter.etherscan as es
import json

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
eth_rpc_url = https://mainnet.infura.io/v3/f8a5ed81ee9940fdaa7d07ee801ba1ef
ava_rpc_url = https://avalanche--mainnet--rpc.datahub.figment.io/apikey/13b0a6af4b9e9f4406aafe275a5ed692/ext/bc/C/rpc
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

    usdt = eth_web3.eth.contract(address=Web3.toChecksumAddress('0xdac17f958d2ee523a2206206994597c13d831ec7'), abi=erc20_abi)
    eth_bridge = eth_web3.eth.contract(address=Web3.toChecksumAddress(eth_bridge_address), abi=bridge_abi)
    eth_handler = eth_web3.eth.contract(address=Web3.toChecksumAddress('0x6147F5a1a4eEa5C529e2F375Bd86f8F58F8Bc990'), abi=handler_abi)

    transfer_event_filter = usdt.events.Transfer.createFilter(fromBlock=11688193, toBlock='latest', argument_filters={
        'to': Web3.toChecksumAddress('0xdAC7Bb7Ce4fF441A235F08408e632FA1D799A147')
    })

    deposit_event_filter = eth_bridge.events.Deposit.createFilter(fromBlock=11688193, toBlock='latest')

    raw_transfer_events = transfer_event_filter.get_all_entries()

    raw_deposit_events = deposit_event_filter.get_all_entries()

    resource_id_cache = {}
    deposit_cache = {}

    # _resourceIDToTokenContractAddress
    for deposit in raw_deposit_events:
        resource_id = deposit.args.resourceID
        if resource_id not in resource_id_cache:
            token_address = eth_handler.functions._resourceIDToTokenContractAddress(resource_id)
            resource_id_cache[resource_id] = token_address

        block = deposit.blockHash
        if block not in deposit_cache:
            deposit_cache[block] = {}

        tx = deposit.transactionHash

        deposit_cache[block][tx] = deposit

    transfer_events = []

    total_value = 0
    for event in raw_transfer_events:
        if event.args['from'] == eth_bridge_address:
            continue

        block = event.blockHash
        tx = event.transactionHash

        if block in deposit_cache:
            if tx in deposit_cache[block]:
                continue

        total_value += event.args['value']
        transfer_events.append({
            'from': event.args['from'],
            'to': event.args['to'],
            'value': event.args['value'],
            'blockNumber': event.blockNumber,
            'blockHash': event.blockHash.hex(),
            'transaction': event.transactionHash.hex()
        })

    with open('usdt_transfers.json', mode='w') as f:
        json.dump(transfer_events, f)

    print("Total USDT Transferred")
    print((total_value / 1e6))

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
    eth_bridge_contract = eth_web3.eth.contract(address=eth_bridge_address, abi=bridge_abi)

    print("Looking for adminWithdrawal in exec transactions")
    admin_withdrawals = []
    withdrawals = {}
    for tx in exec_transactions:
        _, normalized_input = eth_multisig_contract.decode_function_input(tx.input)

        transaction_data = Web3.toHex(normalized_input['data'])

        if transaction_data.startswith('0x780cf004'):
            admin_withdrawals.append(transaction_data)
            _, normalized_withdrawal_input = eth_bridge_contract.decode_function_input(transaction_data)

            token = normalized_withdrawal_input['tokenAddress']
            amount = normalized_withdrawal_input['amountOrTokenID']
            if token not in withdrawals:
                withdrawals[token] = amount
            else:
                withdrawals[token] += amount

    for token, value in withdrawals.items():
        token_contract = eth_web3.eth.contract(address=token, abi=erc20_abi)

        name = token_contract.functions.name().call()
        symbol = token_contract.functions.symbol().call()
        decimals = token_contract.functions.decimals().call()

        withdrawals[token] = {
            'name': name,
            'symbol': symbol,
            'decimals': decimals,
            'amountWithdrawn': value / (10**decimals),
            'amountWithdrawnRaw': value
        }

        print("Total Admin Withdrawal for " + name)
        print(str(value / (10**decimals)) + " " + symbol)

    print("Final totals")
    print(withdrawals)
