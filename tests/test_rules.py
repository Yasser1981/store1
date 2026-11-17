"""اختبار قواعد العمل: الحالة، التدوير، رقم أمر العمل، والتحقق من البيانات."""

from datetime import date

from conftest import TODAY, make_order

from workorders.constants import Status
from workorders.models import compute_status, rolled_to_year
from workorders.validation import allowed_years, number_conflicts, validate


def fields(issues):
    return {i.field for i in issues}


def started(**kw):
    base = dict(submit_no="100", submit_date=date(2026, 2, 1), response="approved", response_no="200",
                response_date=date(2026, 3, 1), committee_head_id=1, start_no="300",
                start_date=date(2026, 4, 1))
    base.update(kw)
    return make_order(**base)


# ----------------------------------------------------------------------
def test_status_sequence():
    o = make_order()
    assert compute_status(o) == Status.DRAFT
    o.submit_no, o.submit_date = "1", date(2026, 1, 5)
    assert compute_status(o) == Status.SUBMITTED
    o.response = "approved"
    assert compute_status(o) == Status.APPROVED
    o.start_no, o.start_date = "2", date(2026, 2, 5)
    assert compute_status(o) == Status.STARTED
    o.close_no, o.close_date = "3", date(2026, 6, 5)
    assert compute_status(o) == Status.CLOSED


def test_status_rejected_and_cancelled():
    assert compute_status(make_order(submit_no="1", response="rejected")) == Status.REJECTED
    assert compute_status(started(cancel_no="9", cancel_date=date(2026, 5, 1))) == Status.CANCELLED
    assert compute_status(make_order(cancel_no="9", cancel_date=date(2026, 5, 1))) == Status.CANCELLED


def test_rollover_based_on_start_year():
    o = started()
    assert rolled_to_year(o, date(2026, 12, 31)) is None
    assert rolled_to_year(o, date(2027, 1, 1)) == 2027
    assert rolled_to_year(o, date(2028, 6, 1)) == 2028
    o.close_no, o.close_date = "5", date(2026, 12, 1)
    assert rolled_to_year(o, date(2028, 6, 1)) is None
    o.close_date = date(2027, 3, 1)
    assert rolled_to_year(o, date(2028, 6, 1)) == 2027
    assert rolled_to_year(make_order(), date(2030, 1, 1)) is None  # غير مباشر به: لا تدوير


def test_allowed_years():
    assert allowed_years(date(2026, 11, 17)) == [2026, 2027]
    assert allowed_years(date(2028, 1, 1)) == [2026, 2027, 2028, 2029]


# ---------------------------------------------------------------- رقم أمر العمل
def test_number_same_year_any_type_conflicts():
    existing = make_order(id=1, order_no=10, order_type="operational")
    new = make_order(order_no=10, order_type="trust")
    assert number_conflicts(new, [existing])


def test_number_reuse_blocked_while_older_open():
    old = make_order(id=1, order_no=10, order_year=2025, submit_no="1", submit_date=date(2025, 3, 1))
    new = make_order(order_no=10, order_year=2026)
    assert number_conflicts(new, [old])


def test_number_reuse_allowed_when_older_finished():
    closed = started(id=1, order_no=10, order_year=2025, close_no="4", close_date=date(2026, 5, 1))
    rejected = make_order(id=2, order_no=11, order_year=2025, submit_no="1", response="rejected")
    cancelled = make_order(id=3, order_no=12, order_year=2025, cancel_no="1", cancel_date=date(2025, 4, 1))
    assert not number_conflicts(make_order(order_no=10, order_year=2026), [closed])
    assert not number_conflicts(make_order(order_no=11, order_year=2026), [rejected])
    assert not number_conflicts(make_order(order_no=12, order_year=2026), [cancelled])


def test_older_order_cannot_be_reopened_if_number_reused_later():
    later = make_order(id=2, order_no=10, order_year=2027)
    older = make_order(id=1, order_no=10, order_year=2026)  # مفتوح
    assert number_conflicts(older, [later])
    older_closed = started(id=1, order_no=10, order_year=2026, close_no="5", close_date=date(2026, 9, 1))
    assert not number_conflicts(older_closed, [later])


