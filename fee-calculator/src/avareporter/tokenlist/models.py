from typing import List

from pydantic import BaseModel


class Token(BaseModel):
    address: str
    chainId: int
    name: str
    symbol: str
    decimals: int
    logoURI: str


class Version(BaseModel):
    major: int
    minor: int
    patch: int


class TokenList(BaseModel):
    name: str
    timestamp: str
    version: Version
    tokens: List[Token]


class TokenReuslt(BaseModel):
    token: Token
    is_normal: bool
    reason: str
    balanceOf: str


class AllTokenResults(BaseModel):
    results: List[TokenReuslt]