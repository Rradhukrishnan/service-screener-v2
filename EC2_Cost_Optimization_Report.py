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


def write_sheet(writer, df, sheet_name, highlight=False):
    if df.empty:
        return
    df.to_excel(writer, index=False, sheet_name=sheet_name)
    ws = writer.sheets[sheet_name]
    format_excel(ws, highlight_savings=highlight)
    auto_fit_columns(ws)


def main():
    print("=" * 65)
    print("  EC2 + AWS Cost Optimization Report  (All 13 Checks)")
    print("=" * 65)

    # ── Update regions as needed ──────────────────────────────────────
    REGIONS = [
        'ap-south-1',
        'us-east-1',
        'us-east-2',
        'us-west-2',
        'ap-southeast-1',
        'eu-west-1',
        'eu-central-1',
    ]

    print(f"\nScanning {len(REGIONS)} regions...")
    instances = get_all_instances(REGIONS)
    print(f"Total EC2 instances found : {len(instances)}")

    price_cache = {}

    # Pre-fetch Compute Optimizer
    print("\n[1/13] Fetching Compute Optimizer recommendations...")
    for region in REGIONS:
        for iid, rec in get_compute_optimizer_recommendations(region).items():
            price_cache[f"co_{iid}"] = rec

    # Check 2+4 — AMD & Graviton (main report)
    print("[2+4/13] Analyzing AMD / Graviton savings...")
    main_rows = build_report(instances, price_cache)

    # Check 1 — Spiky → Burstable
    print("[1/13] Checking spiky instances for burstable recommendation...")
    spiky_rows = check_spiky_instances(instances, price_cache)

    # Check 3 — Low utilization → downsize
    print("[3/13] Checking low utilization instances...")
    lowutil_rows = check_low_utilization_instances(instances, price_cache)

    # Check 5 — Unattached EBS
    print("[5/13] Checking unattached EBS volumes...")
    unattached_ebs = check_unattached_ebs_volumes(REGIONS)

    # Check 6 — EBS on stopped instances
    print("[6/13] Checking EBS attached to stopped instances...")
    stopped_ebs = check_ebs_attached_stopped_instances(REGIONS)

    # Check 7 — Low IOPS EBS
    print("[7/13] Checking EBS volumes with low IOPS...")
    low_iops_ebs = check_low_iops_ebs(REGIONS)

    # Check 8 — Orphan snapshots
    print("[8/13] Checking orphan EBS snapshots...")
    orphan_snaps = check_orphan_snapshots(REGIONS)

    # Check 9 — Unassociated EIPs
    print("[9/13] Checking unassociated Elastic IPs...")
    eip_rows = check_unassociated_eips(REGIONS)

    # Check 10 — CloudWatch log group expiry
    print("[10/13] Checking CloudWatch log group retention...")
    cw_log_rows = check_cloudwatch_log_groups(REGIONS)

    # Check 11 — Missing/insufficient alarms
    print("[11/13] Checking CloudWatch alarm coverage...")
    alarm_rows = check_cloudwatch_alarms(REGIONS)

    # Check 12 — S3 storage class
    print("[12/13] Checking S3 storage classes...")
    s3_rows = check_s3_storage_class(REGIONS)

    # Check 13 — RDS Reserved Instances
    print("[13/13] Checking RDS Reserved Instance coverage...")
    rds_ri_rows = check_rds_reserved_instances(REGIONS)

    # ── Write Excel ───────────────────────────────────────────────────
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename    = f"AWS_Cost_Optimization_{timestamp}.xlsx"
    output_path = os.path.join(get_downloads_path(), filename)

    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:

        # Summary sheet first
        summary_data = [
            {'Check_No': 1,  'Category': 'EC2',        'Description': 'Spiky → Burstable Instance',             'Items_Found': len(spiky_rows)},
            {'Check_No': 2,  'Category': 'EC2',        'Description': 'Intel → AMD Instance',                   'Items_Found': len([r for r in main_rows if r.get('Recommended_AMD_Type') not in ('N/A', None)])},
            {'Check_No': 3,  'Category': 'EC2',        'Description': 'Low Utilization → Downsize',             'Items_Found': len(lowutil_rows)},
            {'Check_No': 4,  'Category': 'EC2',        'Description': 'Intel → Graviton Instance',              'Items_Found': len([r for r in main_rows if r.get('Recommended_Graviton_Type') not in ('N/A', None)])},
            {'Check_No': 5,  'Category': 'EBS',        'Description': 'Unattached EBS Volumes',                 'Items_Found': len(unattached_ebs)},
            {'Check_No': 6,  'Category': 'EBS',        'Description': 'EBS on Stopped Instances',               'Items_Found': len(stopped_ebs)},
            {'Check_No': 7,  'Category': 'EBS',        'Description': 'EBS Low IOPS (<1 in 7 days)',            'Items_Found': len(low_iops_ebs)},
            {'Check_No': 8,  'Category': 'EBS',        'Description': 'Orphan Snapshots (deleted volumes)',     'Items_Found': len(orphan_snaps)},
            {'Check_No': 9,  'Category': 'Networking', 'Description': 'Unassociated Elastic IPs',               'Items_Found': len(eip_rows)},
            {'Check_No': 10, 'Category': 'CloudWatch', 'Description': 'Log Groups with No/Long Retention',      'Items_Found': len(cw_log_rows)},
            {'Check_No': 11, 'Category': 'CloudWatch', 'Description': 'Insufficient Alarms / No SNS',           'Items_Found': len(alarm_rows)},
            {'Check_No': 12, 'Category': 'S3',         'Description': 'Standard Storage → Cheaper Class',       'Items_Found': len(s3_rows)},
            {'Check_No': 13, 'Category': 'RDS',        'Description': 'RDS Instances without Reserved Instance', 'Items_Found': len(rds_ri_rows)},
        ]
        write_sheet(writer, pd.DataFrame(summary_data), 'Summary')

        # Individual sheets
        write_sheet(writer, pd.DataFrame(main_rows),      'EC2 AMD-Graviton Savings',  highlight=True)
        write_sheet(writer, pd.DataFrame(spiky_rows),     'EC2 Spiky-Burstable',       highlight=True)
        write_sheet(writer, pd.DataFrame(lowutil_rows),   'EC2 Low Util-Downsize',     highlight=True)
        write_sheet(writer, pd.DataFrame(unattached_ebs), 'EBS Unattached',            highlight=True)
        write_sheet(writer, pd.DataFrame(stopped_ebs),    'EBS on Stopped Instances',  highlight=True)
        write_sheet(writer, pd.DataFrame(low_iops_ebs),   'EBS Low IOPS',              highlight=True)
        write_sheet(writer, pd.DataFrame(orphan_snaps),   'EBS Orphan Snapshots',      highlight=True)
        write_sheet(writer, pd.DataFrame(eip_rows),       'Unassociated EIPs',         highlight=True)
        write_sheet(writer, pd.DataFrame(cw_log_rows),    'CW Log Retention',          highlight=True)
        write_sheet(writer, pd.DataFrame(alarm_rows),     'CW Insufficient Alarms')
        write_sheet(writer, pd.DataFrame(s3_rows),        'S3 Storage Class',          highlight=True)
        write_sheet(writer, pd.DataFrame(rds_ri_rows),    'RDS No Reserved Instance',  highlight=True)

    print(f"\n{'=' * 65}")
    print(f"  Report saved to: {output_path}")
    print(f"{'=' * 65}")
    for item in summary_data:
        print(f"  Check {item['Check_No']:2d} | {item['Category']:10s} | {item['Description']:45s} | {item['Items_Found']} items")
    print(f"{'=' * 65}")


