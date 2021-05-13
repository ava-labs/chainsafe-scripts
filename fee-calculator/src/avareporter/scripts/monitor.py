import configparser
import json
import time
from dataclasses import dataclass, asdict
from enum import Enum
from functools import partial
from multiprocessing import Pool
from multiprocessing.pool import ThreadPool
from typing import List, Set, Dict, Optional
from pathlib import Path

import requests
from requests import Response
from tqdm.contrib.concurrent import process_map, thread_map

from hexbytes import HexBytes
from web3.contract import Contract

from avareporter.abis import bridge_abi
from web3 import Web3
from avareporter.cli import script
import logging
from logging.config import fileConfig
from logging.config import dictConfig


# temp because cant read file
config_data = """
[monitor]
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
sleep_time = 10
eth_chain_id = 1
ava_chain_id = 2
eth_handler = 0xdAC7Bb7Ce4fF441A235F08408e632FA1D799A147
ava_handler = 0x6147F5a1a4eEa5C529e2F375Bd86f8F58F8Bc990
worker_count = 5
use_child_processes = True
active_proposal_block_alert = 100
passed_proposal_block_alert = 100
"""

CHAIN_NAMES = {
    1: 'Ethereum',
    2: 'Avalanche',
}


EMPTY_BYTES32 = b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'


class ProposalStatus(Enum):
    Inactive = 0
    Active = 1
    Passed = 2
    Executed = 3
    Cancelled = 4


@dataclass
class Proposal:
    resource_id: HexBytes
    data_hash: HexBytes
    yes_votes: List[str]
    no_votes: List[str]
    status: ProposalStatus
    proposed_block: int
    deposit_nonce: int
    deposit_block: Optional[int]
    deposit_transaction_hash: Optional[str]

    def __hash__(self):
        return self.deposit_transaction_hash

    def __cmp__(self, other: 'Proposal'):
        return other.deposit_transaction_hash == self.deposit_transaction_hash


@dataclass
class Bridge:
    contract: Contract
    chain_id: int
    handler: str

    def __setstate__(self, state):
        self.chain_id = state['chain_id']
        self.handler = state['handler']

        web3 = Web3(state['web3']['type'](state['web3']['arg1']))

        self.contract = web3.eth.contract(address=state['web3']['address'], abi=bridge_abi)

    def __getstate__(self):
        provider_type = type(self.contract.web3.provider)
        if isinstance(self.contract.web3.provider, Web3.HTTPProvider) or isinstance(self.contract.web3.provider, Web3.WebsocketProvider):
            p: Web3.HTTPProvider = self.contract.web3.provider
            arg1 = p.endpoint_uri

        return {
            'chain_id': self.chain_id,
            'handler': self.handler,
            'web3': {
                'type': provider_type,
                'arg1': arg1,
                'address': self.contract.address
            }
        }


@dataclass
class MonitorState:
    active_proposals: Dict[int, List[Proposal]]
    passed_proposals: Dict[int, List[Proposal]]
    ava_deposit_count: int = 0
    eth_deposit_count: int = 0
    backup_count: int = 0

    def save(self):
        save_state = Path('.state')
        if save_state.exists():
            backup_state = Path(f'.state.backup.{self.backup_count}')
            save_state.rename(backup_state)

            self.backup_count += 1

        with open(str(save_state.absolute()), mode='w') as f:
            json.dump(asdict(self), f)


@dataclass
class State:
    monitor: MonitorState
    eth_bridge: Bridge
    ava_bridge: Bridge
    config: configparser.ConfigParser


def load_or_new_state() -> MonitorState:
    save_state = Path('.state')
    if not save_state.exists():
        return MonitorState(watched_proposals=set(), watching_proposals=list())

    with open(str(save_state.absolute()), mode='r') as f:
        data = json.load(f)

    return MonitorState(**data)


