#!/usr/bin/env python
# coding=utf-8
# author=Adriano Di Luzio

"""SFTPClone tests."""

# Simply launch me by using nosetests and I'll do the magic.
# I require paramiko

# Python 2.7 backward compatibility
from __future__ import print_function
from __future__ import unicode_literals
from __future__ import absolute_import

import unicodedata

from sftpclone.t.stub_sftp import StubServer, StubSFTPServer
from sftpclone.t.utils import t_path, list_files, file_tree
from sftpclone.sftpclone import SFTPClone, main

import threading
import os
from os.path import join
from shutil import rmtree, copy
import random
from stat import S_ISDIR
import logging
import functools

import paramiko
import socket
import select

from nose import with_setup
from nose.tools import assert_raises, raises, eq_
from contextlib import contextmanager

import sys
# unicode / string differentiation
if sys.version_info > (3, 0):
    from io import StringIO
else:
    from StringIO import StringIO

REMOTE_ROOT = t_path("server_root")
REMOTE_FOLDER = "server_folder"
REMOTE_PATH = join(REMOTE_ROOT, REMOTE_FOLDER)

LOCAL_FOLDER_NAME = "local_folder"
LOCAL_FOLDER = t_path(LOCAL_FOLDER_NAME)

event = threading.Event()

# attach existing loggers (use --nologcapture option to see output)
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


def _start_sftp_server():
    """Start the SFTP local server."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setblocking(0)
    sock.bind(('localhost', 2222))
    sock.listen(10)

    reads = {sock}
    others = set()

    while not event.is_set():
        ready_to_read, _, _ = \
            select.select(
                reads,
                others,
                others,
                1)

        if sock in ready_to_read:
            client_socket, address = sock.accept()
            ts = paramiko.Transport(client_socket)

            host_key = paramiko.RSAKey.from_private_key_file(
                t_path('server_id_rsa')
            )
            ts.add_server_key(host_key)
            server = StubServer()
            ts.set_subsystem_handler(
                'sftp', paramiko.SFTPServer, StubSFTPServer)
            ts.start_server(server=server)

    sock.close()


def setup_module():
    """Setup in a new thread the SFTP local server."""
    os.mkdir(REMOTE_ROOT)

    t = threading.Thread(target=_start_sftp_server, name="server")
    t.start()


def teardown_module():
    """Stop the SFTP server by setting its event.

    Clean remaining directories (in case of failures).
    """
    event.set()

    rmtree(REMOTE_PATH, ignore_errors=True)
    rmtree(LOCAL_FOLDER, ignore_errors=True)
    rmtree(REMOTE_ROOT, ignore_errors=True)


def setup_test():
    """Create the needed directories."""
    os.mkdir(REMOTE_PATH)
    os.mkdir(LOCAL_FOLDER)
setup_test.__test__ = False


def teardown_test():
    """Clean the created directories."""
    logging.info(list_files(LOCAL_FOLDER))
    logging.info(list_files(REMOTE_PATH))

    rmtree(REMOTE_PATH, ignore_errors=True)
    rmtree(LOCAL_FOLDER, ignore_errors=True)
teardown_test.__test__ = False


def _sync(
        password=False, fix=False,
        exclude=None, ssh_agent=False,
        delete=True

):
    """Launch sync and do basic comparison of dir trees."""
    if not password:
        remote = 'test@127.0.0.1:' + '/' + REMOTE_FOLDER
    else:
        remote = 'test:secret@127.0.0.1:' + '/' + REMOTE_FOLDER

    sync = SFTPClone(
        LOCAL_FOLDER,
        remote,
        port=2222,
        fix_symlinks=fix,
        identity_files=[t_path("id_rsa")],
        exclude_file=exclude,
        ssh_agent=ssh_agent,
        delete=delete
    )
    sync.run()

    if not exclude and delete:
        # check the directory trees
        assert \
            file_tree(
                LOCAL_FOLDER
            )[LOCAL_FOLDER_NAME] == file_tree(
                REMOTE_PATH
            )[REMOTE_FOLDER]
_sync.__test__ = False


@contextmanager
def capture_sys_output():
    """Capture standard output and error."""
    caputure_out, capture_err = StringIO(), StringIO()
    current_out, current_err = sys.stdout, sys.stderr
    try:
        sys.stdout, sys.stderr = caputure_out, capture_err
        yield caputure_out, capture_err
    finally:
        sys.stdout, sys.stderr = current_out, current_err


@contextmanager
def override_env_variables():
    """Override user enviromental variables with custom one."""
    vars = ("LOGNAME", "USER", "LNAME", "USERNAME")
    old = [os.environ[v] if v in os.environ else None for v in vars]

    for v in vars:
        os.environ[v] = "test"
    yield

    for i, v in enumerate(vars):
        if old[i]:
            os.environ[v] = old[i]


class SuppressLogging:

    """Context handler class that suppresses logging for some controlled code."""

    def __init__(self, loglevel=logging.CRITICAL):
        """Disable logging."""
        logging.disable(loglevel)
        return

    def __enter__(self):
        """Pass."""
        return

    def __exit__(self, exctype, excval, exctraceback):
        """Enable logging again."""
        logging.disable(logging.NOTSET)
        return False


def _sync_argv(argv):
    """Launch the module's main with given argv and check the result."""
    argv.append("-o")  # allow unknown hosts
    main(argv)

    assert \
        file_tree(
            LOCAL_FOLDER
        )[LOCAL_FOLDER_NAME] == file_tree(
            REMOTE_PATH
        )[REMOTE_FOLDER]