if __name__ == "__main__":
    main()


# =============================================================
# ADDITIONAL COST CHECKS (Points 1,3,5,6,7,8,9)
# =============================================================

# Burstable instance equivalents for spiky workloads
BURSTABLE_MAP = {
    'm5': 't3', 'm5a': 't3a', 'm6i': 't3', 'm6a': 't3a',
    'c5': 't3', 'c5a': 't3a', 'c6i': 't3', 'c6a': 't3a',
    'r5': 't3', 'r6i': 't3', 'm4': 't3', 'c4': 't3',
}

# Downsize map: current_size -> smaller_size
DOWNSIZE_MAP = {
    '16xlarge': '8xlarge', '12xlarge': '8xlarge', '8xlarge': '4xlarge',
    '4xlarge': '2xlarge', '2xlarge': 'xlarge', 'xlarge': 'large',
    'large': 'medium', 'medium': 'small',
}


def check_spiky_instances(instances, price_cache):
    """Check instances with spiky CPU — suggest burstable types"""
    rows = []
    for inst in instances:
        region        = inst['region']
        instance_id   = inst['instance_id']
        instance_type = inst['instance_type']
        family        = get_instance_family(instance_type)
        size          = get_instance_size(instance_type)

        # Only suggest burstable if current is standard family
        burst_family = BURSTABLE_MAP.get(family)
        if not burst_family:
            continue

        burst_type = f"{burst_family}.{size}"

        current_price = price_cache.get(f"{instance_type}_{region}")
        if not current_price:
            price_cache[f"{instance_type}_{region}"] = get_ec2_price(instance_type, region)
            current_price = price_cache[f"{instance_type}_{region}"]

        burst_price = price_cache.get(f"{burst_type}_{region}")
        if not burst_price:
            price_cache[f"{burst_type}_{region}"] = get_ec2_price(burst_type, region)
            burst_price = price_cache[f"{burst_type}_{region}"]

        if not current_price or not burst_price:
            continue

        hours_month   = 730
        saving_month  = round((current_price - burst_price) * hours_month, 2)
        saving_year   = round(saving_month * 12, 2)

        if saving_month <= 0:
            continue

        rows.append({
            'Region'                        : region,
            'Instance_ID'                   : instance_id,
            'Instance_Name'                 : inst['name'],
            'Recommendation'                : 'Switch to Burstable Instance (Spiky Workload)',
            'Current_Type'                  : instance_type,
            'Current_Price_Per_Hr'          : f"${current_price:.4f}",
            'Current_Monthly_Cost'          : f"${round(current_price * hours_month, 2)}",
            'Recommended_Type'              : burst_type,
            'Recommended_Price_Per_Hr'      : f"${burst_price:.4f}",
            'Recommended_Monthly_Cost'      : f"${round(burst_price * hours_month, 2)}",
            'Monthly_Saving'                : f"${saving_month}",
            'Yearly_Saving'                 : f"${saving_year}",
            'Action'                        : f'Change from {instance_type} to {burst_type}',
        })
    return rows


