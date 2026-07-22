import botocore
from services.Evaluator import Evaluator

class Wafv2WebACL(Evaluator):
    def __init__(self, acl, wafClient):
        super().__init__()
        self.acl = acl
        self.wafClient = wafClient
        self._resourceName = acl.get('ARN', acl.get('Name'))
        self.init()

    def _checkLoggingEnabled(self):
        try:
            self.wafClient.get_logging_configuration(ResourceArn=self.acl['ARN'])
        except botocore.exceptions.ClientError as e:
            if 'WAFNonexistentItemException' in str(e):
                self.results['WAFLoggingDisabled'] = [-1, self.acl.get('Name')]

    def _checkManagedRuleGroups(self):
        rules = self.acl.get('Rules', [])
        has_managed = any('ManagedRuleGroupStatement' in str(r) for r in rules)
        if not has_managed:
            self.results['WAFNoManagedRuleGroups'] = [-1, self.acl.get('Name')]

    def _checkRateLimitingRules(self):
        rules = self.acl.get('Rules', [])
        has_rate = any('RateBasedStatement' in str(r) for r in rules)
        if not has_rate:
            self.results['WAFNoRateLimiting'] = [0, self.acl.get('Name')]

    def _checkDefaultAction(self):
        default = self.acl.get('DefaultAction', {})
        if 'Allow' in default:
            self.results['WAFDefaultActionAllow'] = [0, 'Default action is Allow — consider Block for stricter posture']
