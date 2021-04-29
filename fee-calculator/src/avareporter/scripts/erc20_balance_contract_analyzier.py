import csv
import re

from avareporter.cli import script
import avareporter.tokenlist as tokenlist
from avareporter.tokenlist import TokenReuslt, AllTokenResults
from avareporter.utils.strutil import proper_case_to_spaces
import avareporter.etherscan as es

__all__ = [
    'execute'
]


@script('token_balance_code_analyzer')
def execute():
    token_list = tokenlist.token_list_from('https://wispy-bird-88a7.uniswap.workers.dev/?url=http://tokens.1inch.eth.link').tokens

    # Update names
    for token in token_list:
        token.name = proper_case_to_spaces(token.name)

    search = r'function balanceOf\(\s*address\s*[a-zA-Z0-9_-]*\)'
    search2 = r'mapping\s*\(\s*address\s*=\s*>\s*uint256\s*\)\s*public\s*balanceOf\s*;'
    normal_function = r'return\s+[a-zA-Z0-9_]+\s*\[[a-zA-Z_0-9]*\];'
    auto_getter = r'[_]*[a-zA-Z0-9]+;[\s+[_]*[a-zA-Z0-9]+;]*'
    static_call = r'\s*return\s*IERC20\([a-zA-Z0-9_().]*\)\.balanceOf\([a-zA-Z0-9]*\)\s*;'

    normal_tokens = []
    abnormal_tokens = []
    for token in token_list:
        etherscan = es.get_contract_source(token.address, 'UF9IAYD4IHATIXQ3IAW1BMEJX3YSK83SZJ')

        if len(etherscan.result) == 0:
            print("Couldn't find contract for {} at address {}".format(token.name, token.address))
            abnormal_tokens.append(TokenReuslt(token=token, is_normal=False, reason='Could not find contract code'))
            continue

        if etherscan.result[0].ContractName == 'AdminUpgradeabilityProxy' or etherscan.result[0].Implementation != '':
            if etherscan.result[0].Implementation == '':
                abnormal_tokens.append(
                    TokenReuslt(token=token, is_normal=False,
                                reason='Could not find proxy contract code (not verified)', balanceOf=''))
                continue
            # Find proxy contract
            etherscan = es.get_contract_source(etherscan.result[0].Implementation, 'UF9IAYD4IHATIXQ3IAW1BMEJX3YSK83SZJ')
            if len(etherscan.result) > 0:
                source = etherscan.result[0].SourceCode
            else:
                print("Couldn't find proxy contract for {} at address {}".format(token.name, token.address))
                abnormal_tokens.append(TokenReuslt(token=token, is_normal=False,
                                                   reason='Could not find proxy contract code (Etherscan returned no results)',
                                                   balanceOf=''))
                continue
        else:
            source = etherscan.result[0].SourceCode

        try:
            got_results = False
            for match in re.finditer(search, source):
                e = match.end()

                # Now look for a { or a ;
                # If we find a ;, then skip this match
                cursor = e
                found = False
                while cursor < len(source):
                    if source[cursor] == ';':
                        break
                    elif source[cursor] == '{':
                        found = True
                        cursor += 1
                        break
                    elif source[cursor] == '}':
                        break

                    cursor += 1

                if not found:
                    continue

                got_results = True
                # Create new string with contents of this function
                newstr = ""
                scope = 1
                while cursor < len(source):
                    if source[cursor] == '}':
                        scope -= 1

                        if scope == 0:
                            break
                    elif source[cursor] == '{':
                        scope += 1

                    newstr += source[cursor]
                    cursor += 1

                newstr = newstr.replace('\n', '').replace('\r', '').replace('\\n', '').replace('\\r', '').replace('\t',
                                                                                                                  '').replace(
                    '\\t', '').strip()

                if newstr == '':
                    continue

                isnormal = len(re.findall(normal_function, newstr)) >= 1
                isautogetter = len(re.findall(auto_getter, newstr)) >= 1
                isstaticcall = len(re.findall(static_call, newstr)) >= 1

                if isnormal:
                    print("balanceOf function for {} at address {} is normal\n\t{}".format(token.name, token.address,
                                                                                           newstr))
                    normal_tokens.append(
                        TokenReuslt(token=token, is_normal=True, reason='Has normal balanceOf function',
                                    balanceOf=newstr))
                elif isautogetter:
                    print(
                        "balanceOf function for {} at address {} is normal\n\t{}".format(token.name, token.address,
                                                                                         newstr))
                    normal_tokens.append(
                        TokenReuslt(token=token, is_normal=True, reason='Uses compiler auto getter for balanceOf',
                                    balanceOf=newstr))
                elif isstaticcall:
                    print("balanceOf function for {} at address {} is somewhat normal\n\t{}".format(token.name,
                                                                                                    token.address,
                                                                                                    newstr))
                    normal_tokens.append(
                        TokenReuslt(token=token, is_normal=True, reason='Uses Immutable static call', balanceOf=newstr))
                else:
                    results = re.findall(search2, source)
                    if len(results) == 1:
                        print("Token {} has a public balance mapping".format(token.name))
                        normal_tokens.append(
                            TokenReuslt(token=token, is_normal=True, reason='Uses public balanceOf mapping',
                                        balanceOf=newstr))
                    elif len(results) > 1:
                        print("Token {} has multiple public balance mapping".format(token.name))
                        normal_tokens.append(
                            TokenReuslt(token=token, is_normal=True, reason='Uses multiple public balanceOf mapping',
                                        balanceOf=newstr))
                    else:
                        print("balanceOf function for {} at address {} is abnormal\n\t{}".format(token.name,
                                                                                                 token.address, newstr))
                        abnormal_tokens.append(
                            TokenReuslt(token=token, is_normal=False, reason='Has strange balanceOf function',
                                        balanceOf=newstr))

            if not got_results:
                # Check if the mapping is public
                results = re.findall(search2, source)
                if len(results) == 1:
                    print("Token {} has a public balance mapping".format(token.name))
                    normal_tokens.append(
                        TokenReuslt(token=token, is_normal=True, reason='Uses public balanceOf mapping',
                                    balanceOf=results[0]))
                elif len(results) > 1:
                    print("Token {} has multiple public balance mapping".format(token.name))
                    normal_tokens.append(
                        TokenReuslt(token=token, is_normal=True, reason='Uses multiple public balanceOf mapping',
                                    balanceOf=results[0]))
                else:
                    print("Couldn't find balanceOf for {} at address {}".format(token.name, token.address))
                    abnormal_tokens.append(
                        TokenReuslt(token=token, is_normal=False, reason='Could not find balanceOf function',
                                    balanceOf=''))
        except Exception as e:
            print("Got error {}".format(e))
            abnormal_tokens.append(
                TokenReuslt(token=token, is_normal=False, reason='Error finding balanceOf function {}'.format(e),
                            balanceOf=''))

    print("Writing normal CSV")
    with open('normal_tokens.csv', mode='w', newline='') as f:
        token_writer = csv.writer(f, delimiter=',', quoting=csv.QUOTE_ALL)
        token_writer.writerow(
            ['Token Name', 'Token Address', 'Chain ID', 'Decimals', 'Symbol', 'LogoURI', 'Is Normal Balance Function',
             'Reason', 'Balance Function'])
        for token_result in normal_tokens:
            row = [token_result.token.name, token_result.token.address, token_result.token.chainId,
                   token_result.token.decimals, token_result.token.symbol, token_result.token.logoURI,
                   token_result.is_normal, token_result.reason, token_result.balanceOf]
            token_writer.writerow(row)

    print("Writing abnormal CSV")
    with open('abnormal_tokens.csv', mode='w', newline='') as f:
        token_writer = csv.writer(f, delimiter=',', quoting=csv.QUOTE_ALL)
        token_writer.writerow(
            ['Token Name', 'Token Address', 'Chain ID', 'Decimals', 'Symbol', 'LogoURI', 'Is Normal Balance Function',
             'Reason',
             'Balance Function'])
        for token_result in abnormal_tokens:
            row = [token_result.token.name, token_result.token.address, token_result.token.chainId,
                   token_result.token.decimals, token_result.token.symbol, token_result.token.logoURI,
                   token_result.is_normal, token_result.reason, token_result.balanceOf]
            token_writer.writerow(row)

    print("Writing all CSV")
    with open('tokens.csv', mode='w', newline='') as f:
        token_writer = csv.writer(f, delimiter=',', quoting=csv.QUOTE_ALL)
        token_writer.writerow(
            ['Token Name', 'Token Address', 'Chain ID', 'Decimals', 'Symbol', 'LogoURI', 'Is Normal Balance Function',
             'Reason',
             'Balance Function'])
        for token_result in normal_tokens + abnormal_tokens:
            row = [token_result.token.name, token_result.token.address, token_result.token.chainId,
                   token_result.token.decimals, token_result.token.symbol, token_result.token.logoURI,
                   token_result.is_normal, token_result.reason, token_result.balanceOf]
            token_writer.writerow(row)

    print("Writing normal JSON")
    with open('normal_tokens.json', mode='w') as f:
        all_results = AllTokenResults(results=normal_tokens)
        f.write(all_results.json())

    print("Writing abnormal JSON")
    with open('abnormal_tokens.json', mode='w') as f:
        all_results = AllTokenResults(results=abnormal_tokens)
        f.write(all_results.json())

    print("Writing all JSON")
    with open('all.json', mode='w') as f:
        all_results = AllTokenResults(results=normal_tokens + abnormal_tokens)
        f.write(all_results.json())