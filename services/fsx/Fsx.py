import botocore
from services.Service import Service
from services.fsx.drivers.FsxFileSystem import FsxFileSystem
from utils.Tools import _pi

class Fsx(Service):
    def __init__(self, region):
        super().__init__(region)
        self.fsxClient = self.ssBoto.client('fsx', config=self.bConfig)

    def advise(self):
        objs = {}
        paginator = self.fsxClient.get_paginator('describe_file_systems')
        for page in paginator.paginate():
            for fs in page.get('FileSystems', []):
                fs_id = fs.get('FileSystemId')
                _pi('FSx::FileSystem', fs_id)
                obj = FsxFileSystem(fs, self.fsxClient)
                obj.run(self.__class__)
                objs['FSx::' + fs_id] = obj.getInfo()
                del obj
        return objs
