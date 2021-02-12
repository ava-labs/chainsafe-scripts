__all__ = [
    'proper_case_to_spaces'
]


def proper_case_to_spaces(value: str) -> str:
    """
    Place a space after each capital letter found in the string, except for the first letter and if the
    previous letter is also a capital letter


    Examples
    --------
    >>> proper_case_to_spaces('HelloWorld')
    ... "Hello World"

    >>> proper_case_to_spaces("HelloWorldBTC")
    ... "Hello World BTC"

    Parameters
    ----------
    value
        The string to format


    Returns
    -------
    str
        The string formatted given the specification from above
    """
    replacement = ''
    i = 0
    found_lowercase = False
    while i < len(value):
        if i == 0:
            replacement += value[i]
        else:
            char = value[i]
            if char.isupper() and found_lowercase:
                replacement += ' '
                found_lowercase = False
            elif char.islower():
                found_lowercase = True
            replacement += char
        i += 1
    return replacement
