import botocore
from services.Evaluator import Evaluator

class EcsCluster(Evaluator):
    def __init__(self, cluster, ecsClient):
        super().__init__()
        self.cluster = cluster
        self.ecsClient = ecsClient
        self._resourceName = cluster.get('clusterArn', cluster.get('clusterName'))
        self.init()

    def _checkContainerInsights(self):
        """Check if Container Insights monitoring is enabled"""
        settings = self.cluster.get('settings', [])
        for setting in settings:
            if setting.get('name') == 'containerInsights' and setting.get('value') == 'enabled':
                return
        self.results['ECSContainerInsightsDisabled'] = [-1, self.cluster.get('clusterName')]

    def _checkFargateTasksOnly(self):
        """Check for EC2 launch type tasks — Fargate is preferred for security isolation"""
        stats = self.cluster.get('statistics', [])
        for stat in stats:
            if stat.get('name') == 'runningEC2TasksCount':
                count = int(stat.get('value', 0))
                if count > 0:
                    self.results['ECSRunningEC2Tasks'] = [0, f'{count} tasks running on EC2 launch type']
                return

    def _checkExecuteCommandLogging(self):
        """Check if ECS Exec logging is configured for the cluster"""
        config = self.cluster.get('configuration', {})
        exec_config = config.get('executeCommandConfiguration', {})
        logging = exec_config.get('logging', 'NONE')
        if logging == 'NONE':
            self.results['ECSExecLoggingDisabled'] = [-1, self.cluster.get('clusterName')]

    def _checkClusterEncryption(self):
        """Check if ECS Exec uses KMS encryption"""
        config = self.cluster.get('configuration', {})
        exec_config = config.get('executeCommandConfiguration', {})
        if not exec_config.get('kmsKeyId'):
            self.results['ECSExecNoKMSEncryption'] = [0, self.cluster.get('clusterName')]

    def _checkTaskDefinitionSecrets(self):
        """Check running tasks for hardcoded environment variable secrets"""
        try:
            paginator = self.ecsClient.get_paginator('list_tasks')
            for page in paginator.paginate(cluster=self.cluster['clusterArn'], desiredStatus='RUNNING'):
                taskArns = page.get('taskArns', [])
                if not taskArns:
                    continue
                resp = self.ecsClient.describe_tasks(cluster=self.cluster['clusterArn'], tasks=taskArns[:10])
                for task in resp.get('tasks', []):
                    taskDefArn = task.get('taskDefinitionArn', '')
                    tdResp = self.ecsClient.describe_task_definition(taskDefinition=taskDefArn)
                    for container in tdResp.get('taskDefinition', {}).get('containerDefinitions', []):
                        for env in container.get('environment', []):
                            key = env.get('name', '').lower()
                            if any(s in key for s in ['password', 'secret', 'token', 'key', 'api_key']):
                                self.results['ECSHardcodedSecretInEnvVar'] = [-1, container.get('name', '')]
                                return
        except botocore.exceptions.ClientError:
            pass

    def _checkTaskRoleAssigned(self):
        """Check that running task definitions have a task role assigned"""
        try:
            paginator = self.ecsClient.get_paginator('list_task_definitions')
            for page in paginator.paginate(status='ACTIVE'):
                for tdArn in page.get('taskDefinitionArns', [])[:20]:
                    resp = self.ecsClient.describe_task_definition(taskDefinition=tdArn)
                    td = resp.get('taskDefinition', {})
                    if not td.get('taskRoleArn'):
                        self.results['ECSTaskMissingTaskRole'] = [0, tdArn.split('/')[-1]]
                        return
        except botocore.exceptions.ClientError:
            pass

    def _checkReadonlyRootFilesystem(self):
        """Check that containers use read-only root filesystem"""
        try:
            paginator = self.ecsClient.get_paginator('list_task_definitions')
            for page in paginator.paginate(status='ACTIVE'):
                for tdArn in page.get('taskDefinitionArns', [])[:20]:
                    resp = self.ecsClient.describe_task_definition(taskDefinition=tdArn)
                    for container in resp.get('taskDefinition', {}).get('containerDefinitions', []):
                        if not container.get('readonlyRootFilesystem', False):
                            self.results['ECSContainerNoReadonlyRootFS'] = [0, container.get('name', '')]
                            return
        except botocore.exceptions.ClientError:
            pass
