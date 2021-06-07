import configparser
import json
import time
from dataclasses import dataclass, asdict
from enum import Enum
from functools import partial
from multiprocessing import Pool
from multiprocessing.pool import ThreadPool
from typing import List, Set, Dict, Optional, Any
from pathlib import Path

import requests
from requests import Response
from tqdm.contrib.concurrent import process_map, thread_map

from hexbytes import HexBytes
from web3.contract import Contract

from avareporter.abis import bridge_abi, handler_abi, erc20_abi, erc20_nonstandard_abi
from web3 import Web3
from avareporter.cli import script
import logging
from logging.config import fileConfig
from logging.config import dictConfig

CHAIN_NAMES = {
    1: 'Ethereum',
    2: 'Avalanche',
}


EMPTY_BYTES32 = b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
ZERO_ADDRESS = '0x0000000000000000000000000000000000000000'


class ProposalStatus(int, Enum):
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

    def as_dict(self):
        return asdict(self)

    def __hash__(self):
        return self.deposit_transaction_hash

    def __cmp__(self, other: 'Proposal'):
        return other.deposit_transaction_hash == self.deposit_transaction_hash


class AlertType(str, Enum):
    ProposalExpired = 'proposal_expired'
    ProposalNotVoted = 'proposal_not_voted'
    ProposalNotExecuted = 'proposal_not_executed'
    EthImbalance = 'eth_network_imbalance'
    AvaxImbalance = 'avax_network_imbalance'
    Internal = 'internal'
    ProposalVoted = 'proposal_voted'


@dataclass
class Alert:
    data: Optional[Any]
    message: str
    alert_type: AlertType

    def as_dict(self):
        return asdict(self)


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


class BytesEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        if isinstance(o, HexBytes):
            return o.hex()
        elif isinstance(o, bytes):
            return HexBytes(o).hex()
        return json.JSONEncoder.default(self, o)


@dataclass
class MonitorState:
    active_proposals: Dict[str, List[Proposal]]
    passed_proposals: Dict[str, List[Proposal]]
    resource_ids: List[str]
    ava_deposit_count: int = 0
    eth_deposit_count: int = 0

    def save(self):
        save_state = Path('.state')
        if save_state.exists():
            backup_state = Path(f'.state.backup')

            if backup_state.exists():
                backup_state.unlink()

            save_state.rename(backup_state)

        with open(str(save_state.absolute()), mode='w') as f:
            json.dump(asdict(self), f, cls=BytesEncoder)


@dataclass
class State:
    monitor: MonitorState
    eth_bridge: Bridge
    ava_bridge: Bridge
    config: configparser.ConfigParser


def load_or_new_state() -> MonitorState:
    save_state = Path('.state')
    if not save_state.exists():
        return MonitorState(active_proposals={
            '1': [],
            '2': []
        }, passed_proposals={
            '1': [],
            '2': []
        }, resource_ids=[])

    with open(str(save_state.absolute()), mode='r') as f:
        data = json.load(f)

    if 'imbalance_alerts' in data:
        del data['imbalance_alerts']

    return MonitorState(**data)


def log_alert(message: str, atype: AlertType, related_object: Optional[Any] = None):
    logger = logging.getLogger('alert')

    alert = Alert(related_object, message, atype)

    logger.error(json.dumps(alert.as_dict(), cls=BytesEncoder))


def fetch_proposal(origin_bridge: Bridge, destination_bridge: Bridge, nonce: int) -> Proposal:
    try:
        records = origin_bridge.contract.functions._depositRecords(nonce, destination_bridge.chain_id).call()

        hash = Web3.solidityKeccak(['address', 'bytes'], [destination_bridge.handler, records])

        raw_proposal = destination_bridge.contract.functions.getProposal(origin_bridge.chain_id, nonce, hash.hex()).call()

        event_filter = origin_bridge.contract.events.Deposit.createFilter(fromBlock=0, toBlock='latest', argument_filters={
            'depositNonce': nonce
        })

        events = event_filter.get_all_entries()

        temp_proposal = Proposal(
            resource_id=raw_proposal[0],
            data_hash=raw_proposal[1],
            yes_votes=raw_proposal[2],
            no_votes=raw_proposal[3],
            status=ProposalStatus(raw_proposal[4]),
            proposed_block=raw_proposal[5],
            deposit_nonce=nonce,
            deposit_block=None,
            deposit_transaction_hash=None
        )

        if len(events) == 0:
            log_alert(f'Deposit {nonce} not found on Origin Chain {CHAIN_NAMES[origin_bridge.chain_id]}', AlertType.Internal, temp_proposal)
            deposit_block = None
            deposit_transaction_hash = None
        elif len(events) > 1:
            log_alert(f'Multiple Deposit events with the nonce {nonce} found on Origin Chain {CHAIN_NAMES[origin_bridge.chain_id]}', AlertType.Internal, temp_proposal)
            deposit_block = None
            deposit_transaction_hash = None
        else:
            event = events[0]

            if event.args is not None:
                if event.args.resourceID != raw_proposal[0]:
                    log_alert(f'Deposit event found, but proposal resource ID mismatch', AlertType.Internal, temp_proposal)
                    deposit_block = None
                    deposit_transaction_hash = None
                elif event.args.destinationChainID != destination_bridge.chain_id:
                    log_alert(f'Deposit event found, but proposal resource ID mismatch', AlertType.Internal, temp_proposal)
                    deposit_block = None
                    deposit_transaction_hash = None
                else:
                    deposit_block = event.blockNumber
                    deposit_transaction_hash = event.transactionHash
            else:
                log_alert(f'Deposit event found, but unverified (no data in event)', AlertType.Internal, temp_proposal)
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


