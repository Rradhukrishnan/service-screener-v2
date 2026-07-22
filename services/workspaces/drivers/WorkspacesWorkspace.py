import botocore
from services.Evaluator import Evaluator

class WorkspacesWorkspace(Evaluator):
    def __init__(self, workspace, wsClient):
        super().__init__()
        self.workspace = workspace
        self.wsClient = wsClient
        self._resourceName = workspace.get('WorkspaceId')
        self.init()

    def _checkRootVolumeEncryption(self):
        if not self.workspace.get('RootVolumeEncryptionEnabled', False):
            self.results['WSRootVolumeNotEncrypted'] = [-1, self.workspace.get('WorkspaceId')]

    def _checkUserVolumeEncryption(self):
        if not self.workspace.get('UserVolumeEncryptionEnabled', False):
            self.results['WSUserVolumeNotEncrypted'] = [-1, self.workspace.get('WorkspaceId')]

    def _checkRunningMode(self):
        props = self.workspace.get('WorkspaceProperties', {})
        mode = props.get('RunningMode', '')
        if mode == 'ALWAYS_ON':
            self.results['WSAlwaysOnRunningMode'] = [0, f'{self.workspace.get("WorkspaceId")} - consider AUTO_STOP to reduce cost']

    def _checkState(self):
        state = self.workspace.get('State', '')
        if state in ['ERROR', 'UNHEALTHY', 'STOPPED']:
            self.results['WSUnhealthyState'] = [-1, f'{self.workspace.get("WorkspaceId")} is in {state} state']

    def _checkMaintenanceMode(self):
        props = self.workspace.get('WorkspaceProperties', {})
        if not props.get('UserVolumeSizeGib') and not props.get('RootVolumeSizeGib'):
            self.results['WSNoCustomVolumeSizes'] = [0, self.workspace.get('WorkspaceId')]

    def _checkIPAccessControl(self):
        try:
            resp = self.wsClient.describe_workspace_directories()
            dirs = resp.get('Directories', [])
            for d in dirs:
                if not d.get('ipGroupIds'):
                    self.results['WSNoIPAccessControl'] = [0, d.get('DirectoryId', '')]
                    return
        except botocore.exceptions.ClientError:
            pass
