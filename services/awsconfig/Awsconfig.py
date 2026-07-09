import botocore
from utils.Config import Config
from services.Service import Service
from services.awsconfig.drivers.AwsconfigAccount import AwsconfigAccount
from utils.Tools import _pi

class Awsconfig(Service):
    def __init__(self, region):
        super().__init__(region)
        ssBoto = self.ssBoto
        self.configClient = ssBoto.client('config', config=self.bConfig)

    def advise(self):
        objs = {}
        _pi('AWSConfig::Account')
        obj = AwsconfigAccount(self.configClient)
        obj.run(self.__class__)
        objs['AWSConfig::Account'] = obj.getInfo()
        del obj
        return objs
