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

    # def _manage_link(self, local_filename, remote_filename):
    #     # get the local link
    #     local_link = os.readlink(local_filename)
    #     if not local_link.startswith('/'):
    #         local_link = join(self.parent(local_filename), local_link)
    #     r_st = self.sftp.lstat(remote_filename)
    #     if self._is_not_link(r_st):
    #         self.remote_delete(remote_filename)
    #     remote_link = self.sftp.readlink(remote_filename)
    #     if local_link != remote_link:
    #         self.remote_delete(remote_filename)

    #     if not local_link.startswith('/'):
    #         self.sftp.symlink(local_link, remote_filename)

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
        # If it's a directory, then delete content and dir
        if S_ISDIR(r_st.st_mode):
            for item in self.sftp.listdir_attr(remote_path):
                full_path = join(remote_path, item.filename)
                self.remote_delete(full_path, item)
            self.sftp.rmdir(remote_path)

        # Or simply delete simple files
        else:
            self.sftp.remove(remote_path)

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
            inner_remote_path = join(remote_path, remote_st.filename)
            inner_local_path = join(local_path, remote_st.filename)

            if self._must_be_deleted(inner_local_path, remote_st):
                self.remote_delete(inner_remote_path, remote_st)
            elif S_ISDIR(remote_st.st_mode):
                self.check_for_deletion(
                    join(relative_path, remote_st.filename)
                )

    def node_check_for_upload_create(self, relative_path, f):
        """Check if the given directory tree node has to be uploaded/created on the remote folder."""
        if not relative_path:
            relative_path = str()  # we're at the root of the shared dir tree

        # the (absolute) local address of f.
        local_path = join(self.local_path, relative_path, f)
        l_st = os.lstat(local_path)

        # the (absolute) remote address of f.
        remote_path = join(self.remote_path, relative_path, f)

        # First case: f is a directory
        if S_ISDIR(l_st.st_mode):
            try:
                r_st = self.sftp.lstat(remote_path)
                # if it is not a directory, destroy it
                if not S_ISDIR(r_st.st_mode):
                    self.remote_delete(remote_path, r_st)
                    raise IOError
            except IOError:
                self.sftp.mkdir(remote_path)
            # FIXME: uid, gid, mod, utime, ...

            # now, we should traverse f too (recursion magic)
            self.check_for_upload_create(join(relative_path, f))

        # Second case: f is a symbolic link
        elif S_ISLNK(l_st.st_mode):
            local_link = os.readlink(local_path)
            if not local_link.startswith('/'):
                local_link = join(self.local_path, local_link)
                remote_link = join(self.remote_path, local_link)
            try:
                r_st = self.sftp.lstat(remote_path)
                if not S_ISLNK(r_st.st_mode):
                    self.remote_delete(remote_path, r_st)
                    raise IOError

                remote_link = self.sftp.readlink(remote_path)
                if local_link != remote_link:
                    print('DIFFERENT LINK', remote_link, local_link)
                    self.remote_delete(remote_path, r_st)
                    raise IOError

                print('LINKTO', remote_link)
            except IOError:
                self.sftp.symlink(remote_link, remote_path)
            # FIXME: uid, gid, mod, utime, ...

        # Third case: regular file
        elif S_ISREG(l_st.st_mode):
            try:
                r_st = self.sftp.lstat(remote_path)
                if self._file_need_upload(l_st, r_st):
                    self.file_upload(local_path, remote_path, l_st)
            except IOError as e:
                if e.errno == errno.ENOENT:
                    print("In upload %s %s" % (local_path, remote_path))
                    self.file_upload(local_path, remote_path, l_st)

        # Anything else.
        else:
            print("UNSUPPORTED", local_path)

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