_sync_argv.__test__ = False


@with_setup(setup_test, teardown_test)
def test_cli_args():
    """Test CLI arguments."""
    # Suppress STDERR
    with capture_sys_output():
        assert_raises(SystemExit, _sync_argv, [])
        assert_raises(SystemExit, _sync_argv, [LOCAL_FOLDER])

    with override_env_variables():
        _sync_argv(
            [LOCAL_FOLDER,
             '127.0.0.1:' + '/' + REMOTE_FOLDER,
             '-f',
             '-k', t_path("id_rsa"),
             '-p', "2222",
             '-d'
             ],
        )

    _sync_argv(
        [LOCAL_FOLDER,
         'test@127.0.0.1:' + '/' + REMOTE_FOLDER,
         '-f',
         '-k', t_path("id_rsa"),
         '-p', "2222",
         '-d'
         ],
    )

    _sync_argv(
        [LOCAL_FOLDER,
         'test:secret@127.0.0.1:' + '/' + REMOTE_FOLDER,
         '-p', "2222",
         '-d'
         ],
    )

    _sync_argv(
        [LOCAL_FOLDER,
         'test:secret@127.0.0.1:' + '/' + REMOTE_FOLDER,
         '-p', "2222",
         '-n', t_path("known_hosts")
         ],
    )

    _sync_argv(
        [LOCAL_FOLDER,
         'backup:' + '/' + REMOTE_FOLDER,
         '-c', t_path("config"),
         # hard to insert relative path in cfg, so we have to cheat
         '-k', t_path("id_rsa"),
         '-d'
         ],
    )


@with_setup(setup_test, teardown_test)
def test_remote_tilde_home():
    """Test tilde expansion on remote end."""
    normal_files = ("bar", "bis")  # just to add noise
    for f in normal_files:
        os.open(join(LOCAL_FOLDER, f), os.O_CREAT)
        os.open(join(REMOTE_PATH, f), os.O_CREAT)

    sync = SFTPClone(
        LOCAL_FOLDER,
        remote_url='test@127.0.0.1:' + '~' + REMOTE_FOLDER,
        port=2222,
        identity_files=[t_path("id_rsa"),]
    )
    sync.run()

    assert \
        file_tree(
            LOCAL_FOLDER
        )[LOCAL_FOLDER_NAME] == file_tree(
            REMOTE_PATH
        )[REMOTE_FOLDER]


@with_setup(setup_test, teardown_test)
@raises(SystemExit)
def test_ssh_agent_failure():
    """Test ssh_agent failure with bad keys (default)."""
    # Suppress STDERR
    with SuppressLogging():
        with capture_sys_output():
            _sync(ssh_agent=True)


@with_setup(setup_test, teardown_test)
def test_relative_link_to_inner_dir():
    """Test creation of a relative link to a subnode of the tree.

    dovecot.sieve -> sieve/filtri.sieve
    sieve/
        filtri.sieve
    """
    local_no_slash = LOCAL_FOLDER \
        if not LOCAL_FOLDER.endswith("/") else LOCAL_FOLDER.rstrip("/")

    os.mkdir(join(LOCAL_FOLDER, "sieve"))
    source = join(LOCAL_FOLDER, "sieve", "filtri.sieve")
    os.open(source, os.O_CREAT)
    os.symlink(
        source[len(local_no_slash) + 1:],
        join(LOCAL_FOLDER, "dovecot.sieve")
    )
    _sync()
    eq_(
        source[len(local_no_slash) + 1:],
        os.readlink(
            join(REMOTE_PATH, "dovecot.sieve")
        )
    )