def find_all_new_proposals(current_state: State) -> Dict[str, List[Proposal]]:
    logger = logging.getLogger('fetch_new_proposals')

    eth_bridge = current_state.eth_bridge
    ava_bridge = current_state.ava_bridge

    eth_bridge_contract = eth_bridge.contract
    ava_bridge_contract = ava_bridge.contract

    eth_chain_id = str(eth_bridge.chain_id)
    ava_chain_id = str(ava_bridge.chain_id)

    state = current_state.monitor

    worker_count = int(current_state.config['monitor']['worker_count'])
    use_multiprocessing = bool(current_state.config['monitor']['use_child_processes'])

    PoolClass = Pool if use_multiprocessing else ThreadPool

    logger.debug('Grabbing deposit counts')

    # eth -> ava
    ava_deposit_count = eth_bridge_contract.functions._depositCounts(ava_bridge.chain_id).call()
    # ava -> eth
    eth_deposit_count = ava_bridge_contract.functions._depositCounts(eth_bridge.chain_id).call()

    logger.debug('ETH -> AVA Deposits: ' + str(ava_deposit_count))
    logger.debug('AVA -> ETH Deposits: ' + str(eth_deposit_count))

    proposals = {
        eth_chain_id: [],
        ava_chain_id: []
    }
    if state.ava_deposit_count > ava_deposit_count:
        logger.error('Saved state has more deposit counts than what blockchain reported!')
    elif state.ava_deposit_count < ava_deposit_count:
        count = ava_deposit_count - state.ava_deposit_count
        chunksize = int(count / worker_count)

        if chunksize < 5:
            PoolClass = ThreadPool

        if chunksize >= 1:
            with PoolClass(worker_count) as p:
                new_eth_proposals = p.map(partial(fetch_proposal, eth_bridge, ava_bridge),
                                          range(state.ava_deposit_count, ava_deposit_count),
                                          chunksize=chunksize)

                proposals[eth_chain_id] = new_eth_proposals
        else:
            proposals[eth_chain_id] = []
            for nonce in range(state.ava_deposit_count, ava_deposit_count):
                proposals[eth_chain_id].append(fetch_proposal(eth_bridge, ava_bridge, nonce))

    if state.eth_deposit_count > eth_deposit_count:
        logger.error('Saved state has more deposit counts than what blockchain reported!')
    elif state.eth_deposit_count < eth_deposit_count:
        count = ava_deposit_count - state.ava_deposit_count
        chunksize = int(count / worker_count)
        if chunksize < 5:
            PoolClass = ThreadPool

        if chunksize >= 1:
            with PoolClass(worker_count) as p:
                new_ava_proposals = p.map(partial(fetch_proposal, ava_bridge, eth_bridge),
                                          range(state.eth_deposit_count, eth_deposit_count),
                                          chunksize=chunksize)
                proposals[ava_chain_id] = new_ava_proposals
        else:
            proposals[ava_chain_id] = []
            for nonce in range(state.eth_deposit_count, eth_deposit_count):
                proposals[ava_chain_id].append(fetch_proposal(ava_bridge, eth_bridge, nonce))

    state.ava_deposit_count = ava_deposit_count
    state.eth_deposit_count = eth_deposit_count

    # Save new resource ids
    for proposal in proposals[eth_chain_id]:
        if proposal.resource_id.hex() not in state.resource_ids:
            state.resource_ids.append(proposal.resource_id.hex())

    for proposal in proposals[ava_chain_id]:
        if proposal.resource_id.hex() not in state.resource_ids:
            state.resource_ids.append(proposal.resource_id.hex())

    return proposals