def fetch_proposal(origin_bridge: Bridge, destination_bridge: Bridge, nonce: int) -> Proposal:
    try:
        logger = logging.getLogger('fetch_proposal')
        records = origin_bridge.contract.functions._depositRecords(nonce, destination_bridge.chain_id).call()

        hash = Web3.solidityKeccak(['address', 'bytes'], [destination_bridge.handler, records])

        raw_proposal = destination_bridge.contract.functions.getProposal(origin_bridge.chain_id, nonce, hash.hex()).call()

        event_filter = origin_bridge.contract.events.Deposit.createFilter(fromBlock=0, toBlock='latest', argument_filters={
            'depositNonce': nonce
        })

        events = event_filter.get_all_entries()

        if len(events) == 0:
            logger.warning(f'Deposit {nonce} not found on Origin Chain {CHAIN_NAMES[origin_bridge.chain_id]}')
            deposit_block = None
            deposit_transaction_hash = None
        elif len(events) > 1:
            logger.warning(f'Multiple Deposit events with the nonce {nonce} found on Origin Chain {CHAIN_NAMES[origin_bridge.chain_id]}')
            deposit_block = None
            deposit_transaction_hash = None
        else:
            event = events[0]

            if event.args is not None:
                if event.args.resourceID != raw_proposal[0]:
                    logger.warning(f'Deposit event found, but proposal resource ID mismatch')
                    deposit_block = None
                    deposit_transaction_hash = None
                elif event.args.destinationChainID != destination_bridge.chain_id:
                    logger.warning(f'Deposit event found, but proposal resource ID mismatch')
                    deposit_block = None
                    deposit_transaction_hash = None
                else:
                    deposit_block = event.blockNumber
                    deposit_transaction_hash = event.transactionHash
            else:
                logger.warning(f'Deposit event found, but unverified (no data in event)')
                deposit_block = event.blockNumber
                deposit_transaction_hash = event.transactionHash

        return Proposal(
            resource_id=raw_proposal[0],
            data_hash=raw_proposal[1],
            yes_votes=raw_proposal[2],
            no_votes=raw_proposal[3],
            status=ProposalStatus(raw_proposal[4]),
            proposed_block=raw_proposal[5],
            deposit_nonce=nonce,
            deposit_block=deposit_block,
            deposit_transaction_hash=deposit_transaction_hash
        )
    except requests.exceptions.HTTPError as e:
        r: Response = e.response
        if r.status_code == 429:
            time.sleep(5)
            return fetch_proposal(origin_bridge, destination_bridge, nonce)  # Try again
        raise e


def find_all_new_proposals(current_state: State) -> Dict[int, List[Proposal]]:
    logger = logging.getLogger('fetch_new_proposals')

    eth_bridge = current_state.eth_bridge
    ava_bridge = current_state.ava_bridge

    eth_bridge_contract = eth_bridge.contract
    ava_bridge_contract = ava_bridge.contract

    eth_chain_id = eth_bridge.chain_id
    ava_chain_id = ava_bridge.chain_id

    state = current_state.monitor

    worker_count = int(current_state.config['monitor']['worker_count'])
    use_multiprocessing = bool(current_state.config['monitor']['use_child_processes'])

    map_func = process_map if use_multiprocessing else thread_map

    logger.debug('Grabbing deposit counts')

    # eth -> ava
    ava_deposit_count = eth_bridge_contract.functions._depositCounts(ava_chain_id).call()
    # ava -> eth
    eth_deposit_count = ava_bridge_contract.functions._depositCounts(eth_chain_id).call()

    logger.info('ETH -> AVA Deposits: ' + str(ava_deposit_count))
    logger.info('AVA -> ETH Deposits: ' + str(eth_deposit_count))

    proposals = {
        eth_chain_id: [],
        ava_chain_id: []
    }
    if state.ava_deposit_count > ava_deposit_count:
        logger.error('Saved state has more deposit counts than what blockchain reported!')
    elif state.ava_deposit_count < ava_deposit_count:
        new_eth_proposals = map_func(partial(fetch_proposal, eth_bridge, ava_bridge),
                                     range(state.ava_deposit_count, ava_deposit_count),
                                     max_workers=worker_count, chunksize=50)

        proposals[eth_chain_id] = new_eth_proposals

    if state.eth_deposit_count > eth_deposit_count:
        logger.error('Saved state has more deposit counts than what blockchain reported!')
    elif state.eth_deposit_count < eth_deposit_count:
        new_ava_proposals = map_func(partial(fetch_proposal, ava_bridge, eth_bridge),
                                     range(state.eth_deposit_count, eth_deposit_count),
                                     max_workers=worker_count, chunksize=50)
        proposals[ava_chain_id] = new_ava_proposals

    state.ava_deposit_count = ava_deposit_count
    state.eth_deposit_count = eth_deposit_count

    return proposals


