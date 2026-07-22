from services.Service import Service
from services.controltower.drivers.ControltowerAccount import ControltowerAccount
from utils.Tools import _pi

class Controltower(Service):
    def __init__(self, region):
        super().__init__(region)
        self.ctClient = self.ssBoto.client('controltower', config=self.bConfig)
        self.orgClient = self.ssBoto.client('organizations', config=self.bConfig)

    def advise(self):
        objs = {}
        _pi('ControlTower::Account')
        obj = ControltowerAccount(self.ctClient, self.orgClient)
        obj.run(self.__class__)
        objs['ControlTower::Account'] = obj.getInfo()
        del obj
        return objs