def expired_proposals(current_state: State, proposals: Dict[str, List[Proposal]]):
    logger = logging.getLogger('expired_proposals')

    eth_bridge = current_state.eth_bridge
    ava_bridge = current_state.ava_bridge

    eth_chain_id = str(eth_bridge.chain_id)
    ava_chain_id = str(ava_bridge.chain_id)

    logger.debug('Searching for expired proposals on Ethereum')

    for proposal in proposals[eth_chain_id]:
        if proposal.status == ProposalStatus.Cancelled:
            log_alert(f'[Ethereum] Proposal Expired; Deposit Block: {proposal.deposit_block} '
                      f'Deposit Transaction: {proposal.deposit_transaction_hash} '
                      f'Proposed Block: {proposal.proposed_block} '
                      f'Resource ID: {proposal.resource_id.hex()} Data Hash: {proposal.data_hash.hex()} '
                      f'Yes Votes: {len(proposal.yes_votes)} No Votes: {len(proposal.no_votes)}',
                      AlertType.ProposalExpired, proposal)

    logger.debug('Searching for expired proposals on Avalanche')

    for proposal in proposals[ava_chain_id]:
        if proposal.status == ProposalStatus.Cancelled:
            log_alert(f'[Avalanche] Proposal Expired; Deposit Block: {proposal.deposit_block} '
                      f'Deposit Transaction: {proposal.deposit_transaction_hash} '
                      f'Proposed Block: {proposal.proposed_block} '
                      f'Resource ID: {proposal.resource_id.hex()} Data Hash: {proposal.data_hash.hex()} '
                      f'Yes Votes: {len(proposal.yes_votes)} No Votes: {len(proposal.no_votes)}',
                      AlertType.ProposalExpired, proposal)


def watch_active_proposals(current_state: State, proposals: Dict[str, List[Proposal]]):
    logger = logging.getLogger('watch_active_proposals')

    eth_bridge = current_state.eth_bridge
    ava_bridge = current_state.ava_bridge

    eth_chain_id = str(eth_bridge.chain_id)
    ava_chain_id = str(ava_bridge.chain_id)

    logger.debug('Searching for new active proposals on Ethereum')

    for proposal in proposals[eth_chain_id]:
        if proposal.status == ProposalStatus.Active and proposal not in current_state.monitor.active_proposals[eth_chain_id]:
            current_state.monitor.active_proposals[eth_chain_id].append(proposal)

    logger.debug('Searching for new active proposals on Avalanche')

    for proposal in proposals[ava_chain_id]:
        if proposal.status == ProposalStatus.Active and proposal not in current_state.monitor.active_proposals[ava_chain_id]:
            current_state.monitor.active_proposals[ava_chain_id].append(proposal)


def watch_passed_proposals(current_state: State, proposals: Dict[str, List[Proposal]]):
    logger = logging.getLogger('watch_passed_proposals')

    eth_bridge = current_state.eth_bridge
    ava_bridge = current_state.ava_bridge

    eth_chain_id = str(eth_bridge.chain_id)
    ava_chain_id = str(ava_bridge.chain_id)

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

    eth_chain_id = str(eth_bridge.chain_id)
    ava_chain_id = str(ava_bridge.chain_id)

    eth_latest_block = current_state.eth_bridge.contract.web3.eth.block_number
    ava_latest_block = current_state.ava_bridge.contract.web3.eth.block_number

    if len(current_state.monitor.active_proposals[eth_chain_id]) > 0:
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
                log_alert(f'[Ethereum] Proposal has remained active for {block_elapsed} blocks',
                          AlertType.ProposalNotVoted, proposal)
            else:
                logger.debug(f"Proposal has remained pass for {block_elapsed} blocks")
    else:
        logger.debug("Not watching any Ethereum proposals")

    if len(current_state.monitor.active_proposals[ava_chain_id]) > 0:
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
                log_alert(f'[Avalanche] Proposal has remained active for {block_elapsed} blocks',
                          AlertType.ProposalNotVoted, proposal)
            else:
                logger.debug(f"Proposal has remained pass for {block_elapsed} blocks")
    else:
        logger.debug("Not watching any Avalanche proposals")