@with_setup(setup_test, teardown_test)
def test_already_relative_link_to_inner_dir():
    """Test creation of a relative link (that already exists) to a subnode of the tree.

    dovecot.sieve -> sieve/filtri.sieve
    sieve/
        filtri.sieve

    while on remote there is:
    dovecot.sieve -> foo
    """
    local_no_slash = LOCAL_FOLDER \
        if not LOCAL_FOLDER.endswith("/") else LOCAL_FOLDER.rstrip("/")

    os.mkdir(join(LOCAL_FOLDER, "sieve"))
    source = join(LOCAL_FOLDER, "sieve", "filtri.sieve")
    os.open(source, os.O_CREAT)
    os.symlink(
        source[len(local_no_slash) + 1:],
        join(LOCAL_FOLDER, "dovecot.sieve")
    )

    os.symlink(
        "foo",
        join(REMOTE_PATH, "dovecot.sieve")
    )

    _sync()
    eq_(
        source[len(local_no_slash) + 1:],
        os.readlink(
            join(REMOTE_PATH, "dovecot.sieve")
        )
    )


@with_setup(setup_test, teardown_test)
def test_exclude():
    """Test pattern exclusion handling."""
    excluded = {"foofolder"}
    os.mkdir(join(LOCAL_FOLDER, "foofolder"))

    excluded |= {"foo", "foofile"}
    os.open(join(LOCAL_FOLDER, "file_one"), os.O_CREAT)
    os.open(join(LOCAL_FOLDER, "file_two"), os.O_CREAT)
    os.open(join(LOCAL_FOLDER, "foo"), os.O_CREAT)
    os.open(join(LOCAL_FOLDER, "foofile"), os.O_CREAT)

    _sync(exclude=t_path("exclude"))

    assert not set(os.listdir(REMOTE_PATH)) & excluded


@with_setup(setup_test, teardown_test)
def test_inner_exclude():
    """Test pattern exclusion (with recursion) handling."""
    os.mkdir(join(LOCAL_FOLDER, "bar"))
    os.mkdir(join(LOCAL_FOLDER, "bar", "inner"))

    os.open(join(LOCAL_FOLDER, "bar", "file_one"), os.O_CREAT)
    os.open(join(LOCAL_FOLDER, "bar", "inner", "foo"), os.O_CREAT)
    os.open(join(LOCAL_FOLDER, "bar", "inner", "bar"), os.O_CREAT)

    _sync(exclude=t_path("exclude"))

    assert set(os.listdir(join(REMOTE_PATH, "bar"))) == {"file_one", "inner"}
    eq_(set(os.listdir(join(REMOTE_PATH, "bar", "inner"))), {"bar"})


@with_setup(setup_test, teardown_test)
def test_local_relative_link():
    """Test relative links creation/update (cases C/D)."""
    old_cwd = os.getcwd()
    os.chdir(LOCAL_FOLDER)  # relative links!

    inside_symlinks = {
        "3": "afile",
        "5": "inner/foo"
    }

    outside_symlinks = {
        "4": "../foo"
    }

    for link_name, source in inside_symlinks.items():
        os.symlink(source, link_name)

    for link_name, source in outside_symlinks.items():
        os.symlink(source, link_name)

    normal_files = ("bar", "bis")  # just to add noise
    for f in normal_files:
        os.open(f, os.O_CREAT)
        os.open(join(REMOTE_PATH, f), os.O_CREAT)

    _sync()

    for link_name, source in inside_symlinks.items():
        assert os.readlink(join(REMOTE_PATH, link_name)) == source

    for link_name, source in outside_symlinks.items():
        assert os.readlink(join(REMOTE_PATH, link_name)) == source

    os.chdir(old_cwd)


