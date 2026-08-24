import sys

REQUIRED_PYTHON = (3, 10)

# This runs before any submodule is imported, so it lands before the first
# PEP 604 annotation is evaluated. Those (`TTLCache | None` and friends) are
# evaluated at import time and raise a bare TypeError on 3.9 that says nothing
# about the interpreter being too old. Written without 3.10+ syntax, and with
# %-formatting rather than an f-string, so the guard itself still runs on the
# old interpreter it exists to reject.
if sys.version_info < REQUIRED_PYTHON:
    raise RuntimeError(
        "Local Events requires Python %d.%d or newer; this interpreter is "
        "%d.%d.%d (%s). Recreate the virtualenv with a newer interpreter."
        % (
            REQUIRED_PYTHON[0],
            REQUIRED_PYTHON[1],
            sys.version_info[0],
            sys.version_info[1],
            sys.version_info[2],
            sys.executable,
        )
    )