def check_passed_proposals(current_state: State):
    logger = logging.getLogger('check_active_proposals')

    passed_proposal_block_alert = int(current_state.config['monitor']['passed_proposal_block_alert'])

    eth_bridge = current_state.eth_bridge
    ava_bridge = current_state.ava_bridge

    eth_chain_id = str(eth_bridge.chain_id)
    ava_chain_id = str(ava_bridge.chain_id)

    eth_latest_block = current_state.eth_bridge.contract.web3.eth.block_number
    ava_latest_block = current_state.ava_bridge.contract.web3.eth.block_number

    if len(current_state.monitor.passed_proposals[eth_chain_id]) > 0:
        logger.debug('Checking passed Ethereum proposals')

        for proposal in current_state.monitor.passed_proposals[eth_chain_id][:]:
            current_proposal_state = fetch_proposal(current_state.eth_bridge, current_state.ava_bridge, proposal.deposit_nonce)

            if current_proposal_state.status != proposal.status:
                current_state.monitor.passed_proposals[eth_chain_id].remove(proposal)
                continue

            block_elapsed = eth_latest_block - current_proposal_state.proposed_block

            if block_elapsed >= passed_proposal_block_alert:
                log_alert(f'[Ethereum] Proposal has remained passed for {block_elapsed} blocks',
                          AlertType.ProposalExpired, proposal)
            else:
                logger.debug(f"Proposal has remained pass for {block_elapsed} blocks")
    else:
        logger.debug("Not watching any Ethereum proposals")

    if len(current_state.monitor.passed_proposals[ava_chain_id]) > 0:
        logger.debug('Checking passed Avalanche proposals')

        for proposal in current_state.monitor.passed_proposals[ava_chain_id][:]:
            current_proposal_state = fetch_proposal(current_state.ava_bridge, current_state.eth_bridge, proposal.deposit_nonce)

            if current_proposal_state.status != proposal.status:
                current_state.monitor.passed_proposals[ava_chain_id].remove(proposal)
                continue

            block_elapsed = ava_latest_block - current_proposal_state.proposed_block

            if block_elapsed >= passed_proposal_block_alert:
                log_alert(f'[Avalanche] Proposal has remained passed for {block_elapsed} blocks',
                          AlertType.ProposalExpired, proposal)
            else:
                logger.debug(f"Proposal has remained pass for {block_elapsed} blocks")
    else:
        logger.debug("Not watching any Avalanche proposals")


def check_vote_event(state: State, event_filter):
    for event in event_filter.get_new_entries():
        nonce = event.args.depositNonce
        origin = event.args.originChainID
        destination = 1 if origin == 2 else 2

        origin_bridge = state.eth_bridge if origin == 1 else state.ava_bridge
        dst_bridge = state.eth_bridge if destination == 1 else state.ava_bridge

        proposal = fetch_proposal(origin_bridge, dst_bridge, nonce)

        log_alert('New vote for proposal', AlertType.ProposalVoted, proposal)


