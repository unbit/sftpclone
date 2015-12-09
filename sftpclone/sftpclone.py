#!/usr/bin/env python

# Python 2.7 backward compatibility
from __future__ import print_function
from __future__ import unicode_literals
from __future__ import absolute_import

import paramiko
import paramiko.py3compat
import os
import os.path
import sys
import errno
from stat import S_ISDIR, S_ISLNK, S_ISREG, S_IMODE, S_IFMT
import argparse
import logging
from getpass import getuser, getpass
import glob
import socket

"""SFTPClone: sync local and remote directories."""

logger = None

try:
    # Not available in Python 2.x
    FileNotFoundError
except NameError:
    FileNotFoundError = IOError


def configure_logging(level=logging.DEBUG):
    """Configure the module logging engine."""
    if level == logging.DEBUG:
        # For debugging purposes, log from everyone!
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        return logging

    logger = logging.getLogger(__name__)
    logger.setLevel(level)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    return logger


def path_join(*args):
    """
    Wrapper around `os.path.join`.
    Makes sure to join paths of the same type (bytes).
    """
    args = (paramiko.py3compat.u(arg) for arg in args)
    return os.path.join(*args)


class SFTPClone(object):

    """The SFTPClone class."""

    def __init__(self, local_path, remote_url,
                 identity_files=None, port=None, fix_symlinks=False,
                 ssh_config_path=None, ssh_agent=False,
                 exclude_file=None, known_hosts_path=None,
                 delete=True, allow_unknown=False
                 ):
        """Init the needed parameters and the SFTPClient."""
        self.local_path = os.path.realpath(os.path.expanduser(local_path))
        self.logger = logger or configure_logging()

        if not os.path.exists(self.local_path):
            self.logger.error("Local path MUST exist. Exiting.")
            sys.exit(1)

        if exclude_file:
            with open(exclude_file) as f:
                # As in rsync's exclude from, ignore lines with leading ; and #
                # and treat each path as relative (thus by removing the leading
                # /)
                exclude_list = [
                    line.rstrip().lstrip("/")
                    for line in f
                    if not line.startswith((";", "#"))
                ]

                # actually, is a set of excluded files
                self.exclude_list = {
                    g
                    for pattern in exclude_list
                    for g in glob.glob(path_join(self.local_path, pattern))
                }
        else:
            self.exclude_list = set()

        if '@' in remote_url:
            username, hostname = remote_url.split('@', 1)
        else:
            username, hostname = None, remote_url

        hostname, self.remote_path = hostname.split(':', 1)

        password = None
        if username and ':' in username:
            username, password = username.split(':', 1)

        identity_files = identity_files or []
        if ssh_config_path:
            try:
                with open(os.path.expanduser(ssh_config_path)) as c_file:
                    ssh_config = paramiko.SSHConfig()
                    ssh_config.parse(c_file)
                    c = ssh_config.lookup(hostname)

                    hostname = c.get("hostname", hostname)
                    username = c.get("user", username)
                    port = int(c.get("port", port))
                    identity_files = c.get("identityfile", identity_files)
            except Exception as e:
                # it could be safe to continue anyway,
                # because parameters could have been manually specified
                self.logger.error(
                    "Error while parsing ssh_config file: %s. Trying to continue anyway...", e
                )

        # Set default values
        if not username:
            username = getuser()  # defaults to current user

        port = port or 22
        allow_unknown = allow_unknown or False

        self.chown = False
        self.fix_symlinks = fix_symlinks or False
        self.delete = delete if delete is not None else True

        agent_keys = list()
        agent = None

        if ssh_agent:
            try:
                agent = paramiko.agent.Agent()
                agent_keys.append(*agent.get_keys())

                if not agent_keys:
                    agent.close()
                    self.logger.error(
                        "SSH agent didn't provide any valid key. Trying to continue..."
                    )

            except paramiko.SSHException:
                if agent:
                    agent.close()
                self.logger.error(
                    "SSH agent speaks a non-compatible protocol. Ignoring it.")

        if not identity_files and not password and not agent_keys:
            self.logger.error(
                "You need to specify either a password, an identity or to enable the ssh-agent support."
            )
            sys.exit(1)

        # only root can change file owner
        if username == 'root':
            self.chown = True

        try:
            transport = paramiko.Transport((hostname, port))
        except socket.gaierror:
            self.logger.error(
                "Hostname not known. Are you sure you inserted it correctly?")
            sys.exit(1)

        try:
            ssh_host = hostname if port == 22 else "[{}]:{}".format(hostname, port)
            known_hosts = None

            """
            Before starting the transport session, we have to configure it.
            Specifically, we need to configure the preferred PK algorithm.
            If the system already knows a public key of a specific kind for
            a remote host, we have to peek its type as the preferred one.
            """
            if known_hosts_path:
                known_hosts = paramiko.HostKeys()
                known_hosts_path = os.path.realpath(
                    os.path.expanduser(known_hosts_path))

                try:
                    known_hosts.load(known_hosts_path)
                except IOError:
                    self.logger.error(
                        "Error while loading known hosts file at {}. Exiting...".format(
                            known_hosts_path)
                    )
                    sys.exit(1)

                known_keys = known_hosts.lookup(ssh_host)
                if known_keys is not None:
                    # one or more keys are already known
                    # set their type as preferred
                    transport.get_security_options().key_types = \
                        tuple(known_keys.keys())

            transport.start_client()

            if not known_hosts:
                self.logger.warning("Security warning: skipping known hosts check...")
            else:
                pubk = transport.get_remote_server_key()
                if ssh_host in known_hosts.keys():
                    if not known_hosts.check(ssh_host, pubk):
                        self.logger.error(
                            "Security warning: "
                            "remote key fingerprint {} for hostname "
                            "{} didn't match the one in known_hosts {}. "
                            "Exiting...".format(
                                pubk.get_base64(),
                                ssh_host,
                                known_hosts.lookup(hostname),
                            )
                        )
                        sys.exit(1)
                elif not allow_unknown:
                    prompt = ("The authenticity of host '{}' can't be established.\n"
                              "{} key is {}.\n"
                              "Are you sure you want to continue connecting? [y/n] ").format(
                        ssh_host, pubk.get_name(), pubk.get_base64())

                    try:
                        # Renamed to `input` in Python 3.x
                        response = raw_input(prompt)
                    except NameError:
                        response = input(prompt)

                    # Note: we do not modify the user's known_hosts file

                    if not (response == "y" or response == "yes"):
                        self.logger.error(
                            "Host authentication failed."
                        )
                        sys.exit(1)

            def perform_key_auth(pkey):
                try:
                    transport.auth_publickey(
                        username=username,
                        key=pkey
                    )
                    return True
                except paramiko.SSHException:
                    self.logger.warning(
                        "Authentication with identity {}... failed".format(pkey.get_base64()[:10])
                    )
                    return False

            if password:  # Password auth, if specified.
                transport.auth_password(
                    username=username,
                    password=password
                )
            elif agent_keys:  # SSH agent keys have higher priority
                for pkey in agent_keys:
                    if perform_key_auth(pkey):
                        break  # Authentication worked.
                else:  # None of the keys worked.
                    raise paramiko.SSHException
            elif identity_files:  # Then follow identity file (specified from CL or ssh_config)
                # Try identity files one by one, until one works
                for key_path in identity_files:
                    key_path = os.path.expanduser(key_path)

                    try:
                        key = paramiko.RSAKey.from_private_key_file(key_path)
                    except paramiko.PasswordRequiredException:
                        pk_password = getpass(
                            "It seems that your identity from '{}' is encrypted. "
                            "Please enter your password: ".format(key_path)
                        )

                        try:
                            key = paramiko.RSAKey.from_private_key_file(key_path, pk_password)
                        except paramiko.SSHException:
                            self.logger.error(
                                "Incorrect passphrase. Cannot decode private key from '{}'.".format(key_path)
                            )
                            continue
                    except IOError or paramiko.SSHException:
                        self.logger.error(
                            "Something went wrong while opening '{}'. Skipping it.".format(key_path)
                        )
                        continue

                    if perform_key_auth(key):
                        break  # Authentication worked.

                else:  # None of the keys worked.
                    raise paramiko.SSHException
            else:  # No authentication method specified, we shouldn't arrive here.
                assert False
        except paramiko.SSHException:
            self.logger.error(
                "None of the provided authentication methods worked. Exiting."
            )
            transport.close()
            sys.exit(1)
        finally:
            if agent:
                agent.close()

        self.sftp = paramiko.SFTPClient.from_transport(transport)

        if self.remote_path.startswith("~"):
            # nasty hack to let getcwd work without changing dir!
            self.sftp.chdir('.')
            self.remote_path = self.remote_path.replace(
                "~", self.sftp.getcwd())  # home is the initial sftp dir

    @staticmethod
    def _file_need_upload(l_st, r_st):
        return True if \
            l_st.st_size != r_st.st_size or int(l_st.st_mtime) != r_st.st_mtime \
            else False

    @staticmethod
    def _must_be_deleted(local_path, r_st):
        """Return True if the remote correspondent of local_path has to be deleted.

        i.e. if it doesn't exists locally or if it has a different type from the remote one."""
        # if the file doesn't exists
        if not os.path.lexists(local_path):
            return True

        # or if the file type is different
        l_st = os.lstat(local_path)
        if S_IFMT(r_st.st_mode) != S_IFMT(l_st.st_mode):
            return True

        return False

    def _match_modes(self, remote_path, l_st):
        """Match mod, utime and uid/gid with locals one."""
        self.sftp.chmod(remote_path, S_IMODE(l_st.st_mode))
        self.sftp.utime(remote_path, (l_st.st_atime, l_st.st_mtime))

        if self.chown:
            self.sftp.chown(remote_path, l_st.st_uid, l_st.st_gid)

    def file_upload(self, local_path, remote_path, l_st):
        """Upload local_path to remote_path and set permission and mtime."""
        self.sftp.put(local_path, remote_path)
        self._match_modes(remote_path, l_st)

    def remote_delete(self, remote_path, r_st):
        """Remove the remote directory node."""
        # If it's a directory, then delete content and directory
        if S_ISDIR(r_st.st_mode):
            for item in self.sftp.listdir_attr(remote_path):
                full_path = path_join(remote_path, item.filename)
                self.remote_delete(full_path, item)
            self.sftp.rmdir(remote_path)

        # Or simply delete files
        else:
            try:
                self.sftp.remove(remote_path)
            except FileNotFoundError as e:
                self.logger.error(
                    "error while removing {}. trace: {}".format(remote_path, e)
                )

    def check_for_deletion(self, relative_path=None):
        """Traverse the entire remote_path tree.

        Find files/directories that need to be deleted,
        not being present in the local folder.
        """
        if not relative_path:
            relative_path = str()  # root of shared directory tree

        remote_path = path_join(self.remote_path, relative_path)
        local_path = path_join(self.local_path, relative_path)

        for remote_st in self.sftp.listdir_attr(remote_path):
            r_lstat = self.sftp.lstat(path_join(remote_path, remote_st.filename))

            inner_remote_path = path_join(remote_path, remote_st.filename)
            inner_local_path = path_join(local_path, remote_st.filename)

            # check if remote_st is a symlink
            # otherwise could delete file outside shared directory
            if S_ISLNK(r_lstat.st_mode):
                if self._must_be_deleted(inner_local_path, r_lstat):
                    self.remote_delete(inner_remote_path, r_lstat)
                continue

            if self._must_be_deleted(inner_local_path, remote_st):
                self.remote_delete(inner_remote_path, remote_st)
            elif S_ISDIR(remote_st.st_mode):
                self.check_for_deletion(
                    path_join(relative_path, remote_st.filename)
                )

    def create_update_symlink(self, link_destination, remote_path):
        """Create a new link pointing to link_destination in remote_path position."""
        try:  # if there's anything, delete it
            self.sftp.remove(remote_path)
        except IOError:  # that's fine, nothing exists there!
            pass
        finally:  # and recreate the link
            try:
                self.sftp.symlink(link_destination, remote_path)
            except OSError as e:
                # Sometimes, if links are "too" different, symlink fails.
                # Sadly, nothing we can do about it.
                self.logger.error("error while symlinking {} to {}: {}".format(
                    remote_path, link_destination, e))

    def node_check_for_upload_create(self, relative_path, f):
        """Check if the given directory tree node has to be uploaded/created on the remote folder."""
        if not relative_path:
            # we're at the root of the shared directory tree
            relative_path = str()

        # the (absolute) local address of f.
        local_path = path_join(self.local_path, relative_path, f)
        try:
            l_st = os.lstat(local_path)
        except OSError as e:
            """A little background here.
            Sometimes, in big clusters configurations (mail, etc.),
            files could disappear or be moved, suddenly.
            There's nothing to do about it,
            system should be stopped before doing backups.
            Anyway, we log it, and skip it.
            """
            self.logger.error("error while checking {}: {}".format(relative_path, e))
            return

        if local_path in self.exclude_list:
            self.logger.info("Skipping excluded file %s.", local_path)
            return

        # the (absolute) remote address of f.
        remote_path = path_join(self.remote_path, relative_path, f)

        # First case: f is a directory
        if S_ISDIR(l_st.st_mode):
            # we check if the folder exists on the remote side
            # it has to be a folder, otherwise it would have already been
            # deleted
            try:
                self.sftp.stat(remote_path)
            except IOError:  # it doesn't exist yet on remote side
                self.sftp.mkdir(remote_path)

            self._match_modes(remote_path, l_st)

            # now, we should traverse f too (recursion magic!)
            self.check_for_upload_create(path_join(relative_path, f))

        # Second case: f is a symbolic link
        elif S_ISLNK(l_st.st_mode):
            # read the local link
            local_link = os.readlink(local_path)
            absolute_local_link = os.path.realpath(local_link)

            # is it absolute?
            is_absolute = local_link.startswith("/")
            # and does it point inside the shared directory?
            # add trailing slash (security)
            trailing_local_path = path_join(self.local_path, '')
            relpath = os.path.commonprefix(
                [absolute_local_link,
                 trailing_local_path]
            ) == trailing_local_path

            if relpath:
                relative_link = absolute_local_link[len(trailing_local_path):]
            else:
                relative_link = None

            """
            # Refactor them all, be efficient!

            # Case A: absolute link pointing outside shared directory
            #   (we can only update the remote part)
            if is_absolute and not relpath:
                self.create_update_symlink(local_link, remote_path)

            # Case B: absolute link pointing inside shared directory
            #   (we can leave it as it is or fix the prefix to match the one of the remote server)
            elif is_absolute and relpath:
                if self.fix_symlinks:
                    self.create_update_symlink(
                        join(
                            self.remote_path,
                            relative_link,
                        ),
                        remote_path
                    )
                else:
                    self.create_update_symlink(local_link, remote_path)

            # Case C: relative link pointing outside shared directory
            #   (all we can do is try to make the link anyway)
            elif not is_absolute and not relpath:
                self.create_update_symlink(local_link, remote_path)

            # Case D: relative link pointing inside shared directory
            #   (we preserve the relativity and link it!)
            elif not is_absolute and relpath:
                self.create_update_symlink(local_link, remote_path)
            """

            if is_absolute and relpath:
                if self.fix_symlinks:
                    self.create_update_symlink(
                        path_join(
                            self.remote_path,
                            relative_link,
                        ),
                        remote_path
                    )
            else:
                self.create_update_symlink(local_link, remote_path)

        # Third case: regular file
        elif S_ISREG(l_st.st_mode):
            try:
                r_st = self.sftp.lstat(remote_path)
                if self._file_need_upload(l_st, r_st):
                    self.file_upload(local_path, remote_path, l_st)
            except IOError as e:
                if e.errno == errno.ENOENT:
                    self.file_upload(local_path, remote_path, l_st)

        # Anything else.
        else:
            self.logger.warning("Skipping unsupported file %s.", local_path)

    def check_for_upload_create(self, relative_path=None):
        """Traverse the relative_path tree and check for files that need to be uploaded/created.

        Relativity here refers to the shared directory tree."""
        for f in os.listdir(
            path_join(
                self.local_path, relative_path) if relative_path else self.local_path
        ):
            self.node_check_for_upload_create(relative_path, f)

    def run(self):
        """Run the sync.

        Confront the local and the remote directories and perform the needed changes."""
        try:
            if self.delete:
                # First check for items to be removed
                self.check_for_deletion()

            # Now scan local for items to upload/create
            self.check_for_upload_create()
        except FileNotFoundError:
            # If this happens, probably the remote folder doesn't exist.
            self.logger.error(
                "Error while opening remote folder. Are you sure it does exist?")
            sys.exit(1)


