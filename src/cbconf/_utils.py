# Word delimiters and symbols that will not be preserved when re-casing.
import os
import re

_SYMBOLS = "[^a-zA-Z0-9]*"

# Optionally capitalized word.
_WORD = "[A-Z]*[a-z]*[0-9]*"

# Uppercase word, not followed by lowercase letters.
_WORD_UPPER = "[A-Z]+(?![a-z])[0-9]*"


def pascal_case(value: str, strict: bool = True) -> str:
    def substitute_word(symbols, word):
        if strict:
            return word.capitalize()  # Remove all delimiters

        if word.islower():
            delimiter_length = len(symbols[:-1])  # Lose one delimiter
        else:
            delimiter_length = len(symbols)  # Preserve all delimiters

        return ("_" * delimiter_length) + word.capitalize()

    return re.sub(f"({_SYMBOLS})({_WORD_UPPER}|{_WORD})", lambda groups: substitute_word(groups[1], groups[2]), value,)


def get_server_env() -> str:
    return os.environ.get("SERVER_ENV", "local").lower()
