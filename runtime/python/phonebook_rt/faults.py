"""Runtime failures that a contract predicted.

A fault always carries a `code` drawn from the address's `contract.errors`.
That is the difference between a contracted failure and a backend accident: if
a program can fail, the phonebook already said how.
"""

from __future__ import annotations


class PhonebookFault(Exception):
    def __init__(self, code: str, message: str = ""):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}" if message else code)
