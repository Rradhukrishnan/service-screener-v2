import botocore
from services.Evaluator import Evaluator

class AmplifyDriver(Evaluator):
    def __init__(self, app, amplifyClient):
        super().__init__()
        self.app = app
        self.amplifyClient = amplifyClient
        self.appId = app.get('appId', 'unknown')
        self._resourceName = app.get('name', self.appId)

        # Fetch branches
        self.branches = []
        try:
            paginator = self.amplifyClient.get_paginator('list_branches')
            for page in paginator.paginate(appId=self.appId):
                self.branches.extend(page.get('branches', []))
        except botocore.exceptions.ClientError as e:
            print(f'[AmplifyDriver] list_branches error: {e.response["Error"]["Code"]}')

        self.init()

    def _checkBasicAuthOnBranches(self):
        unprotected = []
        for branch in self.branches:
            if not branch.get('enableBasicAuth', False):
                unprotected.append(branch.get('branchName', 'unknown'))
        if unprotected:
            self.results['BasicAuthOnBranches'] = [-1, f'Branches without basic auth: {", ".join(unprotected)}']
        else:
            self.results['BasicAuthOnBranches'] = [1, '']

    def _checkCustomDomainConfigured(self):
        try:
            resp = self.amplifyClient.list_domain_associations(appId=self.appId)
            domains = resp.get('domainAssociations', [])
            if not domains:
                self.results['CustomDomainConfigured'] = [-1, 'No custom domain associated with this app']
            else:
                self.results['CustomDomainConfigured'] = [1, '']
        except botocore.exceptions.ClientError as e:
            print(f'[AmplifyDriver] list_domain_associations error: {e.response["Error"]["Code"]}')

    def _checkAccessLogsEnabled(self):
        # Amplify access logs are stored in S3; check if logging bucket is configured
        # Access logs config is in the app-level settings
        tags = self.app.get('tags', {})
        # Amplify doesn't have a direct "access logs enabled" flag in the API;
        # we check if a backend environment or custom headers indicate logging intent
        # Best proxy: check if app has an associated backend env with logging
        try:
            resp = self.amplifyClient.list_backend_environments(appId=self.appId)
            backends = resp.get('backendEnvironments', [])
            if not backends:
                self.results['AccessLogsEnabled'] = [0, 'No backend environment configured; verify access logging is set up externally']
        except botocore.exceptions.ClientError as e:
            print(f'[AmplifyDriver] list_backend_environments error: {e.response["Error"]["Code"]}')

    def _checkBranchAutoBuildEnabled(self):
        disabled = []
        for branch in self.branches:
            if not branch.get('enableAutoBuild', False):
                disabled.append(branch.get('branchName', 'unknown'))
        if disabled:
            self.results['BranchAutoBuildEnabled'] = [-1, f'Auto-build disabled on branches: {", ".join(disabled)}']
        else:
            self.results['BranchAutoBuildEnabled'] = [1, '']

    def _checkWAFAssociation(self):
        # WAF can be associated via the app's WAF configuration (available in newer Amplify API)
        try:
            resp = self.amplifyClient.get_app(appId=self.appId)
            app_detail = resp.get('app', {})
            waf_config = app_detail.get('wafConfig', {})
            if not waf_config or not waf_config.get('webAclArn'):
                self.results['WAFAssociation'] = [-1, 'No WAF Web ACL associated with this Amplify app']
            else:
                self.results['WAFAssociation'] = [1, '']
        except botocore.exceptions.ClientError as e:
            code = e.response['Error']['Code']
            if code == 'NotFoundException':
                self.results['WAFAssociation'] = [-1, 'App not found']
            else:
                print(f'[AmplifyDriver] get_app error: {code}')
