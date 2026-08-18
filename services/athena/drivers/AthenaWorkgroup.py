import botocore
from services.Evaluator import Evaluator

class AthenaWorkgroup(Evaluator):
    def __init__(self, workgroup, athenaClient):
        super().__init__()
        self.workgroup = workgroup
        self.athenaClient = athenaClient
        self._resourceName = workgroup.get('Name', 'unknown')
        self.config = workgroup.get('Configuration', {})
        self.init()

    def _checkEncryptionEnabled(self):
        """Check if query results are encrypted"""
        result_config = self.config.get('ResultConfiguration', {})
        encryption = result_config.get('EncryptionConfiguration', {})
        if not encryption.get('EncryptionOption'):
            self.results['AthenaNoEncryption'] = [-1, self.workgroup.get('Name')]

    def _checkKMSEncryption(self):
        """Check if KMS encryption is used (not just SSE_S3)"""
        result_config = self.config.get('ResultConfiguration', {})
        encryption = result_config.get('EncryptionConfiguration', {})
        enc_option = encryption.get('EncryptionOption', '')
        if enc_option == 'SSE_S3':
            self.results['AthenaNoKMSEncryption'] = [0,
                f"Using SSE_S3 instead of SSE_KMS or CSE_KMS"]

    def _checkOutputLocation(self):
        """Check if a default output location is configured"""
        result_config = self.config.get('ResultConfiguration', {})
        output_location = result_config.get('OutputLocation', '')
        if not output_location:
            self.results['AthenaNoOutputLocation'] = [-1, self.workgroup.get('Name')]

    def _checkEnforceWorkgroupConfig(self):
        """Check if workgroup settings are enforced (override client settings)"""
        if not self.config.get('EnforceWorkGroupConfiguration', False):
            self.results['AthenaNotEnforced'] = [-1, self.workgroup.get('Name')]

    def _checkPublishCloudWatchMetrics(self):
        """Check if CloudWatch metrics are published"""
        if not self.config.get('PublishCloudWatchMetricsEnabled', False):
            self.results['AthenaNoCloudWatchMetrics'] = [-1, self.workgroup.get('Name')]

    def _checkRequesterPaysEnabled(self):
        """Check if requester pays is enabled (cost control)"""
        if not self.config.get('RequesterPaysEnabled', False):
            self.results['AthenaRequesterPaysDisabled'] = [0, self.workgroup.get('Name')]

    def _checkBytesScannedCutoff(self):
        """Check if a bytes scanned cutoff is set (prevents expensive queries)"""
        cutoff = self.config.get('BytesScannedCutoffPerQuery')
        if not cutoff:
            self.results['AthenaNoBytesScannedLimit'] = [-1, self.workgroup.get('Name')]

    def _checkEngineVersion(self):
        """Check if workgroup is using the latest Athena engine version"""
        engine = self.config.get('EngineVersion', {})
        effective = engine.get('EffectiveEngineVersion', '')
        if effective and 'Athena engine version 2' in effective:
            self.results['AthenaOldEngineVersion'] = [0,
                f"Using {effective} — consider upgrading to v3"]

    def _checkWorkgroupState(self):
        """Check if workgroup is enabled"""
        state = self.workgroup.get('State', '')
        if state != 'ENABLED':
            self.results['AthenaWorkgroupDisabled'] = [0,
                f"Workgroup is {state}"]
