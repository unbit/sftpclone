import paramiko
import os
import os.path
import errno
from stat import S_ISDIR, S_ISLNK, S_ISREG, S_IMODE, S_IFMT


class SFTPsync(object):

    def __init__(self, local_path, remote_url, key=None, port=22):
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

        if self.username == 'root':
            self.chown = True

        self.transport = paramiko.Transport((self.hostname, self.port))
        self.transport.connect(
            username=self.username, password=self.password, pkey=self.pkey)
        self.sftp = paramiko.SFTPClient.from_transport(self.transport)

    def _parent(self, path):
        return os.path.dirname(path)

    def _file_need_upload(self, l_st, r_st):
        if l_st.st_size != r_st.st_size:
            return True
        if int(l_st.st_mtime) != r_st.st_mtime:
            return True
        return False

    def file_upload(self, filename, l_st):
        global chown
        print "uploading", filename
        self.sftp.put(filename, filename)
        self.sftp.chmod(filename, S_IMODE(l_st.st_mode))
        # if chown:
        #    self.sftp.chown(filename, l_st.st_uid, l_st.st_gid)
        self.sftp.utime(filename, (l_st.st_atime, l_st.st_mtime))

    def _manage_link(self, local_filename, remote_filename):
        # get the local link
        local_link = os.readlink(local_filename)
        if not local_link.startswith('/'):
            local_link = os.path.join(self.parent(local_flename), local_link)
        r_st = sftp.lstat(remote_filename)
        if self._is_not_link(r_st):
            self.remote_delete(remote_filename)
        remote_link = sftp.readlink(remote_filename)
        if local_link != remote_link:
            self.remote_delete(remote_filename)

        if not local_link.startswith('/'):
            sftp.symlink(local_link, remote_filename)

    def _must_be_deleted(self, remote, r_mode):
        if not os.path.lexists(remote):
            return True
        l_st = os.lstat(remote)
        if S_IFMT(r_mode) != S_IFMT(l_st.st_mode):
            return True
        return False

    def remote_delete(self, filename, r_st):
        if not S_ISDIR(r_st.st_mode):
            self.sftp.remove(filename)
            return
        for item in self.sftp.listdir_attrs(filename):
            full_filename = os.path.join(filename, item.filename)
            self.remote_delete(full_filename, item)
        print "REMOVE DIRECTORY !!!"

    def traverse_local(self, path):
        # first check for items to be removed
        remote_list = self.sftp.listdir_attr(path)
        for remote in remote_list:
            filename = os.path.join(path, remote.filename)
            if self._must_be_deleted(filename, remote.st_mode):
                print filename, remote.st_mode, "must be deleted !!!"
                self.remote_delete(filename, remote)

        # now scan local for items to upload/create
        dirlist = os.listdir(path)
        for d in dirlist:
            filename = os.path.join(path, d)
            if filename in ('.', '..'):
                continue
            st = os.lstat(filename)
            if S_ISDIR(st.st_mode):
                try:
                    r_st = self.sftp.lstat(filename)
                    # if it is not a directory, destroy it
                    if not S_ISDIR(r_st.st_mode):
                        remote_delete(filename, r_st)
                        raise IOError
                except IOError:
                    self.sftp.mkdir(filename)
                # fix uid,gid,mod,utime ?
                self.traverse_local(filename)
            elif S_ISLNK(st.st_mode):
                local_link = os.readlink(filename)
                if not local_link.startswith('/'):
                    local_link = os.path.join(path, local_link)
                try:
                    r_st = self.sftp.lstat(filename)
                    if not S_ISLNK(r_st.st_mode):
                        self.remote_delete(filename, r_st)
                        raise IOError
                    remote_link = self.sftp.readlink(filename)
                    if local_link != remote_link:
                        print 'DIFFERENT LINK', remote_link, local_link
                        remote_delete(filename, r_st)
                        raise IOError
                    print 'LINKTO', remote_link
                except IOError:
                    self.sftp.symlink(local_link, filename)
                # fix uid,gid,mod,utime ?
                print "LINK", filename
            elif S_ISREG(st.st_mode):
                try:
                    r_st = self.sftp.lstat(filename)
                    if self._file_need_upload(st, r_st):
                        self.file_upload(filename, st)
                except IOError, e:
                    if e.errno == errno.ENOENT:
                        self.file_upload(filename, st)
            else:
                print "UNSUPPORTED", filename

    def run(self, local, remote):
        self.traverse_local(local)


sync = SFTPsync(
    '/unbit', 'u94344@u94344.your-backup.de:/unbit', key='/unbit/caronte_key')
sync.run('/unbit', '/unbit')