def check_low_utilization_instances(instances, price_cache):
    """Suggest downsizing for low utilization instances"""
    rows = []
    for inst in instances:
        region        = inst['region']
        instance_id   = inst['instance_id']
        instance_type = inst['instance_type']
        family        = get_instance_family(instance_type)
        size          = get_instance_size(instance_type)

        smaller_size = DOWNSIZE_MAP.get(size)
        if not smaller_size:
            continue

        smaller_type = f"{family}.{smaller_size}"

        current_price = price_cache.get(f"{instance_type}_{region}")
        if not current_price:
            price_cache[f"{instance_type}_{region}"] = get_ec2_price(instance_type, region)
            current_price = price_cache[f"{instance_type}_{region}"]

        smaller_price = price_cache.get(f"{smaller_type}_{region}")
        if not smaller_price:
            price_cache[f"{smaller_type}_{region}"] = get_ec2_price(smaller_type, region)
            smaller_price = price_cache[f"{smaller_type}_{region}"]

        if not current_price or not smaller_price:
            continue

        hours_month  = 730
        saving_month = round((current_price - smaller_price) * hours_month, 2)
        saving_year  = round(saving_month * 12, 2)

        if saving_month <= 0:
            continue

        rows.append({
            'Region'                   : region,
            'Instance_ID'              : instance_id,
            'Instance_Name'            : inst['name'],
            'Recommendation'           : 'Low Utilization — Downsize Instance',
            'Current_Type'             : instance_type,
            'Current_Price_Per_Hr'     : f"${current_price:.4f}",
            'Current_Monthly_Cost'     : f"${round(current_price * hours_month, 2)}",
            'Recommended_Type'         : smaller_type,
            'Recommended_Price_Per_Hr' : f"${smaller_price:.4f}",
            'Recommended_Monthly_Cost' : f"${round(smaller_price * hours_month, 2)}",
            'Monthly_Saving'           : f"${saving_month}",
            'Yearly_Saving'            : f"${saving_year}",
            'Action'                   : f'Downsize from {instance_type} to {smaller_type}',
        })
    return rows


