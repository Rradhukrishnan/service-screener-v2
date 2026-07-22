import botocore
from services.Evaluator import Evaluator
from utils.Config import Config

class CostexplorerAccount(Evaluator):
    def __init__(self, ceClient, budgetsClient):
        super().__init__()
        self.ceClient = ceClient
        self.budgetsClient = budgetsClient
        self._resourceName = 'CostExplorer::Account'
        self.init()

    def _checkAnomalyMonitors(self):
        try:
            resp = self.ceClient.get_anomaly_monitors()
            monitors = resp.get('AnomalyMonitors', [])
            if not monitors:
                self.results['CENoAnomalyMonitors'] = [-1, 'No cost anomaly monitors defined']
        except botocore.exceptions.ClientError:
            pass

    def _checkAnomalySubscriptions(self):
        try:
            resp = self.ceClient.get_anomaly_subscriptions()
            subs = resp.get('AnomalySubscriptions', [])
            if not subs:
                self.results['CENoAnomalySubscriptions'] = [-1, 'No anomaly alert subscriptions configured']
        except botocore.exceptions.ClientError:
            pass

    def _checkBudgets(self):
        try:
            stsInfo = Config.get('stsInfo')
            account_id = stsInfo.get('Account', '')
            resp = self.budgetsClient.describe_budgets(AccountId=account_id)
            budgets = resp.get('Budgets', [])
            if not budgets:
                self.results['CENoBudgets'] = [-1, 'No AWS Budgets configured']
            else:
                no_alerts = [b['BudgetName'] for b in budgets if not b.get('BudgetLimit')]
                if no_alerts:
                    self.results['CEBudgetNoAlerts'] = [0, f'{len(no_alerts)} budgets have no alerts']
        except botocore.exceptions.ClientError:
            pass

    def _checkSavingsPlans(self):
        try:
            resp = self.ceClient.get_savings_plans_coverage(
                TimePeriod={'Start': '2024-01-01', 'End': '2024-01-31'},
                Granularity='MONTHLY'
            )
            coverages = resp.get('SavingsPlansCoverages', [])
            for c in coverages:
                coverage_pct = float(c.get('Coverage', {}).get('CoveragePercentage', '0') or '0')
                if coverage_pct < 20:
                    self.results['CELowSavingsPlansCoverage'] = [0, f'Savings Plans coverage is {coverage_pct:.1f}%']
                    return
        except botocore.exceptions.ClientError:
            pass
