from services.Service import Service
from services.wafv2.drivers.Wafv2WebACL import Wafv2WebACL
from utils.Tools import _pi

class Wafv2(Service):
    def __init__(self, region):
        super().__init__(region)
        self.wafClient = self.ssBoto.client('wafv2', config=self.bConfig)

    def advise(self):
        objs = {}
        resp = self.wafClient.list_web_acls(Scope='REGIONAL')
        acls = resp.get('WebACLs', [])
        if not acls:
            return objs
        for acl in acls:
            name = acl.get('Name')
            _pi('WAFv2::WebACL', name)
            detail = self.wafClient.get_web_acl(Name=acl['Name'], Scope='REGIONAL', Id=acl['Id'])
            obj = Wafv2WebACL(detail.get('WebACL', {}), self.wafClient)
            obj.run(self.__class__)
            objs['WAFv2::' + name] = obj.getInfo()
            del obj
        return objs
