from services.Service import Service
from services.ses.drivers.SesAccount import SesAccount
from utils.Tools import _pi

class Ses(Service):
    def __init__(self, region):
        super().__init__(region)
        self.sesClient = self.ssBoto.client('sesv2', config=self.bConfig)

    def advise(self):
        objs = {}
        _pi('SES::Account')
        obj = SesAccount(self.sesClient)
        obj.run(self.__class__)
        objs['SES::Account'] = obj.getInfo()
        del obj
        return objs
