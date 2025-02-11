# Released under the MIT License. See LICENSE for details.
"""Initial ballistica bootstrapping."""

from __future__ import annotations

import os
import sys
import signal
import threading
from typing import TYPE_CHECKING

import _ba

if TYPE_CHECKING:
    from typing import Any, TextIO, Callable


class _BAConsoleRedirect:

    def __init__(self, original: TextIO, call: Callable[[str], None]) -> None:
        self._lock = threading.Lock()
        self._linebits: list[str] = []
        self._original = original
        self._call = call
        self._pending_ship = False

    def write(self, sval: Any) -> None:
        """Override standard stdout write."""

        self._call(sval)

        # Now do logging:
        # Add it to our accumulated line.
        # If the message ends in a newline, we can ship it
        # immediately as a log entry. Otherwise, schedule a ship
        # next cycle (if it hasn't yet at that point) so that we
        # can accumulate subsequent prints.
        # (so stuff like print('foo', 123, 'bar') will ship as one entry)
        with self._lock:
            self._linebits.append(sval)
        if sval.endswith('\n'):
            self._shiplog()
        else:
            _ba.pushcall(self._shiplog,
                         from_other_thread=True,
                         suppress_other_thread_warning=True)

    def _shiplog(self) -> None:
        with self._lock:
            line = ''.join(self._linebits)
            if not line:
                return
            self._linebits = []

        # Log messages aren't expected to have trailing newlines.
        if line.endswith('\n'):
            line = line[:-1]
        _ba.log(line, to_stdout=False)

    def flush(self) -> None:
        """Flush the file."""
        self._original.flush()

    def isatty(self) -> bool:
        """Are we a terminal?"""
        return self._original.isatty()


sys.stdout = _BAConsoleRedirect(sys.stdout, _ba.print_stdout)  # type: ignore
sys.stderr = _BAConsoleRedirect(sys.stderr, _ba.print_stderr)  # type: ignore

# Let's lookup mods first (so users can do whatever they want).
# and then our bundled scripts last (don't want bundled site-package
# stuff overwriting system versions)
sys.path.insert(0, _ba.env()['python_directory_user'])
sys.path.append(_ba.env()['python_directory_app'])
sys.path.append(_ba.env()['python_directory_app_site'])

# Tell Python to not handle SIGINT itself (it normally generates
# KeyboardInterrupts which make a mess; we want to do a simple
# clean exit). We capture interrupts per-platform in the C++ layer.
# I tried creating a handler in Python but it seemed to often have
# a delay of up to a second before getting called. (not a huge deal
# but I'm picky).
signal.signal(signal.SIGINT, signal.SIG_DFL)  # Do default handling.

# ..though it turns out we need to set up our C signal handling AFTER
# we've told Python to disable its own; otherwise (on Mac at least) it
# wipes out our existing C handler.
_ba.setup_sigint()

# Sanity check: we should always be run in UTF-8 mode.
if sys.flags.utf8_mode != 1:
    print('ERROR: Python\'s UTF-8 mode is not set.'
          ' This will likely result in errors.')

debug_build = _ba.env()['debug_build']

# We expect dev_mode on in debug builds and off otherwise.
if debug_build != sys.flags.dev_mode:
    print(f'WARNING: Mismatch in debug_build {debug_build}'
          f' and sys.flags.dev_mode {sys.flags.dev_mode}')

# In embedded situations (when we're providing our own Python) let's
# also provide our own root certs so ssl works. We can consider overriding
# this in particular embedded cases if we can verify that system certs
# are working.
# (We also allow forcing this via an env var if the user desires)
# pylint: disable=wrong-import-position
if (_ba.contains_python_dist()
        or os.environ.get('BA_USE_BUNDLED_ROOT_CERTS') == '1'):
    import certifi

    # Let both OpenSSL and requests (if present) know to use this.
    os.environ['SSL_CERT_FILE'] = os.environ['REQUESTS_CA_BUNDLE'] = (
        certifi.where())

# FIXME: I think we should init Python in the main thread, which should
#  also avoid these issues. (and also might help us play better with
#  Python debuggers?)

# Gloriously hacky workaround here:
# Our 'main' Python thread is the game thread (not the app's main
# thread) which means it has a small stack compared to the main
# thread (at least on apple). Sadly it turns out this causes the
# debug build of Python to blow its stack immediately when doing
# some big imports.
# Normally we'd just give the game thread the same stack size as
# the main thread and that'd be the end of it. However
# we're using std::threads which it turns out have no way to set
# the stack size (as of fall '19). Grumble.
#
# However python threads *can* take custom stack sizes.
# (and it appears they might use the main thread's by default?..)
# ...so as a workaround in the debug version, we can run problematic
# heavy imports here in another thread and all is well.
# If we ever see stack overflows in our release build we'll have
# to take more drastic measures like switching from std::threads
# to pthreads.

if debug_build:

    def _thread_func() -> None:
        # pylint: disable=unused-import
        import json
        import urllib.request

    testthread = threading.Thread(target=_thread_func)
    testthread.start()
    testthread.join()
    del testthread

# Clear out the standard quit/exit messages since they don't work for us.
# pylint: disable=c-extension-no-member
if not TYPE_CHECKING:
    import __main__
    del __main__.__builtins__.quit
    del __main__.__builtins__.exit

# Now spin up our App instance, store it on both _ba and ba,
# and return it to the C++ layer.
# noinspection PyProtectedMember
from ba._app import App
import ba

_ba.app = ba.app = App()
