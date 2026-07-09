import botocore
from services.Evaluator import Evaluator

class EcrRepository(Evaluator):
    def __init__(self, repo, ecrClient):
        super().__init__()
        self.repo = repo
        self.ecrClient = ecrClient
        self._resourceName = repo.get('repositoryArn', repo.get('repositoryName'))
        self.init()

    def _checkImageScanOnPush(self):
        """Check if scan-on-push is enabled"""
        config = self.repo.get('imageScanningConfiguration', {})
        if not config.get('scanOnPush', False):
            self.results['ECRScanOnPushDisabled'] = [-1, self.repo.get('repositoryName')]

    def _checkImageTagMutability(self):
        """Check if image tags are immutable"""
        if self.repo.get('imageTagMutability') != 'IMMUTABLE':
            self.results['ECRMutableImageTags'] = [-1, self.repo.get('repositoryName')]

    def _checkEncryptionAtRest(self):
        """Check if repository uses KMS encryption (not default AES256)"""
        enc = self.repo.get('encryptionConfiguration', {})
        if enc.get('encryptionType') != 'KMS':
            self.results['ECRNoKMSEncryption'] = [0, self.repo.get('repositoryName')]

    def _checkRepositoryPolicy(self):
        """Check if repository has a resource policy restricting access"""
        try:
            self.ecrClient.get_repository_policy(repositoryName=self.repo['repositoryName'])
        except botocore.exceptions.ClientError as e:
            if e.response['Error']['Code'] == 'RepositoryPolicyNotFoundException':
                self.results['ECRNoRepositoryPolicy'] = [0, self.repo.get('repositoryName')]

    def _checkLifecyclePolicy(self):
        """Check if a lifecycle policy exists to clean up old images"""
        try:
            self.ecrClient.get_lifecycle_policy(repositoryName=self.repo['repositoryName'])
        except botocore.exceptions.ClientError as e:
            if e.response['Error']['Code'] == 'LifecyclePolicyNotFoundException':
                self.results['ECRNoLifecyclePolicy'] = [-1, self.repo.get('repositoryName')]

    def _checkCriticalVulnerabilities(self):
        """Check for critical vulnerabilities in latest images"""
        try:
            # Get the most recent image
            resp = self.ecrClient.describe_images(
                repositoryName=self.repo['repositoryName'],
                filter={'tagStatus': 'TAGGED'},
                maxResults=5
            )
            images = sorted(
                resp.get('imageDetails', []),
                key=lambda x: x.get('imagePushedAt', ''),
                reverse=True
            )
            if not images:
                return

            latest = images[0]
            scan = latest.get('imageScanFindingsSummary', {})
            findings = scan.get('findingSeverityCounts', {})
            critical = findings.get('CRITICAL', 0)
            high = findings.get('HIGH', 0)

            if critical > 0:
                self.results['ECRCriticalVulnerabilities'] = [-1, f'{critical} CRITICAL vulnerabilities in latest image']
            elif high > 0:
                self.results['ECRHighVulnerabilities'] = [-1, f'{high} HIGH vulnerabilities in latest image']

        except botocore.exceptions.ClientError:
            pass

    def _checkPublicAccess(self):
        """Check if repository policy allows public access"""
        try:
            import json
            resp = self.ecrClient.get_repository_policy(repositoryName=self.repo['repositoryName'])
            policy = json.loads(resp.get('policyText', '{}'))
            for stmt in policy.get('Statement', []):
                principal = stmt.get('Principal', '')
                if principal == '*' and stmt.get('Effect') == 'Allow':
                    self.results['ECRPublicAccessAllowed'] = [-1, self.repo.get('repositoryName')]
                    return
        except botocore.exceptions.ClientError:
            pass
