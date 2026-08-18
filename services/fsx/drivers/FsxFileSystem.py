import botocore
from services.Evaluator import Evaluator

class FsxFileSystem(Evaluator):
    def __init__(self, filesystem, fsxClient):
        super().__init__()
        self.filesystem = filesystem
        self.fsxClient = fsxClient
        self._resourceName = filesystem.get('ResourceARN', filesystem.get('FileSystemId'))
        self.init()

    def _checkEncryption(self):
        """Check if file system is encrypted at rest"""
        kms_key = self.filesystem.get('KmsKeyId', '')
        if not kms_key:
            self.results['FSxNoEncryption'] = [-1, self.filesystem.get('FileSystemId')]

    def _checkBackupEnabled(self):
        """Check if automatic backups are enabled"""
        fs_type = self.filesystem.get('FileSystemType', '')
        if fs_type == 'WINDOWS':
            config = self.filesystem.get('WindowsConfiguration', {})
            retention = config.get('AutomaticBackupRetentionDays', 0)
        elif fs_type == 'LUSTRE':
            config = self.filesystem.get('LustreConfiguration', {})
            retention = config.get('AutomaticBackupRetentionDays', 0)
        elif fs_type == 'ONTAP':
            config = self.filesystem.get('OntapConfiguration', {})
            retention = config.get('AutomaticBackupRetentionDays', 0)
        elif fs_type == 'OPENZFS':
            config = self.filesystem.get('OpenZFSConfiguration', {})
            retention = config.get('AutomaticBackupRetentionDays', 0)
        else:
            retention = 0

        if retention == 0:
            self.results['FSxBackupDisabled'] = [-1, self.filesystem.get('FileSystemId')]

    def _checkMultiAZ(self):
        """Check if Windows file system is Multi-AZ"""
        fs_type = self.filesystem.get('FileSystemType', '')
        if fs_type == 'WINDOWS':
            config = self.filesystem.get('WindowsConfiguration', {})
            deployment = config.get('DeploymentType', '')
            if deployment == 'SINGLE_AZ_1' or deployment == 'SINGLE_AZ_2':
                self.results['FSxSingleAZ'] = [-1, f"{self.filesystem.get('FileSystemId')} ({deployment})"]

    def _checkStorageCapacity(self):
        """Check if storage utilization is available — flag very small FS that may be unused"""
        storage = self.filesystem.get('StorageCapacity', 0)
        if storage < 32 and self.filesystem.get('FileSystemType') != 'LUSTRE':
            self.results['FSxLowStorage'] = [0,
                f"{self.filesystem.get('FileSystemId')} has only {storage}GB — verify if still needed"]

    def _checkLifecycle(self):
        """Check file system lifecycle status"""
        lifecycle = self.filesystem.get('Lifecycle', '')
        if lifecycle in ('MISCONFIGURED', 'FAILED'):
            self.results['FSxUnhealthyLifecycle'] = [-1,
                f"{self.filesystem.get('FileSystemId')} is in {lifecycle} state"]

    def _checkTags(self):
        """Check if file system has required tags"""
        tags = self.filesystem.get('Tags', [])
        if not tags:
            self.results['FSxNoTags'] = [0, self.filesystem.get('FileSystemId')]

    def _checkVPCSecurityGroups(self):
        """Check that security groups are assigned (not default)"""
        subnet_ids = self.filesystem.get('SubnetIds', [])
        if not subnet_ids:
            self.results['FSxNoSubnet'] = [-1, self.filesystem.get('FileSystemId')]
