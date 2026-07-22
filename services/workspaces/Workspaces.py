from services.Service import Service
from services.workspaces.drivers.WorkspacesWorkspace import WorkspacesWorkspace
from utils.Tools import _pi

class Workspaces(Service):
    def __init__(self, region):
        super().__init__(region)
        self.wsClient = self.ssBoto.client('workspaces', config=self.bConfig)

    def advise(self):
        objs = {}
        paginator = self.wsClient.get_paginator('describe_workspaces')
        for page in paginator.paginate():
            for ws in page.get('Workspaces', []):
                ws_id = ws.get('WorkspaceId')
                _pi('WorkSpaces::Workspace', ws_id)
                obj = WorkspacesWorkspace(ws, self.wsClient)
                obj.run(self.__class__)
                objs['WorkSpaces::' + ws_id] = obj.getInfo()
                del obj
        return objs
