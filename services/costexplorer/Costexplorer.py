from services.Service import Service
from services.costexplorer.drivers.CostexplorerAccount import CostexplorerAccount
from utils.Tools import _pi

class Costexplorer(Service):
    def __init__(self, region):
        super().__init__(region)
        self.ceClient = self.ssBoto.client('ce')
        self.budgetsClient = self.ssBoto.client('budgets', config=self.bConfig)

    def advise(self):
        objs = {}
        _pi('CostExplorer::Account')
        obj = CostexplorerAccount(self.ceClient, self.budgetsClient)
        obj.run(self.__class__)
        objs['CostExplorer::Account'] = obj.getInfo()
        del obj
        return objs
