"""
Bundled documentation resources for the helper command.

This module provides access to bundled documentation files that are
packaged with orchestrator-auto when installed via pip.
"""

from importlib import resources
from typing import Tuple, List


def load_docs() -> Tuple[str, List[str]]:
    """
    Load bundled documentation for helper command.

    Returns:
        Tuple of (combined_docs_text, list_of_included_filenames)
    """
    docs = []
    included = []

    for filename in ["README.md", "CLI_REFERENCE.md", "CONFIGURATION.md", "TROUBLESHOOTING.md"]:
        try:
            content = resources.files(__package__).joinpath(filename).read_text(encoding="utf-8")
            docs.append(f"# {filename}\n\n{content}")
            included.append(filename)
        except FileNotFoundError:
            pass

    return "\n\n---\n\n".join(docs), included
