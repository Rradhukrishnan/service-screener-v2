import botocore
from services.Evaluator import Evaluator

class InspectorAccount(Evaluator):
    def __init__(self, inspectorClient):
        super().__init__()
        self.inspectorClient = inspectorClient
        self._resourceName = 'Inspector::Account'
        self._status = {}
        self.init()
        self._loadStatus()

    def _loadStatus(self):
        try:
            resp = self.inspectorClient.batch_get_account_status(accountIds=[])
            accounts = resp.get('accounts', [])
            if accounts:
                self._status = accounts[0].get('resourceState', {})
        except botocore.exceptions.ClientError:
            pass

    def _checkEC2ScanEnabled(self):
        """Check if Inspector EC2 scanning is enabled"""
        ec2 = self._status.get('ec2', {})
        if ec2.get('status') != 'ENABLED':
            self.results['InspectorEC2ScanDisabled'] = [-1, 'EC2 scanning is not enabled']

    def _checkECRScanEnabled(self):
        """Check if Inspector ECR container image scanning is enabled"""
        ecr = self._status.get('ecr', {})
        if ecr.get('status') != 'ENABLED':
            self.results['InspectorECRScanDisabled'] = [-1, 'ECR scanning is not enabled']

    def _checkLambdaScanEnabled(self):
        """Check if Inspector Lambda function scanning is enabled"""
        lmb = self._status.get('lambda', {})
        if lmb.get('status') != 'ENABLED':
            self.results['InspectorLambdaScanDisabled'] = [0, 'Lambda scanning is not enabled']

    def _checkCriticalFindings(self):
        """Check for critical and high severity active findings"""
        try:
            resp = self.inspectorClient.list_findings(
                filterCriteria={
                    'findingStatus': [{'comparison': 'EQUALS', 'value': 'ACTIVE'}],
                    'severity': [{'comparison': 'EQUALS', 'value': 'CRITICAL'}]
                },
                maxResults=10
            )
            findings = resp.get('findings', [])
            if findings:
                self.results['InspectorCriticalFindings'] = [-1, f'{len(findings)}+ critical findings active']
        except botocore.exceptions.ClientError:
            pass

    def _checkHighFindings(self):
        """Check for high severity active findings"""
        try:
            resp = self.inspectorClient.list_findings(
                filterCriteria={
                    'findingStatus': [{'comparison': 'EQUALS', 'value': 'ACTIVE'}],
                    'severity': [{'comparison': 'EQUALS', 'value': 'HIGH'}]
                },
                maxResults=10
            )
            findings = resp.get('findings', [])
            if findings:
                self.results['InspectorHighFindings'] = [-1, f'{len(findings)}+ high severity findings active']
        except botocore.exceptions.ClientError:
            pass

    def _checkAutoRemediationEnabled(self):
        """Check if suppression rules exist (indicates active management of findings)"""
        try:
            resp = self.inspectorClient.list_filters(action='SUPPRESS')
            filters = resp.get('filters', [])
            if not filters:
                self.results['InspectorNoSuppressionRules'] = [0, 'No suppression rules defined — consider managing known exceptions']
        except botocore.exceptions.ClientError:
            pass