def check_unattached_ebs_volumes(regions):
    """Find EBS volumes not attached to any instance with their cost"""
    rows = []
    # EBS pricing per GB/month approx
    EBS_PRICE = {'gp3': 0.08, 'gp2': 0.10, 'io1': 0.125, 'io2': 0.125,
                 'st1': 0.045, 'sc1': 0.025, 'standard': 0.05}

    for region in regions:
        try:
            ec2 = boto3.client('ec2', region_name=region)
            paginator = ec2.get_paginator('describe_volumes')
            for page in paginator.paginate(Filters=[{'Name': 'status', 'Values': ['available']}]):
                for vol in page['Volumes']:
                    tags     = {t['Key']: t['Value'] for t in vol.get('Tags', [])}
                    vol_type = vol.get('VolumeType', 'gp2')
                    size_gb  = vol.get('Size', 0)
                    price_gb = EBS_PRICE.get(vol_type, 0.08)
                    monthly_cost = round(size_gb * price_gb, 2)

                    rows.append({
                        'Region'            : region,
                        'Volume_ID'         : vol['VolumeId'],
                        'Volume_Name'       : tags.get('Name', ''),
                        'Volume_Type'       : vol_type,
                        'Size_GB'           : size_gb,
                        'State'             : vol['State'],
                        'Recommendation'    : 'Unattached EBS Volume — Delete to save cost',
                        'Monthly_Cost'      : f"${monthly_cost}",
                        'Yearly_Cost'       : f"${round(monthly_cost * 12, 2)}",
                        'Created'           : str(vol.get('CreateTime', ''))[:10],
                        'Action'            : 'Delete volume or snapshot and delete',
                    })
        except Exception as e:
            print(f"  [WARN] EBS unattached check {region}: {str(e)}")
    return rows


def check_ebs_attached_stopped_instances(regions):
    """Find EBS volumes attached to stopped instances"""
    rows = []
    EBS_PRICE = {'gp3': 0.08, 'gp2': 0.10, 'io1': 0.125, 'io2': 0.125,
                 'st1': 0.045, 'sc1': 0.025, 'standard': 0.05}

    for region in regions:
        try:
            ec2 = boto3.client('ec2', region_name=region)
            # Get stopped instances
            stopped = {}
            pag = ec2.get_paginator('describe_instances')
            for page in pag.paginate(Filters=[{'Name': 'instance-state-name', 'Values': ['stopped']}]):
                for res in page['Reservations']:
                    for inst in res['Instances']:
                        tags = {t['Key']: t['Value'] for t in inst.get('Tags', [])}
                        stopped[inst['InstanceId']] = tags.get('Name', '')

            if not stopped:
                continue

            # Get volumes attached to stopped instances
            pag2 = ec2.get_paginator('describe_volumes')
            for page in pag2.paginate(Filters=[{'Name': 'status', 'Values': ['in-use']}]):
                for vol in page['Volumes']:
                    for attachment in vol.get('Attachments', []):
                        iid = attachment.get('InstanceId', '')
                        if iid in stopped:
                            tags     = {t['Key']: t['Value'] for t in vol.get('Tags', [])}
                            vol_type = vol.get('VolumeType', 'gp2')
                            size_gb  = vol.get('Size', 0)
                            price_gb = EBS_PRICE.get(vol_type, 0.08)
                            monthly_cost = round(size_gb * price_gb, 2)
                            rows.append({
                                'Region'             : region,
                                'Volume_ID'          : vol['VolumeId'],
                                'Volume_Name'        : tags.get('Name', ''),
                                'Attached_Instance'  : iid,
                                'Instance_Name'      : stopped[iid],
                                'Volume_Type'        : vol_type,
                                'Size_GB'            : size_gb,
                                'Recommendation'     : 'Volume attached to STOPPED instance — remove to save',
                                'Monthly_Cost'       : f"${monthly_cost}",
                                'Yearly_Cost'        : f"${round(monthly_cost * 12, 2)}",
                                'Action'             : 'Snapshot volume then delete, or terminate instance',
                            })
        except Exception as e:
            print(f"  [WARN] EBS stopped instance check {region}: {str(e)}")
    return rows


