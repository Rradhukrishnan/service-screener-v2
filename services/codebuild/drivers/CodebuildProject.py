from services.Evaluator import Evaluator

class CodebuildProject(Evaluator):
    def __init__(self, project):
        super().__init__()
        self.project = project
        self._resourceName = project.get('arn', project.get('name'))
        self.init()

    def _checkPrivilegedMode(self):
        env = self.project.get('environment', {})
        if env.get('privilegedMode', False):
            self.results['CBPrivilegedModeEnabled'] = [-1, self.project.get('name')]

    def _checkArtifactEncryption(self):
        artifacts = self.project.get('artifacts', {})
        if artifacts.get('type') != 'NO_ARTIFACTS' and artifacts.get('encryptionDisabled', False):
            self.results['CBArtifactsNotEncrypted'] = [-1, self.project.get('name')]

    def _checkLogging(self):
        logs = self.project.get('logsConfig', {})
        cw = logs.get('cloudWatchLogs', {})
        s3 = logs.get('s3Logs', {})
        if cw.get('status') != 'ENABLED' and s3.get('status') != 'ENABLED':
            self.results['CBLoggingDisabled'] = [-1, self.project.get('name')]

    def _checkVPCConfig(self):
        if not self.project.get('vpcConfig'):
            self.results['CBNoVPCConfig'] = [0, self.project.get('name')]

    def _checkEnvironmentVariableSecrets(self):
        env_vars = self.project.get('environment', {}).get('environmentVariables', [])
        for var in env_vars:
            if var.get('type') == 'PLAINTEXT':
                name = var.get('name', '').lower()
                if any(s in name for s in ['password', 'secret', 'token', 'key', 'api_key']):
                    self.results['CBHardcodedSecrets'] = [-1, f"Plain-text secret in env var: {var.get('name')}"]
                    return