def check_for_imbalances(current_state: State):
    logger = logging.getLogger('check_for_imbalances')

    tolerance_config_file = Path('imbalance.json')
    if tolerance_config_file.exists():
        with open(str(tolerance_config_file.absolute()), mode='r') as f:
            tolerances = json.load(f)
    else:
        tolerances = {}

    eth_web3 = current_state.eth_bridge.contract.web3
    ava_web3 = current_state.ava_bridge.contract.web3
    for resource_id in current_state.monitor.resource_ids:
        if resource_id == HexBytes(EMPTY_BYTES32).hex()[2:]:
            continue

        tolerance = tolerances.get(resource_id, 0)
        tolerance = tolerances.get('0x'+resource_id, tolerance)

        if tolerance == -1:
            continue  # Ignore this resource

        eth_handler_address = current_state.eth_bridge.contract.functions._resourceIDToHandlerAddress(resource_id).call()
        ava_handler_address = current_state.ava_bridge.contract.functions._resourceIDToHandlerAddress(resource_id).call()

        if eth_handler_address != ZERO_ADDRESS and ava_handler_address != ZERO_ADDRESS:
            eth_handler = eth_web3.eth.contract(address=eth_handler_address, abi=handler_abi)
            ava_handler = ava_web3.eth.contract(address=ava_handler_address, abi=handler_abi)

            eth_token_address = eth_handler.functions._resourceIDToTokenContractAddress(resource_id).call()
            ava_token_address = ava_handler.functions._resourceIDToTokenContractAddress(resource_id).call()

            eth_token = eth_web3.eth.contract(address=eth_token_address, abi=erc20_abi)
            ava_token = ava_web3.eth.contract(address=ava_token_address, abi=erc20_abi)

            try:
                eth_name = eth_token.functions.name().call()
            except OverflowError as e:
                try:
                    eth_token = eth_web3.eth.contract(address=eth_token_address, abi=erc20_nonstandard_abi)
                    eth_name = eth_token.functions.name().call()
                except Exception as e:
                    logger.warning(f"Could not decode token name for Ethereum token contract {eth_token_address}")
                    logger.error(e)
                    eth_name = "~Unknown~"

            try:
                ava_name = ava_token.functions.name().call()
            except OverflowError as e:
                try:
                    ava_token = ava_web3.eth.contract(address=ava_token_address, abi=erc20_nonstandard_abi)
                    ava_name = ava_token.functions.name().call()
                except Exception as e:
                    logger.warning(f"Could not decode token name for Avalanche token contract {ava_token_address}")
                    logger.error(e)
                    ava_name = "~Unknown~"

            eth_balance = eth_token.functions.balanceOf(eth_handler_address).call()
            ava_balance = ava_token.functions.totalSupply().call()

            if eth_balance == 0 and ava_balance == 0:
                continue

            if eth_balance == 0:
                eth_balance = eth_token.functions.totalSupply().call()
                ava_balance = ava_token.functions.balanceOf(ava_handler_address).call()

            if abs(eth_balance - ava_balance) > tolerance:
                difference = max(eth_balance, ava_balance) - min(eth_balance, ava_balance)

                eth_symbol = eth_token.functions.symbol().call()
                ava_symbol = ava_token.functions.symbol().call()

                eth_decimals = eth_token.functions.decimals().call()
                ava_decimals = ava_token.functions.decimals().call()

                data = {
                    'resource': resource_id,
                    'raw_difference': difference,
                    'difference': difference / (10**eth_decimals),
                    'eth': {
                        'name': eth_name,
                        'symbol': eth_symbol,
                        'decimals': eth_decimals,
                        'balance': eth_balance / (10**eth_decimals),
                        'raw_balance': eth_balance,
                        'token': eth_token_address,
                    },
                    'ava': {
                        'name': ava_name,
                        'symbol': ava_symbol,
                        'decimals': ava_decimals,
                        'balance': ava_balance / (10**ava_decimals),
                        'raw_balance': ava_balance,
                        'token': ava_token_address,
                    }
                }

                alert_type = AlertType.EthImbalance
                if ava_balance > eth_balance:
                    alert_type = AlertType.AvaxImbalance

                log_alert(f'Token {ava_name} (Ethereum Name: {eth_name}) has imbalance!', alert_type, data)
        else:
            log_alert(f'Got zero address for resourceId {resource_id}', AlertType.Internal)


@script('monitor')
def execute():
    config_file = Path('config.ini')
    with open(str(config_file.absolute()), mode='r') as f:
        config_data = f.read()

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

    eth_bridge_address = config['monitor']['eth_bridge_address']
    ava_bridge_address = config['monitor']['ava_bridge_address']
    eth_rpc_url = config['monitor']['eth_rpc_url']
    ava_rpc_url = config['monitor']['ava_rpc_url']
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

    eth_fromBlock = 'latest'
    ava_fromBlock = 'latest'

    while True:
        try:
            logger.debug("Setting up Proposal Voted Event filter on Ethereum")

            eth_vote_event_filter = eth_bridge.contract.events.ProposalVote.createFilter(fromBlock=eth_fromBlock, toBlock='latest')
            ava_vote_event_filter = ava_bridge.contract.events.ProposalVote.createFilter(fromBlock=ava_fromBlock, toBlock='latest')

            logger.debug("Checking ProposalVote event filters")
            check_vote_event(state, eth_vote_event_filter)
            check_vote_event(state, ava_vote_event_filter)

            eth_fromBlock = eth_web3.eth.block_number
            ava_fromBlock = ava_web3.eth.block_number

            logger.debug("Scanning for new proposals")

            new_proposals = find_all_new_proposals(state)

            logger.debug(f"Got {len(new_proposals['1'])} new Ethereum proposals and {len(new_proposals['2'])} new Avalanche proposals")

            logger.debug("Checking for imbalances")

            check_for_imbalances(state)

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

            logger.debug("Saving current state")

            state.monitor.save()

            logger.debug(f"Restarting loop in {sleep_time} seconds")

            time.sleep(sleep_time)
        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(e)
            logger.error(f"Swallowing exception, sleeping for {sleep_time} seconds before trying again")
            time.sleep(sleep_time)
            continue
    state.monitor.save()
