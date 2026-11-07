import json
import logging
import uuid
from pathlib import Path

from sqlalchemy import text
from superset.app import create_app

logger = logging.getLogger("fondinsyn.superset")

DATABASE_NAME = "PostgreSQL"
DASHBOARD_TITLE = "Fondinsyn — kvartalsvis fondinnehavsöversikt"
DASHBOARD_SLUG = "fondinsyn-kvartalsdata"
VIEW_DATASETS = {
    "quarter_summary": "v_fondinsyn_quarter_summary",
    "latest_fund_values": "v_fondinsyn_latest_fund_values",
    "latest_security_values": "v_fondinsyn_latest_security_values",
}
CHARTS = (
    {
        "title": "Rapporterat marknadsvärde per kvartal (SEK)",
        "legacy_title": "AUM_Growth",
        "dataset_key": "quarter_summary",
        "viz_type": "echarts_timeseries_line",
        "x_axis": "quarter_end",
        "metric": "market_value_sek",
        "row_limit": 1000,
        "order_desc": False,
        "x_axis_label": "Kvartal",
    },
    {
        "title": "Största fonder – senaste tillgängliga kvartalet",
        "legacy_title": "Country Exposure",
        "dataset_key": "latest_fund_values",
        "viz_type": "echarts_timeseries_bar",
        "x_axis": "fund_name",
        "metric": "market_value_sek",
        "row_limit": 15,
        "order_desc": True,
        "x_axis_label": "Fond",
    },
    {
        "title": "Största värdepappersinnehav – senaste tillgängliga kvartalet",
        "legacy_title": "Portfolio Sector Allocation Over Time",
        "dataset_key": "latest_security_values",
        "viz_type": "echarts_timeseries_bar",
        "x_axis": "security_name",
        "metric": "market_value_sek",
        "row_limit": 15,
        "order_desc": True,
        "x_axis_label": "Värdepapper",
    },
)
DASHBOARD_DESCRIPTION = (
    "En kompletterande analysvy av FI:s kvartalsvisa fondinnehav. "
    "Marknadsvärdena summerar rapporterade innehav och ska inte tolkas som "
    "fondförmögenhet, avkastning eller löpande handel. Källa: "
    "[Finansinspektionens öppna data]"
    "(https://www.fi.se/sv/om-fi/om-webbplatsen/oppen-data/). "
    "Fondinsyn är ett oberoende projekt. Endast informations- och analysändamål; "
    "utgör inte investeringsrådgivning."
)


def execute_view_definitions(database) -> None:
    sql_path = Path(__file__).with_name("fondinsyn_superset_views.sql")
    statements = [statement.strip() for statement in sql_path.read_text().split(";")]
    with database.get_sqla_engine() as engine:
        with engine.begin() as connection:
            for statement in statements:
                if statement:
                    connection.execute(text(statement))


def create_metric(dataset, column_name: str):
    column = next(
        (column for column in dataset.columns if column.column_name == column_name),
        None,
    )
    if column is None:
        raise RuntimeError(
            f"Superset dataset {dataset.table_name} is missing column {column_name}"
        )
    return {
        "aggregate": "SUM",
        "column": column.to_json(),
        "datasourceWarning": False,
        "expressionType": "SIMPLE",
        "hasCustomLabel": True,
        "label": "Marknadsvärde (SEK)",
        "optionName": f"metric_fondinsyn_{column_name}",
        "sqlExpression": None,
    }


def make_chart_params(dataset, chart_config: dict, template_params: dict) -> dict:
    params = dict(template_params)
    for key in (
        "orderby",
        "order_by",
        "series_limit_metric",
        "time_grain_sqla",
        "timeseries_limit_metric",
    ):
        params.pop(key, None)
    params.update(
        {
            "datasource": f"{dataset.id}__table",
            "viz_type": chart_config["viz_type"],
            "x_axis": chart_config["x_axis"],
            "xAxisForceCategorical": True,
            "x_axis_sort": chart_config["x_axis"],
            "x_axis_sort_asc": True,
            "groupby": [],
            "metrics": [create_metric(dataset, chart_config["metric"])],
            "row_limit": chart_config["row_limit"],
            "order_desc": chart_config["order_desc"],
            "adhoc_filters": [],
            "time_range": "No filter",
            "show_legend": False,
            "rich_tooltip": True,
            "x_axis_label": chart_config["x_axis_label"],
            "x_axis_title": chart_config["x_axis_label"],
            "y_axis_label": "Marknadsvärde (SEK)",
            "y_axis_title": "Marknadsvärde (SEK)",
            "y_axis_format": ",.0f",
        }
    )
    if chart_config["dataset_key"] == "quarter_summary":
        params["granularity_sqla"] = "quarter_end"
    else:
        params.pop("granularity_sqla", None)
    return params


