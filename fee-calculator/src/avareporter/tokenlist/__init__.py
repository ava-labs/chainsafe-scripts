import requests
from avareporter.tokenlist.models import TokenList, TokenReuslt, Token, AllTokenResults


def token_list_from(url: str) -> TokenList:
    resp = requests.get(url)
    data = resp.json()

    return TokenList(**data)