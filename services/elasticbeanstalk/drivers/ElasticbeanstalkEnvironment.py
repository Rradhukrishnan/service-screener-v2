import botocore
from services.Evaluator import Evaluator

class ElasticbeanstalkEnvironment(Evaluator):
    def __init__(self, env, ebClient):
        super().__init__()
        self.env = env
        self.ebClient = ebClient
        self._resourceName = env.get('EnvironmentArn', env.get('EnvironmentName'))
        self._settings = {}
        self.init()
        self._loadSettings()

    def _loadSettings(self):
        try:
            resp = self.ebClient.describe_configuration_settings(
                ApplicationName=self.env['ApplicationName'],
                EnvironmentName=self.env['EnvironmentName']
            )
            for cfg in resp.get('ConfigurationSettings', []):
                for opt in cfg.get('OptionSettings', []):
                    key = f"{opt['Namespace']}::{opt['OptionName']}"
                    self._settings[key] = opt.get('Value', '')
        except botocore.exceptions.ClientError:
            pass

    def _checkManagedUpdates(self):
        val = self._settings.get('aws:elasticbeanstalk:managedactions::ManagedActionsEnabled', 'false')
        if val.lower() != 'true':
            self.results['EBManagedUpdatesDisabled'] = [-1, self.env.get('EnvironmentName')]

    def _checkEnhancedHealthReporting(self):
        val = self._settings.get('aws:elasticbeanstalk:healthreporting:system::SystemType', 'basic')
        if val.lower() != 'enhanced':
            self.results['EBEnhancedHealthDisabled'] = [-1, self.env.get('EnvironmentName')]

    def _checkCloudWatchLogs(self):
        val = self._settings.get('aws:elasticbeanstalk:cloudwatch:logs::StreamLogs', 'false')
        if val.lower() != 'true':
            self.results['EBLogStreamingDisabled'] = [-1, self.env.get('EnvironmentName')]

    def _checkLoadBalanced(self):
        tier = self.env.get('Tier', {}).get('Name', '')
        env_type = self._settings.get('aws:elasticbeanstalk:environment::EnvironmentType', '')
        if tier == 'WebServer' and env_type.lower() == 'singleinstance':
            self.results['EBSingleInstanceEnvironment'] = [-1, self.env.get('EnvironmentName')]

    def _checkIMDSv2(self):
        val = self._settings.get('aws:autoscaling:launchconfiguration::DisableIMDSv1', 'false')
        if val.lower() != 'true':
            self.results['EBIMDSv1Enabled'] = [-1, self.env.get('EnvironmentName')]