def build_dashboard_layout(dashboard, charts) -> str:
    layout = json.loads(dashboard.position_json or "{}")
    row_ids = ("ROW-fondinsyn-overview", "ROW-fondinsyn-leaders")
    chart_ids = [f"CHART-explore-{chart.id}-1" for chart in charts]
    existing_chart_nodes = {
        node.get("meta", {}).get("chartId"): node
        for node in layout.values()
        if isinstance(node, dict) and node.get("type") == "CHART"
    }

    for key in list(layout):
        node = layout[key]
        if isinstance(node, dict) and node.get("type") in {"CHART", "ROW"}:
            del layout[key]

    layout["GRID_ID"] = {
        "id": "GRID_ID",
        "type": "GRID",
        "children": list(row_ids),
        "parents": ["ROOT_ID"],
    }
    layout["ROOT_ID"] = {
        "id": "ROOT_ID",
        "type": "ROOT",
        "children": ["GRID_ID"],
    }
    layout.setdefault("HEADER_ID", {"id": "HEADER_ID", "type": "HEADER"})
    layout[row_ids[0]] = {
        "id": row_ids[0],
        "type": "ROW",
        "children": [chart_ids[0]],
        "parents": ["ROOT_ID", "GRID_ID"],
        "meta": {"background": "BACKGROUND_TRANSPARENT"},
    }
    layout[row_ids[1]] = {
        "id": row_ids[1],
        "type": "ROW",
        "children": chart_ids[1:],
        "parents": ["ROOT_ID", "GRID_ID"],
        "meta": {"background": "BACKGROUND_TRANSPARENT"},
    }
    for index, (chart, chart_id) in enumerate(zip(charts, chart_ids)):
        row_id = row_ids[0] if index == 0 else row_ids[1]
        width = 12 if index == 0 else 6
        old_node = existing_chart_nodes.get(chart.id, {})
        old_meta = old_node.get("meta", {})
        layout[chart_id] = {
            "id": chart_id,
            "type": "CHART",
            "children": [],
            "parents": ["ROOT_ID", "GRID_ID", row_id],
            "meta": {
                "chartId": chart.id,
                "height": old_meta.get("height", 50),
                "sliceName": chart.slice_name,
                "uuid": old_meta.get("uuid", str(uuid.uuid4())),
                "width": width,
            },
        }
    return json.dumps(layout)


def provision() -> None:
    from sqlalchemy import or_
    from superset.connectors.sqla.models import SqlaTable
    from superset.extensions import db
    from superset.models.core import Database
    from superset.models.dashboard import Dashboard
    from superset.models.slice import Slice

    database = db.session.query(Database).filter_by(database_name=DATABASE_NAME).one_or_none()
    if database is None:
        raise RuntimeError(f"Superset database connection {DATABASE_NAME!r} was not found")

    execute_view_definitions(database)

    datasets = {}
    for key, table_name in VIEW_DATASETS.items():
        dataset = (
            db.session.query(SqlaTable)
            .filter_by(database_id=database.id, schema="analytics", table_name=table_name)
            .one_or_none()
        )
        if dataset is None:
            dataset = SqlaTable(
                database_id=database.id,
                schema="analytics",
                table_name=table_name,
            )
            db.session.add(dataset)
            db.session.flush()
        dataset.fetch_metadata()
        datasets[key] = dataset

    dashboard = (
        db.session.query(Dashboard)
        .filter(
            or_(
                Dashboard.slug == DASHBOARD_SLUG,
                Dashboard.dashboard_title.in_(
                    (DASHBOARD_TITLE, "Index Funds")
                ),
            )
        )
        .first()
    )
    if dashboard is None:
        dashboard = Dashboard(dashboard_title=DASHBOARD_TITLE, slug=DASHBOARD_SLUG)
        db.session.add(dashboard)
        db.session.flush()

    existing_charts = {chart.slice_name: chart for chart in dashboard.slices}
    templates = {
        chart.viz_type: json.loads(chart.params or "{}")
        for chart in existing_charts.values()
        if chart.viz_type in {"echarts_timeseries_line", "echarts_timeseries_bar"}
    }

    charts = []
    for chart_config in CHARTS:
        chart = existing_charts.get(chart_config["title"])
        if chart is None:
            chart = existing_charts.get(chart_config["legacy_title"])
        if chart is None:
            chart = Slice()
            db.session.add(chart)
            db.session.flush()

        dataset = datasets[chart_config["dataset_key"]]
        template_params = templates.get(chart_config["viz_type"], {})
        chart.slice_name = chart_config["title"]
        chart.viz_type = chart_config["viz_type"]
        chart.datasource_id = dataset.id
        chart.datasource_type = "table"
        chart.query_context = None
        chart.params = json.dumps(
            make_chart_params(dataset, chart_config, template_params),
            default=str,
        )
        chart.description = (
            "Kvartalsvisa FI-uppgifter. Marknadsvärden anges i SEK; "
            "visningen är en historisk rapporteringsögonblicksbild."
        )
        charts.append(chart)

    dashboard.dashboard_title = DASHBOARD_TITLE
    dashboard.slug = DASHBOARD_SLUG
    dashboard.description = DASHBOARD_DESCRIPTION
    dashboard.published = True
    dashboard.slices = charts
    metadata = json.loads(dashboard.json_metadata or "{}")
    metadata["refresh_frequency"] = 900
    metadata["color_scheme"] = "supersetColors"
    dashboard.json_metadata = json.dumps(metadata)
    dashboard.position_json = build_dashboard_layout(dashboard, charts)
    db.session.commit()
    logger.info(
        "Provisioned Fondinsyn Superset dashboard with %d charts and 15-minute refresh",
        len(charts),
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    application = create_app()
    with application.app_context():
        provision()
