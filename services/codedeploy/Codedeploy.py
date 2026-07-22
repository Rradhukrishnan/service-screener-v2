from services.Service import Service
from services.codedeploy.drivers.CodedeployGroup import CodedeployGroup
from utils.Tools import _pi

class Codedeploy(Service):
    def __init__(self, region):
        super().__init__(region)
        self.cdClient = self.ssBoto.client('codedeploy', config=self.bConfig)

    def advise(self):
        objs = {}
        paginator = self.cdClient.get_paginator('list_applications')
        for page in paginator.paginate():
            for app in page.get('applications', []):
                gpaginator = self.cdClient.get_paginator('list_deployment_groups')
                for gpage in gpaginator.paginate(applicationName=app):
                    for group in gpage.get('deploymentGroups', []):
                        _pi('CodeDeploy::Group', group)
                        detail = self.cdClient.get_deployment_group(applicationName=app, deploymentGroupName=group)
                        obj = CodedeployGroup(detail.get('deploymentGroupInfo', {}))
                        obj.run(self.__class__)
                        objs[f'CodeDeploy::{app}::{group}'] = obj.getInfo()
                        del obj
        return objs
