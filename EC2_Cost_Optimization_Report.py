"""
EC2 Cost Optimization Report
=============================
For each EC2 instance:
- Current instance type and processor family
- Recommended AMD/Graviton equivalent
- Current vs recommended pricing
- Monthly/yearly savings estimate
- Savings Plan coverage check
- Last 3 months cost and usage from Cost Explorer
- Compute Optimizer recommendations
"""

import boto3
import json
import pandas as pd
from datetime import datetime, timedelta
import os
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment

# AMD and Graviton equivalents mapping
# Format: current_family -> (amd_equivalent, graviton_equivalent)
INSTANCE_FAMILY_MAP = {
    'm5':   ('m5a',  'm6g'),
    'm5n':  ('m5a',  'm6g'),
    'm4':   ('m5a',  'm6g'),
    'm6i':  ('m6a',  'm6g'),
    'm7i':  ('m7a',  'm7g'),
    'c5':   ('c5a',  'c6g'),
    'c5n':  ('c5a',  'c6g'),
    'c4':   ('c5a',  'c6g'),
    'c6i':  ('c6a',  'c6g'),
    'c7i':  ('c7a',  'c7g'),
    'r5':   ('r5a',  'r6g'),
    'r5n':  ('r5a',  'r6g'),
    'r4':   ('r5a',  'r6g'),
    'r6i':  ('r6a',  'r6g'),
    'r7i':  ('r7a',  'r7g'),
    't3':   ('t3a',  't4g'),
    't2':   ('t3a',  't4g'),
    'x1e':  ('x2gd', 'x2gd'),
    'i3':   ('i3en', 'i4g'),
}

PROCESSOR_MAP = {
    'm5': 'Intel Xeon Platinum 8175M', 'm5a': 'AMD EPYC 7R32', 'm6i': 'Intel Xeon Ice Lake',
    'm6a': 'AMD EPYC 7R13', 'm6g': 'AWS Graviton2', 'm7i': 'Intel Xeon Sapphire Rapids',
    'm7a': 'AMD EPYC Genoa', 'm7g': 'AWS Graviton3',
    'c5': 'Intel Xeon Platinum 8124M', 'c5a': 'AMD EPYC 7R32', 'c6i': 'Intel Xeon Ice Lake',
    'c6a': 'AMD EPYC 7R13', 'c6g': 'AWS Graviton2', 'c7i': 'Intel Xeon Sapphire Rapids',
    'c7a': 'AMD EPYC Genoa', 'c7g': 'AWS Graviton3',
    'r5': 'Intel Xeon Platinum 8175M', 'r5a': 'AMD EPYC 7R32', 'r6i': 'Intel Xeon Ice Lake',
    'r6a': 'AMD EPYC 7R13', 'r6g': 'AWS Graviton2', 'r7i': 'Intel Xeon Sapphire Rapids',
    'r7a': 'AMD EPYC Genoa', 'r7g': 'AWS Graviton3',
    't3': 'Intel Xeon Platinum 8259CL', 't3a': 'AMD EPYC 7571', 't4g': 'AWS Graviton2',
    't2': 'Intel Xeon', 'i3': 'Intel Xeon E5-2686 v4', 'i4g': 'AWS Graviton2',
}


def get_downloads_path():
    return os.path.join(os.path.expanduser('~'), 'Downloads')


def get_instance_family(instance_type):
    """Extract family from instance type e.g. m5.xlarge -> m5"""
    return instance_type.split('.')[0]


def get_instance_size(instance_type):
    """Extract size from instance type e.g. m5.xlarge -> xlarge"""
    parts = instance_type.split('.')
    return parts[1] if len(parts) > 1 else ''


def get_processor(family):
    return PROCESSOR_MAP.get(family, 'Intel/AMD')


def get_amd_graviton_equivalent(instance_type):
    family = get_instance_family(instance_type)
    size   = get_instance_size(instance_type)
    mapping = INSTANCE_FAMILY_MAP.get(family, (None, None))
    amd_type      = f"{mapping[0]}.{size}" if mapping[0] else 'N/A'
    graviton_type = f"{mapping[1]}.{size}" if mapping[1] else 'N/A'
    return amd_type, graviton_type