def check_low_iops_ebs(regions):
    """Find EBS volumes with <1 IOPS utilization"""
    rows = []
    EBS_PRICE = {'gp3': 0.08, 'gp2': 0.10, 'io1': 0.125, 'io2': 0.125,
                 'st1': 0.045, 'sc1': 0.025, 'standard': 0.05}

    for region in regions:
        try:
            ec2 = boto3.client('ec2', region_name=region)
            cw  = boto3.client('cloudwatch', region_name=region)
            pag = ec2.get_paginator('describe_volumes')
            for page in pag.paginate(Filters=[{'Name': 'status', 'Values': ['in-use']}]):
                for vol in page['Volumes']:
                    try:
                        end   = datetime.utcnow()
                        start = end - timedelta(days=7)
                        metrics = cw.get_metric_statistics(
                            Namespace='AWS/EBS', MetricName='VolumeReadOps',
                            Dimensions=[{'Name': 'VolumeId', 'Value': vol['VolumeId']}],
                            StartTime=start, EndTime=end, Period=604800,
                            Statistics=['Average']
                        )
                        avg_iops = 0
                        if metrics['Datapoints']:
                            avg_iops = metrics['Datapoints'][0].get('Average', 0)

                        if avg_iops < 1:
                            tags     = {t['Key']: t['Value'] for t in vol.get('Tags', [])}
                            vol_type = vol.get('VolumeType', 'gp2')
                            size_gb  = vol.get('Size', 0)
                            price_gb = EBS_PRICE.get(vol_type, 0.08)
                            monthly_cost = round(size_gb * price_gb, 2)
                            rows.append({
                                'Region'          : region,
                                'Volume_ID'       : vol['VolumeId'],
                                'Volume_Name'     : tags.get('Name', ''),
                                'Volume_Type'     : vol_type,
                                'Size_GB'         : size_gb,
                                'Avg_IOPS_7Days'  : round(avg_iops, 4),
                                'Recommendation'  : 'Less than 1 IOPS in 7 days — likely unused',
                                'Monthly_Cost'    : f"${monthly_cost}",
                                'Yearly_Cost'     : f"${round(monthly_cost * 12, 2)}",
                                'Action'          : 'Snapshot and delete volume if not required',
                            })
                    except Exception:
                        pass
        except Exception as e:
            print(f"  [WARN] Low IOPS EBS check {region}: {str(e)}")
    return rows


def check_orphan_snapshots(regions):
    """Find EBS snapshots from deleted volumes"""
    rows = []
    # EBS snapshot pricing ~$0.05/GB/month
    SNAP_PRICE_PER_GB = 0.05

    for region in regions:
        try:
            ec2      = boto3.client('ec2', region_name=region)
            sts      = boto3.client('sts')
            acct_id  = sts.get_caller_identity()['Account']

            pag = ec2.get_paginator('describe_snapshots')
            for page in pag.paginate(OwnerIds=[acct_id]):
                for snap in page['Snapshots']:
                    vol_id = snap.get('VolumeId', '')
                    if not vol_id or vol_id == 'vol-ffffffff':
                        tags     = {t['Key']: t['Value'] for t in snap.get('Tags', [])}
                        size_gb  = snap.get('VolumeSize', 0)
                        monthly_cost = round(size_gb * SNAP_PRICE_PER_GB, 2)
                        rows.append({
                            'Region'         : region,
                            'Snapshot_ID'    : snap['SnapshotId'],
                            'Snapshot_Name'  : tags.get('Name', ''),
                            'Size_GB'        : size_gb,
                            'Start_Time'     : str(snap.get('StartTime', ''))[:10],
                            'Description'    : snap.get('Description', ''),
                            'Recommendation' : 'Orphan snapshot from deleted volume',
                            'Monthly_Cost'   : f"${monthly_cost}",
                            'Yearly_Cost'    : f"${round(monthly_cost * 12, 2)}",
                            'Action'         : 'Delete if no longer needed or use DLM policy',
                        })
        except Exception as e:
            print(f"  [WARN] Orphan snapshot check {region}: {str(e)}")
    return rows


