import botocore
from datetime import datetime, timezone, timedelta
from services.Evaluator import Evaluator

class SecretsmanagerDriver(Evaluator):
    def __init__(self, secret, smClient):
        super().__init__()
        self.secret = secret
        self.smClient = smClient
        self.secretId = secret.get('ARN', secret.get('Name', 'unknown'))
        self._resourceName = secret.get('Name', 'unknown')
        self.init()

    def _checkRotationEnabled(self):
        if not self.secret.get('RotationEnabled', False):
            self.results['RotationEnabled'] = [-1, 'Secret rotation is not enabled']
        else:
            self.results['RotationEnabled'] = [1, '']

    def _checkRotationOverdue(self):
        if not self.secret.get('RotationEnabled', False):
            return
        last_rotated = self.secret.get('LastRotatedDate')
        if last_rotated is None:
            self.results['RotationOverdue'] = [-1, 'Secret has never been rotated']
            return
        # Ensure timezone-aware comparison
        if last_rotated.tzinfo is None:
            last_rotated = last_rotated.replace(tzinfo=timezone.utc)
        days_since = (datetime.now(timezone.utc) - last_rotated).days
        if days_since > 90:
            self.results['RotationOverdue'] = [-1, f'Secret has not been rotated in {days_since} days (threshold: 90 days)']
        else:
            self.results['RotationOverdue'] = [1, '']

    def _checkUnusedSecret(self):
        last_accessed = self.secret.get('LastAccessedDate')
        if last_accessed is None:
            self.results['UnusedSecret'] = [-1, 'Secret has never been accessed']
            return
        if last_accessed.tzinfo is None:
            last_accessed = last_accessed.replace(tzinfo=timezone.utc)
        days_since = (datetime.now(timezone.utc) - last_accessed).days
        if days_since > 90:
            self.results['UnusedSecret'] = [-1, f'Secret has not been accessed in {days_since} days']
        else:
            self.results['UnusedSecret'] = [1, '']

    def _checkKMSEncryption(self):
        kms_key = self.secret.get('KmsKeyId', '')
        if not kms_key or kms_key == 'aws/secretsmanager':
            self.results['KMSCustomerManagedKey'] = [-1, 'Secret is using the default AWS-managed KMS key, not a customer-managed key']
        else:
            self.results['KMSCustomerManagedKey'] = [1, '']

    def _checkSecretPolicy(self):
        try:
            resp = self.smClient.get_resource_policy(SecretId=self.secretId)
            policy = resp.get('ResourcePolicy', '')
            if not policy:
                self.results['SecretResourcePolicy'] = [0, 'No resource-based policy is attached to this secret']
            else:
                self.results['SecretResourcePolicy'] = [1, '']
        except botocore.exceptions.ClientError as e:
            code = e.response['Error']['Code']
            if code == 'ResourceNotFoundException':
                self.results['SecretResourcePolicy'] = [0, 'No resource-based policy is attached to this secret']
            else:
                print(f'[SecretsmanagerDriver] get_resource_policy error: {code}')
