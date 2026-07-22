import botocore
from services.Evaluator import Evaluator

class Route53HostedZone(Evaluator):
    def __init__(self, zone, r53Client):
        super().__init__()
        self.zone = zone
        self.r53Client = r53Client
        self._resourceName = zone.get('Id', zone.get('Name'))
        self.init()

    def _checkQueryLogging(self):
        try:
            zone_id = self.zone['Id'].split('/')[-1]
            resp = self.r53Client.list_query_logging_configs(HostedZoneId=zone_id)
            if not resp.get('QueryLoggingConfigs'):
                self.results['R53QueryLoggingDisabled'] = [-1, self.zone.get('Name')]
        except botocore.exceptions.ClientError:
            pass

    def _checkDNSSEC(self):
        try:
            if self.zone.get('Config', {}).get('PrivateZone', False):
                return
            zone_id = self.zone['Id'].split('/')[-1]
            resp = self.r53Client.get_dnssec(HostedZoneId=zone_id)
            status = resp.get('Status', {}).get('ServedSignature', '')
            if status != 'SIGNING':
                self.results['R53DNSSECNotEnabled'] = [-1, self.zone.get('Name')]
        except botocore.exceptions.ClientError:
            pass

    def _checkHealthChecks(self):
        try:
            zone_id = self.zone['Id'].split('/')[-1]
            paginator = self.r53Client.get_paginator('list_resource_record_sets')
            has_failover = False
            for page in paginator.paginate(HostedZoneId=zone_id):
                for record in page.get('ResourceRecordSets', []):
                    if record.get('Failover') or record.get('HealthCheckId'):
                        has_failover = True
                        break
            if not has_failover:
                self.results['R53NoHealthChecks'] = [0, self.zone.get('Name')]
        except botocore.exceptions.ClientError:
            pass

    def _checkPrivateZoneVPCAssociation(self):
        if not self.zone.get('Config', {}).get('PrivateZone', False):
            return
        vpcs = self.zone.get('VPCs', [])
        if not vpcs:
            self.results['R53PrivateZoneNoVPC'] = [-1, self.zone.get('Name')]