def expired_proposals(current_state: State, proposals: Dict[int, List[Proposal]]):
    logger = logging.getLogger('expired_proposals')

    eth_bridge = current_state.eth_bridge
    ava_bridge = current_state.ava_bridge

    eth_chain_id = eth_bridge.chain_id
    ava_chain_id = ava_bridge.chain_id

    logger.debug('Searching for expired proposals on Ethereum')

    for proposal in proposals[eth_chain_id]:
        if proposal.status == ProposalStatus.Cancelled:
            logger.warning(f'[Ethereum] Proposal Expired; Deposit Block: {proposal.deposit_block} '
                           f'Deposit Transaction: {proposal.deposit_transaction_hash} '
                           f'Proposed Block: {proposal.proposed_block} '
                           f'Resource ID: {proposal.resource_id.hex()} Data Hash: {proposal.data_hash.hex()} '
                           f'Yes Votes: {len(proposal.yes_votes)} No Votes: {len(proposal.no_votes)}')


    logger.debug('Searching for expired proposals on Avalanche')

    for proposal in proposals[ava_chain_id]:
        if proposal.status == ProposalStatus.Cancelled:
            logger.warning(f'[Avalanche] Proposal Expired; Deposit Block: {proposal.deposit_block} '
                           f'Deposit Transaction: {proposal.deposit_transaction_hash} '
                           f'Proposed Block: {proposal.proposed_block} '
                           f'Resource ID: {proposal.resource_id.hex()} Data Hash: {proposal.data_hash.hex()} '
                           f'Yes Votes: {len(proposal.yes_votes)} No Votes: {len(proposal.no_votes)}')


def watch_active_proposals(current_state: State, proposals: Dict[int, List[Proposal]]):
    logger = logging.getLogger('watch_active_proposals')

    eth_bridge = current_state.eth_bridge
    ava_bridge = current_state.ava_bridge

    eth_chain_id = eth_bridge.chain_id
    ava_chain_id = ava_bridge.chain_id

    logger.debug('Searching for new active proposals on Ethereum')

    for proposal in proposals[eth_chain_id]:
        if proposal.status == ProposalStatus.Active and proposal not in current_state.monitor.active_proposals[eth_chain_id]:
            current_state.monitor.active_proposals[eth_chain_id].append(proposal)

    logger.debug('Searching for new active proposals on Avalanche')

    for proposal in proposals[ava_chain_id]:
        if proposal.status == ProposalStatus.Active and proposal not in current_state.monitor.active_proposals[ava_chain_id]:
            current_state.monitor.active_proposals[ava_chain_id].append(proposal)


def watch_passed_proposals(current_state: State, proposals: Dict[int, List[Proposal]]):
    logger = logging.getLogger('watch_passed_proposals')

    eth_bridge = current_state.eth_bridge
    ava_bridge = current_state.ava_bridge

    eth_chain_id = eth_bridge.chain_id
    ava_chain_id = ava_bridge.chain_id

    logger.debug('Searching for new passed proposals on Ethereum')

    for proposal in proposals[eth_chain_id]:
        if proposal.status == ProposalStatus.Active and proposal not in current_state.monitor.passed_proposals[eth_chain_id]:
            current_state.monitor.passed_proposals[eth_chain_id].append(proposal)

            logger.debug("Checking if we are already watching the active proposal")


    logger.debug('Searching for new passed proposals on Avalanche')

    for proposal in proposals[ava_chain_id]:
        if proposal.status == ProposalStatus.Active and proposal not in current_state.monitor.passed_proposals[ava_chain_id]:
            current_state.monitor.passed_proposals[ava_chain_id].append(proposal)


