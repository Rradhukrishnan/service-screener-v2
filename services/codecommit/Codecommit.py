from services.Service import Service
from services.codecommit.drivers.CodecommitRepository import CodecommitRepository
from utils.Tools import _pi

class Codecommit(Service):
    def __init__(self, region):
        super().__init__(region)
        self.ccClient = self.ssBoto.client('codecommit', config=self.bConfig)

    def advise(self):
        objs = {}
        paginator = self.ccClient.get_paginator('list_repositories')
        for page in paginator.paginate():
            for repo in page.get('repositories', []):
                name = repo.get('repositoryName')
                _pi('CodeCommit::Repository', name)
                detail = self.ccClient.get_repository(repositoryName=name)
                obj = CodecommitRepository(detail.get('repositoryMetadata', {}), self.ccClient)
                obj.run(self.__class__)
                objs['CodeCommit::' + name] = obj.getInfo()
                del obj
        return objs
