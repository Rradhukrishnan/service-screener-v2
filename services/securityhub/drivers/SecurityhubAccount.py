import botocore
from services.Evaluator import Evaluator

class SecurityhubAccount(Evaluator):
    def __init__(self, shClient):
        super().__init__()
        self.shClient = shClient
        self._resourceName = 'SecurityHub::Account'
        self.init()

    def _checkEnabled(self):
        try:
            self.shClient.describe_hub()
        except botocore.exceptions.ClientError as e:
            if 'InvalidAccessException' in str(e) or 'not subscribed' in str(e).lower():
                self.results['SecurityHubNotEnabled'] = [-1, 'Security Hub is not enabled']

    def _checkStandardsEnabled(self):
        try:
            resp = self.shClient.get_enabled_standards()
            standards = resp.get('StandardsSubscriptions', [])
            if not standards:
                self.results['SecurityHubNoStandardsEnabled'] = [-1, 'No compliance standards enabled']
                return
            enabled = [s['StandardsArn'] for s in standards if s.get('StandardsStatus') == 'READY']
            if not enabled:
                self.results['SecurityHubStandardsNotReady'] = [-1, 'Standards exist but none are READY']
        except botocore.exceptions.ClientError:
            pass

    def _checkCriticalFindings(self):
        try:
            resp = self.shClient.get_findings(
                Filters={
                    'SeverityLabel': [{'Value': 'CRITICAL', 'Comparison': 'EQUALS'}],
                    'RecordState': [{'Value': 'ACTIVE', 'Comparison': 'EQUALS'}],
                    'WorkflowStatus': [{'Value': 'NEW', 'Comparison': 'EQUALS'}]
                },
                MaxResults=10
            )
            findings = resp.get('Findings', [])
            if findings:
                self.results['SecurityHubCriticalFindings'] = [-1, f'{len(findings)}+ critical findings unresolved']
        except botocore.exceptions.ClientError:
            pass

    def _checkAutoEnableControls(self):
        try:
            resp = self.shClient.describe_hub()
            if not resp.get('AutoEnableControls', False):
                self.results['SecurityHubAutoEnableControlsOff'] = [0, 'Auto-enable controls is disabled']
        except botocore.exceptions.ClientError:
            pass
