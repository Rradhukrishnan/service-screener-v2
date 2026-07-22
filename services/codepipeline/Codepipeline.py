from services.Service import Service
from services.codepipeline.drivers.CodepipelinePipeline import CodepipelinePipeline
from utils.Tools import _pi

class Codepipeline(Service):
    def __init__(self, region):
        super().__init__(region)
        self.cpClient = self.ssBoto.client('codepipeline', config=self.bConfig)

    def advise(self):
        objs = {}
        paginator = self.cpClient.get_paginator('list_pipelines')
        for page in paginator.paginate():
            for p in page.get('pipelines', []):
                name = p.get('name')
                _pi('CodePipeline::Pipeline', name)
                detail = self.cpClient.get_pipeline(name=name)
                obj = CodepipelinePipeline(detail.get('pipeline', {}), self.cpClient)
                obj.run(self.__class__)
                objs['CodePipeline::' + name] = obj.getInfo()
                del obj
        return objs