@with_setup(setup_test, teardown_test)
def test_local_absolute_link():
    """Test absolute links creation/update (cases A/B)."""
    inside_symlinks = {
        "3": "afile",  # case A
    }

    outside_symlinks = {
        "4": "/dev/null"  # case B
    }

    os.mkdir(join(REMOTE_ROOT, "dev"))  # otherwise absolute links will fail!

    for link_name, source in inside_symlinks.items():
        os.symlink(join(LOCAL_FOLDER, source), join(LOCAL_FOLDER, link_name))

    for link_name, source in outside_symlinks.items():
        os.symlink(source, join(LOCAL_FOLDER, link_name))

    _sync(fix=True)

    for link_name, source in inside_symlinks.items():
        assert os.readlink(join(REMOTE_PATH, link_name)) == join(
            REMOTE_PATH, source)

    for link_name, source in outside_symlinks.items():
        assert os.readlink(join(REMOTE_PATH, link_name))[
            len(REMOTE_ROOT):] == source


@with_setup(setup_test, teardown_test)
def test_orphaned_remote_symlink():
    """Test deletion of orphaned remote links (not existing in local folder)."""
    os.open(join(REMOTE_PATH, "file"), os.O_CREAT)
    os.open(join(LOCAL_FOLDER, "file"), os.O_CREAT)

    os.symlink(
        join(REMOTE_PATH, "file"),
        join(REMOTE_PATH, "link")
    )

    _sync(fix=True)


@with_setup(setup_test, teardown_test)
def test_directory_upload():
    """Test upload/creation of whole directory trees."""
    # add some dirs to both the local/remote directories
    local_dirs = {str(f) for f in range(8)}
    remote_dirs = set(random.sample(local_dirs, 3))

    spurious_dir = join(
        REMOTE_PATH, random.choice(tuple(local_dirs - remote_dirs)))
    os.open(spurious_dir, os.O_CREAT)

    for f in local_dirs:
        os.mkdir(join(LOCAL_FOLDER, f))
    for f in remote_dirs:
        os.mkdir(join(REMOTE_PATH, f))

    # Locally different is folder, but remotely is a file
    f = "different"
    remote_dirs |= {f}
    os.open(join(REMOTE_PATH, f), os.O_CREAT)
    local_dirs |= {f}
    os.mkdir(join(LOCAL_FOLDER, f))

    full_dirs = set(random.sample(local_dirs, 2))
    for f in full_dirs:
        for i in range(random.randint(1, 10)):
            os.open(join(LOCAL_FOLDER, f, str(i)), os.O_CREAT)

    _sync()

    assert S_ISDIR(os.stat(spurious_dir).st_mode)
    for d in full_dirs:
        assert os.listdir(join(LOCAL_FOLDER, d)) == os.listdir(
            join(REMOTE_PATH, d))


@with_setup(setup_test, teardown_test)
def test_file_upload():
    """
    Test upload/creation of files.

    Upload files present in the local directory but not in the remote one.
    """
    # add some file to both the local/remote directories
    local_files = {str(f) for f in range(5)}
    remote_files = set(random.sample(local_files, 3))

    for f in local_files:
        os.open(join(LOCAL_FOLDER, f), os.O_CREAT)
    for f in remote_files:
        os.open(join(REMOTE_PATH, f), os.O_CREAT)

    local_files |= {"5"}
    with open(join(LOCAL_FOLDER, "5"), 'w') as f:
        print("This is the local file.", file=f)
    remote_files |= {"5"}
    with open(join(REMOTE_PATH, "5"), 'w') as f:
        print("This is the remote file.", file=f)

    local_files |= {"6"}
    l = join(LOCAL_FOLDER, "6")
    with open(l, 'w') as f:
        print("This is another file.", file=f)
    remote_files |= {"6"}
    copy(l, join(REMOTE_PATH, "6"))

    local_files |= {"permissions"}
    l = join(LOCAL_FOLDER, "permissions")
    os.open(l, os.O_CREAT)

    # Sync and check that missing files where uploaded
    # Password authentication here!
    _sync(password=True)

    assert set(os.listdir(REMOTE_PATH)) == local_files
    files = {"5", "6", "permissions"}
    for f in files:
        lf, rf = join(LOCAL_FOLDER, f), join(REMOTE_PATH, f)
        assert os.stat(lf).st_size == os.stat(rf).st_size
        assert os.stat(lf).st_mtime == os.stat(rf).st_mtime
        assert os.stat(lf).st_mode == os.stat(rf).st_mode

        with open(lf, 'r') as f_one:
            with open(rf, 'r') as f_two:
                assert f_one.read() == f_two.read()


