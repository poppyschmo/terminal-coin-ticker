import os
from setuptools import setup, find_packages
from importlib.util import find_spec

here = os.path.abspath(os.path.dirname(__file__))

with open(os.path.join(here, "README.rst"), encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="terminal_coin_ticker",
    author="Jane Soko",
    author_email="boynamedjane@misled.ml",
    version="0.0.7",
    url="https://github.com/poppyschmo/terminal-coin-ticker",
    description="A cryptocurrency ticker for modern terminal emulators",
    long_description=long_description,
    license="Apache 2.0",
    keywords="bitcoin blockchain ethereum cryptocurrency ticker exchange",
    classifiers=[
        "License :: OSI Approved :: Apache Software License",
        "Development Status :: 3 - Alpha",
        "Intended Audience :: End Users/Desktop",
        "Topic :: Office/Business :: Financial",
        "Topic :: Terminals :: Terminal Emulators/X Terminals",
        "Programming Language :: Python :: 3.6",
    ],
    install_requires=["aiohttp" if find_spec("aiohttp") else "websockets"],
    packages=find_packages(),
    python_requires=">=3.6",
    entry_points={
        "console_scripts": [
            "tc-ticker = terminal_coin_ticker.ticker:main_entry"
        ]
    }
)
