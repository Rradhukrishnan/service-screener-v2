import botocore
from services.Evaluator import Evaluator

class ElasticbeanstalkDriver(Evaluator):
    def __init__(self, environment, ebClient):
        super().__init__()
        self.env = environment
        self.ebClient = ebClient
        self._resourceName = environment.get('EnvironmentName', 'unknown')

        env_name = self._resourceName
        app_name = environment.get('ApplicationName', '')

        # Fetch configuration settings
        self.configSettings = []
        try:
            resp = self.ebClient.describe_configuration_settings(
                ApplicationName=app_name,
                EnvironmentName=env_name
            )
            self.configSettings = resp.get('ConfigurationSettings', [])
        except botocore.exceptions.ClientError as e:
            print(f'[ElasticbeanstalkDriver] describe_configuration_settings error: {e.response["Error"]["Code"]}')

        self.init()

    def _getOptionValue(self, namespace, option_name):
        for cfg in self.configSettings:
            for opt in cfg.get('OptionSettings', []):
                if opt.get('Namespace') == namespace and opt.get('OptionName') == option_name:
                    return opt.get('Value')
        return None

    def _checkManagedPlatformUpdates(self):
        val = self._getOptionValue('aws:elasticbeanstalk:managedactions', 'ManagedActionsEnabled')
        if val is None or val.lower() != 'true':
            self.results['ManagedPlatformUpdatesEnabled'] = [-1, 'Managed platform updates are not enabled']
        else:
            self.results['ManagedPlatformUpdatesEnabled'] = [1, '']

    def _checkEnhancedHealthReporting(self):
        val = self._getOptionValue('aws:elasticbeanstalk:healthreporting:system', 'SystemType')
        if val is None or val.lower() != 'enhanced':
            self.results['EnhancedHealthReporting'] = [-1, f'Health reporting is set to: {val or "basic"}']
        else:
            self.results['EnhancedHealthReporting'] = [1, '']

    def _checkLogStreamingToCloudWatch(self):
        val = self._getOptionValue('aws:elasticbeanstalk:cloudwatch:logs', 'StreamLogs')
        if val is None or val.lower() != 'true':
            self.results['LogStreamingToCloudWatch'] = [-1, 'Log streaming to CloudWatch is not enabled']
        else:
            self.results['LogStreamingToCloudWatch'] = [1, '']

    def _checkLoadBalancedEnvironment(self):
        tier = self.env.get('Tier', {}).get('Name', '')
        env_type = self._getOptionValue('aws:elasticbeanstalk:environment', 'EnvironmentType')
        if env_type == 'SingleInstance':
            self.results['LoadBalancedEnvironment'] = [-1, 'Environment is single-instance; consider load-balanced for high availability']
        else:
            self.results['LoadBalancedEnvironment'] = [1, '']

    def _checkIMDSv2(self):
        val = self._getOptionValue('aws:autoscaling:launchconfiguration', 'DisableIMDSv1')
        if val is None or val.lower() != 'true':
            self.results['IMDSv2Enforced'] = [-1, 'IMDSv1 is not disabled; enforce IMDSv2 on instances']
        else:
            self.results['IMDSv2Enforced'] = [1, '']

    def _checkLatestPlatform(self):
        status = self.env.get('Status', '')
        platform_arn = self.env.get('PlatformArn', '')
        update_status = self.env.get('EnvironmentLinks', [])
        # Check VersionLabel for platform update availability
        try:
            resp = self.ebClient.describe_platform_version(PlatformArn=platform_arn)
            platform_status = resp.get('PlatformDescription', {}).get('PlatformStatus', '')
            if platform_status == 'Deprecated':
                self.results['LatestPlatformVersion'] = [-1, f'Platform is deprecated: {platform_arn}']
            else:
                self.results['LatestPlatformVersion'] = [1, '']
        except botocore.exceptions.ClientError as e:
            print(f'[ElasticbeanstalkDriver] describe_platform_version error: {e.response["Error"]["Code"]}')