def create_parser():
    """Create the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description='Sync a local and a remote folder through SFTP.'
    )

    parser.add_argument(
        "path",
        type=str,
        metavar="local-path",
        help="the path of the local folder",
    )

    parser.add_argument(
        "remote",
        type=str,
        metavar="user[:password]@hostname:remote-path",
        help="the ssh-url ([user[:password]@]hostname:remote-path) of the remote folder. "
             "The hostname can be specified as a ssh_config's hostname too. "
             "Every missing information will be gathered from there",
    )

    parser.add_argument(
        "-k",
        "--key",
        metavar="identity-path",
        action="append",
        help="private key identity path (defaults to ~/.ssh/id_rsa)"
    )

    parser.add_argument(
        "-l",
        "--logging",
        choices=['CRITICAL',
                 'ERROR',
                 'WARNING',
                 'INFO',
                 'DEBUG',
                 'NOTSET'],
        default='ERROR',
        help="set logging level"
    )

    parser.add_argument(
        "-p",
        "--port",
        default=22,
        type=int,
        help="SSH remote port (defaults to 22)"
    )

    parser.add_argument(
        "-f",
        "--fix-symlinks",
        action="store_true",
        help="fix symbolic links on remote side"
    )

    parser.add_argument(
        "-a",
        "--ssh-agent",
        action="store_true",
        help="enable ssh-agent support"
    )

    parser.add_argument(
        "-c",
        "--ssh-config",
        metavar="ssh_config path",
        default="~/.ssh/config",
        type=str,
        help="path to the ssh-configuration file (default to ~/.ssh/config)"
    )

    parser.add_argument(
        "-n",
        "--known-hosts",
        metavar="known_hosts path",
        default="~/.ssh/known_hosts",
        type=str,
        help="path to the openSSH known_hosts file"
    )

    parser.add_argument(
        "-d",
        "--disable-known-hosts",
        action="store_true",
        help="disable known_hosts fingerprint checking (security warning!)"
    )

    parser.add_argument(
        "-e",
        "--exclude-from",
        metavar="exclude-from-file-path",
        type=str,
        help="exclude files matching pattern in exclude-from-file-path"
    )

    parser.add_argument(
        "-t",
        "--do-not-delete",
        action="store_true",
        help="do not delete remote files missing from local folder"
    )

    parser.add_argument(
        "-o",
        "--allow-unknown",
        action="store_true",
        help="allow connection to unknown hosts"
    )

    return parser


def main(args=None):
    """The main."""
    parser = create_parser()
    args = vars(parser.parse_args(args))

    log_mapping = {
        'CRITICAL': logging.CRITICAL,
        'ERROR': logging.ERROR,
        'WARNING': logging.WARNING,
        'INFO': logging.INFO,
        'DEBUG': logging.DEBUG,
        'NOTSET': logging.NOTSET,
    }
    log_level = log_mapping[args['logging']]
    del(args['logging'])

    global logger
    logger = configure_logging(log_level)

    args_mapping = {
        "path": "local_path",
        "remote": "remote_url",
        "ssh_config": "ssh_config_path",
        "exclude_from": "exclude_file",
        "known_hosts": "known_hosts_path",
        "do_not_delete": "delete",
        "key": "identity_files",
    }

    kwargs = {  # convert the argument names to class constructor parameters
        args_mapping[k]: v
        for k, v in args.items()
        if v and k in args_mapping
    }

    kwargs.update({
        k: v
        for k, v in args.items()
        if v and k not in args_mapping
    })

    # Special case: disable known_hosts check
    if args['disable_known_hosts']:
        kwargs['known_hosts_path'] = None
        del(kwargs['disable_known_hosts'])

    # Toggle `do_not_delete` flag
    if "delete" in kwargs:
        kwargs["delete"] = not kwargs["delete"]

    # Manually set the default identity file.
    kwargs["identity_files"] = kwargs.get("identity_files", None) or ["~/.ssh/id_rsa"]

    sync = SFTPClone(
        **kwargs
    )
    sync.run()


if __name__ == '__main__':
    main()