def get_ec2_price(instance_type, region, os_type='Linux'):
    """Get on-demand price for an instance type using pricing API"""
    try:
        # Pricing API is only available in us-east-1
        pricing = boto3.client('pricing', region_name='us-east-1')
        region_name_map = {
            'us-east-1': 'US East (N. Virginia)',
            'us-east-2': 'US East (Ohio)',
            'us-west-1': 'US West (N. California)',
            'us-west-2': 'US West (Oregon)',
            'ap-south-1': 'Asia Pacific (Mumbai)',
            'ap-south-2': 'Asia Pacific (Hyderabad)',
            'ap-southeast-1': 'Asia Pacific (Singapore)',
            'ap-southeast-2': 'Asia Pacific (Sydney)',
            'ap-northeast-1': 'Asia Pacific (Tokyo)',
            'ap-northeast-2': 'Asia Pacific (Seoul)',
            'eu-west-1': 'Europe (Ireland)',
            'eu-west-2': 'Europe (London)',
            'eu-central-1': 'Europe (Frankfurt)',
            'ca-central-1': 'Canada (Central)',
            'sa-east-1': 'South America (Sao Paulo)',
        }
        region_full = region_name_map.get(region, region)
        resp = pricing.get_products(
            ServiceCode='AmazonEC2',
            Filters=[
                {'Type': 'TERM_MATCH', 'Field': 'instanceType',    'Value': instance_type},
                {'Type': 'TERM_MATCH', 'Field': 'location',        'Value': region_full},
                {'Type': 'TERM_MATCH', 'Field': 'operatingSystem', 'Value': os_type},
                {'Type': 'TERM_MATCH', 'Field': 'tenancy',         'Value': 'Shared'},
                {'Type': 'TERM_MATCH', 'Field': 'capacitystatus',  'Value': 'Used'},
                {'Type': 'TERM_MATCH', 'Field': 'preInstalledSw',  'Value': 'NA'},
            ],
            MaxResults=1
        )
        if resp['PriceList']:
            price_item = json.loads(resp['PriceList'][0])
            terms = price_item.get('terms', {}).get('OnDemand', {})
            for term in terms.values():
                for dim in term.get('priceDimensions', {}).values():
                    price_str = dim.get('pricePerUnit', {}).get('USD', '0')
                    return float(price_str)
    except Exception as e:
        pass
    return None


def get_last_3_months_cost(instance_id):
    """Get last 3 months cost and usage hours for an EC2 instance"""
    try:
        ce = boto3.client('ce', region_name='us-east-1')
        end   = datetime.now().date().replace(day=1)
        start = (end - timedelta(days=90)).replace(day=1)
        resp = ce.get_cost_and_usage(
            TimePeriod={'Start': str(start), 'End': str(end)},
            Granularity='MONTHLY',
            Filter={
                'And': [
                    {'Dimensions': {'Key': 'SERVICE',     'Values': ['Amazon Elastic Compute Cloud - Compute']}},
                    {'Dimensions': {'Key': 'RESOURCE_ID', 'Values': [instance_id]}}
                ]
            },
            Metrics=['UnblendedCost', 'UsageQuantity'],
            GroupBy=[{'Type': 'DIMENSION', 'Key': 'RESOURCE_ID'}]
        )
        total_cost  = 0.0
        total_hours = 0.0
        monthly = []
        for result in resp.get('ResultsByTime', []):
            period = result['TimePeriod']['Start'][:7]
            for group in result.get('Groups', []):
                cost  = float(group['Metrics']['UnblendedCost']['Amount'])
                hours = float(group['Metrics']['UsageQuantity']['Amount'])
                total_cost  += cost
                total_hours += hours
                monthly.append(f"{period}: ${cost:.2f}")
        return round(total_cost, 2), round(total_hours, 1), ' | '.join(monthly)
    except Exception:
        return 0.0, 0.0, 'N/A'


def check_savings_plan_coverage(instance_id):
    """Check if instance is covered by Savings Plan"""
    try:
        ce = boto3.client('ce', region_name='us-east-1')
        end   = datetime.now().date().replace(day=1)
        start = (end - timedelta(days=30)).replace(day=1)
        resp = ce.get_savings_plans_coverage(
            TimePeriod={'Start': str(start), 'End': str(end)},
            Granularity='MONTHLY',
            Filter={
                'Dimensions': {'Key': 'RESOURCE_ID', 'Values': [instance_id]}
            }
        )
        coverages = resp.get('SavingsPlansCoverages', [])
        for c in coverages:
            pct = float(c.get('Coverage', {}).get('CoveragePercentage', '0') or '0')
            if pct > 0:
                return f'Yes ({pct:.1f}% covered)'
        return 'No'
    except Exception:
        return 'Unknown'


