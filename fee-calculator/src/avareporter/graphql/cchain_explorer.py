from typing import List, Optional

from avareporter.graphql import send_query
from avareporter.graphql.models import AvaTransaction


def get_all_transactions_by_address(address: str, explorer_url: str = 'https://cchain.explorer.avax.network/graphiql',
                                    start_block: int = -1, end_block: Optional[int] = None) -> List[AvaTransaction]:
    items = 'input, blockNumber, createdContractAddressHash, cumulativeGasUsed, error, fromAddressHash, gas,' \
            ' gasPrice, gasUsed, hash, id, index, nonce, status, toAddressHash, value'

    query = '{address(hash: "' + address + '") { transactions(first:5) { edges { cursor, node { ' + items + ' } } pageInfo { hasNextPage, endCursor } } } }'

    has_results = True
    transactions = []
    while has_results:
        results = send_query(explorer_url, query)

        if results['data']['address'] is None:
            break

        edges = results['data']['address']['transactions']['edges']

        for edge in edges:
            transactions.append(edge['node'])

        last_cursor = results['data']['address']['transactions']['pageInfo']['endCursor']

        has_results = results['data']['address']['transactions']['pageInfo']['hasNextPage']

        query = '{address(hash: "' + address + '") { transactions(first:5, after:"' + last_cursor + '") { edges { cursor, node { ' + items + ' } } pageInfo { hasNextPage, endCursor } } } }'

    if start_block > 0:
        transactions = list(filter(lambda t: t['blockNumber'] >= start_block, transactions))

    if end_block is not None:
        transactions = list(filter(lambda t: t['blockNumber'] <= end_block, transactions))

    transactions = list(map(lambda t: AvaTransaction(**t), transactions))

    return transactions
