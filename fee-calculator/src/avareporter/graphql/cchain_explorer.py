from typing import List, Optional

import requests

from avareporter.graphql import send_query
from avareporter.graphql.models import AvaTransaction


def get_all_transactions_by_address(address: str, explorer_url: str = 'https://explorerapi.avax.network',
                                    start_block: int = -1, end_block: Optional[int] = None) -> List[AvaTransaction]:
    if start_block > 0 and end_block is not None:
        cursor = start_block
        count = end_block - start_block

        results = []
        while cursor < end_block:
            current_start = cursor
            current_end = current_start + count

            try:
                tx = get_all_transactions_by_address_unhandled(address, explorer_url, current_start, current_end)
                results.extend(tx)

                cursor += count
            except KeyError:
                count /= 2
                continue

        return results
    else:
        return get_all_transactions_by_address_unhandled(address, explorer_url, start_block, end_block)


def get_all_transactions_by_address_unhandled(address: str, explorer_url: str = 'https://explorerapi.avax.network',
                                    start_block: int = -1, end_block: Optional[int] = None) -> List[AvaTransaction]:
    url = "{}/v2/ctransactions?address={}".format(explorer_url, address)

    if start_block > 0:
        url += "&blockStart={}".format(start_block)

    if end_block is not None:
        url += "&blockEnd={}".format(end_block)

    resp = requests.get(url)
    data = resp.json()

    return list(map(lambda t: AvaTransaction(**t), data['Transactions']))