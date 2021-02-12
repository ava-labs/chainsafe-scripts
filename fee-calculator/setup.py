from setuptools import setup, find_packages

try:
    with open('requirements.txt') as f:
        INSTALL_REQUIREMENTS = f.read().splitlines()
except FileNotFoundError:
    import warnings

    warnings.warn("Could not find requirements.txt")
    INSTALL_REQUIREMENTS = []


TEST_REQUIREMENTS = [
    'pytest >= 3.8'
]

DISTNAME = "avareporter"
LICENSE = "MIT"
AUTHOR = "Eddie Penta"
AUTHOR_EMAIL = "eddie@avalabs.org"

DESCRIPTION = "A set of scripts for chainsafe nodes to run"

setup(
    name=DISTNAME,
    version="1.0.0",
    license=LICENSE,
    author=AUTHOR,
    author_email=AUTHOR_EMAIL,
    description=DESCRIPTION,
    install_requires=INSTALL_REQUIREMENTS,
    tests_require=TEST_REQUIREMENTS,
    python_requires=">=3.6",
    packages=find_packages(where="src", exclude=["tests", "tests.*"]),
    package_dir={"":"src"},
)
