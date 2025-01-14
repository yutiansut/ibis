import numpy as np
import pandas as pd
import pytest


@pytest.mark.parametrize(
    'column',
    [
        'string_col',
        'double_col',
        'date_string_col',
        pytest.param('timestamp_col', marks=pytest.mark.skip(reason='hangs')),
    ],
)
@pytest.mark.notimpl(["datafusion"])
def test_distinct_column(backend, alltypes, df, column):
    expr = alltypes[column].distinct()
    result = expr.execute()
    expected = df[column].unique()
    assert set(result) == set(expected)


@pytest.mark.notimpl(
    [
        "clickhouse",
        "dask",
        "datafusion",
        "duckdb",
        "impala",
        "mysql",
        "pandas",
        "postgres",
        "pyspark",
    ]
)
def test_rowid(con, backend):
    t = con.table('functional_alltypes')
    result = t[t.rowid()].execute()
    first_value = 1
    expected = pd.Series(
        range(first_value, first_value + len(result)),
        dtype=np.int64,
        name='rowid',
    )
    pd.testing.assert_series_equal(result.iloc[:, 0], expected)


@pytest.mark.notimpl(
    [
        "clickhouse",
        "dask",
        "datafusion",
        "duckdb",
        "impala",
        "mysql",
        "pandas",
        "postgres",
        "pyspark",
    ]
)
def test_named_rowid(con, backend):
    t = con.table('functional_alltypes')
    result = t[t.rowid().name('number')].execute()
    first_value = 1
    expected = pd.Series(
        range(first_value, first_value + len(result)),
        dtype=np.int64,
        name='number',
    )
    pd.testing.assert_series_equal(result.iloc[:, 0], expected)
