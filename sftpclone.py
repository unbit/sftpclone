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


class SFTPClone(object):

    """The SFTPClone class."""

    def __init__(self, local_path, remote_url, key=None, port=22):
        """Init the needed parameters and the SFTPClient."""
        self.local_path = local_path
        self.username, self.hostname = remote_url.split('@', 1)
        self.hostname, self.remote_path = self.hostname.split(':', 1)
        self.password = None

        if ':' in self.username:
            self.username, self.password = self.username.split(':', 1)

        self.port = port
        self.chown = False
        self.pkey = None

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

    def file_upload(self, localpath, remotepath, l_st):
        """Upload localpath to remotepath and set permission and mtime."""
        print("uploading", localpath)
        self.sftp.put(localpath, remotepath)
        self.sftp.chmod(remotepath, S_IMODE(l_st.st_mode))
        self.sftp.utime(remotepath, (l_st.st_atime, l_st.st_mtime))

        if self.chown:
            self.sftp.chown(remotepath, l_st.st_uid, l_st.st_gid)

    def _manage_link(self, local_filename, remote_filename):
        # get the local link
        local_link = os.readlink(local_filename)
        if not local_link.startswith('/'):
            local_link = join(self.parent(local_filename), local_link)
        r_st = self.sftp.lstat(remote_filename)
        if self._is_not_link(r_st):
            self.remote_delete(remote_filename)
        remote_link = self.sftp.readlink(remote_filename)
        if local_link != remote_link:
            self.remote_delete(remote_filename)

        if not local_link.startswith('/'):
            self.sftp.symlink(local_link, remote_filename)

    def _must_be_deleted(self, filename, r_st):
        """Return True if filename has to be deleted.

        i.e. if it doesn't exists locally or has a different type from the remote one."""
        # if the file doesn't exists
        if not os.path.lexists(filename):
            return True

        # or if the file type is different
        l_st = os.lstat(filename)
        if S_IFMT(r_st.st_mode) != S_IFMT(l_st.st_mode):
            return True

        return False

    def remote_delete(self, path, r_st):
        """Perform remote deletion of a directory tree."""
        # If it's a directory, delete content and dir
        if S_ISDIR(r_st.st_mode):
            for item in self.sftp.listdir_attr(path):
                full_path = join(path, item.filename)
                self.remote_delete(full_path, item)
            self.sftp.rmdir(path)

        # Or simply delete simple files
        else:
            self.sftp.remove(path)

    def check_for_deletion(self, remote_path):
        """Traverse the entire remote_path tree.

        Find files/directories that need to be deleted,
        not being present in the local folder.
        """
        remote_list = self.sftp.listdir_attr(remote_path)

        for remote_st in remote_list:
            local = join(self.local_path, remote_st.filename)
            if self._must_be_deleted(local, remote_st):
                path = join(remote_path, remote_st.filename)
                self.remote_delete(path, remote_st)
            elif S_ISDIR(remote_st.st_mode):
                self.check_for_deletion(join(remote_path, remote_st.filename))

    def check_for_upload_create(self, local_path):
        """Traverse the entire local_path tree and check for files that need to be uploaded/created."""
        # FIXME!
        try:
            dirlist = os.listdir(local_path)
        except NotADirectoryError:
            dirlist = {local_path}

        for f in dirlist:
            if f in ('.', '..'):
                continue

            local = join(local_path, f)
            l_st = os.lstat(local)

            remote = join(self.remote_path, f)

            # First case: f is a directory
            if S_ISDIR(l_st.st_mode):
                try:
                    r_st = self.sftp.lstat(remote)
                    # if it is not a directory, destroy it
                    if not S_ISDIR(r_st.st_mode):
                        self.remote_delete(remote, r_st)
                        raise IOError
                except IOError:
                    self.sftp.mkdir(remote)
                # FIXME: uid, gid, mod, utime, ...
                relative = join(local_path, f)
                self.check_for_upload_create(relative)

            # Second case: f is a symbolic link
            elif S_ISLNK(l_st.st_mode):
                local_link = os.readlink(local)
                if not local_link.startswith('/'):
                    local_link = join(self.local_path, local_link)
                    remote_link = join(self.remote_path, local_link)
                try:
                    r_st = self.sftp.lstat(remote)
                    if not S_ISLNK(r_st.st_mode):
                        self.remote_delete(remote, r_st)
                        raise IOError

                    remote_link = self.sftp.readlink(remote)
                    if local_link != remote_link:
                        print('DIFFERENT LINK', remote_link, local_link)
                        self.remote_delete(remote, r_st)
                        raise IOError

                    print('LINKTO', remote_link)
                except IOError:
                    self.sftp.symlink(remote_link, remote)
                # FIXME: uid, gid, mod, utime, ...

            # Third case: regular file
            elif S_ISREG(l_st.st_mode):
                try:
                    r_st = self.sftp.lstat(remote)
                    if self._file_need_upload(l_st, r_st):
                        self.file_upload(local, remote, l_st)
                except IOError as e:
                    if e.errno == errno.ENOENT:
                        print("In upload %s %s" % (local, remote))
                        self.file_upload(local, remote, l_st)

            # Anything else.
            else:
                print("UNSUPPORTED", local)

    def run(self):
        """Run the sync.

        Confront the local and the remote directories and perform the needed changes."""
        # first check for items to be removed
        self.check_for_deletion(self.remote_path)

        # now scan local for items to upload/create
        self.check_for_upload_create(self.local_path)
