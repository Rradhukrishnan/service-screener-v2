import botocore
from services.Evaluator import Evaluator

class SesAccount(Evaluator):
    def __init__(self, sesClient):
        super().__init__()
        self.sesClient = sesClient
        self._resourceName = 'SES::Account'
        self.init()

    def _checkSendingEnabled(self):
        try:
            resp = self.sesClient.get_account()
            if not resp.get('SendingEnabled', False):
                self.results['SESSendingDisabled'] = [0, 'Sending is disabled for this account']
        except botocore.exceptions.ClientError:
            pass

    def _checkDKIMOnIdentities(self):
        try:
            paginator = self.sesClient.get_paginator('list_email_identities')
            for page in paginator.paginate():
                for identity in page.get('EmailIdentities', []):
                    name = identity.get('IdentityName')
                    detail = self.sesClient.get_email_identity(EmailIdentity=name)
                    dkim = detail.get('DkimAttributes', {})
                    if not dkim.get('SigningEnabled', False):
                        self.results['SESDKIMNotEnabled'] = [-1, name]
                        return
        except botocore.exceptions.ClientError:
            pass

    def _checkConfigurationSet(self):
        try:
            resp = self.sesClient.list_configuration_sets()
            if not resp.get('ConfigurationSets'):
                self.results['SESNoConfigurationSet'] = [0, 'No configuration sets defined']
        except botocore.exceptions.ClientError:
            pass

    def _checkSuppressionList(self):
        try:
            resp = self.sesClient.get_suppression_options()
            reasons = resp.get('SuppressedReasons', [])
            if not reasons:
                self.results['SESNoSuppressionList'] = [0, 'No suppression reasons configured']
        except botocore.exceptions.ClientError:
            pass
