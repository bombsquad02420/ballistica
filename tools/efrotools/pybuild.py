# Released under the MIT License. See LICENSE for details.
#
"""Functionality related to building python for ios, android, etc."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from efrotools import PYVER, run, readfile, writefile, replace_one

if TYPE_CHECKING:
    from typing import Any

ENABLE_OPENSSL = True
NEWER_PY_TEST = True

PY_VER_EXACT_ANDROID = '3.9.10'
PY_VER_EXACT_APPLE = '3.9.6'

# Filenames we prune from Python lib dirs in source repo to cut down on size.
PRUNE_LIB_NAMES = [
    'config-*', 'idlelib', 'lib-dynload', 'lib2to3', 'multiprocessing',
    'pydoc_data', 'site-packages', 'ensurepip', 'tkinter', 'wsgiref',
    'distutils', 'turtle.py', 'turtledemo', 'test', 'sqlite3/test', 'unittest',
    'dbm', 'venv', 'ctypes/test', 'imaplib.py', '_sysconfigdata_*'
]

# Same but for DLLs dir (windows only)
PRUNE_DLL_NAMES = ['*.ico']


def build_apple(arch: str, debug: bool = False) -> None:
    """Run a build for the provided apple arch (mac, ios, or tvos)."""
    import platform
    import subprocess
    from efro.error import CleanError

    # IMPORTANT; seems we currently wind up building against /usr/local gettext
    # stuff. Hopefully the maintainer fixes this, but for now I need to
    # remind myself to blow it away while building.
    # (via brew remove gettext --ignore-dependencies)
    if ('MacBook-Fro' in platform.node()
            and os.environ.get('SKIP_GETTEXT_WARNING') != '1'):
        if (subprocess.run('which gettext', shell=True,
                           check=False).returncode == 0):
            raise CleanError(
                'NEED TO TEMP-KILL GETTEXT (or set SKIP_GETTEXT_WARNING=1)')

    builddir = 'build/python_apple_' + arch + ('_debug' if debug else '')
    run('rm -rf "' + builddir + '"')
    run('mkdir -p build')
    run('git clone '
        'https://github.com/beeware/Python-Apple-support.git "' + builddir +
        '"')
    os.chdir(builddir)

    # TEMP: Check out a particular commit while the branch head is broken.
    # We can actually fix this to use the current one, but something
    # broke in the underlying build even on old commits so keeping it
    # locked for now...
    # run('git checkout bf1ed73d0d5ff46862ba69dd5eb2ffaeff6f19b6')
    run(f'git checkout {PYVER}')

    txt = readfile('Makefile')

    # Fix a bug where spaces in PATH cause errors (darn you vmware fusion!)
    txt = replace_one(
        txt, '&& PATH=$(PROJECT_DIR)/$(PYTHON_DIR-macOS)/dist/bin:$(PATH) .',
        '&& PATH="$(PROJECT_DIR)/$(PYTHON_DIR-macOS)/dist/bin:$(PATH)" .')

    # Turn doc strings on; looks like it only adds a few hundred k.
    txt = txt.replace('--without-doc-strings', '--with-doc-strings')

    # Set mac/ios version reqs
    # (see issue with utimensat and futimens).
    txt = replace_one(txt, 'MACOSX_DEPLOYMENT_TARGET=10.8',
                      'MACOSX_DEPLOYMENT_TARGET=10.15')
    # And equivalent iOS (11+).
    txt = replace_one(txt, 'CFLAGS-iOS=-mios-version-min=8.0',
                      'CFLAGS-iOS=-mios-version-min=13.0')
    # Ditto for tvOS.
    txt = replace_one(txt, 'CFLAGS-tvOS=-mtvos-version-min=9.0',
                      'CFLAGS-tvOS=-mtvos-version-min=13.0')

    if debug:

        # Add debug build flag
        # (Currently expect to find 2 instances of this).
        dline = '--with-doc-strings --enable-ipv6 --without-ensurepip'
        splitlen = len(txt.split(dline))
        if splitlen != 3:
            raise Exception('unexpected configure lines')
        txt = txt.replace(dline, '--with-pydebug ' + dline)

        # Debug has a different name.
        # (Currently expect to replace 12 instances of this).
        dline = ('python$(PYTHON_VER)'
                 if NEWER_PY_TEST else 'python$(PYTHON_VER)m')
        splitlen = len(txt.split(dline))
        if splitlen != 13:
            raise RuntimeError(f'Unexpected configure line count {splitlen}.')
        txt = txt.replace(
            dline, 'python$(PYTHON_VER)d'
            if NEWER_PY_TEST else 'python$(PYTHON_VER)dm')

    # Inject our custom modifications to fire before building.
    txt = txt.replace(
        '	# Configure target Python\n',
        '	cd $$(PYTHON_DIR-$1) && '
        f'../../../../../tools/pcommand python_apple_patch {arch}\n'
        '	# Configure target Python\n',
    )
    writefile('Makefile', txt)

    # Ok; let 'er rip.
    # (we run these in parallel so limit to 1 job a piece;
    # otherwise they inherit the -j12 or whatever from the top level)
    # (also this build seems to fail with multiple threads)
    run(
        'make -j1 ' + {
            'mac': 'Python-macOS',
            # 'mac': 'build/macOS/Python-3.9.6-macOS/Makefile',
            'ios': 'Python-iOS',
            'tvos': 'Python-tvOS'
        }[arch])
    print('python build complete! (apple/' + arch + ')')


def apple_patch(arch: str) -> None:
    """Run necessary patches on an apple archive before building."""

    # Here's the deal: we want our custom static python libraries to
    # be as similar as possible on apple platforms and android, so let's
    # blow away all the tweaks that this setup does to Setup.local and
    # instead apply our very similar ones directly to Setup, just as we
    # do for android.
    with open('Modules/Setup.local', 'w', encoding='utf-8') as outfile:
        outfile.write('# cleared by efrotools build\n')

    _patch_setup_file('apple', arch)


def build_android(rootdir: str, arch: str, debug: bool = False) -> None:
    """Run a build for android with the given architecture.

    (can be arm, arm64, x86, or x86_64)
    """
    import subprocess

    builddir = 'build/python_android_' + arch + ('_debug' if debug else '')
    run('rm -rf "' + builddir + '"')
    run('mkdir -p build')
    run('git clone '
        'https://github.com/yan12125/python3-android.git "' + builddir + '"')
    os.chdir(builddir)

    # These builds require ANDROID_NDK to be set; make sure that's the case.
    os.environ['ANDROID_NDK'] = subprocess.check_output(
        [f'{rootdir}/tools/pcommand', 'android_sdk_utils',
         'get-ndk-path']).decode().strip()

    # Disable builds for dependencies we don't use.
    ftxt = readfile('Android/build_deps.py')
    # ftxt = replace_one(ftxt, '        NCurses,\n',
    #                    '#        NCurses,\n',)
    ftxt = replace_one(
        ftxt,
        '        '
        'BZip2, GDBM, LibFFI, LibUUID, OpenSSL, Readline, SQLite, XZ, ZLib,\n',
        '        '
        'BZip2, LibUUID, OpenSSL, SQLite, XZ, ZLib,\n',
    )

    # Older ssl seems to choke on newer ndk layouts.
    ftxt = replace_one(
        ftxt,
        "source = 'https://www.openssl.org/source/openssl-1.1.1h.tar.gz'",
        "source = 'https://www.openssl.org/source/openssl-1.1.1l.tar.gz'")

    # Give ourselves a handle to patch the OpenSSL build.
    ftxt = replace_one(
        ftxt,
        '        # OpenSSL handles NDK internal paths by itself',
        '        # Ericf addition: do some patching:\n'
        '        self.run(["../../../../../../../tools/pcommand",'
        ' "python_android_patch_ssl"])\n'
        '        # OpenSSL handles NDK internal paths by itself',
    )

    writefile('Android/build_deps.py', ftxt)

    # Tweak some things in the base build script; grab the right version
    # of Python and also inject some code to modify bits of python
    # after it is extracted.
    ftxt = readfile('build.sh')
    ftxt = replace_one(ftxt, 'PYVER=3.9.0', f'PYVER={PY_VER_EXACT_ANDROID}')
    ftxt = replace_one(
        ftxt, '    popd\n', f'    ../../../tools/pcommand'
        f' python_android_patch Python-{PY_VER_EXACT_ANDROID}\n    popd\n')
    writefile('build.sh', ftxt)

    # Ok, let 'er rip
    exargs = ' --with-pydebug' if debug else ''
    run(f'ARCH={arch} ANDROID_API=21 ./build.sh{exargs}')
    print('python build complete! (android/' + arch + ')')


def android_patch() -> None:
    """Run necessary patches on an android archive before building."""
    _patch_setup_file('android', '?')


def _patch_setup_file(platform: str, arch: str) -> None:
    # pylint: disable=too-many-locals
    # pylint: disable=too-many-statements
    fname = 'Modules/Setup'
    ftxt = readfile(fname)

    if platform == 'android':
        prefix = '$(srcdir)/Android/sysroot/usr'
        uuid_ex = f' -L{prefix}/lib -luuid'
        zlib_ex = f' -I{prefix}/include -L{prefix}/lib -lz'
        bz2_ex = f' -I{prefix}/include -L{prefix}/lib -lbz2'
        ssl_ex = f' -DUSE_SSL -I{prefix}/include -L{prefix}/lib -lssl -lcrypto'
        sqlite_ex = f' -I{prefix}/include -L{prefix}/lib'
        hash_ex = ' -DUSE_SSL -lssl -lcrypto'
        lzma_ex = ' -llzma'
    elif platform == 'apple':
        prefix = '$(srcdir)/Android/sysroot/usr'
        uuid_ex = ''
        zlib_ex = ' -I$(prefix)/include -lz'
        bz2_ex = (' -I$(srcdir)/../Support/BZip2/Headers'
                  ' -L$(srcdir)/../Support/BZip2 -lbzip2')
        ssl_ex = (' -I$(srcdir)/../Support/OpenSSL/Headers'
                  ' -L$(srcdir)/../Support/OpenSSL -lOpenSSL -DUSE_SSL')
        sqlite_ex = ' -I$(srcdir)/Modules/_sqlite'
        hash_ex = (' -I$(srcdir)/../Support/OpenSSL/Headers'
                   ' -L$(srcdir)/../Support/OpenSSL -lOpenSSL -DUSE_SSL')
        lzma_ex = (' -I$(srcdir)/../Support/XZ/Headers'
                   ' -L$(srcdir)/../Support/XZ/ -lxz')
    else:
        raise RuntimeError(f'Unknown platform {platform}')

    # This list should contain all possible compiled modules to start.
    # If any .so files are coming out of builds, their names should be
    # added here to stop that.
    cmodules = [
        '_asyncio', '_bisect', '_blake2', '_codecs_cn', '_codecs_hk',
        '_codecs_iso2022', '_codecs_jp', '_codecs_kr', '_codecs_tw',
        '_contextvars', '_crypt', '_csv', '_ctypes_test', '_ctypes',
        '_curses_panel', '_curses', '_datetime', '_decimal', '_elementtree',
        '_heapq', '_json', '_lsprof', '_lzma', '_md5', '_multibytecodec',
        '_multiprocessing', '_opcode', '_pickle', '_posixsubprocess', '_queue',
        '_random', '_sha1', '_sha3', '_sha256', '_sha512', '_socket',
        '_statistics', '_struct', '_testbuffer', '_testcapi',
        '_testimportmultiple', '_testinternalcapi', '_testmultiphase', '_uuid',
        '_xxsubinterpreters', '_xxtestfuzz', '_zoneinfo', 'array', 'audioop',
        'binascii', 'cmath', 'fcntl', 'grp', 'math', 'mmap', 'ossaudiodev',
        'parser', 'pyexpat', 'resource', 'select', 'syslog', 'termios',
        'unicodedata', 'xxlimited', 'zlib'
    ]

    # Selectively uncomment some existing modules for static compilation.
    enables = [
        '_asyncio', 'array', 'cmath', 'math', '_contextvars', '_struct',
        '_random', '_elementtree', '_pickle', '_datetime', '_zoneinfo',
        '_bisect', '_heapq', '_json', '_statistics', 'unicodedata', 'fcntl',
        'select', 'mmap', '_csv', '_socket', '_sha3', '_blake2', 'binascii',
        '_posixsubprocess'
    ]
    # Note that the _md5 and _sha modules are normally only built if the
    # system does not have the OpenSSL libs containing an optimized
    # version.
    if bool(False):
        enables += ['_md5']

    for enable in enables:
        ftxt = replace_one(ftxt, f'#{enable} ', f'{enable} ')
        cmodules.remove(enable)

    # Disable ones that were enabled:
    disables = ['xxsubtype']
    for disable in disables:
        ftxt = replace_one(ftxt, f'\n{disable} ', f'\n#{disable} ')

    # Additions:
    ftxt += '\n# Additions by efrotools:\n'

    if bool(True):
        ftxt += f'_uuid _uuidmodule.c{uuid_ex}\n'
        cmodules.remove('_uuid')

    ftxt += f'zlib zlibmodule.c{zlib_ex}\n'

    cmodules.remove('zlib')

    # Why isn't this getting built as a shared lib by default?
    # Do we need it for sure?
    ftxt += f'_hashlib _hashopenssl.c{hash_ex}\n'

    ftxt += f'_lzma _lzmamodule.c{lzma_ex}\n'
    cmodules.remove('_lzma')

    ftxt += f'_bz2 _bz2module.c{bz2_ex}\n'

    ftxt += f'_ssl _ssl.c{ssl_ex}\n'

    ftxt += (f'_sqlite3'
             f' _sqlite/cache.c'
             f' _sqlite/connection.c'
             f' _sqlite/cursor.c'
             f' _sqlite/microprotocols.c'
             f' _sqlite/module.c'
             f' _sqlite/prepare_protocol.c'
             f' _sqlite/row.c'
             f' _sqlite/statement.c'
             f' _sqlite/util.c'
             f'{sqlite_ex}'
             f' -DMODULE_NAME=\'\\"sqlite3\\"\''
             f' -DSQLITE_OMIT_LOAD_EXTENSION'
             f' -lsqlite3\n')

    # Mac needs this:
    if arch == 'mac':
        ftxt += ('\n'
                 '# efrotools: mac urllib needs this:\n'
                 '_scproxy _scproxy.c '
                 '-framework SystemConfiguration '
                 '-framework CoreFoundation\n')

    # Explicitly mark the remaining ones as disabled
    # (so Python won't try to build them as dynamic libs).
    remaining_disabled = ' '.join(cmodules)
    ftxt += ('\n# Disabled by efrotools build:\n'
             '*disabled*\n'
             f'{remaining_disabled}\n')
    writefile(fname, ftxt)

    # Ok, this is weird.
    # When applying the module Setup, python looks for any line containing *=*
    # and interprets the whole thing a a global define?...
    # This breaks things for our static sqlite compile above.
    # The check used to look for [A-Z]*=* which didn't break, so let' just
    # change it back to that for now.
    # UPDATE: Currently this seems to only be necessary on Android;
    # perhaps this broke between 3.9.6 and 3.9.7 or perhaps the apple
    # bundle already patches it ¯\_(ツ)_/¯
    fname = 'Modules/makesetup'
    txt = readfile(fname)
    if platform == 'android':
        txt = replace_one(txt, '		*=*)'
                          '	DEFS="$line$NL$DEFS"; continue;;',
                          '		[A-Z]*=*)	DEFS="$line$NL$DEFS";'
                          ' continue;;')
    assert txt.count('[A-Z]*=*') == 1
    writefile(fname, txt)


def android_patch_ssl() -> None:
    """Run necessary patches on an android ssl before building."""

    # We bundle our own SSL root certificates on various platforms and use
    # the OpenSSL 'SSL_CERT_FILE' env var override to get them to be used
    # by default. However, OpenSSL is picky about allowing env-vars to be
    # used and something about the Android environment makes it disallow
    # them. So we need to force the issue. Alternately we could explicitly
    # pass 'cafile' args to SSLContexts whenever we do network-y stuff
    # but it seems cleaner to just have things work by default.
    fname = 'crypto/getenv.c'
    txt = readfile(fname)
    txt = replace_one(
        txt,
        ('char *ossl_safe_getenv(const char *name)\n'
         '{\n'),
        ('char *ossl_safe_getenv(const char *name)\n'
         '{\n'
         '    // ERICF TWEAK: ALWAYS ALLOW GETENV.\n'
         '    return getenv(name);\n'),
    )
    writefile(fname, txt)


def winprune() -> None:
    """Prune unneeded files from windows python dists."""
    for libdir in ('assets/src/windows/Win32/Lib',
                   'assets/src/windows/x64/Lib'):
        assert os.path.isdir(libdir)
        run('cd "' + libdir + '" && rm -rf ' + ' '.join(PRUNE_LIB_NAMES))
    for dlldir in ('assets/src/windows/Win32/DLLs',
                   'assets/src/windows/x64/DLLs'):
        assert os.path.isdir(dlldir)
        run('cd "' + dlldir + '" && rm -rf ' + ' '.join(PRUNE_DLL_NAMES))
    print('Win-prune successful.')


def gather() -> None:
    """Gather per-platform python headers, libs, and modules together.

    This assumes all embeddable py builds have been run successfully,
    and that PROJROOT is the cwd.
    """
    # pylint: disable=too-many-locals

    do_android = True

    # First off, clear out any existing output.
    existing_dirs = [
        os.path.join('src/external', d) for d in os.listdir('src/external')
        if d.startswith('python-') and d != 'python-notes.txt'
    ]
    existing_dirs += [
        os.path.join('assets/src', d) for d in os.listdir('assets/src')
        if d.startswith('pylib-')
    ]
    if not do_android:
        existing_dirs = [d for d in existing_dirs if 'android' not in d]

    for existing_dir in existing_dirs:
        run('rm -rf "' + existing_dir + '"')

    apost2 = f'src/Python-{PY_VER_EXACT_ANDROID}/Android/sysroot'
    for buildtype in ['debug', 'release']:
        debug = buildtype == 'debug'
        bsuffix = '_debug' if buildtype == 'debug' else ''
        bsuffix2 = '-debug' if buildtype == 'debug' else ''
        libname = 'python' + PYVER + ('d' if debug else '')

        bases = {
            'mac': f'build/python_apple_mac{bsuffix}/build/macOS',
            'ios': f'build/python_apple_ios{bsuffix}/build/iOS',
            'tvos': f'build/python_apple_tvos{bsuffix}/build/tvOS',
            'android_arm': f'build/python_android_arm{bsuffix}/build',
            'android_arm64': f'build/python_android_arm64{bsuffix}/build',
            'android_x86': f'build/python_android_x86{bsuffix}/build',
            'android_x86_64': f'build/python_android_x86_64{bsuffix}/build'
        }
        bases2 = {
            'android_arm': f'build/python_android_arm{bsuffix}/{apost2}',
            'android_arm64': f'build/python_android_arm64{bsuffix}/{apost2}',
            'android_x86': f'build/python_android_x86{bsuffix}/{apost2}',
            'android_x86_64': f'build/python_android_x86_64{bsuffix}/{apost2}'
        }

        # Note: only need pylib for the first in each group.
        builds: list[dict[str, Any]] = [{
            'name':
                'macos',
            'group':
                'apple',
            'headers':
                bases['mac'] + '/Support/Python/Headers',
            'libs': [
                bases['mac'] + '/Support/Python/libPython.a',
                bases['mac'] + '/Support/OpenSSL/libOpenSSL.a',
                bases['mac'] + '/Support/XZ/libxz.a',
                bases['mac'] + '/Support/BZip2/libbzip2.a',
            ],
            'pylib':
                (bases['mac'] + f'/Python-{PY_VER_EXACT_APPLE}-macOS/lib'),
        }, {
            'name':
                'ios',
            'group':
                'apple',
            'headers':
                bases['ios'] + '/Support/Python/Headers',
            'libs': [
                bases['ios'] + '/Support/Python/libPython.a',
                bases['ios'] + '/Support/OpenSSL/libOpenSSL.a',
                bases['ios'] + '/Support/XZ/libxz.a',
                bases['ios'] + '/Support/BZip2/libbzip2.a',
            ],
        }, {
            'name':
                'tvos',
            'group':
                'apple',
            'headers':
                bases['tvos'] + '/Support/Python/Headers',
            'libs': [
                bases['tvos'] + '/Support/Python/libPython.a',
                bases['tvos'] + '/Support/OpenSSL/libOpenSSL.a',
                bases['tvos'] + '/Support/XZ/libxz.a',
                bases['tvos'] + '/Support/BZip2/libbzip2.a',
            ],
        }, {
            'name': 'android_arm',
            'group': 'android',
            'headers': bases['android_arm'] + f'/usr/include/{libname}',
            'libs': [
                bases['android_arm'] + f'/usr/lib/lib{libname}.a',
                bases2['android_arm'] + '/usr/lib/libssl.a',
                bases2['android_arm'] + '/usr/lib/libcrypto.a',
                bases2['android_arm'] + '/usr/lib/liblzma.a',
                bases2['android_arm'] + '/usr/lib/libsqlite3.a',
                bases2['android_arm'] + '/usr/lib/libbz2.a',
                bases2['android_arm'] + '/usr/lib/libuuid.a',
            ],
            'libinst': 'android_armeabi-v7a',
            'pylib': (bases['android_arm'] + '/usr/lib/python' + PYVER),
        }, {
            'name': 'android_arm64',
            'group': 'android',
            'headers': bases['android_arm64'] + f'/usr/include/{libname}',
            'libs': [
                bases['android_arm64'] + f'/usr/lib/lib{libname}.a',
                bases2['android_arm64'] + '/usr/lib/libssl.a',
                bases2['android_arm64'] + '/usr/lib/libcrypto.a',
                bases2['android_arm64'] + '/usr/lib/liblzma.a',
                bases2['android_arm64'] + '/usr/lib/libsqlite3.a',
                bases2['android_arm64'] + '/usr/lib/libbz2.a',
                bases2['android_arm64'] + '/usr/lib/libuuid.a',
            ],
            'libinst': 'android_arm64-v8a',
        }, {
            'name': 'android_x86',
            'group': 'android',
            'headers': bases['android_x86'] + f'/usr/include/{libname}',
            'libs': [
                bases['android_x86'] + f'/usr/lib/lib{libname}.a',
                bases2['android_x86'] + '/usr/lib/libssl.a',
                bases2['android_x86'] + '/usr/lib/libcrypto.a',
                bases2['android_x86'] + '/usr/lib/liblzma.a',
                bases2['android_x86'] + '/usr/lib/libsqlite3.a',
                bases2['android_x86'] + '/usr/lib/libbz2.a',
                bases2['android_x86'] + '/usr/lib/libuuid.a',
            ],
            'libinst': 'android_x86',
        }, {
            'name': 'android_x86_64',
            'group': 'android',
            'headers': bases['android_x86_64'] + f'/usr/include/{libname}',
            'libs': [
                bases['android_x86_64'] + f'/usr/lib/lib{libname}.a',
                bases2['android_x86_64'] + '/usr/lib/libssl.a',
                bases2['android_x86_64'] + '/usr/lib/libcrypto.a',
                bases2['android_x86_64'] + '/usr/lib/liblzma.a',
                bases2['android_x86_64'] + '/usr/lib/libsqlite3.a',
                bases2['android_x86_64'] + '/usr/lib/libbz2.a',
                bases2['android_x86_64'] + '/usr/lib/libuuid.a',
            ],
            'libinst': 'android_x86_64',
        }]

        for build in builds:
            grp = build['group']
            if not do_android and grp == 'android':
                continue
            builddir = f'src/external/python-{grp}{bsuffix2}'
            header_dst = os.path.join(builddir, 'include')
            lib_dst = os.path.join(builddir, 'lib')
            assets_src_dst = f'assets/src/pylib-{grp}'

            # Do some setup only once per group.
            if not os.path.exists(builddir):
                run('mkdir -p "' + builddir + '"')
                run('mkdir -p "' + lib_dst + '"')

                # Only pull modules into game assets on release pass.
                if not debug:
                    # Copy system modules into the src assets
                    # dir for this group.
                    run('mkdir -p "' + assets_src_dst + '"')
                    run('rsync --recursive --include "*.py"'
                        ' --exclude __pycache__ --include "*/" --exclude "*" "'
                        + build['pylib'] + '/" "' + assets_src_dst + '"')

                    # Prune a bunch of modules we don't need to cut
                    # down on size.
                    run('cd "' + assets_src_dst + '" && rm -rf ' +
                        ' '.join(PRUNE_LIB_NAMES))

                    # Some minor filtering to system scripts:
                    # on iOS/tvOS, addusersitepackages() leads to a crash
                    # due to _sysconfigdata_dm_ios_darwin module not existing,
                    # so let's skip that.
                    fname = f'{assets_src_dst}/site.py'
                    txt = readfile(fname)
                    txt = replace_one(
                        txt,
                        '    known_paths = addusersitepackages(known_paths)',
                        '    # efro tweak: this craps out on ios/tvos.\n'
                        '    # (and we don\'t use it anyway)\n'
                        '    # known_paths = addusersitepackages(known_paths)')
                    writefile(fname, txt)

                # Copy in a base set of headers (everything in a group should
                # be using the same headers)
                run(f'cp -r "{build["headers"]}" "{header_dst}"')

                # Clear whatever pyconfigs came across; we'll build our own
                # universal one below.
                run('rm ' + header_dst + '/pyconfig*')

                # Write a master pyconfig header that reroutes to each
                # platform's actual header.
                with open(header_dst + '/pyconfig.h', 'w',
                          encoding='utf-8') as hfile:
                    hfile.write(
                        '#if BA_OSTYPE_MACOS\n'
                        '#include "pyconfig-macos.h"\n\n'
                        '#elif BA_OSTYPE_IOS\n'
                        '#include "pyconfig-ios.h"\n\n'
                        '#elif BA_OSTYPE_TVOS\n'
                        '#include "pyconfig-tvos.h"\n\n'
                        '#elif BA_OSTYPE_ANDROID and defined(__arm__)\n'
                        '#include "pyconfig-android_arm.h"\n\n'
                        '#elif BA_OSTYPE_ANDROID and defined(__aarch64__)\n'
                        '#include "pyconfig-android_arm64.h"\n\n'
                        '#elif BA_OSTYPE_ANDROID and defined(__i386__)\n'
                        '#include "pyconfig-android_x86.h"\n\n'
                        '#elif BA_OSTYPE_ANDROID and defined(__x86_64__)\n'
                        '#include "pyconfig-android_x86_64.h"\n\n'
                        '#else\n'
                        '#error unknown platform\n\n'
                        '#endif\n')

            # Now copy each build's config headers in with unique names.
            cfgs = [
                f for f in os.listdir(build['headers'])
                if f.startswith('pyconfig')
            ]

            # Copy config headers to their filtered names.
            for cfg in cfgs:
                out = cfg.replace('pyconfig', 'pyconfig-' + build['name'])
                if cfg == 'pyconfig.h':

                    # For platform's root pyconfig.h we need to filter
                    # contents too (those headers can themselves include
                    # others; ios for instance points to a arm64 and a
                    # x86_64 variant).
                    contents = readfile(build['headers'] + '/' + cfg)
                    contents = contents.replace('pyconfig',
                                                'pyconfig-' + build['name'])
                    writefile(header_dst + '/' + out, contents)
                else:
                    # other configs we just rename
                    run('cp "' + build['headers'] + '/' + cfg + '" "' +
                        header_dst + '/' + out + '"')

            # Copy in libs. If the lib gave a specific install name,
            # use that; otherwise use name.
            targetdir = lib_dst + '/' + build.get('libinst', build['name'])
            run('rm -rf "' + targetdir + '"')
            run('mkdir -p "' + targetdir + '"')
            for lib in build['libs']:
                run('cp "' + lib + '" "' + targetdir + '"')

    print('Great success!')
