import requests


def send_query(url: str, query: str):
    data = {
        'query': query,
        "variables": None,
        "operationName": None
    }

    resp = requests.post(url, data)

    return resp.json()


from avareporter.graphql.cchain_explorer import get_all_transactions_by_address

__all__ = [
    'send_query',
    'get_all_transactions_by_address'
]