def test_number_does_not_conflict_with_itself():
    o = make_order(id=5, order_no=10)
    assert not number_conflicts(o, [make_order(id=5, order_no=10)])


# ---------------------------------------------------------------- التحقق
def test_required_basic_fields():
    o = make_order(order_no=None, order_type=None, project_name="  ", work_type=None)
    f = fields(validate(o, [], TODAY))
    assert {"order_no", "order_type", "project_name", "work_type"} <= f


def test_network_conditional_fields():
    f = fields(validate(make_order(work_type="network"), [], TODAY))
    assert "voltage" in f
    f = fields(validate(make_order(work_type="network", voltage="33"), [], TODAY))
    assert "tech_class" in f and "sector_id" not in f
    f = fields(validate(make_order(work_type="network", voltage="11"), [], TODAY))
    assert {"tech_class", "sector_id"} <= f
    f = fields(validate(make_order(work_type="network", voltage="lv"), [], TODAY))
    assert "sector_id" in f and "tech_class" not in f
    ok = make_order(work_type="network", voltage="11", tech_class="new", sector_id=1)
    assert validate(ok, [], TODAY) == []


def test_book_number_and_date_together():
    f = fields(validate(make_order(submit_no="12"), [], TODAY))
    assert "submit_date" in f
    f = fields(validate(make_order(submit_date=date(2026, 1, 1)), [], TODAY))
    assert "submit_no" in f


def test_response_requires_submission():
    o = make_order(response="approved", response_no="5", response_date=date(2026, 3, 1))
    assert "response" in fields(validate(o, [], TODAY))


def test_dates_must_follow_sequence():
    o = started(response_date=date(2026, 1, 1))  # قبل تاريخ الرفع
    assert "response_date" in fields(validate(o, [], TODAY))
    o = started(start_date=date(2026, 2, 15))  # قبل تاريخ الموافقة
    assert "start_date" in fields(validate(o, [], TODAY))
    o = started(close_no="7", close_date=date(2026, 3, 15))  # قبل تاريخ المباشرة
    assert "close_date" in fields(validate(o, [], TODAY))


def test_future_dates_rejected():
    o = make_order(submit_no="1", submit_date=date(2026, 11, 18))
    assert "submit_date" in fields(validate(o, [], TODAY))


def test_start_requires_head_and_approval():
    o = started(committee_head_id=None)
    assert "committee_head" in fields(validate(o, [], TODAY))
    o = started(response="pending", response_no=None, response_date=None)
    assert "start_no" in fields(validate(o, [], TODAY))


def test_close_requires_start():
    o = make_order(submit_no="1", submit_date=date(2026, 1, 1), response="approved", response_no="2",
                   response_date=date(2026, 2, 1), close_no="3", close_date=date(2026, 3, 1))
    assert "close_no" in fields(validate(o, [], TODAY))


def test_rejected_cannot_have_execution():
    o = started(response="rejected")
    f = fields(validate(o, [], TODAY))
    assert "start_no" in f


def test_cancel_rules():
    o = started(cancel_no="9", cancel_date=date(2026, 3, 15))  # قبل المباشرة
    assert "cancel_date" in fields(validate(o, [], TODAY))
    o = started(cancel_no="9", cancel_date=date(2026, 5, 1))
    assert validate(o, [], TODAY) == []
    o = started(close_no="8", close_date=date(2026, 6, 1), cancel_no="9", cancel_date=date(2026, 7, 1))
    assert "cancel_no" in fields(validate(o, [], TODAY))


def test_valid_full_order():
    o = started(close_no="400", close_date=date(2026, 10, 1), labor_alloc=150_000_000,
                materials_alloc=0, materials={1: 500, 6: 12})
    assert validate(o, [], TODAY) == []


def test_book_numbers_digits_only():
    o = make_order(submit_no="12ت", submit_date=date(2026, 1, 1))
    assert "submit_no" in fields(validate(o, [], TODAY))