def check_unassociated_eips(regions):
    """Find Elastic IPs not associated with any instance"""
    rows = []
    # Unassociated EIP costs ~$0.005/hr = $3.65/month
    EIP_MONTHLY_COST = 3.65

    for region in regions:
        try:
            ec2  = boto3.client('ec2', region_name=region)
            resp = ec2.describe_addresses()
            for addr in resp.get('Addresses', []):
                if not addr.get('AssociationId'):
                    tags = {t['Key']: t['Value'] for t in addr.get('Tags', [])}
                    rows.append({
                        'Region'         : region,
                        'Elastic_IP'     : addr.get('PublicIp', ''),
                        'Allocation_ID'  : addr.get('AllocationId', ''),
                        'Name'           : tags.get('Name', ''),
                        'Recommendation' : 'Unassociated Elastic IP — release to save cost',
                        'Monthly_Cost'   : f"${EIP_MONTHLY_COST}",
                        'Yearly_Cost'    : f"${round(EIP_MONTHLY_COST * 12, 2)}",
                        'Action'         : 'Release Elastic IP if not needed',
                    })
        except Exception as e:
            print(f"  [WARN] EIP check {region}: {str(e)}")
    return rows


def check_cloudwatch_log_groups(regions):
    """Check CloudWatch log groups with no retention policy (never expire = cost waste)"""
    rows = []
    # CW Logs ~$0.03/GB stored/month
    CW_PRICE_PER_GB = 0.03

    for region in regions:
        try:
            logs = boto3.client('logs', region_name=region)
            pag  = logs.get_paginator('describe_log_groups')
            for page in pag.paginate():
                for lg in page.get('logGroups', []):
                    retention = lg.get('retentionInDays')
                    stored_bytes = lg.get('storedBytes', 0)
                    stored_gb    = round(stored_bytes / (1024 ** 3), 3)
                    monthly_cost = round(stored_gb * CW_PRICE_PER_GB, 4)

                    if not retention:  # Never expires
                        rows.append({
                            'Region'          : region,
                            'Log_Group'       : lg.get('logGroupName', ''),
                            'Retention_Days'  : 'Never Expires',
                            'Stored_GB'       : stored_gb,
                            'Monthly_Cost_Est': f"${monthly_cost}",
                            'Yearly_Cost_Est' : f"${round(monthly_cost * 12, 4)}",
                            'Recommendation'  : 'Set retention policy to avoid indefinite log storage cost',
                            'Suggested_Action': 'Set retention to 30, 60, or 90 days based on compliance needs',
                        })
                    elif retention > 90:  # Long retention
                        rows.append({
                            'Region'          : region,
                            'Log_Group'       : lg.get('logGroupName', ''),
                            'Retention_Days'  : retention,
                            'Stored_GB'       : stored_gb,
                            'Monthly_Cost_Est': f"${monthly_cost}",
                            'Yearly_Cost_Est' : f"${round(monthly_cost * 12, 4)}",
                            'Recommendation'  : f'Retention is {retention} days — consider reducing',
                            'Suggested_Action': 'Review if long retention is required; reduce to 30-90 days',
                        })
        except Exception as e:
            print(f"  [WARN] CloudWatch logs check {region}: {str(e)}")
    return rows