def get_compute_optimizer_recommendations(region):
    """Get Compute Optimizer EC2 recommendations"""
    recommendations = {}
    try:
        co = boto3.client('compute-optimizer', region_name=region)
        paginator = co.get_paginator('get_ec2_instance_recommendations')
        for page in paginator.paginate():
            for rec in page.get('instanceRecommendations', []):
                iid = rec.get('instanceArn', '').split('/')[-1]
                finding = rec.get('finding', '')
                options = rec.get('recommendationOptions', [])
                best = options[0] if options else {}
                recommendations[iid] = {
                    'finding'         : finding,
                    'recommended_type': best.get('instanceType', 'N/A'),
                    'estimated_saving': best.get('estimatedMonthlySavings', {}).get('value', 0),
                    'saving_currency' : best.get('estimatedMonthlySavings', {}).get('currency', 'USD'),
                    'perf_risk'       : best.get('performanceRisk', 'N/A'),
                }
    except Exception as e:
        print(f"  [WARN] Compute Optimizer: {str(e)}")
    return recommendations


def get_all_instances(regions):
    """Get all EC2 instances across specified regions"""
    all_instances = []
    for region in regions:
        print(f"  Scanning region: {region}")
        try:
            ec2 = boto3.client('ec2', region_name=region)
            paginator = ec2.get_paginator('describe_instances')
            for page in paginator.paginate(
                Filters=[{'Name': 'instance-state-name', 'Values': ['running', 'stopped']}]
            ):
                for reservation in page['Reservations']:
                    for inst in reservation['Instances']:
                        tags = {t['Key']: t['Value'] for t in inst.get('Tags', [])}
                        all_instances.append({
                            'region'        : region,
                            'instance_id'   : inst['InstanceId'],
                            'instance_type' : inst['InstanceType'],
                            'state'         : inst['State']['Name'],
                            'name'          : tags.get('Name', ''),
                            'platform'      : inst.get('Platform', 'Linux'),
                            'launch_time'   : str(inst.get('LaunchTime', '')[:10]) if inst.get('LaunchTime') else '',
                            'tags'          : tags,
                        })
        except Exception as e:
            print(f"  [WARN] {region}: {str(e)}")
    return all_instances


