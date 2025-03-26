import os

import pydash
from celery import shared_task

from dashboard.data.adherence import GuidelineAdherenceCheckAdult1L, GuidelineAdherenceCheckPaed1L
from dashboard.data.adherence import GuidelineAdherenceCheckAdult2L
from dashboard.data.blanks import BlanksQualityCheck, MultipleCheck, WebBasedCheck, IsReportingCheck
from dashboard.data.consumption_patients import ConsumptionAndPatientsQualityCheck
from dashboard.data.cycles import BalancesMatchCheck, StablePatientVolumesCheck, WarehouseFulfillmentCheck, StableConsumptionCheck, OrdersOverTimeCheck
from dashboard.data.free_form_report import FreeFormReport
from dashboard.data.negatives import NegativeNumbersQualityCheck
from dashboard.data.nn import NNRTICURRENTADULTSCheck, NNRTINewAdultsCheck, NNRTINEWPAEDCheck
from dashboard.data.nn import NNRTICURRENTPAEDCheck
from dashboard.data.utils import facility_has_single_order, timeit
from dashboard.helpers import YES, get_prev_cycle, WEB, F1, F2, F3, DEFAULT, NO, NAME, C_COUNT, A_COUNT, P_COUNT, WEB_PAPER, C_RECORDS, A_RECORDS, P_RECORDS
from dashboard.models import Score, Cycle, Consumption, AdultPatientsRecord, PAEDPatientsRecord, MultipleOrderFacility


@timeit
def persist_consumption(report):
    persist_records(report.locs, Consumption, report.cs, report.cycle)


@timeit
def persist_adult_records(report):
    persist_records(report.locs, AdultPatientsRecord, report.ads, report.cycle)


@timeit
def persist_paed_records(report):
    persist_records(report.locs, PAEDPatientsRecord, report.pds, report.cycle)


def persist_records(locs, model, collection, cycle):
    adult_records = []
    for facility in locs:
        facility_name = facility.get('name', None)
        records = collection.get(facility_name)
        ip = facility.get('IP', None)
        district = facility.get('District', None)
        warehouse = facility.get('Warehouse', None)
        for r in records:
            c = model(
                name=facility_name,
                ip=ip,
                district=district,
                warehouse=warehouse,
                cycle=cycle,
                **r
            )
            adult_records.append(c)
    model.objects.filter(cycle=cycle).delete()
    model.objects.bulk_create(adult_records)


def build_mof(report):
    def func(facility):
        facility_name = facility.get('name', None)
        ip = facility.get('IP', None)
        district = facility.get('District', None)
        warehouse = facility.get('Warehouse', None)
        return MultipleOrderFacility(
            cycle=report.cycle,
            name=facility_name,
            ip=ip,
            district=district,
            warehouse=warehouse)

    return func


@timeit
def persist_multiple_order_records(report):
    facilities_with_multiple_orders = pydash.reject(report.locs, lambda f: facility_has_single_order(f))
    all = pydash.collect(facilities_with_multiple_orders, build_mof(report))
    MultipleOrderFacility.objects.filter(cycle=report.cycle).delete()
    MultipleOrderFacility.objects.bulk_create(all)


@timeit
def calculate_scores_for_checks_in_cycle(report):
    run_checks(report)
    persist_scores(report)
    persist_consumption(report)
    persist_adult_records(report)
    persist_paed_records(report)
    persist_multiple_order_records(report)


@timeit
def run_checks(report):
    other_report = get_report_for_other_cycle(report)
    checks = [
        BlanksQualityCheck(),
        NegativeNumbersQualityCheck(),
        ConsumptionAndPatientsQualityCheck(),
        MultipleCheck(),
        WebBasedCheck(),
        IsReportingCheck(),
        GuidelineAdherenceCheckAdult1L(),
        GuidelineAdherenceCheckAdult2L(),
        GuidelineAdherenceCheckPaed1L(),
        NNRTICURRENTADULTSCheck(),
        NNRTICURRENTPAEDCheck(),
        NNRTINewAdultsCheck(),
        NNRTINEWPAEDCheck(),
        BalancesMatchCheck(),
        OrdersOverTimeCheck(),
        StableConsumptionCheck(),
        WarehouseFulfillmentCheck(),
        StablePatientVolumesCheck()
    ]
    for facility in report.locs:
        facility_data = build_facility_data(facility, report)
        other_facility_data = build_facility_data(facility, other_report)
        for check in checks:
            for combination in check.combinations:
                facility['scores'][check.test][combination[NAME]] = check.for_each_facility(facility_data, combination, other_facility_data)


def build_facility_data(facility, report):
    facility_data = {}
    facility_name = facility[NAME]
    c_records = report.cs[facility_name]
    a_records = report.ads[facility_name]
    p_records = report.pds[facility_name]
    facility_data[C_COUNT] = len(c_records)
    facility_data[A_COUNT] = len(a_records)
    facility_data[P_COUNT] = len(p_records)
    facility_data[WEB_PAPER] = facility[WEB_PAPER].strip()
    facility_data[C_RECORDS] = c_records
    facility_data[A_RECORDS] = a_records
    facility_data[P_RECORDS] = p_records
    facility_data['Multiple'] = facility['Multiple']
    facility_data['status'] = facility['status']
    facility_data[NAME] = facility_name
    return facility_data


@timeit
def get_report_for_other_cycle(report):
    prev_cycle_title = get_prev_cycle(report.cycle)
    other_report = FreeFormReport(None, prev_cycle_title)
    if Cycle.objects.filter(title=prev_cycle_title).exists():
        prev_cycle = Cycle.objects.get(title=prev_cycle_title)
        other_report = other_report.build_form_db(prev_cycle)
    return other_report


@timeit
def persist_scores(report):
    scores = list()
    mapping = {
        F1: {"pass": "f1_pass_count", "fail": "f1_fail_count"},
        F2: {"pass": "f2_pass_count", "fail": "f2_fail_count"},
        F3: {"pass": "f3_pass_count", "fail": "f3_fail_count"},
        DEFAULT: {"pass": "default_pass_count", "fail": "default_fail_count"},
    }
    for facility in report.locs:
        s = Score(
            name=facility.get('name', None),
            ip=facility.get('IP', None),
            district=facility.get('District', None),
            warehouse=facility.get('Warehouse', None),
            cycle=report.cycle)
        for key, value in facility['scores'].items():
            setattr(s, key, value)
            for f, result in value.items():
                formulation_mapping = mapping.get(f)
                if result in [YES, WEB]:
                    model_field = formulation_mapping.get("pass")
                    s.__dict__[model_field] += 1
                elif result in [NO]:
                    model_field = formulation_mapping.get("fail")
                    s.__dict__[model_field] += 1

        scores.append(s)
    Score.objects.filter(cycle=report.cycle).delete()
    Score.objects.bulk_create(scores)


@shared_task
def import_general_report(path, cycle):
    report = load_report(cycle, path)
    save_report(report)
    os.remove(path)
    calculate_scores_for_checks_in_cycle(report)


@timeit
def save_report(report):
    report.save()


@timeit
def load_report(cycle, path):
    report = FreeFormReport(path, cycle).load()
    return report


@shared_task
@timeit
def update_checks(cycle_ids):
    data = Cycle.objects.filter(id_in=cycle_ids).all()
    for cycle in data:
        report = FreeFormReport(None, cycle.title).build_form_db(cycle)
        calculate_scores_for_checks_in_cycle(report)
