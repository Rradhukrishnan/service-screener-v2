import botocore
from services.Evaluator import Evaluator

class SecurityhubDriver(Evaluator):
    def __init__(self, shClient, region):
        super().__init__()
        self.shClient = shClient
        self.region = region
        self._resourceName = 'Account'
        self.hubEnabled = False

        try:
            resp = self.shClient.describe_hub()
            self.hubArn = resp.get('HubArn', '')
            self.hubEnabled = True
        except botocore.exceptions.ClientError as e:
            code = e.response['Error']['Code']
            if code in ['InvalidAccessException', 'ResourceNotFoundException']:
                self.hubEnabled = False
            else:
                print(f'[SecurityhubDriver] describe_hub error: {code}')

        self.init()

    def _checkSecurityHubEnabled(self):
        if not self.hubEnabled:
            self.results['SecurityHubEnabled'] = [-1, 'AWS Security Hub is not enabled in this region']
        else:
            self.results['SecurityHubEnabled'] = [1, '']

    def _checkStandardsEnabled(self):
        if not self.hubEnabled:
            return
        try:
            resp = self.shClient.get_enabled_standards()
            standards = resp.get('StandardsSubscriptions', [])
            standard_names = [s.get('StandardsArn', '').split('/')[-2] for s in standards if s.get('StandardsStatus') == 'READY']
            has_cis = any('cis' in n.lower() for n in standard_names)
            has_fsbp = any('aws-foundational' in s.get('StandardsArn', '').lower() for s in standards)
            has_pci = any('pci' in n.lower() for n in standard_names)

            if not standards:
                self.results['SecurityStandardsEnabled'] = [-1, 'No security standards are enabled in Security Hub']
            elif not (has_cis or has_fsbp or has_pci):
                self.results['SecurityStandardsEnabled'] = [-1, 'CIS, FSBP, or PCI-DSS standards are not enabled']
            else:
                self.results['SecurityStandardsEnabled'] = [1, '']
        except botocore.exceptions.ClientError as e:
            print(f'[SecurityhubDriver] get_enabled_standards error: {e.response["Error"]["Code"]}')

    def _checkHighCriticalFindings(self):
        if not self.hubEnabled:
            return
        try:
            resp = self.shClient.get_findings(
                Filters={
                    'SeverityLabel': [
                        {'Value': 'HIGH', 'Comparison': 'EQUALS'},
                        {'Value': 'CRITICAL', 'Comparison': 'EQUALS'}
                    ],
                    'RecordState': [{'Value': 'ACTIVE', 'Comparison': 'EQUALS'}],
                    'WorkflowStatus': [{'Value': 'NEW', 'Comparison': 'EQUALS'}]
                },
                MaxResults=1
            )
            findings = resp.get('Findings', [])
            total = resp.get('Total', len(findings))
            if findings:
                self.results['HighCriticalFindings'] = [-1, f'Active HIGH/CRITICAL findings exist (sample count: {len(findings)}+)']
            else:
                self.results['HighCriticalFindings'] = [1, '']
        except botocore.exceptions.ClientError as e:
            print(f'[SecurityhubDriver] get_findings error: {e.response["Error"]["Code"]}')

    def _checkAutoEnableNewAccounts(self):
        if not self.hubEnabled:
            return
        try:
            resp = self.shClient.describe_hub()
            auto_enable = resp.get('AutoEnableControls', False)
            if not auto_enable:
                self.results['AutoEnableNewAccounts'] = [-1, 'Auto-enable controls for new organization accounts is not enabled']
            else:
                self.results['AutoEnableNewAccounts'] = [1, '']
        except botocore.exceptions.ClientError as e:
            print(f'[SecurityhubDriver] describe_hub error: {e.response["Error"]["Code"]}')