def check_active_proposals(current_state: State):
    logger = logging.getLogger('check_active_proposals')

    active_proposal_block_alert = int(current_state.config['monitor']['active_proposal_block_alert'])

    eth_bridge = current_state.eth_bridge
    ava_bridge = current_state.ava_bridge

    eth_chain_id = eth_bridge.chain_id
    ava_chain_id = ava_bridge.chain_id

    eth_latest_block = current_state.eth_bridge.contract.web3.eth.block_number
    ava_latest_block = current_state.ava_bridge.contract.web3.eth.block_number

    logger.debug('Checking active Ethereum proposals')

    for proposal in current_state.monitor.active_proposals[eth_chain_id][:]:
        current_proposal_state = fetch_proposal(current_state.eth_bridge, current_state.ava_bridge, proposal.deposit_nonce)

        if current_proposal_state.status != proposal.status:
            current_state.monitor.active_proposals[eth_chain_id].remove(proposal)
            if current_proposal_state.status == ProposalStatus.Passed:
                current_state.monitor.passed_proposals[eth_chain_id].append(current_proposal_state)
            continue

        block_elapsed = eth_latest_block - current_proposal_state.proposed_block

        if block_elapsed >= active_proposal_block_alert:
            logger.warning(f'[Ethereum] Proposal has remained active for {block_elapsed} blocks')

    logger.debug('Checking active Avalanche proposals')

    for proposal in current_state.monitor.active_proposals[ava_chain_id][:]:
        current_proposal_state = fetch_proposal(current_state.ava_bridge, current_state.eth_bridge, proposal.deposit_nonce)

        if current_proposal_state.status != proposal.status:
            current_state.monitor.active_proposals[ava_chain_id].remove(proposal)
            if current_proposal_state.status == ProposalStatus.Passed:
                current_state.monitor.passed_proposals[ava_chain_id].append(current_proposal_state)
            continue

        block_elapsed = ava_latest_block - current_proposal_state.proposed_block

        if block_elapsed >= active_proposal_block_alert:
            logger.warning(f'[Avalanche] Proposal has remained active for {block_elapsed} blocks')


def check_passed_proposals(current_state: State):
    logger = logging.getLogger('check_active_proposals')

    passed_proposal_block_alert = int(current_state.config['monitor']['passed_proposal_block_alert'])

    eth_bridge = current_state.eth_bridge
    ava_bridge = current_state.ava_bridge

    eth_chain_id = eth_bridge.chain_id
    ava_chain_id = ava_bridge.chain_id

    eth_latest_block = current_state.eth_bridge.contract.web3.eth.block_number
    ava_latest_block = current_state.ava_bridge.contract.web3.eth.block_number

    logger.debug('Checking passed Ethereum proposals')

    for proposal in current_state.monitor.passed_proposals[eth_chain_id][:]:
        current_proposal_state = fetch_proposal(current_state.eth_bridge, current_state.ava_bridge, proposal.deposit_nonce)

        if current_proposal_state.status != proposal.status:
            current_state.monitor.passed_proposals[eth_chain_id].remove(proposal)
            continue

        block_elapsed = eth_latest_block - current_proposal_state.proposed_block

        if block_elapsed >= passed_proposal_block_alert:
            logger.warning(f'[Ethereum] Proposal has remained passed for {block_elapsed} blocks')

    logger.debug('Checking passed Avalanche proposals')

    for proposal in current_state.monitor.passed_proposals[ava_chain_id][:]:
        current_proposal_state = fetch_proposal(current_state.ava_bridge, current_state.eth_bridge, proposal.deposit_nonce)

        if current_proposal_state.status != proposal.status:
            current_state.monitor.passed_proposals[ava_chain_id].remove(proposal)
            continue

        block_elapsed = ava_latest_block - current_proposal_state.proposed_block

        if block_elapsed >= passed_proposal_block_alert:
            logger.warning(f'[Avalanche] Proposal has remained passed for {block_elapsed} blocks')


