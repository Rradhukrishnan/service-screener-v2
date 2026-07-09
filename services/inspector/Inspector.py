import botocore
from utils.Config import Config
from services.Service import Service
from services.inspector.drivers.InspectorAccount import InspectorAccount
from utils.Tools import _pi

class Inspector(Service):
    def __init__(self, region):
        super().__init__(region)
        ssBoto = self.ssBoto
        self.inspectorClient = ssBoto.client('inspector2', config=self.bConfig)

    def advise(self):
        objs = {}
        _pi('Inspector::Account')
        obj = InspectorAccount(self.inspectorClient)
        obj.run(self.__class__)
        objs['Inspector::Account'] = obj.getInfo()
        del obj
        return objs
