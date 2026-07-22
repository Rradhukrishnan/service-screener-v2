from services.Service import Service
from services.securityhub.drivers.SecurityhubAccount import SecurityhubAccount
from utils.Tools import _pi

class Securityhub(Service):
    def __init__(self, region):
        super().__init__(region)
        self.shClient = self.ssBoto.client('securityhub', config=self.bConfig)

    def advise(self):
        objs = {}
        _pi('SecurityHub::Account')
        obj = SecurityhubAccount(self.shClient)
        obj.run(self.__class__)
        objs['SecurityHub::Account'] = obj.getInfo()
        del obj
        return objs
