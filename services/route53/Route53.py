from services.Service import Service
from services.route53.drivers.Route53HostedZone import Route53HostedZone
from utils.Tools import _pi

class Route53(Service):
    def __init__(self, region):
        super().__init__(region)
        self.r53Client = self.ssBoto.client('route53')

    def advise(self):
        objs = {}
        paginator = self.r53Client.get_paginator('list_hosted_zones')
        for page in paginator.paginate():
            for zone in page.get('HostedZones', []):
                name = zone.get('Name')
                _pi('Route53::HostedZone', name)
                obj = Route53HostedZone(zone, self.r53Client)
                obj.run(self.__class__)
                objs['Route53::' + name] = obj.getInfo()
                del obj
        return objs
