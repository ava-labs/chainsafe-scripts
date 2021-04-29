import csv
import time
from typing import List

import requests
from avareporter.cli import script
import avareporter.etherscan as es
from pydantic import BaseModel
from web3 import Web3
import avareporter.abis as abis
import avareporter.graphql as avaes

__all__ = [
    'verify_all_ids'
]


class Resource(BaseModel):
    resource: str
    tokenAddress: str
    handlerAddress: str


class FullResource(Resource):
    tokenName: str
    tokenSymbol: str
    tokenDecimals: int


class BadResource(Resource):
    reason: str


class Results(BaseModel):
    results: List[BadResource]


@script("verify-resources")
def verify_all_ids():
    ethereum_bridge = '0x96B845aBE346b49135B865E5CeDD735FC448C3aD'
    avalanche_bridge = '0x6460777cDa22AD67bBb97536FFC446D65761197E'

    eth_web3 = Web3(Web3.HTTPProvider('https://mainnet.infura.io/v3/f8a5ed81ee9940fdaa7d07ee801ba1ef'))
    ava_web3 = Web3(Web3.HTTPProvider('https://avalanche--mainnet--rpc.datahub.figment.io/apikey/13b0a6af4b9e9f4406aafe275a5ed692/ext/bc/C/rpc'))
    eth_bridge_abi = abis.eth_bridge_abi
    ava_bridge_abi = abis.ava_bridge_abi

    eth_bridge_contract = eth_web3.eth.contract(address=ethereum_bridge, abi=eth_bridge_abi)
    ava_bridge_contract = ava_web3.eth.contract(address=avalanche_bridge, abi=ava_bridge_abi)

    transaction_response = es.get_transactions_by_account(ethereum_bridge)

    # resouceid -> contract address
    ethereum_resource_ids = {}
    avalanche_resource_ids = {}
    bad_resources = []

    handler_address_match = None

    for tx in transaction_response.result:
        if tx.input.startswith('0xcb10f215'):
            # Grab the resource ID from this
            # And contract address

            _, normalized_input = eth_bridge_contract.decode_function_input(tx.input)

            if 'resourceID' in normalized_input and 'handlerAddress' in normalized_input and 'tokenAddress' in normalized_input:
                resource_id = normalized_input['resourceID']
                handler_address = normalized_input['handlerAddress']
                token_address = normalized_input['tokenAddress']

                if handler_address_match is None:
                    handler_address_match = normalized_input['handlerAddress']
                elif handler_address_match != normalized_input['handlerAddress']:
                    bad_resources.append(
                        BadResource(resource=resource_id.hex(), tokenAddress=token_address, handlerAddress=handler_address,
                                    reason='Expected handler address {}'.format(handler_address_match)))

                ethereum_resource_ids[resource_id] = Resource(resource=resource_id.hex(), tokenAddress=token_address,
                                                              handlerAddress=handler_address)

    transactions = list(reversed(avaes.get_all_transactions_by_address('0x6460777cDa22AD67bBb97536FFC446D65761197E')))
    handler_address_match = None

    for tx in transactions:
        input = tx.input
        if input.startswith('0xcb10f215'):
            _, normalized_input = ava_bridge_contract.decode_function_input(input)

            if 'resourceID' in normalized_input and 'handlerAddress' in normalized_input and 'tokenAddress' in normalized_input:
                resource_id = normalized_input['resourceID']
                handler_address = normalized_input['handlerAddress']
                token_address = normalized_input['tokenAddress']

                if handler_address_match is None:
                    handler_address_match = normalized_input['handlerAddress']
                elif handler_address_match != normalized_input['handlerAddress']:
                    bad_resources.append(
                        BadResource(resource=resource_id.hex(), tokenAddress=token_address, handlerAddress=handler_address,
                                    reason='Expected handler address {}'.format(handler_address_match)))

                avalanche_resource_ids[resource_id] = Resource(resource=resource_id.hex(), tokenAddress=token_address,
                                                               handlerAddress=handler_address)

    sleep_timeout = 10
    success = False
    # Now check to see if all Eth resource IDs exist on Avalanche
    for resource_id in ethereum_resource_ids.keys():
        if resource_id not in avalanche_resource_ids:
            bad_resources.append(BadResource(**ethereum_resource_ids[resource_id].dict(),
                                             reason='This resourceID is not on Avalanche, but is on Ethereum'))
        else:
            erc20_abi = abis.erc20
            eth_name = ''
            eth_symbol = ''
            eth_decimals = 0

            ava_name = ''
            ava_symbol = ''
            ava_decimals = 0
            while True:
                try:
                    eth_token_address = ethereum_resource_ids[resource_id].tokenAddress
                    ava_token_address = avalanche_resource_ids[resource_id].tokenAddress

                    if eth_token_address == ava_token_address:
                        bad_resources.append(BadResource(**ethereum_resource_ids[resource_id].dict(),
                                                         reason="Token address is the same on both chains. Is this right?"))

                    eth_token = eth_web3.eth.contract(address=eth_token_address, abi=erc20_abi)
                    ava_token = ava_web3.eth.contract(address=ava_token_address, abi=erc20_abi)

                    ava_name = ava_token.functions.name().call()
                    ava_symbol = ava_token.functions.symbol().call()
                    ava_decimals = ava_token.functions.decimals().call()

                    eth_name = eth_token.functions.name().call()
                    eth_symbol = eth_token.functions.symbol().call()
                    eth_decimals = eth_token.functions.decimals().call()

                    if eth_name != ava_name:
                        if ava_name == '':
                            ava_name = 'missing!!'
                        if eth_name == '':
                            eth_name = 'missing!!'
                        bad_resources.append(BadResource(**ethereum_resource_ids[resource_id].dict(),
                                                         reason="Token name on Ethereum is {}, but on Avalanche it's {}".format(
                                                             eth_name, ava_name)))

                    if eth_symbol != ava_symbol:
                        if ava_symbol == '':
                            ava_symbol = 'missing!!'
                        if eth_symbol == '':
                            eth_symbol = 'missing!!'
                        bad_resources.append(BadResource(**ethereum_resource_ids[resource_id].dict(),
                                                         reason="Token symbol on Ethereum is {}, but on Avalanche it's {}".format(
                                                             eth_symbol, ava_symbol)))

                    if eth_decimals != ava_decimals:
                        bad_resources.append(BadResource(**ethereum_resource_ids[resource_id].dict(),
                                                         reason="Token decimals on Ethereum is {}, but on Avalanche it's {}".format(
                                                             eth_decimals, ava_decimals)))

                    ava_token = ava_web3.eth.contract(address=ava_token_address, abi=abis.erc20_minter)
                    ava_handler = avalanche_resource_ids[resource_id].handlerAddress

                    minter_role_key = ava_token.functions.MINTER_ROLE().call()
                    has_minter_role = ava_token.functions.hasRole(minter_role_key, ava_handler).call()

                    if not has_minter_role:
                        bad_resources.append(BadResource(**avalanche_resource_ids[resource_id].dict(),
                                                         reason="This token doesn't have the minter role on Avalanche"))
                    success = True
                    break
                except requests.exceptions.HTTPError as e:
                    if 'too many requests' in str(e).lower():
                        if not success:
                            sleep_timeout *= 2
                        print("Got too many requests error")
                        print("Waiting {} seconds".format(sleep_timeout))
                        time.sleep(sleep_timeout)
                        success = False
                        continue
                    else:
                        bad_resources.append(BadResource(**avalanche_resource_ids[resource_id].dict(),
                                                         reason="Error validating token data {}".format(e)))
                        break
                except Exception as e:
                    if str(e) == 'Python int too large to convert to C ssize_t':
                        erc20_abi = abis.backup_erc20
                        continue
                    bad_resources.append(BadResource(**avalanche_resource_ids[resource_id].dict(),
                                                     reason="Error validating token data {}".format(e)))
                    break

            ethereum_resource_ids[resource_id] = FullResource(**ethereum_resource_ids[resource_id].dict(),
                                                              tokenName=eth_name, tokenSymbol=eth_symbol,
                                                              tokenDecimals=eth_decimals)

            avalanche_resource_ids[resource_id] = FullResource(**avalanche_resource_ids[resource_id].dict(),
                                                               tokenName=ava_name, tokenSymbol=ava_symbol,
                                                               tokenDecimals=ava_decimals)

    for resource_id in avalanche_resource_ids.keys():
        if resource_id not in ethereum_resource_ids:
            bad_resources.append(BadResource(**avalanche_resource_ids[resource_id].dict(),
                                             reason='This resourceID is not on Ethereum, but is on Avalanche'))

    with open('bad_resources.json', mode='w') as f:
        data = Results(results=bad_resources)

        f.write(data.json())

    with open('bad_resources.csv', mode='w', newline='') as f:
        token_writer = csv.writer(f, delimiter=',', quoting=csv.QUOTE_ALL)
        token_writer.writerow(['ResourceID', 'Token Address', 'Handler Address', 'Reason'])
        for token_result in bad_resources:
            row = [token_result.resource, token_result.tokenAddress, token_result.handlerAddress, token_result.reason]
            token_writer.writerow(row)

    with open('resources.csv', mode='w', newline='') as f:
        token_writer = csv.writer(f, delimiter=',', quoting=csv.QUOTE_ALL)
        token_writer.writerow(['Resource ID', 'Ethereum Token Address', 'Ethereum Handler Address',
                               'Ethereum Token Name', 'Ethereum Token Symbol', 'Ethereum Token Decimals',
                               'Avalanche Token Address', 'Avalanche Handler Address',
                               'Avalanche Token Name', 'Avalanche Token Symbol', 'Avalanche Token Decimals'])
        for resource in ethereum_resource_ids.keys():
            eth_resource = ethereum_resource_ids[resource]
            if resource not in avalanche_resource_ids:
                ava_resource = FullResource(resource=resource.hex(), tokenAddress='missing', handlerAddress='missing',
                                            tokenName='missing', tokenSymbol='missing', tokenDecimals=0)
            else:
                ava_resource = avalanche_resource_ids[resource]

            if not isinstance(eth_resource, FullResource):
                erc20_abi = abis.erc20
                eth_name = ''
                eth_symbol = ''
                eth_decimals = 0
                while True:
                    try:
                        eth_token = eth_web3.eth.contract(address=eth_resource.tokenAddress, abi=erc20_abi)

                        eth_name = eth_token.functions.name().call()
                        eth_symbol = eth_token.functions.symbol().call()
                        eth_decimals = eth_token.functions.decimals().call()

                        break
                    except Exception as e:
                        if str(e) == 'Python int too large to convert to C ssize_t':
                            erc20_abi = abis.backup_erc20
                            continue
                        bad_resources.append(BadResource(**ethereum_resource_ids[resource].dict(),
                                                         reason="Error validating token data {}".format(e)))
                        break

                eth_resource = FullResource(**ethereum_resource_ids[resource].dict(),
                                            tokenName=eth_name, tokenSymbol=eth_symbol,
                                            tokenDecimals=eth_decimals)

            if not isinstance(ava_resource, FullResource):
                erc20_abi = abis.erc20

                ava_name = ''
                ava_symbol = ''
                ava_decimals = 0

                while True:
                    try:
                        ava_token = ava_web3.eth.contract(address=ava_resource.tokenAddress, abi=erc20_abi)

                        ava_name = ava_token.functions.name().call()
                        ava_symbol = ava_token.functions.symbol().call()
                        ava_decimals = ava_token.functions.decimals().call()


                        break
                    except Exception as e:
                        if str(e) == 'Python int too large to convert to C ssize_t':
                            erc20_abi = abis.backup_erc20
                            continue
                        bad_resources.append(BadResource(**avalanche_resource_ids[resource].dict(),
                                                         reason="Error validating token data {}".format(e)))
                        break

                ava_resource = FullResource(**avalanche_resource_ids[resource].dict(),
                                            tokenName=ava_name, tokenSymbol=ava_symbol,
                                            tokenDecimals=ava_decimals)

            row = [resource.hex(), eth_resource.tokenAddress, eth_resource.handlerAddress, eth_resource.tokenName,
                   eth_resource.tokenSymbol, eth_resource.tokenDecimals, ava_resource.tokenAddress,
                   ava_resource.handlerAddress, ava_resource.tokenName, ava_resource.tokenSymbol,
                   ava_resource.tokenDecimals]
            token_writer.writerow(row)
