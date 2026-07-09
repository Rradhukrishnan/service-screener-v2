import botocore
from services.Evaluator import Evaluator

class AwsconfigAccount(Evaluator):
    def __init__(self, configClient):
        super().__init__()
        self.configClient = configClient
        self._resourceName = 'AWSConfig::Account'
        self.init()

    def _checkConfigEnabled(self):
        """Check if AWS Config is enabled with at least one recorder"""
        try:
            resp = self.configClient.describe_configuration_recorders()
            recorders = resp.get('ConfigurationRecorders', [])
            if not recorders:
                self.results['ConfigRecorderMissing'] = [-1, 'No configuration recorder found']
                return

            # Check recorder status
            statusResp = self.configClient.describe_configuration_recorder_status()
            statuses = statusResp.get('ConfigurationRecordersStatus', [])
            for status in statuses:
                if not status.get('recording', False):
                    self.results['ConfigRecorderNotRecording'] = [-1, status.get('name', '')]

        except botocore.exceptions.ClientError as e:
            if e.response['Error']['Code'] in ('AccessDeniedException', 'NoSuchConfigurationRecorderException'):
                self.results['ConfigRecorderMissing'] = [-1, 'Access denied or no recorder']

    def _checkDeliveryChannel(self):
        """Check if a delivery channel (S3 + SNS) is configured"""
        try:
            resp = self.configClient.describe_delivery_channels()
            channels = resp.get('DeliveryChannels', [])
            if not channels:
                self.results['ConfigDeliveryChannelMissing'] = [-1, 'No delivery channel configured']
                return

            for channel in channels:
                if not channel.get('s3BucketName'):
                    self.results['ConfigDeliveryChannelNoS3'] = [-1, channel.get('name', '')]
                if not channel.get('snsTopicARN'):
                    self.results['ConfigDeliveryChannelNoSNS'] = [0, channel.get('name', '')]

        except botocore.exceptions.ClientError as e:
            self.results['ConfigDeliveryChannelMissing'] = [-1, str(e.response['Error']['Code'])]

    def _checkAllResourceTypesRecorded(self):
        """Check if Config records all supported resource types"""
        try:
            resp = self.configClient.describe_configuration_recorders()
            for recorder in resp.get('ConfigurationRecorders', []):
                spec = recorder.get('recordingGroup', {})
                if not spec.get('allSupported', False) and not spec.get('includeGlobalResourceTypes', False):
                    self.results['ConfigNotRecordingAllResources'] = [-1, recorder.get('name', '')]

        except botocore.exceptions.ClientError as e:
            pass

    def _checkConformancePacks(self):
        """Check if any conformance packs are deployed (best practice for compliance)"""
        try:
            resp = self.configClient.describe_conformance_packs()
            packs = resp.get('ConformancePackDetails', [])
            if not packs:
                self.results['ConfigNoConformancePacks'] = [0, 'No conformance packs deployed']

        except botocore.exceptions.ClientError as e:
            pass

    def _checkRemediationActions(self):
        """Check if auto-remediation rules exist"""
        try:
            resp = self.configClient.describe_config_rules()
            rules = resp.get('ConfigRules', [])
            if not rules:
                self.results['ConfigNoRules'] = [-1, 'No AWS Config rules defined']

        except botocore.exceptions.ClientError as e:
            pass

    def _checkRetentionPeriod(self):
        """Check if a retention configuration is set (default is 7 years)"""
        try:
            resp = self.configClient.describe_retention_configurations()
            configs = resp.get('RetentionConfigurations', [])
            if not configs:
                self.results['ConfigNoRetentionConfiguration'] = [0, 'Using default retention period']

        except botocore.exceptions.ClientError as e:
            pass
