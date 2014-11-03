"""SFTPClone: sync local and remote directories."""

# Python 2.7 backward compatibility
from __future__ import print_function
from __future__ import unicode_literals
from __future__ import absolute_import

import paramiko
import os
import os.path
from os.path import join
import errno
from stat import S_ISDIR, S_ISLNK, S_ISREG, S_IMODE, S_IFMT
import argparse
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


class SFTPClone(object):

    """The SFTPClone class."""

    def __init__(self, local_path, remote_url, key=None, port=22, fix_symlinks=False):
        """Init the needed parameters and the SFTPClient."""
        self.local_path = os.path.realpath(local_path)
        self.username, self.hostname = remote_url.split('@', 1)
        self.hostname, self.remote_path = self.hostname.split(':', 1)
        self.password = None

        if ':' in self.username:
            self.username, self.password = self.username.split(':', 1)

        self.port = port
        self.chown = False
        self.pkey = None

        self.fix_symlinks = fix_symlinks

        if key:
            self.pkey = paramiko.RSAKey.from_private_key_file(key)

        # only root can change file owner
        if self.username == 'root':
            self.chown = True

        self.transport = paramiko.Transport((self.hostname, self.port))
        self.transport.connect(
            username=self.username,
            password=self.password,
            pkey=self.pkey)
        self.sftp = paramiko.SFTPClient.from_transport(self.transport)

    def _file_need_upload(self, l_st, r_st):
        return True if \
            (l_st.st_size != r_st.st_size) or (int(l_st.st_mtime) != r_st.st_mtime) \
            else False

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

    def _must_be_deleted(self, local_path, r_st):
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

    def remote_delete(self, remote_path, r_st):
        """Remove the remote directory node."""
        # If it's a directory, then delete content and directory
        if S_ISDIR(r_st.st_mode):
            for item in self.sftp.listdir_attr(remote_path):
                full_path = join(remote_path, item.filename)
                self.remote_delete(full_path, item)
            self.sftp.rmdir(remote_path)

        # Or simply delete files
        else:
            try:
                self.sftp.remove(remote_path)
            except FileNotFoundError as e:
                logging.error(
                    "error while removing {}. trace: {}".format(remote_path, e)
                )

    def check_for_deletion(self, relative_path=None):
        """Traverse the entire remote_path tree.

        Find files/directories that need to be deleted,
        not being present in the local folder.
        """
        if not relative_path:
            relative_path = str()  # root of shared directory tree

        remote_path = join(self.remote_path, relative_path)
        local_path = join(self.local_path, relative_path)

        for remote_st in self.sftp.listdir_attr(remote_path):
            r_lstat = self.sftp.lstat(join(remote_path, remote_st.filename))

            inner_remote_path = join(remote_path, remote_st.filename)
            inner_local_path = join(local_path, remote_st.filename)

            # check if remote_st is a symlink
            # otherwise could delete file outside shared directory
            if S_ISLNK(r_lstat.st_mode):
                if (self._must_be_deleted(inner_local_path, r_lstat)):
                    self.remote_delete(inner_remote_path, r_lstat)
                continue

            if self._must_be_deleted(inner_local_path, remote_st):
                self.remote_delete(inner_remote_path, remote_st)
            elif S_ISDIR(remote_st.st_mode):
                self.check_for_deletion(
                    join(relative_path, remote_st.filename)
                )

    def create_update_symlink(self, link_destination, remote_path):
        """Create a new link pointing to link_destination in remote_path position."""
        logging.debug("Linking {} to {}".format(remote_path, link_destination))

        try:
            try:  # check if the remote link exists
                remote_link = self.sftp.readlink(remote_path)

                # if it does exist and it is different, update it
                if link_destination != remote_link:
                    self.sftp.remove(remote_path)
                    self.sftp.symlink(link_destination, remote_path)
            except IOError:  # if not, create it and done!
                self.sftp.symlink(link_destination, remote_path)
        except OSError as e:  # sometimes symlinking fails if absolute path are "too" different
        # Sadly, nothing we can do about it.
            logging.error("error while symlinking {} to {}: {}".format(remote_path, link_destination, e))

    def node_check_for_upload_create(self, relative_path, f):
        """Check if the given directory tree node has to be uploaded/created on the remote folder."""
        if not relative_path:
            # we're at the root of the shared directory tree
            relative_path = str()

        # the (absolute) local address of f.
        local_path = join(self.local_path, relative_path, f)
        l_st = os.lstat(local_path)

        # the (absolute) remote address of f.
        remote_path = join(self.remote_path, relative_path, f)

        # First case: f is a directory
        if S_ISDIR(l_st.st_mode):
            # we check if the folder exists on the remote side
            # it has to be a folder, otherwise it would have already been
            # deleted
            try:
                r_st = self.sftp.stat(remote_path)
            except IOError:  # it doesn't exist yet on remote side
                self.sftp.mkdir(remote_path)

            self._match_modes(remote_path, l_st)

            # now, we should traverse f too (recursion magic!)
            self.check_for_upload_create(join(relative_path, f))

        # Second case: f is a symbolic link
        elif S_ISLNK(l_st.st_mode):
            # read the local link
            local_link = os.readlink(local_path)
            absolute_local_link = os.path.realpath(local_link)

            # is it absolute?
            is_absolute = local_link.startswith("/")
            # and does it point inside the shared directory?
            trailing_local_path = join(self.local_path, '')  # add trailing slash (security)
            relpath = os.path.commonprefix(
                [absolute_local_link,
                 trailing_local_path]
            ) == trailing_local_path

            if relpath:
                relative_link = absolute_local_link[len(trailing_local_path):]
            else:
                relative_link = None

            logging.debug(
                "TAG: %s %s %s %s %s",
                local_link,
                absolute_local_link,
                self.local_path,
                is_absolute,
                relpath,
            )

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
            logging.error("UNSUPPORTED", local_path)

    def check_for_upload_create(self, relative_path=None):
        """Traverse the relative_path tree and check for files that need to be uploaded/created.

        Relativity here refers to the shared directory tree."""
        for f in os.listdir(
            join(
                self.local_path, relative_path) if relative_path else self.local_path
        ):
            self.node_check_for_upload_create(relative_path, f)

    def run(self):
        """Run the sync.

        Confront the local and the remote directories and perform the needed changes."""
        # first check for items to be removed
        self.check_for_deletion()

        # now scan local for items to upload/create
        self.check_for_upload_create()


def main():
    """The main."""
    parser = argparse.ArgumentParser(
        description='Sync a local and a remote folder through SFTP.')
    parser.add_argument(
        "local",
        type=str,
        help="the path of the local folder",
    )

    parser.add_argument(
        "remote",
        type=str,
        help="the ssh-url of the remote folder",
    )

    parser.add_argument(
        "-k",
        "--key",
        type=str,
        help="Private key identity path."
    )

    parser.add_argument(
        "-p",
        "--port",
        type=int,
        help="The remote port."
    )

    parser.add_argument(
        "-f",
        "--fix_absolute_symlinks",
        action="store_true",
        help="Fix absolute symlinks on remote side."
    )

    args = parser.parse_args()

    sync = SFTPClone(
        local_path=args.local,
        remote_url=args.remote,
        port=args.port,
        key=args.key,
        fix_symlinks=args.fix_absolute_symlinks
    )
    sync.run()


if __name__ == '__main__':
    print("FOOO!")
    main()
