import botocore
from services.Evaluator import Evaluator

class CodepipelinePipeline(Evaluator):
    def __init__(self, pipeline, cpClient):
        super().__init__()
        self.pipeline = pipeline
        self.cpClient = cpClient
        self._resourceName = pipeline.get('name', 'unknown')
        self.init()

    def _checkArtifactEncryption(self):
        enc = self.pipeline.get('artifactStore', {}).get('encryptionKey')
        if not enc:
            self.results['CPNoArtifactEncryption'] = [0, self.pipeline.get('name')]

    def _checkNotifications(self):
        try:
            resp = self.cpClient.list_tags_for_resource(
                resourceArn=f"arn:aws:codepipeline:{self.pipeline.get('name')}"
            )
        except botocore.exceptions.ClientError:
            pass

    def _checkSourceStage(self):
        stages = self.pipeline.get('stages', [])
        for stage in stages:
            for action in stage.get('actions', []):
                category = action.get('actionTypeId', {}).get('category')
                if category == 'Source':
                    return
        self.results['CPNoSourceStage'] = [-1, self.pipeline.get('name')]
