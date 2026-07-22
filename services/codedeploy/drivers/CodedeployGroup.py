from services.Evaluator import Evaluator

class CodedeployGroup(Evaluator):
    def __init__(self, group):
        super().__init__()
        self.group = group
        self._resourceName = group.get('deploymentGroupArn', group.get('deploymentGroupName'))
        self.init()

    def _checkDeploymentConfig(self):
        config = self.group.get('deploymentConfigName', '')
        risky = ['CodeDeployDefault.AllAtOnce', 'CodeDeployDefault.ECSAllAtOnce']
        if config in risky:
            self.results['CDAllAtOnceDeployment'] = [-1, config]

    def _checkAutoRollback(self):
        rollback = self.group.get('autoRollbackConfiguration', {})
        if not rollback.get('enabled', False):
            self.results['CDAutoRollbackDisabled'] = [-1, self.group.get('deploymentGroupName')]

    def _checkAlarms(self):
        alarms = self.group.get('alarmConfiguration', {})
        if not alarms.get('enabled', False) or not alarms.get('alarms'):
            self.results['CDNoAlarms'] = [0, self.group.get('deploymentGroupName')]

    def _checkLoadBalancer(self):
        lb_info = self.group.get('loadBalancerInfo', {})
        has_lb = lb_info.get('targetGroupInfoList') or lb_info.get('elbInfoList') or lb_info.get('targetGroupPairInfoList')
        if not has_lb:
            self.results['CDNoLoadBalancer'] = [0, self.group.get('deploymentGroupName')]
