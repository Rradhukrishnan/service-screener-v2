import botocore
from datetime import datetime, timezone, timedelta
from services.Evaluator import Evaluator

class SecretsmanagerSecret(Evaluator):
    def __init__(self, secret, smClient):
        super().__init__()
        self.secret = secret
        self.smClient = smClient
        self._resourceName = secret.get('ARN', secret.get('Name'))
        self.init()

    def _checkRotationEnabled(self):
        if not self.secret.get('RotationEnabled', False):
            self.results['SMRotationDisabled'] = [-1, self.secret.get('Name')]

    def _checkRotationOverdue(self):
        if not self.secret.get('RotationEnabled', False):
            return
        last_rotated = self.secret.get('LastRotatedDate')
        if last_rotated:
            age = (datetime.now(timezone.utc) - last_rotated).days
            if age > 90:
                self.results['SMRotationOverdue'] = [-1, f'{age} days since last rotation']

    def _checkKMSEncryption(self):
        kms_key = self.secret.get('KmsKeyId', '')
        if not kms_key or kms_key == 'aws/secretsmanager':
            self.results['SMNoCustomKMS'] = [0, self.secret.get('Name')]

    def _checkUnused(self):
        last_accessed = self.secret.get('LastAccessedDate')
        if last_accessed:
            age = (datetime.now(timezone.utc) - last_accessed).days
            if age > 90:
                self.results['SMSecretUnused'] = [-1, f'Not accessed in {age} days']
        elif not last_accessed:
            created = self.secret.get('CreatedDate')
            if created:
                age = (datetime.now(timezone.utc) - created).days
                if age > 30:
                    self.results['SMSecretNeverAccessed'] = [0, f'Created {age} days ago, never accessed']
