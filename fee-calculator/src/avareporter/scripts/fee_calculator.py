import configparser
import csv
from typing import List, Dict, Tuple

from pydantic import BaseModel
from web3 import Web3

from avareporter.cli import script
import avareporter.etherscan as es
import avareporter.graphql as ava
from avareporter.models import Transaction


class Result(BaseModel):
    reward: int
    gasPercent: float
    gasUsed: float


class AllResults(BaseModel):
    results: Dict[str, Result]
    start_block: int
    end_block: int


class BothResults(BaseModel):
    eth_results: AllResults
    ava_results: AllResults


def fee_calculate(addresses: List[str], multisig_only: List[str],
                  multisig_transactions: List[Transaction],
                  bridge_transactions: List[Transaction]) -> Tuple[Dict[str, float], float]:
    all_transactions = multisig_transactions + bridge_transactions
    filtered_transactions = list(filter(
        lambda t: t.from_address in addresses or t.to_address in addresses,
        all_transactions
    ))
    multisig_only_transactions = list(filter(
        lambda t: t.from_address in multisig_only or t.to_address in multisig_only,
        multisig_transactions
    ))

    total_gas = sum(int(t.gasUsed) for t in filtered_transactions + multisig_only_transactions)

    all_users = {
        address: sum(int(t.gasUsed) for t in
                                 filter(lambda t: t.from_address == address or t.to_address == address,
                                        filtered_transactions)) / total_gas
        for address in addresses
    }

    multisig_only_users = {
        address: sum(int(t.gasUsed) for t in
                                 filter(lambda t: t.from_address == address or t.to_address == address,
                                        multisig_only_transactions)) / total_gas
        for address in multisig_only
    }

    all_users.update(multisig_only_users)
    
    # Remove assert
    # assert(sum(i for i in all_users.values()) == 1.0)

    return all_users, total_gas


@script('fee-calculator')
def execute():
    config = configparser.ConfigParser()
    config.read('config.ini')

    addresses = config['fee_calculator']['addresses'].split(',')
    multisig_only = config['fee_calculator']['multisig_only_addresses'].split(',')
    eth_multisig_address = config['fee_calculator']['eth_multisig_address']
    ava_multisig_address = config['fee_calculator']['ava_multisig_address']
    eth_bridge_address = config['fee_calculator']['eth_bridge_address']
    ava_bridge_address = config['fee_calculator']['ava_bridge_address']
    eth_start_block = int(config['fee_calculator']['eth_start_block'])
    ava_start_block = int(config['fee_calculator']['ava_start_block'])
    eth_end_block = config['fee_calculator']['eth_end_block']
    ava_end_block = config['fee_calculator']['ava_end_block']
    eth_rpc_url = config['fee_calculator']['eth_rpc_url']
    ava_rpc_url = config['fee_calculator']['ava_rpc_url']
    output_csv = bool(config['fee_calculator']['output_csv'])
    output_json = bool(config['fee_calculator']['output_json'])
    output_stdout = bool(config['fee_calculator']['output_stdout'])

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

    # Map all addresses to be lowercase
    addresses = list(map(lambda s: s.lower().strip(), addresses))
    multisig_only = list(map(lambda s: s.lower().strip(), multisig_only))

    print("Grabbing all Ethereum Multisig transactions via Etherscan")
    eth_multisig_transactions = es.get_transactions_by_account(eth_multisig_address, start_block=eth_start_block,
                                                               end_block=eth_end_block).result

    print("Grabbing all Ethereum Bridge transactions via Etherscan")
    eth_bridge_transactions = es.get_transactions_by_account(eth_bridge_address, start_block=eth_start_block,
                                                             end_block=eth_end_block).result

    print("Grabbing all Avalanche Multisig transactions via Avascanner")
    ava_multisig_transactions = ava.get_all_transactions_by_address(ava_multisig_address, start_block=ava_start_block,
                                                                    end_block=ava_end_block)

    print("Grabbing all Avalanche Bridge transactions via Avascanner")
    ava_bridge_transactions = ava.get_all_transactions_by_address(ava_bridge_address, start_block=ava_start_block,
                                                                  end_block=ava_end_block)

    print("Calculating Ethereum fees and total gas")
    eth_results, eth_total_gas = fee_calculate(addresses, multisig_only, eth_multisig_transactions, eth_bridge_transactions)
    print("Calculating Avalanche fees and total gas")
    ava_results, ava_total_gas = fee_calculate(addresses, multisig_only, ava_multisig_transactions, ava_bridge_transactions)

    print("Grabbing balance of Ethereum bridge")
    eth_balance = eth_web3.eth.get_balance(eth_bridge_address)
    print("Grabbing balance of Avalanche bridge")
    ava_balance = ava_web3.eth.get_balance(ava_bridge_address)

    print("Formatting Ethereum results")
    final_eth_results = {
        address: Result(reward=value * ava_balance, gasPercent=value * 100, gasUsed=value * eth_total_gas)
        for address, value in eth_results.items()
    }

    print("Formatting Avalanche results")
    final_ava_results = {
        address: Result(reward=value * eth_balance, gasPercent=value * 100, gasUsed=value * ava_total_gas)
        for address, value in ava_results.items()
    }

    if not output_csv and not output_json and not output_stdout:
        # Default to stdout
        print("Defaulting to STDOUT")
        output_stdout = True

    if output_csv:
        print("Writing CSV files")
        with open('eth_fee_distribution.csv', mode='w', newline='') as f:
            csv_writer = csv.writer(f, delimiter=',', quoting=csv.QUOTE_ALL)
            csv_writer.writerow(['Address', 'Reward (Wei)', 'Reward (Avax)', 'Gas Percentage', 'Gas Used', 'Start Block', "End Block"])
            for address, value in final_eth_results.items():
                csv_writer.writerow([address, value.reward, Web3.fromWei(value.reward, 'ether'), value.gasPercent, value.gasUsed, eth_start_block, eth_end_block])

        with open('ava_fee_distribution.csv', mode='w', newline='') as f:
            csv_writer = csv.writer(f, delimiter=',', quoting=csv.QUOTE_ALL)
            csv_writer.writerow(['Address', 'Reward (Wei)', 'Reward (ETH)', 'Gas Percentage', 'Gas Used', 'Start Block', "End Block"])
            for address, value in final_ava_results.items():
                csv_writer.writerow([address, value.reward, Web3.fromWei(value.reward, 'ether'), value.gasPercent, value.gasUsed, ava_start_block, ava_end_block])

    if output_json:
        print("Writing JSON files")
        with open('eth_fee_distribution.json', mode='w') as f:
            temp = AllResults(results=final_eth_results, start_block=eth_start_block, end_block=eth_end_block)
            f.write(temp.json())

        with open('ava_fee_distribution.json', mode='w') as f:
            temp = AllResults(results=final_ava_results, start_block=ava_start_block, end_block=ava_end_block)
            f.write(temp.json())

    if output_stdout:
        temp = BothResults(eth_results=AllResults(results=final_eth_results,
                                                  start_block=eth_start_block, end_block=eth_end_block),
                           ava_results=AllResults(results=final_ava_results,
                                                  start_block=ava_start_block, end_block=ava_end_block))

        print(temp.json())