@with_setup(setup_test, teardown_test)
def test_remote_but_not_local_files():
    """
    Test deletion of files (when needed).

    Remove files present on the remote directory but not in the local one.
    """
    # add some file to the remote directory
    remote_files = {str(f) for f in range(8)}
    local_files = set(random.sample(remote_files, 3))

    for f in remote_files:
        os.open(join(REMOTE_PATH, f), os.O_CREAT)
    for f in local_files:
        os.open(join(LOCAL_FOLDER, f), os.O_CREAT)

    # Locally different is folder, but remotely is a file
    f = "different"
    remote_files |= {f}
    os.open(join(REMOTE_PATH, f), os.O_CREAT)
    local_files |= {f}
    os.mkdir(join(LOCAL_FOLDER, f))

    # Sync and check the results
    _sync()
    assert set(os.listdir(REMOTE_PATH)) == local_files


@with_setup(setup_test, teardown_test)
def test_remote_but_not_local_directories():
    """
    Test deletion of directories (when needed).

    Remove directories present on the remote directory but not in the local one.
    """
    # add some directories to the remote directory
    remote_dirs = {str(f) for f in range(6)}
    local_dirs = set(random.sample(remote_dirs, 4))

    for f in remote_dirs:
        os.mkdir(join(REMOTE_PATH, f))
    for f in local_dirs:
        os.mkdir(join(LOCAL_FOLDER, f))

    # now we create some remote directories that should be deleted
    full_dirs = set(random.sample(local_dirs, 2))
    for f in full_dirs:
        inner_path = join(REMOTE_PATH, f)
        for s in range(random.randint(1, 4)):
            inner_path = join(inner_path, str(s))
            os.mkdir(inner_path)

        for i in range(3):
            os.open(join(inner_path, str(i)), os.O_CREAT)

    # Locally different is a file, but remotely is a folder
    f = "different"
    remote_dirs |= {f}
    os.open(join(LOCAL_FOLDER, f), os.O_CREAT)
    local_dirs |= {f}
    os.mkdir(join(REMOTE_PATH, f))

    # Sync and check the results
    _sync()

    assert set(os.listdir(REMOTE_PATH)) == local_dirs
    for f in full_dirs:
        assert os.listdir(join(REMOTE_PATH, f)) == os.listdir(
            join(LOCAL_FOLDER, f))


@with_setup(setup_test, teardown_test)
def test_remote_dot_not_delete():
    """Test do not delete missing local files on remote end."""
    normal_files = ("bar", "bis")  # just to add noise
    for f in normal_files:
        os.open(join(LOCAL_FOLDER, f), os.O_CREAT)
        os.open(join(REMOTE_PATH, f), os.O_CREAT)

    normal_dir = "dir"
    os.mkdir(join(LOCAL_FOLDER, normal_dir))

    remote_only = ("remote", "only")  # just to add noise
    for f in remote_only:
        os.open(join(REMOTE_PATH, f), os.O_CREAT)

    remote_dir = "remote_dir"
    os.mkdir(join(REMOTE_PATH, remote_dir))

    _sync(delete=False)

    local = set(file_tree(LOCAL_FOLDER)[LOCAL_FOLDER_NAME].keys())
    remote = set(file_tree(REMOTE_PATH)[REMOTE_FOLDER].keys())
    normal_files = set(normal_files)
    remote_only = set(remote_only)

    assert local < remote
    assert normal_files < remote
    assert normal_dir in remote
    assert remote_only < remote
    assert remote_dir in remote
    assert remote_dir not in local
    assert not remote_only & local


@with_setup(setup_test, teardown_test)
def test_handle_unicode_files():
    """Test handling unicode files."""
    files = ("à", "é")
    for f in files:
        os.open(join(LOCAL_FOLDER, f), os.O_CREAT)

    local_dir = "container"
    os.mkdir(join(LOCAL_FOLDER, local_dir))

    unicode_name = "Sağlayıcısı"
    os.open(join(LOCAL_FOLDER, local_dir, unicode_name), os.O_CREAT)

    directory = "ò"
    os.mkdir(join(REMOTE_PATH, directory))

    _sync()

    remote_files = os.listdir(REMOTE_PATH)

    _u = functools.partial(unicodedata.normalize, "NFKD")

    remote_files = {_u(c) for c in remote_files}
    files = {_u(c) for c in files}
    files |= {_u("container")}
    assert remote_files == files
    assert _u(unicode_name) in (_u(f) for f in os.listdir(join(REMOTE_PATH, "container")))