@script('monitor')
def execute():
    config = configparser.ConfigParser()
    config.read_string(config_data)

    logging_config = Path('logging.conf')
    if logging_config.exists():
        fileConfig(str(logging_config.absolute()))
    else:
        dictConfig(dict(
            version=1,
            formatters={
                'f': {'format':
                          '%(asctime)s %(name)-12s %(levelname)-8s %(message)s'}
            },
            handlers={
                'h': {'class': 'logging.StreamHandler',
                      'formatter': 'f',
                      'level': logging.DEBUG}
            },
            root={
                'handlers': ['h'],
                'level': logging.DEBUG,
            }
        ))

    logger = logging.getLogger('WATCHER')

    addresses = config['monitor']['addresses'].split(',')
    multisig_only = config['monitor']['multisig_only_addresses'].split(',')
    eth_multisig_address = config['monitor']['eth_multisig_address']
    ava_multisig_address = config['monitor']['ava_multisig_address']
    eth_bridge_address = config['monitor']['eth_bridge_address']
    ava_bridge_address = config['monitor']['ava_bridge_address']
    eth_start_block = int(config['monitor']['eth_start_block'])
    ava_start_block = int(config['monitor']['ava_start_block'])
    eth_end_block = config['monitor']['eth_end_block']
    ava_end_block = config['monitor']['ava_end_block']
    eth_rpc_url = config['monitor']['eth_rpc_url']
    ava_rpc_url = config['monitor']['ava_rpc_url']
    output_csv = bool(config['monitor']['output_csv'])
    output_json = bool(config['monitor']['output_json'])
    output_stdout = bool(config['monitor']['output_stdout'])
    sleep_time = int(config['monitor']['sleep_time'])
    eth_chain_id = int(config['monitor']['eth_chain_id'])
    ava_chain_id = int(config['monitor']['ava_chain_id'])
    eth_handler = config['monitor']['eth_handler']
    ava_handler = config['monitor']['ava_handler']

    logger.debug('Connecting to ETH Web3')
    eth_web3 = Web3(Web3.HTTPProvider(eth_rpc_url))
    logger.debug('Connecting to AVA Web3')
    ava_web3 = Web3(Web3.HTTPProvider(ava_rpc_url))

    logger.debug('Building contract instances')
    eth_bridge_contract = eth_web3.eth.contract(address=eth_bridge_address, abi=bridge_abi)
    ava_bridge_contract = ava_web3.eth.contract(address=ava_bridge_address, abi=bridge_abi)

    logger.debug("Building ETH Bridge Data")
    eth_bridge = Bridge(contract=eth_bridge_contract, chain_id=eth_chain_id, handler=eth_handler)

    logger.debug("Building AVA Bridge Data")
    ava_bridge = Bridge(contract=ava_bridge_contract, chain_id=ava_chain_id, handler=ava_handler)

    monitor_state = load_or_new_state()

    state = State(monitor=monitor_state, eth_bridge=eth_bridge, ava_bridge=ava_bridge, config=config)

    try:
        while True:
            new_proposals = find_all_new_proposals(state)

            logger.debug("Looking for expired proposals")

            expired_proposals(state, new_proposals)

            logger.debug("Looking for new active proposals")

            watch_active_proposals(state, new_proposals)

            logger.debug("Looking for new passed proposals")

            watch_passed_proposals(state, new_proposals)

            logger.debug("Checking active proposals")

            check_active_proposals(state)

            logger.debug("Checking passed proposals")

            check_passed_proposals(state)

            logger.debug(f"Restarting loop in {sleep_time} seconds")

            time.sleep(sleep_time)
    except KeyboardInterrupt:
        pass