def build_report(instances, price_cache):
    """Build the full cost optimization rows"""
    rows = []
    print(f"\nAnalyzing {len(instances)} instances...")

    for inst in instances:
        region        = inst['region']
        instance_id   = inst['instance_id']
        instance_type = inst['instance_type']
        family        = get_instance_family(instance_type)

        print(f"  {instance_id} ({instance_type}) [{region}]")

        current_processor = get_processor(family)
        amd_type, graviton_type = get_amd_graviton_equivalent(instance_type)

        # Current price
        cache_key = f"{instance_type}_{region}"
        if cache_key not in price_cache:
            price_cache[cache_key] = get_ec2_price(instance_type, region)
        current_price = price_cache[cache_key]

        # AMD price
        amd_price = None
        if amd_type != 'N/A':
            amd_key = f"{amd_type}_{region}"
            if amd_key not in price_cache:
                price_cache[amd_key] = get_ec2_price(amd_type, region)
            amd_price = price_cache[amd_key]

        # Graviton price
        graviton_price = None
        if graviton_type != 'N/A':
            grav_key = f"{graviton_type}_{region}"
            if grav_key not in price_cache:
                price_cache[grav_key] = get_ec2_price(graviton_type, region)
            graviton_price = price_cache[grav_key]

        # Savings calculations (730 hours/month)
        hours_month = 730
        current_monthly = round(current_price * hours_month, 2) if current_price else 'N/A'

        amd_monthly      = round(amd_price * hours_month, 2) if amd_price else 'N/A'
        graviton_monthly = round(graviton_price * hours_month, 2) if graviton_price else 'N/A'

        amd_saving_month = round((current_price - amd_price) * hours_month, 2) \
            if current_price and amd_price else 'N/A'
        amd_saving_year  = round(amd_saving_month * 12, 2) \
            if isinstance(amd_saving_month, float) else 'N/A'

        graviton_saving_month = round((current_price - graviton_price) * hours_month, 2) \
            if current_price and graviton_price else 'N/A'
        graviton_saving_year  = round(graviton_saving_month * 12, 2) \
            if isinstance(graviton_saving_month, float) else 'N/A'

        # Cost Explorer — last 3 months
        actual_cost_3m, usage_hours_3m, monthly_breakdown = get_last_3_months_cost(instance_id)

        # Savings Plan coverage
        sp_coverage = check_savings_plan_coverage(instance_id)

        # Compute Optimizer
        co_rec = price_cache.get(f"co_{instance_id}", {})
        co_finding   = co_rec.get('finding', 'N/A')
        co_rec_type  = co_rec.get('recommended_type', 'N/A')
        co_saving    = co_rec.get('estimated_saving', 'N/A')

        rows.append({
            'Region'                          : region,
            'Instance_ID'                     : instance_id,
            'Instance_Name'                   : inst['name'],
            'State'                           : inst['state'],
            'Current_Instance_Type'           : instance_type,
            'Current_Processor'               : current_processor,
            'Current_OnDemand_Price_Per_Hr'   : f"${current_price:.4f}" if current_price else 'N/A',
            'Current_Monthly_Cost_OnDemand'   : f"${current_monthly}" if isinstance(current_monthly, float) else 'N/A',
            'Recommended_AMD_Type'            : amd_type,
            'AMD_Processor'                   : get_processor(get_instance_family(amd_type)) if amd_type != 'N/A' else 'N/A',
            'AMD_Price_Per_Hr'                : f"${amd_price:.4f}" if amd_price else 'N/A',
            'AMD_Monthly_Cost'                : f"${amd_monthly}" if isinstance(amd_monthly, float) else 'N/A',
            'AMD_Saving_Per_Month'            : f"${amd_saving_month}" if isinstance(amd_saving_month, float) else 'N/A',
            'AMD_Saving_Per_Year'             : f"${amd_saving_year}" if isinstance(amd_saving_year, float) else 'N/A',
            'Recommended_Graviton_Type'       : graviton_type,
            'Graviton_Processor'              : get_processor(get_instance_family(graviton_type)) if graviton_type != 'N/A' else 'N/A',
            'Graviton_Price_Per_Hr'           : f"${graviton_price:.4f}" if graviton_price else 'N/A',
            'Graviton_Monthly_Cost'           : f"${graviton_monthly}" if isinstance(graviton_monthly, float) else 'N/A',
            'Graviton_Saving_Per_Month'       : f"${graviton_saving_month}" if isinstance(graviton_saving_month, float) else 'N/A',
            'Graviton_Saving_Per_Year'        : f"${graviton_saving_year}" if isinstance(graviton_saving_year, float) else 'N/A',
            'Savings_Plan_Coverage'           : sp_coverage,
            'Actual_Cost_Last_3_Months_USD'   : f"${actual_cost_3m}",
            'Usage_Hours_Last_3_Months'       : usage_hours_3m,
            'Monthly_Cost_Breakdown'          : monthly_breakdown,
            'ComputeOptimizer_Finding'        : co_finding,
            'ComputeOptimizer_Recommended'    : co_rec_type,
            'ComputeOptimizer_Monthly_Saving' : f"${co_saving}" if co_saving != 'N/A' else 'N/A',
            'Launch_Time'                     : inst['launch_time'],
        })
    return rows


def format_excel(ws, highlight_savings=False):
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    green_fill  = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
    thin_border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin')
    )
    for cell in ws[1]:
        cell.font = header_font
        cell.fill = header_fill
        cell.border = thin_border
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.border = thin_border
            cell.alignment = Alignment(horizontal='left', vertical='top', wrap_text=True)
            # Highlight saving columns in green
            if highlight_savings and cell.column_letter in ['N', 'O', 'T', 'U']:
                if cell.value and cell.value != 'N/A' and str(cell.value).startswith('$'):
                    try:
                        val = float(str(cell.value).replace('$', ''))
                        if val > 0:
                            cell.fill = green_fill
                    except Exception:
                        pass


def auto_fit_columns(ws):
    for col in ws.columns:
        max_len = 0
        col_letter = col[0].column_letter
        for cell in col:
            try:
                val = str(cell.value) if cell.value else ''
                if len(val) > max_len:
                    max_len = len(val)
            except Exception:
                pass
        ws.column_dimensions[col_letter].width = min(max_len + 4, 50)