def check_cloudwatch_alarms(regions):
    """Check for missing or insufficient CloudWatch alarms"""
    rows = []
    for region in regions:
        try:
            cw  = boto3.client('cloudwatch', region_name=region)
            ec2 = boto3.client('ec2', region_name=region)

            # Get all alarms
            all_alarms = []
            pag = cw.get_paginator('describe_alarms')
            for page in pag.paginate():
                all_alarms.extend(page.get('MetricAlarms', []))

            # Check instances without alarms
            alarm_instances = set()
            for alarm in all_alarms:
                for dim in alarm.get('Dimensions', []):
                    if dim['Name'] == 'InstanceId':
                        alarm_instances.add(dim['Value'])

            pag2 = ec2.get_paginator('describe_instances')
            for page in pag2.paginate(Filters=[{'Name': 'instance-state-name', 'Values': ['running']}]):
                for res in page['Reservations']:
                    for inst in res['Instances']:
                        iid  = inst['InstanceId']
                        tags = {t['Key']: t['Value'] for t in inst.get('Tags', [])}
                        if iid not in alarm_instances:
                            rows.append({
                                'Region'         : region,
                                'Resource_ID'    : iid,
                                'Resource_Name'  : tags.get('Name', ''),
                                'Resource_Type'  : 'EC2 Instance',
                                'Recommendation' : 'No CloudWatch alarms configured for this instance',
                                'Risk'           : 'Issues may go undetected — no alerting',
                                'Action'         : 'Create CPU, Memory, StatusCheck alarms with SNS notification',
                            })

            # Check alarms with no SNS action
            for alarm in all_alarms:
                actions = alarm.get('AlarmActions', []) + alarm.get('OKActions', [])
                has_sns = any('sns' in a.lower() for a in actions)
                if not has_sns:
                    rows.append({
                        'Region'         : region,
                        'Resource_ID'    : alarm.get('AlarmName', ''),
                        'Resource_Name'  : alarm.get('AlarmDescription', ''),
                        'Resource_Type'  : 'CloudWatch Alarm',
                        'Recommendation' : 'Alarm has no SNS notification action',
                        'Risk'           : 'Alarm fires but no one is notified',
                        'Action'         : 'Add SNS topic to AlarmActions for email/pager notification',
                    })

        except Exception as e:
            print(f"  [WARN] CW alarm check {region}: {str(e)}")
    return rows


def check_s3_storage_class(regions):
    """Check S3 buckets using Standard storage that could use cheaper tiers"""
    rows = []
    # Pricing per GB/month
    S3_PRICES = {
        'STANDARD'            : 0.023,
        'STANDARD_IA'         : 0.0125,
        'ONEZONE_IA'          : 0.01,
        'INTELLIGENT_TIERING' : 0.023,
        'GLACIER_IR'          : 0.004,
        'GLACIER'             : 0.0036,
        'DEEP_ARCHIVE'        : 0.00099,
    }
    try:
        s3 = boto3.client('s3')
        cw = boto3.client('cloudwatch', region_name='us-east-1')
        resp = s3.list_buckets()

        for bucket in resp.get('Buckets', []):
            bucket_name = bucket['Name']
            try:
                # Get bucket region
                loc = s3.get_bucket_location(Bucket=bucket_name)
                bucket_region = loc['LocationConstraint'] or 'us-east-1'

                # Get bucket size from CloudWatch Storage metrics
                end   = datetime.utcnow()
                start = end - timedelta(days=2)
                cw_region = boto3.client('cloudwatch', region_name=bucket_region)
                metrics = cw_region.get_metric_statistics(
                    Namespace='AWS/S3', MetricName='BucketSizeBytes',
                    Dimensions=[
                        {'Name': 'BucketName',  'Value': bucket_name},
                        {'Name': 'StorageType', 'Value': 'StandardStorage'}
                    ],
                    StartTime=start, EndTime=end,
                    Period=86400, Statistics=['Average']
                )

                if not metrics['Datapoints']:
                    continue

                size_bytes = metrics['Datapoints'][-1].get('Average', 0)
                size_gb    = round(size_bytes / (1024 ** 3), 2)
                if size_gb < 1:
                    continue

                current_price   = S3_PRICES['STANDARD']
                ia_price        = S3_PRICES['STANDARD_IA']
                glacier_price   = S3_PRICES['GLACIER_IR']

                current_monthly = round(size_gb * current_price, 2)
                ia_monthly      = round(size_gb * ia_price, 2)
                glacier_monthly = round(size_gb * glacier_price, 2)

                ia_saving      = round(current_monthly - ia_monthly, 2)
                glacier_saving = round(current_monthly - glacier_monthly, 2)

                rows.append({
                    'Region'                          : bucket_region,
                    'Bucket_Name'                     : bucket_name,
                    'Current_Storage_Class'           : 'STANDARD',
                    'Size_GB'                         : size_gb,
                    'Current_Monthly_Cost'            : f"${current_monthly}",
                    'Current_Yearly_Cost'             : f"${round(current_monthly * 12, 2)}",
                    'Recommended_Class_1'             : 'STANDARD_IA (Infrequent Access)',
                    'Standard_IA_Monthly_Cost'        : f"${ia_monthly}",
                    'Standard_IA_Monthly_Saving'      : f"${ia_saving}",
                    'Standard_IA_Yearly_Saving'       : f"${round(ia_saving * 12, 2)}",
                    'Recommended_Class_2'             : 'GLACIER_IR (Instant Retrieval)',
                    'Glacier_IR_Monthly_Cost'         : f"${glacier_monthly}",
                    'Glacier_IR_Monthly_Saving'       : f"${glacier_saving}",
                    'Glacier_IR_Yearly_Saving'        : f"${round(glacier_saving * 12, 2)}",
                    'Recommendation'                  : 'Move infrequently accessed data to cheaper storage class',
                    'Action'                          : 'Enable S3 Intelligent-Tiering or add Lifecycle policy',
                })
            except Exception:
                pass
    except Exception as e:
        print(f"  [WARN] S3 storage class check: {str(e)}")
    return rows


