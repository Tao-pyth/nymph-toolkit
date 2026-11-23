"""Signal worker admission before a deliberately held SQLite transaction in tests."""

# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
from nymph_toolkit.subsystems.cognition import factory as cognition_factory


def factory(context, config):
    service = cognition_factory(context, config)
    execute = service.store.execute
    def observed(operation, *args):
        if operation == "learn":
            Path(config["path"]).with_suffix(".entered").write_text("worker admitted", encoding="ascii")
        return execute(operation, *args)
    service.store.execute = observed
    return service
