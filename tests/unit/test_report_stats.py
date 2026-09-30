from datetime import UTC, date, datetime, timedelta

from app.models.enums import DocumentStatus as S
from app.reports.pdf import ReportData, render_report
from app.reports.stats import (
    DeadlineCategory,
    ResolutionFact,
    classify_deadline,
    compute_executor_stats,
    is_resolution_overdue,
)

TODAY = date(2026, 9, 30)
NOW = datetime(2026, 9, 30, 12, tzinfo=UTC)


def test_executor_stats_average_and_overdue_percent():
    facts = [
        ResolutionFact("e1", "Иванов", "d1", NOW - timedelta(days=4), NOW, date(2026, 9, 29)),  # с просрочкой
        ResolutionFact("e1", "Иванов", "d2", NOW - timedelta(days=2), NOW, date(2026, 10, 5)),  # в срок
        ResolutionFact("e2", "Петров", "d3", NOW - timedelta(days=9), None, date(2026, 9, 20)),  # не исполнена
    ]
    stats = compute_executor_stats(facts, TODAY)
    assert [s.executor_name for s in stats] == ["Иванов", "Петров"]
    assert (stats[0].avg_days, stats[0].overdue, stats[0].overdue_pct) == (3.0, 1, 50.0)
    assert (stats[1].avg_days, stats[1].overdue_pct, stats[1].executed) == (None, 100.0, 0)


def test_overdue_rules_for_resolution():
    fact = ResolutionFact("e", "X", "d", NOW - timedelta(days=1), None, TODAY)
    assert not is_resolution_overdue(fact, TODAY)                       # срок сегодня — еще не просрочка
    assert is_resolution_overdue(fact, TODAY + timedelta(days=1))


def test_deadline_classification():
    deadline = date(2026, 9, 20)
    assert classify_deadline(deadline, S.EXECUTED, date(2026, 9, 25), TODAY) == (DeadlineCategory.LATE, 5)
    assert classify_deadline(deadline, S.EXECUTED, date(2026, 9, 18), TODAY) == (DeadlineCategory.ON_TIME, -2)
    assert classify_deadline(deadline, S.ARCHIVED, deadline, TODAY) == (DeadlineCategory.ON_TIME, 0)
    assert classify_deadline(deadline, S.IN_EXECUTION, None, TODAY) == (DeadlineCategory.OVERDUE, 10)
    assert classify_deadline(date(2026, 10, 20), S.IN_EXECUTION, None, TODAY) == (DeadlineCategory.IN_PROGRESS, None)
    assert classify_deadline(deadline, S.EXECUTED, None, TODAY) == (DeadlineCategory.UNKNOWN, None)


def test_pdf_is_generated_with_cyrillic_and_special_chars():
    data = ReportData(
        title="Отчет по документам", period="01.09.2026 — 30.09.2026", generated_at=datetime.now(),
        generated_by="Иванова А. С. (делопроизводитель)", columns=["Номер", "Корреспондент", "Содержание"],
        col_weights=[2, 3, 6], rows=[["ВХ-2026-000001", "ООО «Ромашка» & Ко", "Запрос <данных> " * 20]] * 80,
        filters=["статус: на исполнении"], summary=[("Всего документов", "80")])
    pdf = render_report(data)
    assert pdf.startswith(b"%PDF") and len(pdf) > 5000


def test_empty_report_still_renders():
    data = ReportData(title="Пустой отчет", period="—", generated_at=datetime.now(), generated_by="—",
                      columns=["A"], col_weights=[1], rows=[])
    assert render_report(data).startswith(b"%PDF")