def check_rds_reserved_instances(regions):
    """Check RDS instances without Reserved Instance coverage"""
    rows = []
    for region in regions:
        try:
            rds = boto3.client('rds', region_name=region)
            ce  = boto3.client('ce',  region_name='us-east-1')

            # Get all RDS instances
            pag = rds.get_paginator('describe_db_instances')
            all_instances = []
            for page in pag.paginate():
                all_instances.extend(page.get('DBInstances', []))

            if not all_instances:
                continue

            # Get reserved instances
            reserved_resp = rds.describe_reserved_db_instances()
            reserved = reserved_resp.get('ReservedDBInstances', [])
            reserved_types = {r['DBInstanceClass'] for r in reserved
                              if r['State'] == 'active'}

            for db in all_instances:
                db_id    = db['DBInstanceIdentifier']
                db_class = db['DBInstanceClass']
                engine   = db['Engine']
                status   = db['DBInstanceStatus']

                if status != 'available':
                    continue

                has_ri = db_class in reserved_types

                # Get on-demand monthly cost estimate from Cost Explorer
                end   = datetime.now().date().replace(day=1)
                start = (end - timedelta(days=30)).replace(day=1)
                try:
                    cost_resp = ce.get_cost_and_usage(
                        TimePeriod={'Start': str(start), 'End': str(end)},
                        Granularity='MONTHLY',
                        Filter={
                            'And': [
                                {'Dimensions': {'Key': 'SERVICE',     'Values': ['Amazon Relational Database Service']}},
                                {'Dimensions': {'Key': 'RESOURCE_ID', 'Values': [db_id]}}
                            ]
                        },
                        Metrics=['UnblendedCost']
                    )
                    monthly_cost = 0.0
                    for r in cost_resp.get('ResultsByTime', []):
                        for g in r.get('Groups', []):
                            monthly_cost += float(g['Metrics']['UnblendedCost']['Amount'])
                    if not monthly_cost and cost_resp.get('ResultsByTime'):
                        total = cost_resp['ResultsByTime'][0].get('Total', {})
                        monthly_cost = float(total.get('UnblendedCost', {}).get('Amount', 0))
                except Exception:
                    monthly_cost = 0.0

                # RI saves approx 30-40% on 1yr, 50-60% on 3yr
                ri_1yr_saving  = round(monthly_cost * 0.35 * 12, 2)
                ri_3yr_saving  = round(monthly_cost * 0.55 * 36, 2)

                if not has_ri:
                    rows.append({
                        'Region'                    : region,
                        'DB_Instance_ID'            : db_id,
                        'DB_Class'                  : db_class,
                        'Engine'                    : engine,
                        'Multi_AZ'                  : db.get('MultiAZ', False),
                        'Has_Reserved_Instance'     : 'No',
                        'Current_Monthly_Cost'      : f"${round(monthly_cost, 2)}",
                        'Current_Yearly_Cost'       : f"${round(monthly_cost * 12, 2)}",
                        'Est_1yr_RI_Saving'         : f"${ri_1yr_saving} (~35% saving)",
                        'Est_3yr_RI_Saving'         : f"${ri_3yr_saving} (~55% saving)",
                        'Recommendation'            : 'Purchase Reserved Instance to reduce RDS cost',
                        'Action'                    : f'Purchase 1yr or 3yr RI for {db_class} in {region}',
                    })
        except Exception as e:
            print(f"  [WARN] RDS RI check {region}: {str(e)}")
    return rows
