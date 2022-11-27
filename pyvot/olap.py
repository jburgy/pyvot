from bisect import bisect
from itertools import groupby
from operator import itemgetter
from sqlite3 import Connection, Row

from jinja2 import DictLoader, Environment

_ENV = Environment(
    trim_blocks=True,
    lstrip_blocks=True,
    loader=DictLoader(
        {
            "table_info": "PRAGMA table_info('{{ table }}')",
            "query": """
            {% set comma = ", " %}
            SELECT
                {{ dimensions|join(comma) }},
                {% set outer = joiner(comma) %}
                {% for measure, aggfunc in measures.items() %}
                {{ outer() }}{{ aggfunc.__name__|default(aggfunc) }}({{ measure }}) AS {{ measure }}
                {% endfor %}
            FROM (
                SELECT
                    {% set inner = joiner(comma) %}
                    {% for dimension in dimensions %}
                    {{ inner() }}IFNULL(NULLIF({{ dimension }}, ''), 'OTHER') AS {{ dimension }}
                    {% endfor %}
                    {{ inner() }}{{ measures|join(comma) }}
                FROM {{ table }}
            ) AS t
            GROUP BY {{ dimensions|join(comma) }}
            ORDER BY {{ dimensions|join(comma) }}
            """,
        }
    ),
)


def table_info(conn: Connection, table: str) -> list[Row]:
    return conn.execute(_ENV.get_template("table_info").render(table=table)).fetchall()


def _pivot(items: list[Row], measures, get_row_key, get_col_key):
    row_keys: list[tuple[str]] = []
    col_keys: list[tuple[str]] = []
    values: list[list[float]] = []
    for item in items:
        row_key = get_row_key(item)
        if not row_keys or row_key != row_keys[-1]:
            row_keys.append(row_key)
            last = []
            values.append(last)

        for measure in measures:
            col_key = get_col_key(item)
            if len(measures) > 1 or col_key == ():
                col_key = (measure,) + col_key
            index = bisect(col_keys, col_key)
            if not index or col_key != col_keys[index - 1]:
                col_keys.insert(index, col_key)
                for value in values[:-1]:
                    value.insert(index, None)
            else:
                index -= 1

            last.extend([None] * (index - len(last)))
            last.append(item[measure])

    return row_keys, col_keys, values


def _ensure_tuples(items):
    return [item if isinstance(item, tuple) else (item,) for item in items]


def _compress(names: list[str], keys: list[tuple[str]], span_name: str):
    return {
        name.title(): [
            item
            for label in [
                {
                    span_name: sum(1 for _ in group),
                    "value": (key[-1] if isinstance(key, tuple) else key).title(),
                }
                for key, group in groupby(keys, itemgetter(*range(depth + 1)))
            ]
            for item in [label] + [None] * (label[span_name] - 1)
        ]
        for depth, name in enumerate(names)
    }


def pivot_table(
    conn: Connection,
    table: str,
    rows: list[str],
    cols: list[str],
    measures: dict,
    format: str = "{:.2f}",
) -> dict:
    if not rows:
        return {"col_labels": {}, "row_labels": {}, "values": []}

    query = _ENV.get_template("query").render(
        table=table,
        dimensions=rows + cols,
        measures=measures,
    )
    res = conn.execute(query)
    items = res.fetchall()
    row_labels, col_labels, values = _pivot(
        items,
        measures,
        itemgetter(*rows) if rows else lambda _: "Total",
        itemgetter(*cols) if cols else lambda _: (),
    )
    formatter = format.format

    return {
        "col_labels": _compress(
            cols or ["Vote"], _ensure_tuples(col_labels), "colspan"
        ),
        "row_labels": _compress(
            rows or ["Vote"], _ensure_tuples(row_labels or ["Total"]), "rowspan"
        ),
        "values": [
            [
                {"value": value, "formatted": "" if value is None else formatter(value)}
                for value in row
            ]
            for row in values
        ],
    }


if __name__ == "__main__":
    from pprint import pprint
    from sqlite3 import connect

    with connect("elections.db") as conn:
        conn.row_factory = Row
        pprint(
            pivot_table(
                conn=conn,
                table="house_precinct_general",
                rows=["state"],
                cols=["party_simplified"],
                measures={"Votes": sum},
                format="{:d}",
            )
        )
