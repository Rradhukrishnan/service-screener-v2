from services.Service import Service
from services.codebuild.drivers.CodebuildProject import CodebuildProject
from utils.Tools import _pi

class Codebuild(Service):
    def __init__(self, region):
        super().__init__(region)
        self.cbClient = self.ssBoto.client('codebuild', config=self.bConfig)

    def advise(self):
        objs = {}
        paginator = self.cbClient.get_paginator('list_projects')
        names = []
        for page in paginator.paginate():
            names.extend(page.get('projects', []))
        if not names:
            return objs
        for i in range(0, len(names), 100):
            batch = self.cbClient.batch_get_projects(names=names[i:i+100])
            for project in batch.get('projects', []):
                name = project.get('name')
                _pi('CodeBuild::Project', name)
                obj = CodebuildProject(project)
                obj.run(self.__class__)
                objs['CodeBuild::' + name] = obj.getInfo()
                del obj
        return objs