def main():
    print("=" * 65)
    print("  EC2 Cost Optimization Report")
    print("=" * 65)

    # Define regions to scan — update this list as needed
    REGIONS = [
        'ap-south-1',
        'us-east-1',
        'us-east-2',
        'us-west-2',
        'ap-southeast-1',
        'eu-west-1',
        'eu-central-1',
    ]

    print(f"\nScanning {len(REGIONS)} regions for EC2 instances...")
    instances = get_all_instances(REGIONS)
    print(f"Total instances found: {len(instances)}")

    if not instances:
        print("No instances found.")
        return

    # Pre-fetch Compute Optimizer recommendations per region
    price_cache = {}
    print("\nFetching Compute Optimizer recommendations...")
    for region in REGIONS:
        co_recs = get_compute_optimizer_recommendations(region)
        for iid, rec in co_recs.items():
            price_cache[f"co_{iid}"] = rec
    print(f"Compute Optimizer recommendations fetched: {len([k for k in price_cache if k.startswith('co_')])}")

    # Build report rows
    rows = build_report(instances, price_cache)

    if not rows:
        print("No data to report.")
        return

    # Write Excel
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename    = f"EC2_Cost_Optimization_{timestamp}.xlsx"
    output_path = os.path.join(get_downloads_path(), filename)

    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:

        # Sheet 1 — All instances full details
        df = pd.DataFrame(rows)
        df.to_excel(writer, index=False, sheet_name='All Instances')
        ws = writer.sheets['All Instances']
        format_excel(ws, highlight_savings=True)
        auto_fit_columns(ws)

        # Sheet 2 — Only instances with savings potential
        savings_rows = [r for r in rows
                        if r.get('AMD_Saving_Per_Month') not in ('N/A', '$0.0', None)
                        or r.get('Graviton_Saving_Per_Month') not in ('N/A', '$0.0', None)]
        if savings_rows:
            pd.DataFrame(savings_rows).to_excel(
                writer, index=False, sheet_name='Savings Opportunities')
            ws2 = writer.sheets['Savings Opportunities']
            format_excel(ws2, highlight_savings=True)
            auto_fit_columns(ws2)

        # Sheet 3 — No Savings Plan coverage
        no_sp = [r for r in rows if r.get('Savings_Plan_Coverage') == 'No']
        if no_sp:
            pd.DataFrame(no_sp)[['Region','Instance_ID','Instance_Name',
                'Current_Instance_Type','Current_Monthly_Cost_OnDemand',
                'Actual_Cost_Last_3_Months_USD','Savings_Plan_Coverage']].to_excel(
                writer, index=False, sheet_name='No Savings Plan')
            ws3 = writer.sheets['No Savings Plan']
            format_excel(ws3)
            auto_fit_columns(ws3)

        # Sheet 4 — Summary by region
        summary = {}
        for r in rows:
            reg = r['Region']
            if reg not in summary:
                summary[reg] = {'Region': reg, 'Instance_Count': 0,
                    'Total_AMD_Monthly_Saving': 0.0, 'Total_Graviton_Monthly_Saving': 0.0,
                    'Total_Actual_Cost_3M': 0.0, 'No_Savings_Plan_Count': 0}
            summary[reg]['Instance_Count'] += 1
            try:
                summary[reg]['Total_AMD_Monthly_Saving'] += float(
                    str(r.get('AMD_Saving_Per_Month', '0')).replace('$', '') or '0')
            except Exception:
                pass
            try:
                summary[reg]['Total_Graviton_Monthly_Saving'] += float(
                    str(r.get('Graviton_Saving_Per_Month', '0')).replace('$', '') or '0')
            except Exception:
                pass
            try:
                summary[reg]['Total_Actual_Cost_3M'] += float(
                    str(r.get('Actual_Cost_Last_3_Months_USD', '0')).replace('$', '') or '0')
            except Exception:
                pass
            if r.get('Savings_Plan_Coverage') == 'No':
                summary[reg]['No_Savings_Plan_Count'] += 1

        df_sum = pd.DataFrame(list(summary.values()))
        df_sum['Total_AMD_Monthly_Saving']      = df_sum['Total_AMD_Monthly_Saving'].apply(lambda x: f"${x:.2f}")
        df_sum['Total_Graviton_Monthly_Saving'] = df_sum['Total_Graviton_Monthly_Saving'].apply(lambda x: f"${x:.2f}")
        df_sum['Total_Actual_Cost_3M']          = df_sum['Total_Actual_Cost_3M'].apply(lambda x: f"${x:.2f}")
        df_sum.to_excel(writer, index=False, sheet_name='Summary by Region')
        ws4 = writer.sheets['Summary by Region']
        format_excel(ws4)
        auto_fit_columns(ws4)

    print(f"\nReport saved to: {output_path}")
    print(f"Total instances analyzed : {len(rows)}")
    print(f"Savings opportunities    : {len(savings_rows) if savings_rows else 0}")
    print(f"No Savings Plan          : {len(no_sp) if no_sp else 0}")


if __name__ == "__main__":
    main()
