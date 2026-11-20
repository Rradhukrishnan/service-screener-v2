import botocore

from services.Service import Service
from utils.Config import Config as Config_int

from services.sftp.drivers.SftpDriver import SftpDriver

from utils.Tools import _pi


class Sftp(Service):
    """AWS Transfer Family servers (SFTP/FTPS/FTP/AS2)."""

    def __init__(self, region):
        super().__init__(region)

        ssBoto = self.ssBoto
        self.transfer_client = ssBoto.client('transfer', config=self.bConfig)

    def get_resources(self):
        server_ids = []
        try:
            paginator = self.transfer_client.get_paginator('list_servers')
            for page in paginator.paginate():
                for server in page.get('Servers', []):
                    server_ids.append(server['ServerId'])
        except botocore.exceptions.ClientError as e:
            print("(Not showstopper): Error during transfer list_servers {}".format(e.response['Error']['Code']))
            return []

        servers = []
        for server_id in server_ids:
            try:
                resp = self.transfer_client.describe_server(ServerId=server_id)
            except botocore.exceptions.ClientError as e:
                print("(Not showstopper): Error during transfer describe_server {}".format(e.response['Error']['Code']))
                continue

            server = resp['Server']
            if self.tags and not self.resourceHasTags(server.get('Tags', [])):
                continue
            servers.append(server)

        return servers

    def advise(self):
        objs = {}

        for server in self.get_resources():
            _pi('SFTP', server['ServerId'])
            obj = SftpDriver(server, self.transfer_client)
            obj.run(self.__class__)

            objs['SFTP::' + server['ServerId']] = obj.getInfo()
            del obj

        return objs


if __name__ == "__main__":
    Config_int.init()
    o = Sftp('ap-southeast-1')
    out = o.advise()
    print(out)
