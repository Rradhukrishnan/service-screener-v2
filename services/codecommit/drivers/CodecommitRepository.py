import botocore
from services.Evaluator import Evaluator

class CodecommitRepository(Evaluator):
    def __init__(self, repo, ccClient):
        super().__init__()
        self.repo = repo
        self.ccClient = ccClient
        self._resourceName = repo.get('Arn', repo.get('repositoryName'))
        self.init()

    def _checkNotifications(self):
        try:
            resp = self.ccClient.list_tags_for_resource(resourceArn=self.repo.get('Arn', ''))
            tags = resp.get('tags', {})
            if not tags:
                self.results['CCNoTags'] = [0, self.repo.get('repositoryName')]
        except botocore.exceptions.ClientError:
            pass

    def _checkApprovalRules(self):
        try:
            resp = self.ccClient.list_approval_rule_templates()
            templates = resp.get('approvalRuleTemplateNames', [])
            if not templates:
                self.results['CCNoApprovalRules'] = [0, 'No approval rule templates defined']
        except botocore.exceptions.ClientError:
            pass

    def _checkDefaultBranch(self):
        if not self.repo.get('defaultBranch'):
            self.results['CCNoDefaultBranch'] = [0, self.repo.get('repositoryName')]
